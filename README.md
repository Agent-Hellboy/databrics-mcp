# Databricks MCP

Read-only Streamable HTTP MCP server for a Databricks workspace. It exposes
catalog metadata and bounded SQL tools while preserving the caller's identity
through an OAuth-protected resource-server boundary.

MCP authorization is optional in the protocol, but this service is designed for
private data and therefore requires authorization in production. The
authorization server can be self-hosted or provided by a third party. See
[`docs/authorization.md`](docs/authorization.md) for the protocol flow and
configuration contract.

## Tools

- `list_warehouses`
- `list_catalogs`
- `list_schemas`
- `list_tables`
- `describe_table`
- `sample_table`
- `search_tables`
- `run_readonly_sql`

SQL accepts one `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, or `EXPLAIN` statement and
returns at most 200 rows. No write, cluster, job, DBFS, or secret tools are
exposed. Table sampling requires a three-part Unity Catalog identifier and is
capped at 100 rows.

## Client configuration

Configure an MCP client with the public resource URL:

```json
{
  "mcpServers": {
    "databricks": {
      "type": "http",
      "url": "https://mcp.example.com/databricks"
    }
  }
}
```

The client discovers the authorization server after the resource server returns
an OAuth challenge. Do not place OAuth client secrets, Databricks PATs, or
resource-server private keys in client configuration.

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATABRICKS_HOST` | Approved HTTPS Databricks workspace URL |
| `PUBLIC_BASE_URL` / `MCP_SERVER_URL` | Canonical public MCP resource URL |
| `MCP_AUTH_ISSUER` | Authorization-server issuer |
| `MCP_AUTH_JWKS_URI` | JWKS endpoint for validating MCP access tokens |
| `MCP_AUTH_TOKEN_ENDPOINT` | Optional upstream token-exchange endpoint |
| `MCP_AUTH_CONNECTOR` | Upstream connector or audience |
| `MCP_AUTH_CLIENT_ID` | Resource-server client ID for token exchange |
| `MCP_AUTH_CLIENT_PRIVATE_KEY_FILE` | Mounted private key for token exchange |
| `MCP_AUTH_CLIENT_KEY_ID_FILE` | Mounted key ID for token exchange |
| `DATABRICKS_REQUIRED_GROUP` | Required Databricks group |
| `DATABRICKS_ALLOWED_WAREHOUSE_IDS` | Explicit comma-separated warehouse allowlist |

Start from [`deploy/service.env.example`](deploy/service.env.example). Keep
real credentials and deployment-specific values outside Git.

## Local run

```bash
uv run uvicorn mcp_databricks.server:app --host 127.0.0.1 --port 6328
# or
python -m mcp_databricks
```

The canonical Python entrypoint is `mcp_databricks.server`. The ASGI app is
available as `mcp_databricks.server:app` for uvicorn, Hypercorn, or another
ASGI host.

## Docker deployment

```bash
docker build -f deploy/Dockerfile -t databricks-mcp:latest .
docker run --rm -p 127.0.0.1:6328:6328 \
  --env-file deploy/service.env.example \
  databricks-mcp:latest
```

For production, mount the resource-server exchange key read-only, use a real
secret-managed environment file, and put the service behind an HTTPS reverse
proxy. The reverse proxy must route the MCP endpoint and the protected-resource
metadata endpoint; authorization-server endpoints remain owned by the separate
authorization service.

## Layout

```text
mcp_databricks/
  server.py          canonical uvicorn/module entrypoint
  app.py             FastMCP instance and Streamable HTTP ASGI assembly
  auth/              resource-server auth configuration and display metadata
  middleware.py      per-request token exchange and caller identity
  client.py          per-request Databricks WorkspaceClient
  config.py          request credentials and SQL/identifier validation
  policy.py          fail-closed group and warehouse policy
  usage_metrics.py   best-effort SQLite request metrics
  tools/             explicit tool registration modules
tests/               auth, policy, discovery, and SQL validation tests
deploy/              generic Docker and reverse-proxy examples
docs/                authorization and integration notes
```

Tools are plain module-scope functions registered explicitly, so importing a
tool module has no server-side side effects and each function remains directly
callable from tests.
