#!/usr/bin/env python3
"""One-time operator tool: list every SQL warehouse in a Databricks workspace.

Not part of the MCP tool surface and never reachable from an MCP client. The
`list_warehouses` MCP tool (mcp_databricks.tools.warehouses) is deliberately
fail-closed: it only returns warehouses already on DATABRICKS_ALLOWED_WAREHOUSE_IDS,
regardless of the caller's OAuth scopes. That means it cannot be used to find
which IDs belong in that allowlist in the first place. Run this script once,
directly against the workspace with an operator's own Databricks credentials,
to see every warehouse and choose which ones this service should be allowed
to query.

Usage:
    DATABRICKS_HOST=https://workspace.cloud.databricks.com \\
    DATABRICKS_TOKEN=... \\
    uv run python scripts/list_all_warehouses.py

Any Databricks SDK authentication method works (a token, a CLI profile, or
SSO); see https://docs.databricks.com/en/dev-tools/auth for details.
"""

from __future__ import annotations

import sys

from databricks.sdk import WorkspaceClient


def main() -> int:
    client = WorkspaceClient()
    warehouses = list(client.warehouses.list())
    if not warehouses:
        print("No SQL warehouses found in this workspace.", file=sys.stderr)
        return 1

    print(f"{'ID':<20} {'STATE':<12} NAME")
    for warehouse in warehouses:
        print(f"{warehouse.id:<20} {warehouse.state!s:<12} {warehouse.name}")

    print(
        "\nSet DATABRICKS_ALLOWED_WAREHOUSE_IDS to a comma-separated list of the "
        "IDs above that this MCP server should be allowed to query.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
