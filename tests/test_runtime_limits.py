"""Query limits and display identity must be settable without editing source."""

from __future__ import annotations

import pytest

from mcp_databricks.auth.consent_config import server_display_name, server_website
from mcp_databricks.tools.sql import (
    DEFAULT_MAX_ROWS,
    DEFAULT_MAX_SAMPLE_ROWS,
    DEFAULT_WAIT_TIMEOUT,
    max_rows,
    max_sample_rows,
    sample_table,
    wait_timeout,
)


def test_limits_fall_back_to_documented_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("MCP_MAX_ROWS", "MCP_MAX_SAMPLE_ROWS", "MCP_SQL_WAIT_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    assert max_rows() == DEFAULT_MAX_ROWS
    assert max_sample_rows() == DEFAULT_MAX_SAMPLE_ROWS
    assert wait_timeout() == DEFAULT_WAIT_TIMEOUT


def test_limits_are_env_backed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_MAX_ROWS", "50")
    monkeypatch.setenv("MCP_MAX_SAMPLE_ROWS", "5")
    monkeypatch.setenv("MCP_SQL_WAIT_TIMEOUT", "30s")
    assert max_rows() == 50
    assert max_sample_rows() == 5
    assert wait_timeout() == "30s"


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_non_positive_limits_are_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("MCP_MAX_ROWS", value)
    with pytest.raises(ValueError, match="positive integer"):
        max_rows()


def test_sample_limit_ceiling_only_clamps_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """MCP_MAX_SAMPLE_ROWS is a ceiling, never a floor: asking for more is
    clamped to it, asking for less is honored."""
    monkeypatch.setenv("MCP_MAX_SAMPLE_ROWS", "10")
    seen: dict[str, str] = {}

    def fake_run(warehouse_id: str, statement: str) -> dict:
        seen["statement"] = statement
        return {}

    monkeypatch.setattr("mcp_databricks.tools.sql.run_readonly_sql", fake_run)
    monkeypatch.setattr(
        "mcp_databricks.tools.sql.validate_table_identifier", lambda name: name
    )

    sample_table("w", "cat.sch.tbl", limit=999)
    assert seen["statement"].endswith("LIMIT 10")

    sample_table("w", "cat.sch.tbl", limit=3)
    assert seen["statement"].endswith("LIMIT 3")


def test_server_website_is_required_and_fails_closed_on_the_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It is shown to the person deciding whether to authorize, so shipping
    example.com points them at a domain the operator does not control."""
    monkeypatch.setenv("MCP_SERVER_WEBSITE", "")
    with pytest.raises(ValueError, match="required"):
        server_website()

    for placeholder in (
        "https://example.com/databricks",
        "https://www.example.com",
        "https://example.com:8443/x",
    ):
        monkeypatch.setenv("MCP_SERVER_WEBSITE", placeholder)
        with pytest.raises(ValueError, match="example.com"):
            server_website()

    monkeypatch.setenv("MCP_SERVER_WEBSITE", "https://mcp.corp.internal/databricks")
    assert server_website() == "https://mcp.corp.internal/databricks"


def test_server_display_name_is_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_SERVER_DISPLAY_NAME", raising=False)
    assert server_display_name() == "Databricks MCP"
    monkeypatch.setenv("MCP_SERVER_DISPLAY_NAME", "Acme Databricks")
    assert server_display_name() == "Acme Databricks"
