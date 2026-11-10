"""Swagger 2.0 to OpenAPI 3.0.3 conversion.

Covers the parts vendors actually use: host/basePath servers (including the
broken ``basePath``-is-a-URL case), formData bodies, consumes/produces media
types, array parameters wrapped in ``schema`` and security definitions.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .servers import is_local_url, set_servers

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

_PARAM_SCHEMA_KEYS = (
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

_BRACKETED = re.compile(r"^([^\[]+)\[(.+)\]$")


def _derive_server(swagger: dict) -> str | None:
    base_path = str(swagger.get("basePath") or "").strip()
    if base_path.startswith(("http://", "https://")):
        # Apipie's broken output: basePath holds the real URL while host is
        # localhost:3000.
        return base_path.rstrip("/")

    host = str(swagger.get("host") or "").strip()
    if not host:
        return None
    if is_local_url(host if "://" in host else f"http://{host}"):
        return None

    schemes = swagger.get("schemes") or ["https"]
    scheme = str(schemes[0]).lower()
    path = base_path if not base_path or base_path.startswith("/") else f"/{base_path}"
    return f"{scheme}://{host}{path}".rstrip("/")


def _rewrite_ref(value: str) -> str:
    return value.replace("#/definitions/", "#/components/schemas/").replace(
        "#/parameters/", "#/components/parameters/"
    ).replace("#/responses/", "#/components/responses/")


def _convert_schema(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return copy.deepcopy(schema)

    converted = copy.deepcopy(schema)

    if "$ref" in converted:
        converted["$ref"] = _rewrite_ref(str(converted["$ref"]))

    if converted.get("type") == "file":
        converted["type"] = "string"
        converted["format"] = "binary"

    if isinstance(converted.get("discriminator"), str):
        converted["discriminator"] = {"propertyName": converted["discriminator"]}

    if converted.pop("x-nullable", False):
        converted["nullable"] = True

    properties = converted.get("properties")
    if isinstance(properties, dict):
        converted["properties"] = {
            name: _convert_schema(child) for name, child in properties.items()
        }

    if isinstance(converted.get("items"), dict):
        converted["items"] = _convert_schema(converted["items"])

    for key in ("allOf", "oneOf", "anyOf"):
        if isinstance(converted.get(key), list):
            converted[key] = [_convert_schema(child) for child in converted[key]]

    if isinstance(converted.get("additionalProperties"), dict):
        converted["additionalProperties"] = _convert_schema(
            converted["additionalProperties"]
        )

    if isinstance(converted.get("not"), dict):
        converted["not"] = _convert_schema(converted["not"])

    return converted


def _schema_from_parameter(parameter: dict) -> dict:
    schema = {
        key: copy.deepcopy(parameter[key])
        for key in _PARAM_SCHEMA_KEYS
        if key in parameter
    }
    schema.setdefault("type", "string")
    if schema["type"] == "file":
        return {"type": "string", "format": "binary"}
    if schema["type"] == "array":
        items = parameter.get("items")
        schema["items"] = _convert_schema(items) if items else {"type": "string"}
    return schema


def _convert_parameter(parameter: dict) -> dict:
    converted: dict[str, Any] = {}
    for key in ("name", "in", "description", "required", "allowEmptyValue", "deprecated"):
        if key in parameter:
            converted[key] = copy.deepcopy(parameter[key])

    converted["schema"] = _schema_from_parameter(parameter)

    if parameter.get("in") == "query" and parameter.get("type") == "array":
        collection_format = parameter.get("collectionFormat", "csv")
        style, explode = {
            "csv": ("form", False),
            "multi": ("form", True),
            "ssv": ("spaceDelimited", False),
            "pipes": ("pipeDelimited", False),
        }.get(collection_format, ("form", False))
        converted["style"] = style
        converted["explode"] = explode

    return converted


def _name_tokens(name: str) -> list[str]:
    match = _BRACKETED.match(name)
    if not match:
        return [name]
    return [match.group(1), *[token for token in match.group(2).split("][") if token]]


def _assign_form(
    node: dict,
    tokens: list[str],
    leaf: dict,
    *,
    required: bool,
) -> None:
    if len(tokens) == 1:
        node.setdefault("properties", {})[tokens[0]] = leaf
        if required:
            node.setdefault("required", []).append(tokens[0])
        return
    child = node.setdefault("properties", {}).setdefault(
        tokens[0], {"type": "object", "properties": {}}
    )
    child.setdefault("properties", {})
    _assign_form(child, tokens[1:], leaf, required=required)


def _form_schema(parameters: list[dict]) -> dict:
    root: dict[str, Any] = {"type": "object", "properties": {}}
    for parameter in parameters:
        leaf = _schema_from_parameter(parameter)
        if parameter.get("description"):
            leaf["description"] = parameter["description"]
        _assign_form(
            root,
            _name_tokens(str(parameter.get("name", ""))),
            leaf,
            required=bool(parameter.get("required")),
        )
    return root


def _convert_response(response: dict, produces: list[str]) -> dict:
    if not isinstance(response, dict):
        return {"description": ""}
    if "$ref" in response:
        return {"$ref": _rewrite_ref(str(response["$ref"]))}

    converted: dict[str, Any] = {"description": response.get("description", "")}

    headers = response.get("headers")
    if isinstance(headers, dict) and headers:
        converted["headers"] = {
            name: {
                **(
                    {"description": header["description"]}
                    if isinstance(header, dict) and header.get("description")
                    else {}
                ),
                "schema": _schema_from_parameter(header or {}),
            }
            for name, header in headers.items()
        }

    schema = response.get("schema")
    if isinstance(schema, dict):
        media_type = produces[0] if produces else "application/json"
        converted["content"] = {media_type: {"schema": _convert_schema(schema)}}

    return converted


def _convert_operation(
    operation: dict,
    swagger: dict,
    *,
    form_media_type: str,
) -> dict:
    converted: dict[str, Any] = {}
    for key in ("tags", "summary", "description", "externalDocs", "deprecated", "security"):
        if key in operation:
            converted[key] = copy.deepcopy(operation[key])
    if "operationId" in operation:
        converted["operationId"] = operation["operationId"]
    for key, value in operation.items():
        if key.startswith("x-"):
            converted[key] = copy.deepcopy(value)

    parameters: list[dict] = []
    form_parameters: list[dict] = []
    body_parameter: dict | None = None
    for parameter in operation.get("parameters", []) or []:
        if not isinstance(parameter, dict):
            continue
        location = parameter.get("in")
        if location == "formData":
            form_parameters.append(parameter)
        elif location == "body":
            body_parameter = parameter
        else:
            parameters.append(_convert_parameter(parameter))
    if parameters:
        converted["parameters"] = parameters

    consumes = operation.get("consumes") or swagger.get("consumes") or []
    produces = operation.get("produces") or swagger.get("produces") or []

    if body_parameter is not None:
        media_type = consumes[0] if consumes else "application/json"
        request_body: dict[str, Any] = {
            "required": bool(body_parameter.get("required")),
            "content": {
                media_type: {
                    "schema": _convert_schema(body_parameter.get("schema") or {})
                }
            },
        }
        if body_parameter.get("description"):
            request_body["description"] = body_parameter["description"]
        converted["requestBody"] = request_body
    elif form_parameters:
        has_file = any(parameter.get("type") == "file" for parameter in form_parameters)
        media_type = "multipart/form-data" if has_file else form_media_type
        converted["requestBody"] = {
            "required": any(bool(parameter.get("required")) for parameter in form_parameters),
            "content": {media_type: {"schema": _form_schema(form_parameters)}},
        }

    responses = {
        str(code): _convert_response(response, produces)
        for code, response in (operation.get("responses") or {}).items()
    }
    if responses:
        converted["responses"] = responses

    return converted


def _convert_security_definitions(swagger: dict) -> dict:
    schemes: dict[str, Any] = {}
    for name, definition in (swagger.get("securityDefinitions") or {}).items():
        if not isinstance(definition, dict):
            continue
        kind = definition.get("type")
        entry: dict[str, Any] = {}
        if definition.get("description"):
            entry["description"] = definition["description"]

        if kind == "apiKey":
            entry.update(
                {
                    "type": "apiKey",
                    "name": definition.get("name"),
                    "in": definition.get("in"),
                }
            )
        elif kind == "basic":
            entry.update({"type": "http", "scheme": "basic"})
        elif kind == "oauth2":
            entry["type"] = "oauth2"
            flow = definition.get("flow")
            scopes = copy.deepcopy(definition.get("scopes") or {})
            if flow == "implicit":
                entry["flows"] = {
                    "implicit": {
                        "authorizationUrl": definition.get("authorizationUrl"),
                        "scopes": scopes,
                    }
                }
            elif flow == "password":
                entry["flows"] = {
                    "password": {
                        "tokenUrl": definition.get("tokenUrl"),
                        "scopes": scopes,
                    }
                }
            elif flow == "application":
                entry["flows"] = {
                    "clientCredentials": {
                        "tokenUrl": definition.get("tokenUrl"),
                        "scopes": scopes,
                    }
                }
            elif flow == "accessCode":
                entry["flows"] = {
                    "authorizationCode": {
                        "authorizationUrl": definition.get("authorizationUrl"),
                        "tokenUrl": definition.get("tokenUrl"),
                        "scopes": scopes,
                    }
                }
        else:
            continue
        schemes[name] = entry
    return schemes


def convert(
    swagger: dict,
    *,
    server_url: str | None = None,
    server_description: str | None = None,
    form_media_type: str = "application/json",
) -> dict:
    """Convert a Swagger 2.0 document to OpenAPI 3.0.3."""

    if str(swagger.get("swagger")) != "2.0":
        raise ValueError("expected a Swagger 2.0 document")

    source_info = swagger.get("info") or {}
    info: dict[str, Any] = {
        key: copy.deepcopy(source_info[key])
        for key in ("title", "version", "description", "termsOfService")
        if key in source_info
    }
    info.setdefault("title", "Untitled API")
    info.setdefault("version", "1.0")
    for key in ("contact", "license"):
        if key in source_info:
            info[key] = copy.deepcopy(source_info[key])
    for key, value in source_info.items():
        if key.startswith("x-") and value is not None:
            info[key] = copy.deepcopy(value)

    document: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": info,
        "paths": {},
    }

    chosen_server = server_url or _derive_server(swagger)
    if not chosen_server or is_local_url(chosen_server):
        raise ValueError(
            "the source has no usable production server; pass server_url explicitly"
        )
    set_servers(document, chosen_server, description=server_description)

    if isinstance(swagger.get("tags"), list):
        document["tags"] = copy.deepcopy(swagger["tags"])
    if isinstance(swagger.get("externalDocs"), dict):
        document["externalDocs"] = copy.deepcopy(swagger["externalDocs"])
    for key, value in swagger.items():
        if key.startswith("x-"):
            document[key] = copy.deepcopy(value)
    if isinstance(swagger.get("security"), list):
        document["security"] = copy.deepcopy(swagger["security"])

    for path, path_item in (swagger.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        converted_path: dict[str, Any] = {}
        for key, value in path_item.items():
            if key in HTTP_METHODS and isinstance(value, dict):
                converted_path[key] = _convert_operation(
                    value, swagger, form_media_type=form_media_type
                )
            elif key == "parameters":
                shared = [
                    _convert_parameter(parameter)
                    for parameter in value
                    if isinstance(parameter, dict)
                    and parameter.get("in") not in ("body", "formData")
                ]
                if shared:
                    converted_path["parameters"] = shared
            elif key == "$ref" or key.startswith("x-"):
                converted_path[key] = copy.deepcopy(value)
        if converted_path:
            document["paths"][path] = converted_path

    components: dict[str, Any] = {}
    if isinstance(swagger.get("definitions"), dict):
        components["schemas"] = {
            name: _convert_schema(schema)
            for name, schema in swagger["definitions"].items()
        }

    converted_parameters = {}
    for name, parameter in (swagger.get("parameters") or {}).items():
        if not isinstance(parameter, dict):
            continue
        if parameter.get("in") in ("body", "formData"):
            continue
        converted_parameters[name] = _convert_parameter(parameter)
    if converted_parameters:
        components["parameters"] = converted_parameters

    global_produces = swagger.get("produces") or []
    converted_responses = {}
    for name, response in (swagger.get("responses") or {}).items():
        converted_responses[name] = _convert_response(response, global_produces)
    if converted_responses:
        components["responses"] = converted_responses

    security_schemes = _convert_security_definitions(swagger)
    if security_schemes:
        components["securitySchemes"] = security_schemes

    components = {key: value for key, value in components.items() if value}
    if components:
        document["components"] = components

    return document
