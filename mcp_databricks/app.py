"""ASGI application: Databricks MCP resource server at /mcp."""

from __future__ import annotations

import logging
import os

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.types import ASGIApp

from mcp_databricks.auth import build_auth_provider
from mcp_databricks.auth.consent_config import SERVER_DISPLAY_NAME, SERVER_WEBSITE
from mcp_databricks.middleware import AuthContextMiddleware
from mcp_databricks.policy import read_only_policy
from mcp_databricks.tools import register_tools
from mcp_databricks.usage_metrics import UsageMetricsMiddleware

logger = logging.getLogger("databricks-mcp")

DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "127.0.0.1:6328", "localhost", "localhost:6328")


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
    return UsageMetricsMiddleware(http)


app = create_app()

__all__ = [
    "DEFAULT_ALLOWED_HOSTS",
    "allowed_hosts",
    "app",
    "build_mcp",
    "create_app",
    "host_origin_protection",
    "mcp",
]
