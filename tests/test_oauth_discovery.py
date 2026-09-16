"""OAuth discovery tests (no live Databricks).

These pin the exact discovery paths and the resource identifier, because both are
load-bearing for the public nginx routes: the 401 challenge tells clients where the
PRM lives, and nginx must have a matching root-level location or discovery 404s in
production while loopback still looks healthy.
"""

from __future__ import annotations

import pytest

BASE_URL = "https://mcp.example.com/databricks"
PRM_PATH = "/.well-known/oauth-protected-resource/databricks/mcp"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client():
    from httpx import ASGITransport, AsyncClient

    from mcp_databricks.app import create_app

    return AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    )


@pytest.mark.anyio
async def test_protected_resource_metadata_is_served_at_the_service_scoped_path(
    client,
) -> None:
    async with client as c:
        response = await c.get(PRM_PATH)
    assert response.status_code == 200
    body = response.json()
    assert body["resource"] == f"{BASE_URL}/mcp"
    assert [issuer.rstrip("/") for issuer in body["authorization_servers"]] == [
        "https://auth.example.com"
    ]
    assert body["bearer_methods_supported"] == ["header"]


@pytest.mark.anyio
async def test_prm_is_not_served_at_the_bare_service_path(client) -> None:
    """The FastMCP resource is the mounted /mcp endpoint."""
    async with client as c:
        response = await c.get(PRM_PATH.removesuffix("/mcp"))
    assert response.status_code == 404


@pytest.mark.anyio
async def test_unauthorized_mcp_points_at_the_served_prm_path(client) -> None:
    async with client as c:
        response = await c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            headers={"Accept": "application/json, text/event-stream"},
        )
    assert response.status_code in {401, 403}
    challenge = response.headers.get("www-authenticate", "")
    assert (
        f'resource_metadata="{BASE_URL.split("/databricks")[0]}{PRM_PATH}"' in challenge
    )


@pytest.mark.anyio
async def test_authorization_server_metadata_is_not_served_by_the_resource_server(
    client,
) -> None:
    """Authorization-server metadata lives on the auth service, not here."""
    async with client as c:
        response = await c.get("/.well-known/oauth-authorization-server")
    assert response.status_code == 404
