"""OAuth resource-server integration: verify JWTs and exchange workspace tokens."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from mcp_auth_client import (
    TokenExchangeError,
    build_exchange_client,
    build_remote_auth,
    public_base_url,
)

from mcp_databricks.auth.consent_config import server_website

DEFAULT_CONNECTOR = "databricks"
DEFAULT_MCP_PATH = "/mcp"
DEFAULT_EXCHANGE_CLIENT = "databricks-mcp"
DEFAULT_ALLOWED_HOST_SUFFIXES = (
    ".cloud.databricks.com",
    ".azuredatabricks.net",
    ".gcp.databricks.com",
)

# The single source of truth for scope names: tools/catalog.py, tools/sql.py,
# and tools/warehouses.py gate their tools with these, and this module's own
# build_auth_provider (and app.py's bare protected-resource-metadata route)
# advertise the same list. Previously each site had its own copy of the
# literal string, free to drift independently.
CATALOG_READ_SCOPE = "catalog:read"
SQL_READ_SCOPE = "sql:read"
PROTECTED_RESOURCE_SCOPES = [CATALOG_READ_SCOPE, SQL_READ_SCOPE]


def allowed_host_suffixes() -> tuple[str, ...]:
    raw = os.getenv("DATABRICKS_ALLOWED_HOST_SUFFIXES")
    if raw is None:
        return DEFAULT_ALLOWED_HOST_SUFFIXES
    suffixes = tuple(
        f".{item.strip().lower().lstrip('*.')}"
        for item in raw.split(",")
        if item.strip()
    )
    if not suffixes:
        raise ValueError("DATABRICKS_ALLOWED_HOST_SUFFIXES must not be empty")
    if any(
        any(character in suffix for character in ":/\\") or suffix == "."
        for suffix in suffixes
    ):
        raise ValueError("DATABRICKS_ALLOWED_HOST_SUFFIXES contains an invalid suffix")
    return suffixes


def workspace_host() -> str:
    host = os.environ.get("DATABRICKS_HOST", "").strip().rstrip("/")
    parsed = urlparse(host)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not any(
            parsed.hostname.lower().endswith(suffix)
            for suffix in allowed_host_suffixes()
        )
    ):
        raise ValueError(
            "DATABRICKS_HOST must be an approved HTTPS Databricks workspace host."
        )
    return host


def auth_issuer() -> str:
    issuer = os.getenv("MCP_AUTH_ISSUER", "").strip()
    if not issuer:
        raise ValueError("MCP_AUTH_ISSUER is required")
    return issuer.rstrip("/")


def mcp_path() -> str:
    """Where this server mounts its MCP endpoint, relative to the base URL.

    One resolved value feeds four places that must agree: the mount point
    itself, the token audience, the "resource" field of the protected-resource
    metadata, and the path the usage-metrics middleware matches on. They were
    four separate "/mcp" literals, so a deployment behind a different mount
    point had to change each one and would otherwise fail in a way that looks
    like an auth bug (every token rejected on audience) rather than a routing
    one.
    """
    raw = os.getenv("MCP_PATH", "").strip() or DEFAULT_MCP_PATH
    normalized = "/" + raw.strip("/")
    if normalized == "/":
        raise ValueError(
            "MCP_PATH must name a path below the base URL (e.g. /mcp); "
            "mounting at the root leaves the audience indistinguishable "
            "from the base URL the authorization server issues tokens for"
        )
    return normalized


def auth_jwks_uri() -> str:
    return (
        os.getenv("MCP_AUTH_JWKS_URI", "").strip()
        or f"{auth_issuer()}/.well-known/jwks.json"
    )


def auth_token_endpoint() -> str:
    return os.getenv("MCP_AUTH_TOKEN_ENDPOINT", "").strip() or f"{auth_issuer()}/token"


def auth_jwks_ssrf_safe() -> bool:
    raw = os.getenv("MCP_AUTH_JWKS_SSRF_SAFE", "true").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError("MCP_AUTH_JWKS_SSRF_SAFE must be a boolean")


def auth_connector() -> str:
    return (
        os.getenv("MCP_AUTH_CONNECTOR", DEFAULT_CONNECTOR).strip() or DEFAULT_CONNECTOR
    )


def auth_exchange_client_id() -> str:
    return (
        os.getenv("MCP_AUTH_CLIENT_ID", DEFAULT_EXCHANGE_CLIENT).strip()
        or DEFAULT_EXCHANGE_CLIENT
    )


def auth_exchange_private_key() -> bytes:
    raw = os.getenv("MCP_AUTH_CLIENT_PRIVATE_KEY_FILE", "").strip()
    if not raw:
        raise ValueError("MCP_AUTH_CLIENT_PRIVATE_KEY_FILE is required")
    path = Path(raw)
    if not path.is_file():
        raise ValueError(f"MCP exchange private key does not exist: {path}")
    return path.read_bytes()


def auth_exchange_key_id() -> str:
    key_id = os.getenv("MCP_AUTH_CLIENT_KEY_ID", "").strip()
    key_id_file = os.getenv("MCP_AUTH_CLIENT_KEY_ID_FILE", "").strip()
    if key_id and key_id_file:
        raise ValueError(
            "set only one of MCP_AUTH_CLIENT_KEY_ID or MCP_AUTH_CLIENT_KEY_ID_FILE"
        )
    if key_id_file:
        path = Path(key_id_file)
        if not path.is_file():
            raise ValueError(f"MCP exchange key id file does not exist: {path}")
        key_id = path.read_text().strip()
    if not key_id:
        raise ValueError(
            "MCP_AUTH_CLIENT_KEY_ID or MCP_AUTH_CLIENT_KEY_ID_FILE is required"
        )
    return key_id


def build_auth_provider():
    return build_remote_auth(
        resource_url=public_base_url(),
        issuer=auth_issuer(),
        jwks_uri=auth_jwks_uri(),
        scopes_supported=PROTECTED_RESOURCE_SCOPES,
        ssrf_safe=auth_jwks_ssrf_safe(),
        mcp_path=mcp_path(),
    )


def build_token_exchange_client():
    return build_exchange_client(
        auth_token_endpoint(),
        auth_connector(),
        auth_exchange_client_id(),
        auth_exchange_private_key(),
        auth_exchange_key_id(),
    )


__all__ = [
    "CATALOG_READ_SCOPE",
    "PROTECTED_RESOURCE_SCOPES",
    "SQL_READ_SCOPE",
    "TokenExchangeError",
    "allowed_host_suffixes",
    "auth_connector",
    "auth_exchange_client_id",
    "auth_exchange_key_id",
    "auth_exchange_private_key",
    "auth_issuer",
    "auth_jwks_ssrf_safe",
    "auth_jwks_uri",
    "auth_token_endpoint",
    "build_auth_provider",
    "build_token_exchange_client",
    "mcp_path",
    "server_website",
    "workspace_host",
]
