"""Databricks display copy for the configured authorization server.

These two strings are this service's own identity, so they live here rather than
being imported from an authorization-server library -- the library must not have to know
the name of every service that uses it.
"""

from __future__ import annotations

SERVER_DISPLAY_NAME = "Databricks MCP"
SERVER_WEBSITE = "https://example.com/databricks"

__all__ = ["SERVER_DISPLAY_NAME", "SERVER_WEBSITE"]
