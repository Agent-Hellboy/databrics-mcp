"""Canonical process entrypoint for the Databricks MCP service."""

from __future__ import annotations

import os

import uvicorn

from mcp_databricks.app import app, build_mcp, create_app, mcp


def main() -> None:
    """Run the Streamable HTTP MCP server with uvicorn."""
    uvicorn.run(
        app,
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "6328")),
        log_level=os.getenv("MCP_LOG_LEVEL", "info"),
    )


__all__ = ["app", "build_mcp", "create_app", "main", "mcp"]


if __name__ == "__main__":
    main()
