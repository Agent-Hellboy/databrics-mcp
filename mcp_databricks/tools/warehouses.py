"""SQL warehouse discovery tools."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.auth import require_scopes

from mcp_databricks.client import workspace_client
from mcp_databricks.policy import read_only_policy


def list_warehouses() -> list[dict]:
    """List SQL warehouses available to the caller's Databricks OAuth identity."""
    client, _ = workspace_client()
    return [
        {
            "id": warehouse.id,
            "name": warehouse.name,
            "state": str(warehouse.state),
            "type": str(warehouse.warehouse_type),
        }
        for warehouse in client.warehouses.list()
        if read_only_policy().allows_warehouse(warehouse.id)
    ]


def register(mcp: FastMCP) -> None:
    mcp.tool(auth=require_scopes("sql:read"))(list_warehouses)


__all__ = ["list_warehouses", "register"]
