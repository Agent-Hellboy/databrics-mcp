"""Fail-closed Databricks group and SQL warehouse authorization policy."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.upper() == "REPLACE_ME":
        raise ValueError(f"{name} is required and must not be a placeholder")
    return value


@dataclass(frozen=True)
class ReadOnlyPolicy:
    """Mandatory resource-server policy, independent of upstream OAuth scopes."""

    required_group: str
    allowed_warehouse_ids: frozenset[str]

    @classmethod
    def from_env(cls) -> "ReadOnlyPolicy":
        group = _required_env("DATABRICKS_REQUIRED_GROUP")
        warehouse_ids = frozenset(
            item.strip()
            for item in _required_env("DATABRICKS_ALLOWED_WAREHOUSE_IDS").split(",")
            if item.strip()
        )
        if not warehouse_ids:
            raise ValueError(
                "DATABRICKS_ALLOWED_WAREHOUSE_IDS must contain at least one id"
            )
        if "*" in warehouse_ids:
            raise ValueError("DATABRICKS_ALLOWED_WAREHOUSE_IDS must not use a wildcard")
        return cls(required_group=group, allowed_warehouse_ids=warehouse_ids)

    def require_user(self, client: Any) -> None:
        user = client.current_user.me()
        group_names = {
            value
            for group in (getattr(user, "groups", None) or [])
            for value in (
                getattr(group, "display", None),
                getattr(group, "value", None),
            )
            if value
        }
        if self.required_group not in group_names:
            raise PermissionError(
                f"Databricks user must belong to required group {self.required_group!r}"
            )

    def allows_warehouse(self, warehouse_id: str | None) -> bool:
        return bool(warehouse_id and warehouse_id in self.allowed_warehouse_ids)

    def require_warehouse(self, warehouse_id: str) -> str:
        normalized = (warehouse_id or "").strip()
        if normalized not in self.allowed_warehouse_ids:
            raise PermissionError(
                "SQL warehouse is not approved for MCP read-only access"
            )
        return normalized


@lru_cache(maxsize=1)
def read_only_policy() -> ReadOnlyPolicy:
    return ReadOnlyPolicy.from_env()


__all__ = ["ReadOnlyPolicy", "read_only_policy"]
