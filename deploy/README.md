# Deploy the Databricks MCP resource server

This service is an OAuth-protected MCP resource server. The authorization
server is deployed separately and owns user login, consent, client registration,
token issuance, and signing keys.

Use a deployment-specific hostname instead of the placeholders below. Do not
commit the resulting environment file.

## Prerequisites

- A Databricks workspace and an approved HTTPS host URL.
- An MCP-compatible authorization server with OAuth discovery and JWKS.
- An explicit group and SQL warehouse allowlist.
- A secret-managed resource-server private key for optional token exchange.
- Docker and an HTTPS reverse proxy.

## Configure

Copy [`service.env.example`](service.env.example) to a secret-managed location
and set:

- the canonical resource URL;
- authorization-server issuer, JWKS, and token endpoints;
- the resource-server exchange client key files;
- the required Databricks group;
- approved SQL warehouse IDs.

Startup must fail closed when the required group, warehouse allowlist, workspace
host, or exchange credentials are missing.

## Build and run

```bash
docker build -f deploy/Dockerfile -t databricks-mcp:latest .
docker run -d --name databricks-mcp-server --restart unless-stopped \
  -p 127.0.0.1:6328:6328 \
  -v /var/lib/mcp-metrics:/metrics \
  -v mcp-resource-auth:/var/lib/mcp-resource-auth:ro \
  --env-file /path/to/service.env \
  databricks-mcp:latest
```

The container should listen only on loopback and sit behind an HTTPS reverse
proxy. Mount the resource-server private key read-only. Never mount user OAuth
client secrets or authorization-server signing keys into this container.

## Reverse proxy

Expose the MCP endpoint and its Protected Resource Metadata endpoint. A typical
deployment uses:

- `/databricks` for MCP traffic;
- `/.well-known/oauth-protected-resource/databricks` for discovery;
- a separate authorization-service host or path for OAuth endpoints.

The proxy must preserve `Authorization`, `Origin`, and MCP transport headers,
disable response buffering for Streamable HTTP, and use a long read timeout.
Validate the proxy configuration before reloading it.

## Verification

Check discovery and the unauthenticated challenge before testing a browser flow:

```bash
curl -i https://mcp.example.com/.well-known/oauth-protected-resource/databricks
curl -i -X POST https://mcp.example.com/databricks \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

Expected behavior is a metadata response followed by `401 Unauthorized` with a
`WWW-Authenticate` resource-metadata challenge. After authorization, verify a
catalog read, a bounded SQL read, group denial, and warehouse allowlist denial.

## Rollback

Keep the previous image tag and deployment configuration. Roll back the image,
restore the previous proxy configuration if changed, validate it, and verify
the metadata and challenge endpoints again.
