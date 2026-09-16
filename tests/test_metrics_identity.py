"""Metrics must attribute to the authenticated user, not 'unknown'.

UsageMetricsMiddleware wraps *outside* http_app, so its _record() runs in a finally
that fires after AuthContextMiddleware's finally has already reset the ContextVars.
The ASGI scope is a plain dict and outlives them, so the identity travels there.
"""

from __future__ import annotations

import sqlite3

import pytest

from mcp_databricks.config import REQUEST_USER_ID, SCOPE_USER_ID
from mcp_databricks.usage_metrics import UsageMetricsMiddleware

USER = "user@example.com"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _row_user_id(db_path) -> str | None:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT user_id FROM mcp_call_metrics ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return row[0] if row else None


async def _drive(app, headers=None):
    """Send one POST /mcp through the middleware."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": headers or [],
        "client": ("10.0.0.1", 5000),
    }
    body = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_catalogs"}}'
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return sent


@pytest.mark.anyio
async def test_identity_survives_the_contextvar_reset(tmp_path, monkeypatch) -> None:
    db = tmp_path / "databricks-mcp-metrics.sqlite3"
    monkeypatch.setenv("MCP_METRICS_DB_PATH", str(db))
    # conftest disables metrics for the rest of the suite; _record returns early
    # without it, and swallows every failure, so the table would silently not exist.
    monkeypatch.setenv("MCP_METRICS_ENABLED", "true")

    async def inner(scope, receive, send):
        # Mirror AuthContextMiddleware: set both channels, then reset the ContextVar
        # in a finally, exactly as it does once the response is done.
        reset = REQUEST_USER_ID.set(USER)
        scope[SCOPE_USER_ID] = USER
        try:
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})
        finally:
            REQUEST_USER_ID.reset(reset)

    await _drive(UsageMetricsMiddleware(inner))
    assert _row_user_id(db) == USER


@pytest.mark.anyio
async def test_header_fallback_still_attributes_during_rollout(
    tmp_path, monkeypatch
) -> None:
    db = tmp_path / "databricks-mcp-metrics.sqlite3"
    monkeypatch.setenv("MCP_METRICS_DB_PATH", str(db))
    # conftest disables metrics for the rest of the suite; _record returns early
    # without it, and swallows every failure, so the table would silently not exist.
    monkeypatch.setenv("MCP_METRICS_ENABLED", "true")

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    await _drive(
        UsageMetricsMiddleware(inner),
        headers=[(b"x-databricks-user", b"legacy@example.com")],
    )
    assert _row_user_id(db) == "legacy@example.com"


@pytest.mark.anyio
async def test_unauthenticated_call_records_unknown(tmp_path, monkeypatch) -> None:
    db = tmp_path / "databricks-mcp-metrics.sqlite3"
    monkeypatch.setenv("MCP_METRICS_DB_PATH", str(db))
    # conftest disables metrics for the rest of the suite; _record returns early
    # without it, and swallows every failure, so the table would silently not exist.
    monkeypatch.setenv("MCP_METRICS_ENABLED", "true")

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    await _drive(UsageMetricsMiddleware(inner))
    assert _row_user_id(db) == "unknown"
