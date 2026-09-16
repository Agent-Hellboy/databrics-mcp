"""Safe request credential and read-only SQL validation helpers."""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from mcp_databricks.auth import workspace_host

READ_ONLY_START = re.compile(
    r"^\s*(select|with|show|describe|explain)\b", re.IGNORECASE
)
MUTATING_EXPRESSIONS = (
    exp.DML,
    exp.DDL,
    exp.Alter,
    exp.Drop,
    exp.TruncateTable,
    exp.Grant,
    exp.Revoke,
    exp.Use,
    exp.Into,
)
TABLE_IDENTIFIER = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$"
)

# Per-request Databricks user access token (set by middleware / tool entry).
REQUEST_ACCESS_TOKEN: ContextVar[str | None] = ContextVar(
    "request_access_token", default=None
)
REQUEST_USER_ID: ContextVar[str | None] = ContextVar("request_user_id", default=None)

# ASGI scope key carrying the authenticated identity. UsageMetricsMiddleware wraps
# outside http_app and therefore runs after AuthContextMiddleware has reset the
# ContextVars above; the scope dict is the only channel that outlives them.
SCOPE_USER_ID = "mcp_databricks.user_id"


@dataclass(frozen=True)
class RequestCredentials:
    host: str
    token: str
    user_id: str


def credentials_from_access_token(
    token: str, user_id: str | None = None
) -> RequestCredentials:
    cleaned = (token or "").strip()
    if not cleaned:
        raise ValueError("Databricks OAuth access token is required.")
    return RequestCredentials(
        host=workspace_host(),
        token=cleaned,
        user_id=(user_id or "").strip() or "unknown",
    )


def credentials_from_current_request() -> RequestCredentials:
    token = REQUEST_ACCESS_TOKEN.get()
    if not token:
        raise ValueError(
            "Databricks credentials are available only during an authenticated MCP request."
        )
    return credentials_from_access_token(token, REQUEST_USER_ID.get())


def _parsed_query_is_read_only(tree: exp.Expression, normalized: str) -> bool:
    if any(isinstance(node, MUTATING_EXPRESSIONS) for node in tree.walk()):
        return False
    if isinstance(tree, exp.Query | exp.Describe):
        return True
    if isinstance(tree, exp.Command):
        command = normalized.split(None, 1)[0].lower()
        if command == "show":
            return True
        if command == "explain" and len(normalized.split(None, 1)) == 2:
            explained = normalized.split(None, 1)[1]
            try:
                explained_trees = sqlglot.parse(explained, read="databricks")
            except ParseError:
                return False
            return (
                len(explained_trees) == 1
                and explained_trees[0] is not None
                and _parsed_query_is_read_only(explained_trees[0], explained)
            )
    return False


def validate_readonly_sql(statement: str) -> str:
    normalized = statement.strip()
    if not normalized or not READ_ONLY_START.match(normalized):
        raise ValueError(
            "Only read-only SELECT, WITH, SHOW, DESCRIBE, and EXPLAIN statements are allowed."
        )
    try:
        trees = sqlglot.parse(normalized, read="databricks")
    except ParseError as exc:
        raise ValueError("SQL statement is not valid Databricks SQL.") from exc
    if (
        len(trees) != 1
        or trees[0] is None
        or not _parsed_query_is_read_only(trees[0], normalized)
    ):
        raise ValueError("Submit one parsed read-only SQL statement only.")
    return normalized


def validate_table_identifier(full_name: str) -> str:
    """Allow a simple three-part Unity Catalog identifier in generated SQL."""
    normalized = full_name.strip()
    if not TABLE_IDENTIFIER.fullmatch(normalized):
        raise ValueError(
            "Table name must be a three-part identifier: catalog.schema.table."
        )
    return normalized
