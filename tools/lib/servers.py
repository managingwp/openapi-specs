"""Explicit server overrides; a published spec must never point at localhost."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

LOCAL_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}


def is_local_url(url: str) -> bool:
    """Return True for localhost, loopback, wildcard and unspecified hosts."""

    try:
        hostname = urlsplit(url).hostname
    except ValueError:
        return False
    if not hostname:
        return False
    host = hostname.lower().rstrip(".")
    if host in LOCAL_HOSTNAMES or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def set_servers(
    document: dict,
    url: str,
    *,
    description: str | None = None,
) -> dict:
    """Replace ``servers`` with a single explicit, non-local URL."""

    cleaned = url.strip().rstrip("/")
    if not cleaned.startswith(("http://", "https://")):
        raise ValueError(f"server URL must be absolute http(s), got {url!r}")
    if is_local_url(cleaned):
        raise ValueError(f"refusing to publish a localhost server URL: {url!r}")
    entry: dict[str, str] = {"url": cleaned}
    if description:
        entry["description"] = description
    document["servers"] = [entry]
    return document


def validate_servers(document: dict) -> list[str]:
    """Return human-readable problems with the document's ``servers`` entry."""

    servers = document.get("servers")
    if not isinstance(servers, list) or not servers:
        return ["servers is missing or empty"]
    problems: list[str] = []
    for index, server in enumerate(servers):
        url = server.get("url") if isinstance(server, dict) else None
        if not url:
            problems.append(f"servers[{index}] has no url")
        elif is_local_url(url):
            problems.append(f"servers[{index}] points at localhost: {url}")
    return problems
