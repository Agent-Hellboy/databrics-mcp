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
EXPOSE 6328
CMD ["uvicorn", "mcp_databricks.app:app", "--host", "0.0.0.0", "--port", "6328"]
