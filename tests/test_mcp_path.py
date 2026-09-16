"""MCP_PATH has to reach every place that used to say "/mcp".

Four things must agree on where this server mounts: the ASGI route, the
"resource" field of the protected-resource metadata, the path-scoped location
that metadata is published at, and the audience tokens are validated against.
They were four independent literals, so a deployment that moved off /mcp would
half-work — routing fine, every token rejected on audience — which reads like
an auth bug and is not one. These tests pin them to one value.
"""

from __future__ import annotations

import pytest

BASE_URL = "https://mcp.example.com/databricks"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_default_is_mcp(monkeypatch) -> None:
    from mcp_databricks.auth import mcp_path

    monkeypatch.delenv("MCP_PATH", raising=False)
    assert mcp_path() == "/mcp"


@pytest.mark.parametrize(
    "configured", ["/tools", "tools", "/tools/", "tools/", "  /tools  "]
)
def test_path_is_normalized_to_one_spelling(monkeypatch, configured) -> None:
    """Every spelling has to land on the same string.

    The value is concatenated onto the base URL to form the audience, so
    "tools" and "/tools/" producing different audiences would be a token
    rejection that depends on how someone typed an env var.
    """
    from mcp_databricks.auth import mcp_path

    monkeypatch.setenv("MCP_PATH", configured)
    assert mcp_path() == "/tools"


@pytest.mark.parametrize("configured", ["/", "//", "   /   "])
def test_mounting_at_the_root_is_rejected(monkeypatch, configured) -> None:
    from mcp_databricks.auth import mcp_path

    monkeypatch.setenv("MCP_PATH", configured)
    with pytest.raises(ValueError, match="MCP_PATH"):
        mcp_path()


def test_resource_identifier_and_audience_are_the_same_string(monkeypatch) -> None:
    """The one assertion that catches a half-applied MCP_PATH.

    The audience comes from the SDK (resource URL + mcp_path) and the resource
    identifier from this package; if either stopped honouring MCP_PATH, tokens
    would be issued for one string and validated against another.
    """
    from mcp_databricks.app import mcp_resource_url
    from mcp_databricks.auth import build_auth_provider

    monkeypatch.setenv("MCP_PATH", "/tools")
    audience = build_auth_provider().token_verifier.audience
    assert mcp_resource_url() == f"{BASE_URL}/tools"
    assert audience == mcp_resource_url()


@pytest.mark.anyio
async def test_metadata_follows_the_configured_path(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    from mcp_databricks.app import create_app

    monkeypatch.setenv("MCP_PATH", "/tools")
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        scoped = await client.get(
            "/.well-known/oauth-protected-resource/databricks/tools"
        )
        stale = await client.get("/.well-known/oauth-protected-resource/databricks/mcp")
        bare = await client.get("/.well-known/oauth-protected-resource")

    assert scoped.status_code == 200
    assert scoped.json()["resource"] == f"{BASE_URL}/tools"
    # The scoped location is derived, not appended to: the old one must be gone,
    # or a client that cached the previous challenge keeps discovering a
    # resource identifier this server no longer issues tokens for.
    assert stale.status_code == 404
    assert bare.status_code == 200
    assert bare.json() == scoped.json()


@pytest.mark.anyio
async def test_mcp_endpoint_moves_with_the_configured_path(monkeypatch) -> None:
    """Routing has to move too, not just the metadata.

    An unauthenticated POST is enough to tell "this route exists and is
    protected" (401) from "this route does not exist" (404), without needing a
    real token.
    """
    from httpx import ASGITransport, AsyncClient

    from mcp_databricks.app import create_app

    monkeypatch.setenv("MCP_PATH", "/tools")
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        moved = await client.post("/tools", json={})
        old = await client.post("/mcp", json={})

    assert moved.status_code == 401
    assert old.status_code == 404


def test_metrics_middleware_matches_the_mcp_path_not_a_metadata_path(
    monkeypatch,
) -> None:
    """The metrics middleware only records requests whose path equals its own.

    Pointed at anything else it records nothing at all, and since it swallows
    every failure by design, that shows up as an empty metrics table rather
    than an error. Pinning the value is the only way this stays caught.
    """
    from mcp_databricks.app import create_app

    monkeypatch.setenv("MCP_PATH", "/tools")
    assert create_app().path == "/tools"
