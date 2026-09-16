"""Per-request WorkspaceClient built from the exchanged Databricks token."""

from __future__ import annotations

from databricks.sdk import WorkspaceClient

from mcp_databricks.config import (
    REQUEST_ACCESS_TOKEN,
    REQUEST_USER_ID,
    RequestCredentials,
    credentials_from_access_token,
)
from mcp_databricks.policy import read_only_policy


def workspace_client() -> tuple[WorkspaceClient, RequestCredentials]:
    """Client for the caller's identity, so Unity Catalog grants apply to the human.

    AuthContextMiddleware exchanges the MCP JWT and stores the Databricks
    workspace token on REQUEST_ACCESS_TOKEN. FastMCP's get_access_token() still
    holds the MCP JWT, which Databricks would reject.
    """
    credentials = credentials_from_access_token(
        REQUEST_ACCESS_TOKEN.get() or "",
        REQUEST_USER_ID.get(),
    )
    client = WorkspaceClient(host=credentials.host, token=credentials.token)
    read_only_policy().require_user(client)
    return client, credentials


__all__ = ["workspace_client"]
