"""ASGI middleware that publishes identity and exchanges the MCP JWT."""

from __future__ import annotations

import json
import logging

from fastmcp.server.dependencies import get_access_token
from mcp_as_client import TokenExchangeError
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_databricks.auth import build_token_exchange_client
from mcp_databricks.config import REQUEST_ACCESS_TOKEN, REQUEST_USER_ID, SCOPE_USER_ID

logger = logging.getLogger("databricks-mcp.middleware")

_EXCHANGE = None


def _exchange_client():
    global _EXCHANGE
    if _EXCHANGE is None:
        _EXCHANGE = build_token_exchange_client()
    return _EXCHANGE


async def close_exchange_client() -> None:
    """Close the process-wide SDK client during ASGI shutdown."""
    global _EXCHANGE
    client, _EXCHANGE = _EXCHANGE, None
    close = getattr(client, "aclose", None)
    if close is not None:
        await close()


async def _send_unauthorized(send: Send, detail: str) -> None:
    body = json.dumps({"error": "invalid_token", "error_description": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Bearer error="invalid_token"'),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class AuthContextMiddleware:
    """Populate ContextVars from the MCP JWT after exchanging it for a Databricks token."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":

            async def receive_with_shutdown():
                message = await receive()
                if message["type"] == "lifespan.shutdown":
                    await close_exchange_client()
                return message

            await self.app(scope, receive_with_shutdown, send)
            return

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token_reset = REQUEST_ACCESS_TOKEN.set(None)
        user_reset = REQUEST_USER_ID.set(None)
        try:
            user = scope.get("user")
            access = getattr(user, "access_token", None) if user is not None else None
            if access is None:
                access = get_access_token()
            if access and getattr(access, "token", None):
                try:
                    exchanged = await _exchange_client().exchange(access.token)
                except TokenExchangeError as exc:
                    logger.warning("token exchange failed: %s", exc)
                    await _send_unauthorized(send, "upstream token exchange failed")
                    return
                REQUEST_ACCESS_TOKEN.set(exchanged.access_token)
                claims = getattr(access, "claims", None) or {}
                # JWTVerifier builds AccessToken without ever setting `subject`, so the
                # MCP JWT's `sub` survives only in the parsed claims. Reading it there
                # is what keeps this off the DCR client id, which names a client
                # registration rather than a person.
                user_id = (
                    getattr(access, "subject", None)
                    or claims.get("sub")
                    or claims.get("email")
                    or claims.get("preferred_username")
                    or getattr(access, "client_id", None)
                    or "unknown"
                )
                REQUEST_USER_ID.set(str(user_id))
                scope[SCOPE_USER_ID] = str(user_id)
            await self.app(scope, receive, send)
        finally:
            REQUEST_ACCESS_TOKEN.reset(token_reset)
            REQUEST_USER_ID.reset(user_reset)


__all__ = ["AuthContextMiddleware", "close_exchange_client"]
