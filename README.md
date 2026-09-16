# Databricks MCP

Read-only [Model Context Protocol](https://modelcontextprotocol.io/) server for
Databricks. It exposes catalog metadata and bounded SQL tools over Streamable
HTTP while preserving the caller's identity through an OAuth-protected resource
server.

Authorization is optional in MCP, but this service requires it in production
because it exposes private workspace data. The authorization server may be
self-hosted or provided by a third party. See
[`docs/authorization.md`](docs/authorization.md).

## Tools

| Area | Tools |
| --- | --- |
| Catalog | `list_catalogs`, `list_schemas`, `list_tables`, `describe_table`, `search_tables` |
| SQL | `run_readonly_sql`, `sample_table` |
| Warehouses | `list_warehouses` |

SQL is limited to one `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, or `EXPLAIN`
statement. Results are bounded, table sampling requires a three-part Unity
Catalog identifier, and no write, job, cluster, DBFS, or secret tools are
exposed.

## Requirements

- Python 3.12+
- A Databricks workspace
- An MCP-compatible OAuth authorization server
- The companion authorization-client package configured in `pyproject.toml`

## Configuration

Copy [`deploy/service.env.example`](deploy/service.env.example) and set the
deployment-specific values:

| Variable | Purpose |
| --- | --- |
| `DATABRICKS_HOST` | HTTPS Databricks workspace URL |
| `PUBLIC_BASE_URL` / `MCP_SERVER_URL` | Canonical MCP resource URL |
| `MCP_AUTH_ISSUER` | Authorization-server issuer |
| `MCP_AUTH_JWKS_URI` | JWKS endpoint for access-token validation |
| `MCP_AUTH_TOKEN_ENDPOINT` | Optional downstream token-exchange endpoint |
| `MCP_AUTH_CLIENT_PRIVATE_KEY_FILE` | Resource-server exchange key |
| `MCP_AUTH_CLIENT_KEY_ID_FILE` | Exchange-key identifier |
| `DATABRICKS_REQUIRED_GROUP` | Required Databricks group |
| `DATABRICKS_ALLOWED_WAREHOUSE_IDS` | Explicit warehouse allowlist |

Keep real credentials, tokens, keys, and deployment env files out of Git.

## Run locally

```bash
uv run uvicorn mcp_databricks.server:app --host 127.0.0.1 --port 6328
```

Or:

```bash
python -m mcp_databricks
```

The MCP endpoint is `/mcp` by default. The canonical ASGI entrypoint is
`mcp_databricks.server:app`.

## Development checks

```bash
ruff check .
ruff format --check .
python -m compileall -q mcp_databricks tests
uv run pytest
```

The first three checks run in public CI without service credentials. The full
test suite also requires the companion authorization-client package and its
development dependencies.

## Release

Push a tag such as `v0.2.3`; the release workflow reruns validation, builds
the Python distributions, and publishes a GitHub Release with the artifacts.

## Deployment

- **Docker:** build `deploy/Dockerfile`, inject a secret-managed env file, and
  mount the resource-server key read-only.
- **Kubernetes:** run the container as a non-root Deployment, store env values
  and keys in Secrets, and expose it through an HTTPS Ingress.

- [`docs/authorization.md`](docs/authorization.md): MCP OAuth flow and provider integration
- [`deploy/README.md`](deploy/README.md): Docker and reverse-proxy checklist
- [`deploy/service.env.example`](deploy/service.env.example): neutral configuration template

The authorization server owns login, consent, client registration, token
issuance, and signing keys. This repository owns the Databricks MCP tools,
resource-server policy, and downstream workspace integration.
