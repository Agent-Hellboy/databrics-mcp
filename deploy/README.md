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
- `MCP_ALLOWED_HOSTS`, as a comma-separated list of accepted Host values;
- `MCP_HOST_ORIGIN_PROTECTION=true` unless the proxy cannot provide a matching
  Origin header;
- `DATABRICKS_ALLOWED_HOST_SUFFIXES` when using a supported Databricks cloud
  hostname outside the default AWS, Azure, and GCP suffixes.

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

Create the named volume and resource-server keypair before the first run. The
key ID must match the public key registered with the authorization server:

```bash
docker volume create mcp-resource-auth
docker run --rm -v mcp-resource-auth:/var/lib/mcp-resource-auth alpine:3.20 \
  sh -c 'apk add --no-cache openssl >/dev/null && umask 077 && \
    openssl genrsa -out /var/lib/mcp-resource-auth/private.pem 2048 && \
    printf "%s\\n" databricks-mcp-resource > /var/lib/mcp-resource-auth/key_id'
```

The image keeps JWKS SSRF protection enabled by default. If a deployment has a
reviewed private-network JWKS endpoint, set `MCP_AUTH_JWKS_SSRF_SAFE=false` in
the runtime environment; it is intentionally not baked into the image.

The container should listen only on loopback and sit behind an HTTPS reverse
proxy. Mount the resource-server private key read-only. Never mount user OAuth
client secrets or authorization-server signing keys into this container.

## Reverse proxy

Expose the MCP endpoint and its Protected Resource Metadata endpoint. A typical
deployment uses:

- `/databricks/mcp` for MCP traffic (`/databricks` may remain as a compatibility alias);
- `/.well-known/oauth-protected-resource/databricks/mcp` for discovery;
- a separate authorization-service host or path for OAuth endpoints.

The proxy must preserve `Authorization`, `Origin`, and MCP transport headers,
disable response buffering for Streamable HTTP, and use a long read timeout.
Validate the proxy configuration before reloading it.

## Verification

Check discovery and the unauthenticated challenge before testing a browser flow:

```bash
curl -i https://mcp.example.com/.well-known/oauth-protected-resource/databricks/mcp
curl -i -X POST https://mcp.example.com/databricks/mcp \
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
