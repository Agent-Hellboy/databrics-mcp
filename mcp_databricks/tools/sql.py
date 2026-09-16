"""Read-only SQL execution tools."""

from __future__ import annotations

from databricks.sdk.service.sql import Disposition, Format
from fastmcp import FastMCP
from fastmcp.server.auth import require_scopes

from mcp_databricks.client import workspace_client
from mcp_databricks.config import validate_readonly_sql, validate_table_identifier
from mcp_databricks.policy import read_only_policy

MAX_ROWS = 200
MAX_SAMPLE_ROWS = 100


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
        wait_timeout="10s",
        row_limit=MAX_ROWS,
    )
    return {
        "statement_id": result.statement_id,
        "status": str(result.status.state) if result.status else None,
        "result": result.result.as_dict() if result.result else None,
    }


def sample_table(warehouse_id: str, full_name: str, limit: int = 20) -> dict:
    """Return a capped sample of a validated Unity Catalog table."""
    safe_name = validate_table_identifier(full_name)
    safe_limit = min(max(limit, 1), MAX_SAMPLE_ROWS)
    # Calls the plain function, not the registered tool: mcp.tool() returns the
    # undecorated callable, so this stays a direct in-process call.
    return run_readonly_sql(
        warehouse_id=warehouse_id,
        statement=f"SELECT * FROM {safe_name} LIMIT {safe_limit}",
    )


def register(mcp: FastMCP) -> None:
    for tool in (sample_table, run_readonly_sql):
        mcp.tool(auth=require_scopes("sql:read"))(tool)


__all__ = ["MAX_ROWS", "MAX_SAMPLE_ROWS", "register", "run_readonly_sql", "sample_table"]
