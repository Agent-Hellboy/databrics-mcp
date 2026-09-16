"""Databricks display copy for the configured authorization server.

These two strings are this service's own identity, so they live here rather than
being imported from an authorization-server library -- the library must not have to know
the name of every service that uses it.
"""

from __future__ import annotations

import os

DEFAULT_SERVER_DISPLAY_NAME = "Databricks MCP"
PLACEHOLDER_WEBSITE_HOSTS = ("example.com", "www.example.com")


def server_display_name() -> str:
    return (
        os.getenv("MCP_SERVER_DISPLAY_NAME", "").strip() or DEFAULT_SERVER_DISPLAY_NAME
    )


def server_website() -> str:
    """The URL shown to users in client UI, via FastMCP(website_url=...).

    Required, and fail-closed on the placeholder: this is surfaced to the
    person deciding whether to authorize, so shipping example.com points them
    at a domain the operator does not control. policy.py already rejects its
    own REPLACE_ME placeholder the same way, for the same reason.
    """
    website = os.getenv("MCP_SERVER_WEBSITE", "").strip()
    if not website:
        raise ValueError("MCP_SERVER_WEBSITE is required")
    host = website.split("//", 1)[-1].split("/", 1)[0].split("@")[-1].lower()
    if host.split(":")[0] in PLACEHOLDER_WEBSITE_HOSTS:
        raise ValueError(
            "MCP_SERVER_WEBSITE must not be an example.com placeholder: it is "
            "shown to users authorizing this server"
        )
    return website


__all__ = [
    "DEFAULT_SERVER_DISPLAY_NAME",
    "PLACEHOLDER_WEBSITE_HOSTS",
    "server_display_name",
    "server_website",
]
