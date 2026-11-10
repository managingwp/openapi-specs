"""Repair parameter names that MCP clients cannot expose as tool properties.

Claude rejects tool input property names outside ``^[a-zA-Z0-9_.-]{1,64}$``.
Vendors often use Rails-style ``q[field]`` query parameters and
``domain[address]`` form fields. Query filters become one nested ``q``
deepObject parameter; form fields become nested JSON object properties.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterator
from typing import Any

#: The property-name rule enforced by Claude and checked by the linter.
MCP_NAME = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")

_BRACKETED = re.compile(r"^([A-Za-z0-9_.-]+)\[(.+)\]$")
_LEAF_SCHEMA_KEYS = (
    "type",
    "format",
    "items",
    "enum",
    "default",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "multipleOf",
)


def _param_schema(parameter: dict) -> dict:
    schema = parameter.get("schema")
    if isinstance(schema, dict):
        return copy.deepcopy(schema)
    built = {key: copy.deepcopy(parameter[key]) for key in _LEAF_SCHEMA_KEYS if key in parameter}
    built.setdefault("type", "string")
    if built.get("type") == "array" and "items" not in built:
        built["items"] = {"type": "string"}
    return built


def _assign(
    node: dict,
    tokens: list[str],
    leaf: dict,
    *,
    description: str | None,
    required: bool,
) -> None:
    if len(tokens) == 1:
        node.setdefault("properties", {})[tokens[0]] = leaf
        if description:
            leaf["description"] = description
        if required:
            node.setdefault("required", []).append(tokens[0])
        return

    child = node.setdefault("properties", {}).setdefault(
        tokens[0], {"type": "object", "properties": {}}
    )
    child.setdefault("properties", {})
    _assign(
        child,
        tokens[1:],
        leaf,
        description=description,
        required=required,
    )


def hoist_bracketed_query_params(
    operation: dict,
    *,
    description: str | None = None,
) -> dict:
    """Collapse ``q[a]``, ``q[b]`` query parameters into one ``q`` deepObject.

    The wire format is unchanged: ``style: deepObject`` with ``explode: true``
    serializes the object back to ``q[a]=...&q[b]=...``.
    """

    parameters = operation.get("parameters")
    if not isinstance(parameters, list) or not parameters:
        return operation

    groups: dict[str, list[tuple[list[str], dict]]] = {}
    order: list[str] = []
    for parameter in parameters:
        if not isinstance(parameter, dict) or parameter.get("in") != "query":
            continue
        match = _BRACKETED.match(str(parameter.get("name", "")))
        if not match:
            continue
        prefix = match.group(1)
        tokens = [token for token in match.group(2).split("][") if token]
        if not tokens:
            continue
        if prefix not in groups:
            groups[prefix] = []
            order.append(prefix)
        groups[prefix].append((tokens, parameter))

    if not groups:
        return operation

    objects: dict[str, dict[str, Any]] = {}
    for prefix in order:
        schema: dict[str, Any] = {"type": "object", "properties": {}}
        for tokens, parameter in groups[prefix]:
            _assign(
                schema,
                tokens,
                _param_schema(parameter),
                description=parameter.get("description"),
                required=bool(parameter.get("required")),
            )
        objects[prefix] = {
            "name": prefix,
            "in": "query",
            "required": False,
            "style": "deepObject",
            "explode": True,
            "schema": schema,
            "description": description
            or (
                f"Nested `{prefix}` filter object. The bridge must support "
                f"`deepObject`; on the wire this stays `{prefix}[field]=value`."
            ),
        }

    rebuilt: list[dict] = []
    emitted: set[str] = set()
    for parameter in parameters:
        match = (
            _BRACKETED.match(str(parameter.get("name", "")))
            if isinstance(parameter, dict) and parameter.get("in") == "query"
            else None
        )
        if match:
            prefix = match.group(1)
            if prefix in objects and prefix not in emitted:
                rebuilt.append(objects[prefix])
                emitted.add(prefix)
        else:
            rebuilt.append(parameter)

    operation["parameters"] = rebuilt
    return operation


def iter_property_names(schema: Any) -> Iterator[str]:
    """Yield every property name in a schema, at any depth."""

    if not isinstance(schema, dict):
        return
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, child in properties.items():
            yield str(name)
            yield from iter_property_names(child)
    if isinstance(schema.get("items"), dict):
        yield from iter_property_names(schema["items"])
    for key in ("allOf", "oneOf", "anyOf"):
        for child in schema.get(key, []) or []:
            yield from iter_property_names(child)
    if isinstance(schema.get("additionalProperties"), dict):
        yield from iter_property_names(schema["additionalProperties"])
    if isinstance(schema.get("not"), dict):
        yield from iter_property_names(schema["not"])


def _parameter_problems(parameter: Any, label: str) -> list[str]:
    problems: list[str] = []
    if not isinstance(parameter, dict):
        return problems
    name = str(parameter.get("name", ""))
    if not MCP_NAME.match(name):
        problems.append(
            f"{label}: parameter name {name!r} does not match "
            f"^[a-zA-Z0-9_.-]{{1,64}}$"
        )
    for child in iter_property_names(parameter.get("schema")):
        if not MCP_NAME.match(child):
            problems.append(
                f"{label}: parameter {name!r} property {child!r} does not match "
                f"^[a-zA-Z0-9_.-]{{1,64}}$"
            )
    return problems


def invalid_property_names(document: dict) -> list[str]:
    """Return parameter and request-body property names that break MCP clients."""

    problems: list[str] = []
    for path, path_item in document.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for parameter in path_item.get("parameters", []) or []:
            problems.extend(_parameter_problems(parameter, f"PATH {path}"))
        for method, operation in path_item.items():
            if method not in ("get", "put", "post", "delete", "options", "head", "patch", "trace"):
                continue
            if not isinstance(operation, dict):
                continue
            for parameter in operation.get("parameters", []) or []:
                problems.extend(_parameter_problems(parameter, f"{method.upper()} {path}"))
            request_body = operation.get("requestBody")
            if isinstance(request_body, dict):
                for media in request_body.get("content", {}).values():
                    if not isinstance(media, dict):
                        continue
                    for child in iter_property_names(media.get("schema")):
                        if not MCP_NAME.match(child):
                            problems.append(
                                f"{method.upper()} {path}: request-body property {child!r} "
                                f"does not match ^[a-zA-Z0-9_.-]{{1,64}}$"
                            )
    return problems
