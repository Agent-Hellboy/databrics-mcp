"""Read-only SQL execution tools."""

from __future__ import annotations

import os

from databricks.sdk.service.sql import Disposition, Format
from fastmcp import FastMCP
from fastmcp.server.auth import require_scopes

from mcp_databricks.auth import SQL_READ_SCOPE
from mcp_databricks.client import workspace_client
from mcp_databricks.config import validate_readonly_sql, validate_table_identifier
from mcp_databricks.policy import read_only_policy

DEFAULT_MAX_ROWS = 200
DEFAULT_MAX_SAMPLE_ROWS = 100
DEFAULT_WAIT_TIMEOUT = "10s"


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def max_rows() -> int:
    """Row cap for run_readonly_sql, via MCP_MAX_ROWS."""
    return _positive_int_env("MCP_MAX_ROWS", DEFAULT_MAX_ROWS)


def max_sample_rows() -> int:
    """Hard ceiling on sample_table's caller-supplied limit, via
    MCP_MAX_SAMPLE_ROWS. It stays a ceiling, not a default: a caller asking
    for more than this is clamped down to it, never up."""
    return _positive_int_env("MCP_MAX_SAMPLE_ROWS", DEFAULT_MAX_SAMPLE_ROWS)


def wait_timeout() -> str:
    """Statement wait timeout passed to Databricks, via MCP_SQL_WAIT_TIMEOUT.

    Databricks accepts 0s or 5s-50s; the value is passed through rather than
    parsed here so its own error surfaces instead of a guess about the range.
    """
    return os.getenv("MCP_SQL_WAIT_TIMEOUT", "").strip() or DEFAULT_WAIT_TIMEOUT


def run_readonly_sql(
    warehouse_id: str,
    statement: str,
    catalog: str | None = None,
    schema: str | None = None,
) -> dict:
    """Execute one bounded read-only SQL statement on an authorized SQL warehouse."""
    client, _ = workspace_client()
    result = client.statement_execution.execute_statement(
        statement=validate_readonly_sql(statement),
        warehouse_id=read_only_policy().require_warehouse(warehouse_id),
        catalog=catalog,
        schema=schema,
        disposition=Disposition.INLINE,
        format=Format.JSON_ARRAY,
        wait_timeout=wait_timeout(),
        row_limit=max_rows(),
    )
    return {
        "statement_id": result.statement_id,
        "status": str(result.status.state) if result.status else None,
        "result": result.result.as_dict() if result.result else None,
    }


def sample_table(warehouse_id: str, full_name: str, limit: int = 20) -> dict:
    """Return a capped sample of a validated Unity Catalog table."""
    safe_name = validate_table_identifier(full_name)
    safe_limit = min(max(limit, 1), max_sample_rows())
    # Calls the plain function, not the registered tool: mcp.tool() returns the
    # undecorated callable, so this stays a direct in-process call.
    return run_readonly_sql(
        warehouse_id=warehouse_id,
        statement=f"SELECT * FROM {safe_name} LIMIT {safe_limit}",
    )


def register(mcp: FastMCP) -> None:
    for tool in (sample_table, run_readonly_sql):
        mcp.tool(auth=require_scopes(SQL_READ_SCOPE))(tool)


__all__ = [
    "DEFAULT_MAX_ROWS",
    "DEFAULT_MAX_SAMPLE_ROWS",
    "DEFAULT_WAIT_TIMEOUT",
    "max_rows",
    "max_sample_rows",
    "register",
    "run_readonly_sql",
    "sample_table",
    "wait_timeout",
]
