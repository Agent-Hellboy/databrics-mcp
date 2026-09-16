"""Tool registration for the Databricks MCP server.

Tool functions live at module scope and are registered explicitly rather than by
import-time decorator, so importing a tool module has no side effect on any server
instance and the functions stay directly callable in tests.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_databricks.tools import catalog, sql, warehouses

_MODULES = (warehouses, catalog, sql)


def register_tools(mcp: FastMCP) -> None:
    """Register every tool module on the given server."""
    for module in _MODULES:
        module.register(mcp)


__all__ = ["catalog", "register_tools", "sql", "warehouses"]
