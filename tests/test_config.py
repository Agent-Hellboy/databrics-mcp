"""Unit tests for Databricks MCP config and resource-server auth."""

from __future__ import annotations

import pytest
from fastmcp.server.auth.auth import RemoteAuthProvider

from mcp_databricks.auth import build_auth_provider
from mcp_databricks.config import (
    credentials_from_access_token,
    validate_readonly_sql,
    validate_table_identifier,
)


def test_credentials_require_token() -> None:
    with pytest.raises(ValueError, match="access token"):
        credentials_from_access_token("")


def test_credentials_from_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABRICKS_HOST", "https://workspace.cloud.databricks.com")
    creds = credentials_from_access_token("tok-abc", "user@example.com")
    assert creds.token == "tok-abc"
    assert creds.user_id == "user@example.com"
    assert creds.host.endswith("cloud.databricks.com")


def test_sp_style_headers_are_not_used() -> None:
    import mcp_databricks.config as config

    assert not hasattr(config, "credentials_from_headers")
    assert not hasattr(config, "HEADER_CLIENT_ID")


def test_readonly_sql() -> None:
    for statement in (
        "SELECT 1",
        "WITH rows AS (SELECT 1) SELECT * FROM rows",
        "SHOW CATALOGS",
        "DESCRIBE TABLE main.default.t",
        "EXPLAIN SELECT 1",
    ):
        assert validate_readonly_sql(statement) == statement


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM x",
        "SELECT 1; DELETE FROM x",
        "WITH rows AS (SELECT 1) DELETE FROM x",
        "SELECT * INTO new_table FROM old_table",
        "EXPLAIN DELETE FROM x",
    ],
)
def test_mutating_sql_is_rejected(statement: str) -> None:
    with pytest.raises(ValueError):
        validate_readonly_sql(statement)


def test_table_identifier() -> None:
    assert validate_table_identifier("main.default.t") == "main.default.t"
    with pytest.raises(ValueError):
        validate_table_identifier("not_three_part")


def test_build_auth_provider_is_a_resource_server() -> None:
    provider = build_auth_provider()
    assert isinstance(provider, RemoteAuthProvider)
    assert (
        str(provider.authorization_servers[0]).rstrip("/") == "https://auth.example.com"
    )


def test_workspace_client_uses_exchanged_token_not_mcp_jwt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcp_databricks.config import REQUEST_ACCESS_TOKEN, REQUEST_USER_ID
    from mcp_databricks import client as client_mod

    seen: dict[str, str] = {}

    class _FakeWorkspace:
        def __init__(self, host: str, token: str) -> None:
            seen["host"] = host
            seen["token"] = token

    monkeypatch.setattr(client_mod, "WorkspaceClient", _FakeWorkspace)
    monkeypatch.setattr(
        client_mod,
        "read_only_policy",
        lambda: type("Policy", (), {"require_user": lambda self, client: None})(),
    )
    token_reset = REQUEST_ACCESS_TOKEN.set("databricks-workspace-token")
    user_reset = REQUEST_USER_ID.set("dev@example.com")
    try:
        _, creds = client_mod.workspace_client()
    finally:
        REQUEST_ACCESS_TOKEN.reset(token_reset)
        REQUEST_USER_ID.reset(user_reset)
    assert seen["token"] == "databricks-workspace-token"
    assert creds.token == "databricks-workspace-token"
    assert creds.user_id == "dev@example.com"
