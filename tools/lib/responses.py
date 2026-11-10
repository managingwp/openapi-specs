"""Add the success and error responses that vendor specs usually omit."""

from __future__ import annotations

from typing import Any

from .operation_ids import iter_operations

ERROR_RESPONSE_NAME = "Error"
ERROR_DESCRIPTION = (
    "Error (400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, "
    "422 Unprocessable Entity, 500 Server Error)"
)


def ensure_error_response(document: dict) -> dict:
    """Create the shared ``components.responses.Error`` entry."""

    components = document.setdefault("components", {})
    responses = components.setdefault("responses", {})
    responses[ERROR_RESPONSE_NAME] = {
        "description": ERROR_DESCRIPTION,
        "content": {
            "application/json": {
                "schema": {"type": "object", "additionalProperties": True}
            }
        },
    }
    return document


def _is_error_code(code: str) -> bool:
    return code == "default" or code[:1] in {"4", "5"}


def ensure_success_responses(
    document: dict,
    *,
    description: str = "Successful response",
    overrides: dict[str, dict[str, Any]] | None = None,
) -> dict:
    """Ensure every operation has a 2xx response and reference the shared error.

    ``overrides`` is keyed by the final operationId. Each value may set
    ``description``, ``media_type`` and ``schema`` for the generated ``200``.
    """

    ensure_error_response(document)
    overrides = overrides or {}

    for _path, _method, operation in iter_operations(document):
        responses = operation.setdefault("responses", {})
        if not isinstance(responses, dict):
            responses = {}
            operation["responses"] = responses

        success_codes = [code for code in responses if str(code).startswith("2")]
        if not success_codes:
            override = overrides.get(str(operation.get("operationId", "")), {})
            media_type = override.get("media_type", "application/json")
            schema = override.get(
                "schema", {"type": "object", "additionalProperties": True}
            )
            responses["200"] = {
                "description": override.get("description", description),
                "content": {media_type: {"schema": schema}},
            }

        for code in list(responses):
            if _is_error_code(str(code)) and "$ref" not in responses[code]:
                responses[code] = {"$ref": f"#/components/responses/{ERROR_RESPONSE_NAME}"}

    return document
