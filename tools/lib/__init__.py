"""Shared fix-ups used by every per-API converter.

The modules are deliberately small and composable:

- ``swagger2``      Swagger 2.0 -> OpenAPI 3.0.3, including form bodies.
- ``servers``       explicit production servers, never localhost.
- ``auth``          security scheme injection.
- ``operation_ids`` short, unique snake_case tool names.
- ``parameters``    bracketed names -> deepObject / nested objects, plus checks.
- ``types``         boolean, integer and ID corrections.
- ``descriptions``  HTML -> Markdown, credential scrubbing, list repair.
- ``responses``     generic success responses and a shared error response.
- ``secrets``       refusal to publish token-shaped values.
- ``writer``        deterministic JSON output with a secret check.
- ``mcphub``        MCPHub server configuration builder.
"""

from . import (  # noqa: F401
    auth,
    descriptions,
    mcphub,
    operation_ids,
    parameters,
    responses,
    secrets,
    servers,
    swagger2,
    types,
    writer,
)

__all__ = [
    "auth",
    "descriptions",
    "mcphub",
    "operation_ids",
    "parameters",
    "responses",
    "secrets",
    "servers",
    "swagger2",
    "types",
    "writer",
]
