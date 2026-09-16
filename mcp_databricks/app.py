"""ASGI application: Databricks MCP resource server at /mcp."""

from __future__ import annotations

import logging

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
        host_origin_protection=False,
        allowed_hosts=["127.0.0.1", "127.0.0.1:6328", "localhost", "localhost:6328"],
        middleware=[Middleware(AuthContextMiddleware)],
    )
    return UsageMetricsMiddleware(http)


app = create_app()

__all__ = ["app", "build_mcp", "create_app", "mcp"]
