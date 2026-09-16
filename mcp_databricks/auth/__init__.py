"""OAuth resource-server integration: verify JWTs and exchange workspace tokens."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from mcp_auth_client import PrivateKeyJWTClientAuth, TokenExchangeClient

from mcp_databricks.auth.consent_config import SERVER_WEBSITE

DEFAULT_CONNECTOR = "databricks"
DEFAULT_EXCHANGE_CLIENT = "databricks-mcp"
DEFAULT_ALLOWED_HOST_SUFFIXES = (
    ".cloud.databricks.com",
    ".azuredatabricks.net",
    ".gcp.databricks.com",
)


class TokenExchangeError(RuntimeError):
    """Raised when the configured downstream token exchange cannot complete."""


@dataclass
class _TokenExchangeAdapter:
    client: TokenExchangeClient
    audience: str
    entered: bool = False

    async def exchange(self, subject_token: str):
        try:
            if not self.entered:
                await self.client.__aenter__()
                self.entered = True
            return await self.client.exchange(subject_token, audience=self.audience)
        except Exception as exc:
            raise TokenExchangeError("downstream token exchange failed") from exc

    async def aclose(self) -> None:
        if self.entered:
            await self.client.__aexit__(None, None, None)
            self.entered = False


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


def auth_jwks_uri() -> str:
    return (
        os.getenv("MCP_AUTH_JWKS_URI", "").strip()
        or f"{auth_issuer()}/.well-known/jwks.json"
    )


def auth_token_endpoint() -> str:
    return os.getenv("MCP_AUTH_TOKEN_ENDPOINT", "").strip() or f"{auth_issuer()}/token"


def public_base_url() -> str:
    for key in ("PUBLIC_BASE_URL", "MCP_SERVER_URL"):
        value = os.getenv(key, "").strip().rstrip("/")
        if value:
            return value
    raise ValueError("one of PUBLIC_BASE_URL or MCP_SERVER_URL is required")


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
    resource = public_base_url()
    verifier = JWTVerifier(
        jwks_uri=auth_jwks_uri(),
        issuer=auth_issuer(),
        audience=f"{resource}/mcp",
        base_url=resource,
        ssrf_safe=auth_jwks_ssrf_safe(),
    )
    return RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[auth_issuer()],
        base_url=resource,
        scopes_supported=["catalog:read", "sql:read"],
    )


def build_token_exchange_client() -> _TokenExchangeAdapter:
    client_auth = PrivateKeyJWTClientAuth(
        auth_exchange_client_id(),
        auth_exchange_private_key(),
        auth_exchange_key_id(),
    )
    client = TokenExchangeClient(auth_token_endpoint(), client_auth=client_auth)
    return _TokenExchangeAdapter(client, auth_connector())


__all__ = [
    "SERVER_WEBSITE",
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
    "workspace_host",
]
