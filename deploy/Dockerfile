# Build from the repo root:
#   docker build -f databricks/deploy/Dockerfile -t databricks-mcp:<tag> .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY auth-sdk /app/auth-sdk
COPY databricks/pyproject.toml databricks/uv.lock databricks/README.md /app/databricks/
COPY databricks/mcp_databricks /app/databricks/mcp_databricks

WORKDIR /app/databricks
# --reinstall-package: neither local package's version changes between releases,
# so the uv cache would otherwise serve stale wheels and silently ship old code.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable \
        --reinstall-package databricks-mcp --reinstall-package mcp-as-client

FROM python:3.12-slim

RUN useradd --create-home --uid 1000 appuser && \
    mkdir -p /var/lib/mcp-resource-auth && \
    chown appuser:appuser /var/lib/mcp-resource-auth

WORKDIR /app
COPY --from=build --chown=appuser:appuser /app/databricks/.venv /app/databricks/.venv
ENV PATH="/app/databricks/.venv/bin:$PATH"

USER appuser
ENV MCP_METRICS_DB_PATH=/metrics/databricks-mcp-metrics.sqlite3
# If the authorization server's JWKS endpoint is only reachable on a private
# network, configure the deployment-specific SSRF policy explicitly. Keep the
# JWKS URI server-side and never accept it from a client request.
ENV MCP_AUTH_JWKS_SSRF_SAFE=false
EXPOSE 6328
CMD ["uvicorn", "mcp_databricks.app:app", "--host", "0.0.0.0", "--port", "6328"]
