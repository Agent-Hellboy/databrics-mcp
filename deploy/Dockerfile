FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends --yes ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md LICENSE /app/
COPY mcp_databricks /app/mcp_databricks

# --reinstall-package: neither local package's version changes between releases,
# so the uv cache would otherwise serve stale wheels and silently ship old code.
# No cache mount here: it requires BuildKit's buildx component, which isn't
# guaranteed on a stock Docker install, and deploy/README.md documents a
# plain `docker build`. This build is not repeated often enough for the
# cache to be worth that portability cost.
RUN uv sync --frozen --no-dev --no-editable \
        --reinstall-package databricks-mcp --reinstall-package mcp-auth-client

FROM python:3.12-slim

RUN useradd --create-home --uid 1000 appuser && \
    mkdir -p /var/lib/mcp-resource-auth /metrics && \
    chown -R appuser:appuser /var/lib/mcp-resource-auth /metrics

WORKDIR /app
COPY --from=build --chown=appuser:appuser /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

USER appuser
ENV MCP_METRICS_DB_PATH=/metrics/databricks-mcp-metrics.sqlite3
# 0.0.0.0 so the container is reachable at all; server.py's own MCP_HOST
# default (127.0.0.1) is meant for a bare-metal/dev run, not a container.
ENV MCP_HOST=0.0.0.0
EXPOSE 6328
# Runs server.py's entrypoint instead of invoking uvicorn directly, so
# MCP_PORT/MCP_HOST/MCP_LOG_LEVEL actually take effect here — a hardcoded
# `uvicorn ... --port 6328` CMD made MCP_PORT a documented setting that did
# nothing for this, the only supported deployment path.
CMD ["python", "-m", "mcp_databricks"]
