"""AuthContextMiddleware must name the human behind an MCP JWT.

The authorization server puts the Databricks user in the MCP JWT's `sub`. It
cannot put them in
`email` or `preferred_username`: the connector requests `sql unity-catalog offline_access openid email profile`, and without `openid` Databricks returns no id_token, so the only
identity the authorization server sees is the `sub` of the upstream access token.

On this side FastMCP's JWTVerifier builds AccessToken without ever setting
`subject`, so the parsed claims are the only place that `sub` survives.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_databricks.config import SCOPE_USER_ID
from mcp_databricks.middleware import AuthContextMiddleware

USER = "user@example.com"
DCR_CLIENT_ID = "dd842253-82b4-4327-936a-aabe5fe453e0"


class _AccessToken:
    """What JWTVerifier hands back: claims populated, `subject` left as None."""

    def __init__(self, claims: dict, subject: str | None = None) -> None:
        self.token = "mcp-jwt"
        self.subject = subject
        self.claims = claims
        self.client_id = DCR_CLIENT_ID


class _User:
    def __init__(self, access_token: _AccessToken) -> None:
        self.access_token = access_token


class _InjectUser:
    def __init__(self, app, user) -> None:
        self.app = app
        self.user = user

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        scope["user"] = self.user
        await self.app(scope, receive, send)


class _Exchanged:
    access_token = "databricks-token"


class _OkExchange:
    async def exchange(self, token: str):
        return _Exchanged()


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _user_id_for(access: _AccessToken, monkeypatch: pytest.MonkeyPatch) -> str | None:
    monkeypatch.setattr("mcp_databricks.middleware._EXCHANGE", _OkExchange())
    seen: dict[str, str | None] = {}

    async def ok(request):
        seen["user_id"] = request.scope.get(SCOPE_USER_ID)
        return JSONResponse({"ok": True})

    inner = Starlette(routes=[Route("/mcp", ok, methods=["POST"])])
    app = _InjectUser(AuthContextMiddleware(inner), _User(access))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert response.status_code == 200
    return seen.get("user_id")


@pytest.mark.anyio
async def test_sub_claim_names_the_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """The production shape: `sub` only, and it must not fall through to the client id."""
    access = _AccessToken(claims={"sub": USER, "iss": "https://auth.example.com"})
    assert await _user_id_for(access, monkeypatch) == USER


@pytest.mark.anyio
async def test_email_claim_is_used_when_sub_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A connector that returns OIDC profile claims instead of `sub` still attributes."""
    access = _AccessToken(claims={"email": USER})
    assert await _user_id_for(access, monkeypatch) == USER


@pytest.mark.anyio
async def test_verifier_supplied_subject_is_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    """If a future verifier does populate `subject`, it stays authoritative."""
    access = _AccessToken(claims={"email": "someone-else@example.com"}, subject=USER)
    assert await _user_id_for(access, monkeypatch) == USER


@pytest.mark.anyio
async def test_client_id_is_the_last_resort(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no identity claim at all there is nothing better than the DCR client."""
    access = _AccessToken(claims={"iss": "https://auth.example.com"})
    assert await _user_id_for(access, monkeypatch) == DCR_CLIENT_ID
