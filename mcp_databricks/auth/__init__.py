"""OAuth resource-server integration: verify JWTs and exchange workspace tokens."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from mcp_as_client import (
    TokenExchangeClient,
    build_exchange_client,
    build_remote_auth,
    public_base_url,
)

from mcp_databricks.auth.consent_config import SERVER_WEBSITE

DEFAULT_ISSUER = "https://auth.example.com"
DEFAULT_CONNECTOR = "databricks"
DEFAULT_EXCHANGE_CLIENT = "databricks-mcp"


def workspace_host() -> str:
    host = os.environ.get("DATABRICKS_HOST", "").strip().rstrip("/")
    parsed = urlparse(host)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(
        ".cloud.databricks.com"
    ):
        raise ValueError("DATABRICKS_HOST must be an approved HTTPS Databricks workspace host.")
    return host


def auth_issuer() -> str:
    return (
        os.getenv("MCP_AUTH_ISSUER", "").strip()
        or DEFAULT_ISSUER
    ).rstrip("/")


def auth_jwks_uri() -> str:
    return (
        os.getenv("MCP_AUTH_JWKS_URI", "").strip()
        or f"{auth_issuer()}/.well-known/jwks.json"
    )


def auth_token_endpoint() -> str:
    return (
        os.getenv("MCP_AUTH_TOKEN_ENDPOINT", "").strip()
        or f"{auth_issuer()}/token"
    )


def auth_connector() -> str:
    return os.getenv("MCP_AUTH_CONNECTOR", DEFAULT_CONNECTOR).strip() or DEFAULT_CONNECTOR


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
    resource = public_base_url(env_keys=("PUBLIC_BASE_URL", "MCP_SERVER_URL"))
    return build_remote_auth(
        resource_url=resource,
        issuer=auth_issuer(),
        jwks_uri=auth_jwks_uri(),
        scopes_supported=["catalog:read", "sql:read"],
        ssrf_safe=os.getenv("MCP_AUTH_JWKS_SSRF_SAFE", "true").lower()
        not in {"0", "false", "no", "off"},
    )


def build_token_exchange_client() -> TokenExchangeClient:
    return build_exchange_client(
        token_endpoint=auth_token_endpoint(),
        audience=auth_connector(),
        client_id=auth_exchange_client_id(),
        private_key=auth_exchange_private_key(),
        key_id=auth_exchange_key_id(),
    )


__all__ = [
    "SERVER_WEBSITE",
    "auth_connector",
    "auth_exchange_client_id",
    "auth_exchange_key_id",
    "auth_exchange_private_key",
    "auth_issuer",
    "auth_jwks_uri",
    "auth_token_endpoint",
    "build_auth_provider",
    "build_token_exchange_client",
    "workspace_host",
]
