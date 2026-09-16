"""Shared pytest env so importing mcp_databricks.app does not fail."""

from __future__ import annotations

import os

os.environ.setdefault("DATABRICKS_HOST", "https://workspace.cloud.databricks.com")
os.environ.setdefault("PUBLIC_BASE_URL", "https://mcp.example.com/databricks")
os.environ.setdefault("MCP_SERVER_URL", "https://mcp.example.com/databricks")
os.environ.setdefault("MCP_AUTH_ISSUER", "https://auth.example.com")
os.environ.setdefault("MCP_SERVER_WEBSITE", "https://mcp.test.invalid/databricks")
os.environ.setdefault(
    "MCP_AUTH_JWKS_URI", "https://auth.example.com/.well-known/jwks.json"
)
os.environ.setdefault("MCP_AUTH_TOKEN_ENDPOINT", "https://auth.example.com/token")
os.environ.setdefault("MCP_AUTH_CONNECTOR", "databricks")
os.environ.setdefault("MCP_AUTH_JWKS_SSRF_SAFE", "false")
os.environ.setdefault(
    "MCP_ALLOWED_HOSTS", "127.0.0.1,127.0.0.1:6328,localhost,localhost:6328,test"
)
os.environ.setdefault("MCP_HOST_ORIGIN_PROTECTION", "false")
os.environ.setdefault("MCP_METRICS_ENABLED", "false")
os.environ.setdefault("DATABRICKS_REQUIRED_GROUP", "mcp_users")
os.environ.setdefault("DATABRICKS_ALLOWED_WAREHOUSE_IDS", "warehouse-test")
