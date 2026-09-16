"""MCP-facing scopes and Databricks read-only resource policy."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mcp_databricks.policy import ReadOnlyPolicy
from mcp_databricks.tools import catalog, sql, warehouses


class _ToolRecorder:
    def __init__(self) -> None:
        self.checks = {}

    def tool(self, **kwargs):
        def register(function):
            self.checks[function.__name__] = kwargs["auth"]
            return function

        return register


def _context(*scopes: str):
    return SimpleNamespace(token=SimpleNamespace(scopes=list(scopes)))


def test_every_databricks_tool_has_a_resource_scope() -> None:
    recorder = _ToolRecorder()
    catalog.register(recorder)
    warehouses.register(recorder)
    sql.register(recorder)

    catalog_tools = {
        "list_catalogs",
        "list_schemas",
        "list_tables",
        "describe_table",
        "search_tables",
    }
    sql_tools = {"list_warehouses", "sample_table", "run_readonly_sql"}
    assert set(recorder.checks) == catalog_tools | sql_tools
    for name in catalog_tools:
        assert recorder.checks[name](_context("catalog:read"))
        assert not recorder.checks[name](_context("sql:read"))
    for name in sql_tools:
        assert recorder.checks[name](_context("sql:read"))
        assert not recorder.checks[name](_context("catalog:read"))


def test_policy_requires_exact_group_and_warehouse() -> None:
    policy = ReadOnlyPolicy(
        required_group="mcp_users",
        allowed_warehouse_ids=frozenset({"warehouse-1"}),
    )
    allowed_user = SimpleNamespace(
        groups=[SimpleNamespace(display="mcp_users", value="group-id")]
    )
    denied_user = SimpleNamespace(
        groups=[SimpleNamespace(display="other", value="other-id")]
    )

    policy.require_user(
        SimpleNamespace(current_user=SimpleNamespace(me=lambda: allowed_user))
    )
    with pytest.raises(PermissionError, match="required group"):
        policy.require_user(
            SimpleNamespace(current_user=SimpleNamespace(me=lambda: denied_user))
        )
    assert policy.require_warehouse("warehouse-1") == "warehouse-1"
    assert not policy.allows_warehouse("warehouse-2")
    with pytest.raises(PermissionError, match="not approved"):
        policy.require_warehouse("warehouse-2")


def test_policy_environment_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABRICKS_REQUIRED_GROUP", raising=False)
    monkeypatch.delenv("DATABRICKS_ALLOWED_WAREHOUSE_IDS", raising=False)
    with pytest.raises(ValueError, match="DATABRICKS_REQUIRED_GROUP"):
        ReadOnlyPolicy.from_env()
