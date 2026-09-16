"""Exchange failure must surface as 401, never a Databricks backend call."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_databricks.middleware import AuthContextMiddleware
from mcp_as_client import TokenExchangeError


class _User:
    def __init__(self, token: str) -> None:
        self.access_token = type(
            "T",
            (),
            {"token": token, "subject": "dev", "claims": {}, "client_id": "c"},
        )()


class _InjectUser:
    def __init__(self, app, user) -> None:
        self.app = app
        self.user = user

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        scope["user"] = self.user
        await self.app(scope, receive, send)


class _FailingExchange:
    async def exchange(self, token: str):
        raise TokenExchangeError("invalid_grant", "nope", status_code=401)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_exchange_failure_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mcp_databricks.middleware._EXCHANGE", _FailingExchange())

    async def ok(request):
        return JSONResponse({"ok": True})

    inner = Starlette(routes=[Route("/mcp", ok, methods=["POST"])])
    app = _InjectUser(AuthContextMiddleware(inner), _User("mcp-jwt"))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}
        )
    assert denied.status_code == 401
    assert denied.json()["error"] == "invalid_token"
