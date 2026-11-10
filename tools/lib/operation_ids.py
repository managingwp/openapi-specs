"""Rewrite operationIds into short, unique snake_case MCP tool names."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
_SNAKE_INVALID = re.compile(r"[^a-z0-9]+")
_LEADING_V2 = re.compile(r"^v\d+$")


def iter_operations(document: dict) -> Iterator[tuple[str, str, dict]]:
    """Yield ``(path, method, operation)`` for every operation in the document."""

    for path, path_item in document.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if isinstance(operation, dict):
                yield path, method, operation


def auto_operation_id(method: str, path: str) -> str:
    """Generate a readable snake_case name from a method and path."""

    segments: list[str] = [method.lower()]
    for raw in path.split("/"):
        segment = raw.strip()
        if not segment or _LEADING_V2.match(segment):
            continue
        segment = re.sub(r"\.json$", "", segment, flags=re.IGNORECASE)
        parameter = re.fullmatch(r"\{([^}]+)\}", segment)
        if parameter:
            segments.append(parameter.group(1).lower())
        else:
            segments.append(segment.lower())
    return normalize_operation_id("_".join(segments))


def normalize_operation_id(value: str) -> str:
    """Lowercase, collapse anything outside ``[a-z0-9_]`` and trim underscores."""

    cleaned = _SNAKE_INVALID.sub("_", value.strip().lower())
    return cleaned.strip("_")


def rewrite_operation_ids(
    document: dict,
    mapping: Mapping[str, str] | None = None,
    *,
    max_length: int = 40,
) -> dict[str, str]:
    """Rewrite every operationId, using ``mapping`` where supplied.

    Keys are the vendor's original operationIds. Anything unmapped gets an
    auto-generated name. Names are unique and at most ``max_length`` characters.
    """

    mapping = dict(mapping or {})
    used: set[str] = set()
    rewritten: dict[str, str] = {}

    for path, method, operation in iter_operations(document):
        source = str(operation.get("operationId") or "")
        candidate = mapping.get(source) or auto_operation_id(method, path)
        candidate = normalize_operation_id(candidate) or auto_operation_id(method, path)
        candidate = candidate[:max_length].strip("_") or "operation"

        if candidate in used:
            suffix = 2
            while True:
                ending = f"_{suffix}"
                base = candidate[: max_length - len(ending)].strip("_")
                attempt = f"{base}{ending}"
                if attempt not in used:
                    candidate = attempt
                    break
                suffix += 1

        used.add(candidate)
        operation["operationId"] = candidate
        if source:
            rewritten[source] = candidate

    return rewritten
