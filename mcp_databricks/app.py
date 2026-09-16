"""ASGI application: Databricks MCP resource server at /mcp."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from mcp_databricks.auth import (
    PROTECTED_RESOURCE_SCOPES,
    auth_issuer,
    build_auth_provider,
)
from mcp_databricks.auth import public_base_url as auth_public_base_url
from mcp_databricks.auth.consent_config import SERVER_DISPLAY_NAME, SERVER_WEBSITE
from mcp_databricks.middleware import AuthContextMiddleware
from mcp_databricks.policy import read_only_policy
from mcp_databricks.tools import register_tools
from mcp_databricks.usage_metrics import UsageMetricsMiddleware

logger = logging.getLogger("databricks-mcp")

# Derived from MCP_PORT (not hardcoded to 6328) so that changing the port
# alone keeps the default host allowlist self-consistent. Deploying on a
# different port without also updating this was the classic way to turn a
# healthy server into a 421, since Starlette's host check compares against
# whatever the client's Host header actually says, port included.
_DEFAULT_PORT = os.getenv("MCP_PORT", "6328").strip() or "6328"
DEFAULT_ALLOWED_HOSTS = (
    "127.0.0.1",
    f"127.0.0.1:{_DEFAULT_PORT}",
    "localhost",
    f"localhost:{_DEFAULT_PORT}",
)


def configure_logging() -> None:
    """Give this package's own loggers ("databricks-mcp" and its children,
    e.g. "databricks-mcp.middleware") a handler and a level.

    Nothing else in the process does this. uvicorn's own logging setup (see
    server.py, which passes MCP_LOG_LEVEL straight to uvicorn.run) only
    configures its own "uvicorn"/"uvicorn.error"/"uvicorn.access" loggers —
    it never touches the root logger or this package's namespace. Without
    this, every logger.info/debug call anywhere in this package (including
    the ones added for debugging auth failures) is silently dropped: only
    WARNING and above reach Python's last-resort stderr handler, regardless
    of MCP_LOG_LEVEL. Confirmed directly: an unconfigured "databricks-mcp"
    logger's effective level is WARNING with zero handlers on the root logger.
    """
    level_name = os.getenv("MCP_LOG_LEVEL", "info").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    base_logger = logging.getLogger("databricks-mcp")
    if not base_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        base_logger.addHandler(handler)
        base_logger.propagate = False
    base_logger.setLevel(level)


configure_logging()


def allowed_hosts() -> list[str]:
    raw = os.getenv("MCP_ALLOWED_HOSTS", "")
    hosts = [item.strip() for item in raw.split(",") if item.strip()]
    return hosts or list(DEFAULT_ALLOWED_HOSTS)


def host_origin_protection() -> bool:
    raw = os.getenv("MCP_HOST_ORIGIN_PROTECTION", "true").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError("MCP_HOST_ORIGIN_PROTECTION must be a boolean")


def build_mcp() -> FastMCP:
    # Validate mandatory authorization policy at startup, before accepting traffic.
    read_only_policy()
    mcp = FastMCP(
        SERVER_DISPLAY_NAME,
        website_url=SERVER_WEBSITE,
        instructions=(
            "Read-only Databricks workspace access. "
            "Authenticate with the configured authorization server."
        ),
        auth=build_auth_provider(),
    )
    register_tools(mcp)
    return mcp


mcp = build_mcp()
logger.info(
    "databricks-mcp configured: issuer=%s resource=%s allowed_hosts=%s "
    "host_origin_protection=%s",
    auth_issuer(),
    auth_public_base_url(),
    allowed_hosts(),
    host_origin_protection(),
)


PROTECTED_RESOURCE_METADATA_PREFIX = "/.well-known/oauth-protected-resource"


def protected_resource_metadata_document() -> dict:
    """The one protected-resource metadata document (RFC 9728).

    Served from this single function at both the path-scoped location
    (/.well-known/oauth-protected-resource/mcp, where the WWW-Authenticate
    challenge sends every client) and the bare one (which some clients probe
    first), replacing the route FastMCP generates.

    Replacing it is the point: FastMCP's route builds the document through
    the upstream `mcp` package's ProtectedResourceMetadata model, whose
    authorization_servers field is typed list[AnyHttpUrl], and pydantic
    appends "/" to any URL with no path. The authorization server advertises
    its issuer exactly as configured, with no trailing slash, and RFC 8414 §2
    requires the issuer a client discovers to be identical to the one the
    metadata names. Publishing "http://host/" here against an AS that says
    "http://host" is a mismatch a strict client rejects, and it is not
    fixable by passing a different string in: the normalization happens on
    the way out, inside a pinned third-party model.
    """
    resource = auth_public_base_url()
    return {
        "resource": f"{resource}/mcp",
        "authorization_servers": [auth_issuer()],
        "scopes_supported": list(PROTECTED_RESOURCE_SCOPES),
        "bearer_methods_supported": ["header"],
    }


def protected_resource_metadata_paths() -> tuple[str, ...]:
    """Where the document above is served.

    RFC 9728 §3.1 inserts /.well-known/oauth-protected-resource between the
    host and the resource's own path, so a resource at
    https://host/databricks/mcp publishes at
    /.well-known/oauth-protected-resource/databricks/mcp. That path-scoped
    location is the one the WWW-Authenticate challenge names, so it has to be
    derived from the configured base URL rather than assumed to be "/mcp" —
    a deployment behind a path prefix uses a different one. The bare path is
    served too, because some clients probe it before the scoped one.
    """
    resource_path = urlparse(f"{auth_public_base_url()}/mcp").path
    scoped = f"{PROTECTED_RESOURCE_METADATA_PREFIX}{resource_path}"
    if scoped == PROTECTED_RESOURCE_METADATA_PREFIX:
        return (scoped,)
    return (scoped, PROTECTED_RESOURCE_METADATA_PREFIX)


async def _protected_resource_metadata(_request: Request) -> JSONResponse:
    return JSONResponse(protected_resource_metadata_document())


class _CacheWellKnownResponses:
    """Adds Cache-Control to every /.well-known/* GET response.

    These documents change only on redeploy, never per request. Without this,
    a client that never sends a conditional request (most don't) refetches
    the same static document on every connection attempt, which is
    indistinguishable in the logs from a client stuck retrying because
    something is actually failing — observed directly: one failed connection
    attempt fetched the same document eight times. Applied as ASGI middleware
    rather than per-route so it also covers FastMCP's own built-in
    protected-resource-metadata route, which this module doesn't construct
    the response for directly.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/.well-known/"):
            await self.app(scope, receive, send)
            return

        async def send_with_cache_control(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(name.lower() == b"cache-control" for name, _ in headers):
                    headers.append((b"cache-control", b"max-age=3600"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cache_control)


def create_app() -> ASGIApp:
    """Streamable HTTP MCP resource server, wrapped in usage metrics.

    UsageMetricsMiddleware deliberately wraps the outside so a metrics failure can
    never break MCP traffic; because of that it runs after AuthContextMiddleware has
    reset its ContextVars, which is why the identity also travels on the ASGI scope.
    """
    http = mcp.http_app(
        path="/mcp",
        transport="streamable-http",
        host_origin_protection=host_origin_protection(),
        allowed_hosts=allowed_hosts(),
        middleware=[Middleware(AuthContextMiddleware)],
    )
    # Drop FastMCP's generated protected-resource-metadata route(s) and serve
    # both the path-scoped and bare locations from one handler, so the two can
    # never disagree. Routes are matched in order, so shadowing by appending
    # would leave the generated one winning at the path-scoped location — the
    # one the WWW-Authenticate challenge actually points clients at.
    routes = http.router.routes
    routes[:] = [
        route
        for route in routes
        if not getattr(route, "path", "").startswith(PROTECTED_RESOURCE_METADATA_PREFIX)
    ]
    for path in protected_resource_metadata_paths():
        http.add_route(path, _protected_resource_metadata, methods=["GET"])
    return UsageMetricsMiddleware(_CacheWellKnownResponses(http))


app = create_app()

__all__ = [
    "DEFAULT_ALLOWED_HOSTS",
    "PROTECTED_RESOURCE_METADATA_PREFIX",
    "allowed_hosts",
    "app",
    "build_mcp",
    "create_app",
    "host_origin_protection",
    "mcp",
    "protected_resource_metadata_document",
]
