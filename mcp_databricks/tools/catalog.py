"""Unity Catalog metadata tools: catalogs, schemas, tables, search."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.auth import require_scopes

from mcp_databricks.client import workspace_client
from mcp_databricks.config import validate_table_identifier

MAX_SEARCH_CATALOGS = 5
MAX_SEARCH_SCHEMAS_PER_CATALOG = 10


def list_catalogs(max_results: int = 100) -> list[dict]:
    """List Unity Catalog catalogs visible to the caller."""
    client, _ = workspace_client()
    return [
        {"name": catalog.name, "comment": catalog.comment}
        for catalog in client.catalogs.list(max_results=min(max(max_results, 1), 100))
    ]


def list_schemas(catalog_name: str, max_results: int = 100) -> list[dict]:
    """List schemas visible in one Unity Catalog catalog."""
    client, _ = workspace_client()
    return [
        {
            "name": schema.name,
            "catalog_name": schema.catalog_name,
            "comment": schema.comment,
        }
        for schema in client.schemas.list(
            catalog_name=catalog_name, max_results=min(max(max_results, 1), 100)
        )
    ]


def list_tables(
    catalog_name: str, schema_name: str, max_results: int = 100
) -> list[dict]:
    """List tables visible in one Unity Catalog schema."""
    client, _ = workspace_client()
    return [
        {
            "name": table.name,
            "table_type": str(table.table_type),
            "comment": table.comment,
        }
        for table in client.tables.list(
            catalog_name=catalog_name,
            schema_name=schema_name,
            max_results=min(max(max_results, 1), 100),
        )
    ]


def describe_table(full_name: str) -> dict:
    """Return columns, types, comments, and table type for one Unity Catalog table."""
    client, _ = workspace_client()
    table = client.tables.get(full_name=validate_table_identifier(full_name))
    return {
        "full_name": table.full_name,
        "table_type": str(table.table_type),
        "comment": table.comment,
        "columns": [
            {
                "name": column.name,
                "type": column.type_text,
                "comment": column.comment,
                "nullable": column.nullable,
            }
            for column in (table.columns or [])
        ],
    }


def search_tables(query: str, max_results: int = 20) -> list[dict]:
    """Find visible tables by name or comment using a bounded metadata scan."""
    needle = query.strip().lower()
    if not needle:
        raise ValueError("Search query is required.")
    client, _ = workspace_client()
    matches: list[dict] = []
    for catalog in client.catalogs.list(max_results=MAX_SEARCH_CATALOGS):
        for schema in client.schemas.list(
            catalog_name=catalog.name, max_results=MAX_SEARCH_SCHEMAS_PER_CATALOG
        ):
            for table in client.tables.list(
                catalog_name=catalog.name, schema_name=schema.name, max_results=100
            ):
                if needle in f"{table.name or ''} {table.comment or ''}".lower():
                    matches.append(
                        {
                            "full_name": table.full_name,
                            "table_type": str(table.table_type),
                            "comment": table.comment,
                        }
                    )
                    if len(matches) >= min(max(max_results, 1), 50):
                        return matches
    return matches


def register(mcp: FastMCP) -> None:
    for tool in (
        list_catalogs,
        list_schemas,
        list_tables,
        describe_table,
        search_tables,
    ):
        mcp.tool(auth=require_scopes("catalog:read"))(tool)


__all__ = [
    "describe_table",
    "list_catalogs",
    "list_schemas",
    "list_tables",
    "register",
    "search_tables",
]
