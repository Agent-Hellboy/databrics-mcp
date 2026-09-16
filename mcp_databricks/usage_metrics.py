"""SQLite usage metrics for Databricks MCP HTTP requests."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mcp_databricks.config import REQUEST_USER_ID, SCOPE_USER_ID

SERVER_NAME = "databricks"
DEFAULT_DB_PATH = "/tmp/databricks-mcp-metrics.sqlite3"
logger = logging.getLogger("databricks-mcp.metrics")


class UsageMetricsMiddleware:
    """Best-effort MCP POST metrics; failures never interrupt traffic."""

    def __init__(self, app: ASGIApp, path: str = "/mcp") -> None:
        self.app = app
        self.path = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != self.path
        ):
            await self.app(scope, receive, send)
            return
        body: list[bytes] = []
        status: int | None = None
        started = time.monotonic()

        async def wrapped_receive() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                body.append(message.get("body", b""))
            return message

        async def wrapped_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        finally:
            self._record(
                scope, b"".join(body), status, int((time.monotonic() - started) * 1000)
            )

    @staticmethod
    def _record(
        scope: Scope, body: bytes, status: int | None, duration_ms: int
    ) -> None:
        if os.environ.get("MCP_METRICS_ENABLED", "true").lower() in {
            "0",
            "false",
            "no",
            "off",
        }:
            return
        try:
            payload: Any = json.loads(body.decode("utf-8")) if body else {}
            if isinstance(payload, list):
                payload = payload[0] if payload else {}
            params = payload.get("params", {}) if isinstance(payload, dict) else {}
            rpc_method = payload.get("method") if isinstance(payload, dict) else None
            tool_name = (
                params.get("name")
                if rpc_method == "tools/call" and isinstance(params, dict)
                else None
            )
            headers = dict(scope.get("headers", []))
            client = scope.get("client") or ("unknown",)
            user_id = "unknown"
            # scope first: this middleware wraps outside http_app, so by the time
            # _record runs AuthContextMiddleware has reset the ContextVar and
            # REQUEST_USER_ID.get() is None. The scope dict still holds it.
            user_id = scope.get(SCOPE_USER_ID) or REQUEST_USER_ID.get() or user_id
            if user_id == "unknown":
                user_id = (
                    headers.get(b"x-databricks-user", b"").decode("latin-1")
                    or headers.get(b"x-mcp-user", b"").decode("latin-1")
                    or "unknown"
                )
            db_path = Path(os.environ.get("MCP_METRICS_DB_PATH", DEFAULT_DB_PATH))
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(db_path, timeout=5) as conn:
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS mcp_call_metrics (
                      id INTEGER PRIMARY KEY AUTOINCREMENT, server TEXT NOT NULL, user_id TEXT NOT NULL,
                      tool_name TEXT, rpc_method TEXT, http_method TEXT NOT NULL, path TEXT NOT NULL,
                      status_code INTEGER, duration_ms INTEGER NOT NULL, session_id TEXT,
                      client_host TEXT, user_agent TEXT, error TEXT, created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_mcp_call_metrics_created_at ON mcp_call_metrics(created_at);
                    CREATE INDEX IF NOT EXISTS idx_mcp_call_metrics_user_tool ON mcp_call_metrics(user_id, tool_name);
                """)
                conn.execute(
                    """INSERT INTO mcp_call_metrics
                    (server,user_id,tool_name,rpc_method,http_method,path,status_code,duration_ms,session_id,client_host,user_agent,error,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        SERVER_NAME,
                        user_id,
                        tool_name,
                        rpc_method,
                        "POST",
                        "/mcp",
                        status,
                        duration_ms,
                        headers.get(b"mcp-session-id", b"").decode("latin-1") or None,
                        str(client[0]),
                        headers.get(b"user-agent", b"").decode("latin-1") or None,
                        None,
                        datetime.now(UTC).isoformat(),
                    ),
                )
        except Exception:
            logger.debug("metrics recording failed", exc_info=True)
            return
