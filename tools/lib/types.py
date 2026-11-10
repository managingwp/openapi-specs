"""Correct types that Swagger producers commonly get wrong.

Vendors frequently describe booleans as strings with a ``true``/``false`` enum,
numeric IDs as ``number`` and paging parameters as strings. MCP clients rely on
the JSON types, so these are fixed centrally.
"""

from __future__ import annotations

import re
from typing import Any

PAGING_TOKENS = {"page", "per", "limit", "offset", "count", "days"}
_INT_LITERAL = re.compile(r"^-?\d+$")


def _is_bool_literal(value: Any) -> bool:
    return isinstance(value, bool) or (
        isinstance(value, str) and value.strip().lower() in {"true", "false"}
    )


def _is_int_literal(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, str) and bool(_INT_LITERAL.match(value.strip()))


def _tokens(name: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", name.lower()) if token]


def is_id_name(name: str) -> bool:
    lowered = name.lower()
    return lowered == "id" or lowered.endswith("_id")


def is_paging_name(name: str) -> bool:
    return any(token in PAGING_TOKENS for token in _tokens(name))


def fix_schema(
    schema: Any,
    name: str = "",
    *,
    integer_names: frozenset[str] = frozenset(),
    string_id_names: frozenset[str] = frozenset(),
) -> None:
    """Fix one schema in place, recursing through properties and items."""

    if not isinstance(schema, dict):
        return

    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        if all(_is_bool_literal(value) for value in enum):
            schema["type"] = "boolean"
            schema.pop("enum", None)
        elif all(_is_int_literal(value) for value in enum):
            schema["type"] = "integer"
            schema["enum"] = [int(value) for value in enum]

    schema_type = schema.get("type")
    lowered = name.lower()
    if schema_type == "number" and name:
        if (
            (is_id_name(lowered) and lowered not in string_id_names)
            or is_paging_name(lowered)
            or lowered in integer_names
        ):
            schema["type"] = "integer"
    elif schema_type == "string" and name:
        if is_paging_name(lowered) or lowered in integer_names:
            schema["type"] = "integer"
            schema.pop("enum", None)

    properties = schema.get("properties")
    if isinstance(properties, dict):
        for child_name, child in properties.items():
            fix_schema(
                child,
                child_name,
                integer_names=integer_names,
                string_id_names=string_id_names,
            )
    if isinstance(schema.get("items"), dict):
        fix_schema(
            schema["items"],
            name,
            integer_names=integer_names,
            string_id_names=string_id_names,
        )
    for key in ("allOf", "oneOf", "anyOf"):
        for child in schema.get(key, []) or []:
            fix_schema(
                child,
                name,
                integer_names=integer_names,
                string_id_names=string_id_names,
            )
    if isinstance(schema.get("additionalProperties"), dict):
        fix_schema(
            schema["additionalProperties"],
            name,
            integer_names=integer_names,
            string_id_names=string_id_names,
        )


def _fix_parameters(
    parameters: Any,
    *,
    integer_names: frozenset[str],
    string_id_names: frozenset[str],
) -> None:
    if not isinstance(parameters, list):
        return
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        if isinstance(parameter.get("schema"), dict):
            fix_schema(
                parameter["schema"],
                str(parameter.get("name", "")),
                integer_names=integer_names,
                string_id_names=string_id_names,
            )


def fix_document(
    document: dict,
    *,
    integer_names: frozenset[str] | set[str] = frozenset(),
    string_id_names: frozenset[str] | set[str] = frozenset(),
) -> dict:
    """Apply type fixes across parameters, request bodies and components."""

    integer_names = frozenset(integer_names)
    string_id_names = frozenset(string_id_names)

    for path_item in document.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        _fix_parameters(
            path_item.get("parameters"),
            integer_names=integer_names,
            string_id_names=string_id_names,
        )
        for method, operation in path_item.items():
            if method not in ("get", "put", "post", "delete", "options", "head", "patch", "trace"):
                continue
            if not isinstance(operation, dict):
                continue
            _fix_parameters(
                operation.get("parameters"),
                integer_names=integer_names,
                string_id_names=string_id_names,
            )
            request_body = operation.get("requestBody")
            if isinstance(request_body, dict):
                for media in request_body.get("content", {}).values():
                    if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                        fix_schema(
                            media["schema"],
                            integer_names=integer_names,
                            string_id_names=string_id_names,
                        )
            responses = operation.get("responses")
            if isinstance(responses, dict):
                for response in responses.values():
                    if not isinstance(response, dict):
                        continue
                    for media in response.get("content", {}).values():
                        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                            fix_schema(
                                media["schema"],
                                integer_names=integer_names,
                                string_id_names=string_id_names,
                            )

    components = document.get("components", {})
    for schema_name, schema in components.get("schemas", {}).items():
        fix_schema(
            schema,
            schema_name,
            integer_names=integer_names,
            string_id_names=string_id_names,
        )
    for parameter_name, parameter in components.get("parameters", {}).items():
        if isinstance(parameter, dict) and isinstance(parameter.get("schema"), dict):
            fix_schema(
                parameter["schema"],
                str(parameter.get("name", parameter_name)),
                integer_names=integer_names,
                string_id_names=string_id_names,
            )

    return document
