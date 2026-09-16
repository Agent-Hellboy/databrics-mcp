"""Tests for deployment-controlled host and cloud configuration."""

from __future__ import annotations

import pytest

from mcp_databricks.app import allowed_hosts, host_origin_protection
from mcp_databricks.auth import allowed_host_suffixes, auth_issuer, workspace_host


def test_allowed_hosts_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "mcp.example.com, mcp.example.com:443")
    assert allowed_hosts() == ["mcp.example.com", "mcp.example.com:443"]


@pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
def test_host_origin_protection_accepts_true_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("MCP_HOST_ORIGIN_PROTECTION", value)
    assert host_origin_protection() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off"])
def test_host_origin_protection_accepts_false_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("MCP_HOST_ORIGIN_PROTECTION", value)
    assert host_origin_protection() is False


def test_host_origin_protection_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_HOST_ORIGIN_PROTECTION", "sometimes")
    with pytest.raises(ValueError, match="must be a boolean"):
        host_origin_protection()


@pytest.mark.parametrize(
    "host",
    [
        "https://workspace.cloud.databricks.com",
        "https://workspace.azuredatabricks.net",
        "https://workspace.gcp.databricks.com",
    ],
)
def test_workspace_host_accepts_supported_clouds(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    monkeypatch.delenv("DATABRICKS_ALLOWED_HOST_SUFFIXES", raising=False)
    monkeypatch.setenv("DATABRICKS_HOST", host)
    assert workspace_host() == host


def test_workspace_host_suffixes_are_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABRICKS_ALLOWED_HOST_SUFFIXES", "example.internal")
    monkeypatch.setenv("DATABRICKS_HOST", "https://workspace.example.internal")
    assert allowed_host_suffixes() == (".example.internal",)
    assert workspace_host() == "https://workspace.example.internal"


def test_workspace_host_remains_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABRICKS_HOST", "https://workspace.cloud.databricks.com.evil")
    with pytest.raises(ValueError, match="approved HTTPS"):
        workspace_host()

    monkeypatch.setenv("DATABRICKS_ALLOWED_HOST_SUFFIXES", "")
    with pytest.raises(ValueError, match="must not be empty"):
        allowed_host_suffixes()


def test_auth_issuer_has_no_silent_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # A misconfigured deployment must fail loudly at startup rather than
    # trust a placeholder issuer that no real token was ever signed by.
    monkeypatch.setenv("MCP_AUTH_ISSUER", "")
    with pytest.raises(ValueError, match="MCP_AUTH_ISSUER is required"):
        auth_issuer()

    monkeypatch.setenv("MCP_AUTH_ISSUER", "https://auth.example.com/")
    assert auth_issuer() == "https://auth.example.com"
