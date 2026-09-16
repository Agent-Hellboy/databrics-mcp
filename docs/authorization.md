# MCP authorization

MCP authorization is optional. An HTTP MCP server may be public, use its own
authorization server, or delegate to a third-party OAuth/OIDC provider. When
authorization is enabled, MCP clients discover the authorization server through
OAuth Protected Resource Metadata and send a bearer token on each request. See
the [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization).

This Databricks service intentionally requires authorization in production
because its tools expose private workspace data.

## Resource server versus authorization server

This repository is an MCP **resource server**, not an authorization server. A
separate authorization service is responsible for user login, consent, client
registration or client metadata, token issuance, signing keys, and OAuth
discovery. The resource server only validates tokens intended for its canonical
resource URL and applies its own tool scopes and data policy.

The small authorization-client adapter used by this service provides:

- JWT verification against the authorization server's JWKS;
- protected-resource metadata and OAuth challenge integration;
- optional RFC 8693 exchange for a downstream workspace token;
- short-lived, per-user exchange-token caching.

The inbound MCP token must not be forwarded to Databricks. If a downstream API
needs another credential, exchange or mint a separate token for that audience.

## Request flow

```text
MCP client
    │ 1. request without token
    ▼
Resource server ── 401 + protected-resource metadata ──▶ MCP client
    ▲                                                   │
    │ 4. retry with MCP bearer token                    │ 2. discover and authorize
    │                                                   ▼
    └──────────── validated token ◀──────────── Authorization server
                         │
                         │ 5. optional token exchange
                         ▼
                    Databricks API
```

The deployed sequence is:

1. The client calls the MCP endpoint and receives `401` with a
   `WWW-Authenticate` resource-metadata URL when it lacks a valid token.
2. The client reads protected-resource metadata and discovers the configured
   authorization-server issuer.
3. The user completes OAuth authorization and consent at that authorization
   server.
4. The client retries with `Authorization: Bearer <token>`.
5. The resource server validates the token's signature, issuer, audience, and
   scopes, then applies its own group and warehouse policy.
6. If the downstream workspace needs a different credential, middleware performs
   a separate token exchange using the resource server's private client key.

## Configuration

```dotenv
DATABRICKS_HOST=https://workspace.cloud.databricks.com
PUBLIC_BASE_URL=https://mcp.example.com/databricks
MCP_SERVER_URL=https://mcp.example.com/databricks
MCP_AUTH_ISSUER=https://auth.example.com
MCP_AUTH_JWKS_URI=https://auth.example.com/.well-known/jwks.json
MCP_AUTH_TOKEN_ENDPOINT=https://auth.example.com/token
MCP_AUTH_CONNECTOR=databricks
MCP_AUTH_CLIENT_ID=databricks-mcp-resource
MCP_AUTH_CLIENT_PRIVATE_KEY_FILE=/var/lib/mcp-resource-auth/private.pem
MCP_AUTH_CLIENT_KEY_ID_FILE=/var/lib/mcp-resource-auth/key_id
DATABRICKS_REQUIRED_GROUP=authorized_users
DATABRICKS_ALLOWED_WAREHOUSE_IDS=replace-with-approved-ids
```

The canonical resource URL must match the audience for issued MCP tokens. The
resource-server private key authenticates the service during token exchange; it
is not a user credential and must be mounted from a secret store.

## Bootstrapping DATABRICKS_ALLOWED_WAREHOUSE_IDS

`DATABRICKS_ALLOWED_WAREHOUSE_IDS` is fail-closed: the `list_warehouses` MCP
tool only ever returns warehouses already on that list, independent of the
caller's upstream OAuth scopes. That means the tool can't be used to discover
which IDs to put in the allowlist in the first place — by the time it can see
a warehouse, that warehouse is already approved.

To find the IDs before the service is configured, run
[`scripts/list_all_warehouses.py`](../scripts/list_all_warehouses.py) once,
directly against the workspace, using an operator's own Databricks credentials
(for example `DATABRICKS_HOST` and `DATABRICKS_TOKEN`, or a configured CLI
profile) rather than the MCP OAuth flow:

```bash
DATABRICKS_HOST=https://workspace.cloud.databricks.com \
DATABRICKS_TOKEN=... \
uv run python scripts/list_all_warehouses.py
```

Pick the IDs that should be reachable through this MCP server and set
`DATABRICKS_ALLOWED_WAREHOUSE_IDS` to that comma-separated list. The script is
not part of the MCP tool surface and is never exposed to MCP clients.

## Third-party authorization servers

A third-party authorization server can be used if it supports the MCP OAuth
discovery and resource-indicator contract, publishes signing keys, and issues
tokens intended for this resource server. Configure its issuer, JWKS URI, and
scopes through the same resource-server boundary.

If the provider cannot perform the required MCP client-registration flow, use an
OAuth proxy or a provider-specific adapter. If its access token is not accepted
by Databricks, retain a separate downstream exchange adapter. These are
deployment choices; the MCP tools do not need to change.

The [FastMCP remote OAuth guide](https://gofastmcp.com/v2/servers/auth/remote-oauth)
describes the resource-server side of this pattern.

## Reverse-proxy requirements

The proxy must expose:

- the MCP endpoint, usually `/databricks/mcp` or `/mcp`;
- the corresponding `/.well-known/oauth-protected-resource/...` metadata path;
- a callback route only when the authorization service requires one.

The authorization service owns its own authorization, token, registration, JWKS,
and consent routes. Do not copy those secrets or signing keys into this
resource-server repository.
