"""Inject OpenAPI security schemes for APIs whose source declares none."""

from __future__ import annotations

from typing import Any


def _ensure_components(document: dict) -> dict:
    return document.setdefault("components", {})


def add_scheme(
    document: dict,
    name: str,
    scheme: dict[str, Any],
    *,
    require_globally: bool = True,
) -> dict:
    """Add a named security scheme and optionally make it the global default."""

    schemes = _ensure_components(document).setdefault("securitySchemes", {})
    schemes[name] = scheme
    if require_globally:
        existing = document.get("security")
        if not isinstance(existing, list) or not existing:
            document["security"] = [{name: []}]
    return document


def add_api_key(
    document: dict,
    *,
    name: str = "TokenAuth",
    header: str = "Authorization",
    location: str = "header",
    description: str | None = None,
) -> dict:
    """Add an apiKey scheme (a header token by default)."""

    scheme: dict[str, Any] = {
        "type": "apiKey",
        "in": location,
        "name": header,
    }
    if description:
        scheme["description"] = description
    return add_scheme(document, name, scheme)


def add_bearer(
    document: dict,
    *,
    name: str = "BearerAuth",
    bearer_format: str | None = "JWT",
    description: str | None = None,
) -> dict:
    """Add an HTTP bearer scheme."""

    scheme: dict[str, Any] = {"type": "http", "scheme": "bearer"}
    if bearer_format:
        scheme["bearerFormat"] = bearer_format
    if description:
        scheme["description"] = description
    return add_scheme(document, name, scheme)


def add_basic(
    document: dict,
    *,
    name: str = "BasicAuth",
    description: str | None = None,
) -> dict:
    """Add an HTTP basic scheme."""

    scheme: dict[str, Any] = {"type": "http", "scheme": "basic"}
    if description:
        scheme["description"] = description
    return add_scheme(document, name, scheme)


def has_scheme(document: dict) -> bool:
    """Return True when at least one security scheme exists."""

    schemes = document.get("components", {}).get("securitySchemes")
    return isinstance(schemes, dict) and bool(schemes)
