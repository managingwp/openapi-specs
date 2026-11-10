"""Build an MCPHub ``mcp_settings.json`` fragment for an OpenAPI spec."""

from __future__ import annotations

from typing import Any


def api_key_server(
    server_name: str,
    spec_url: str,
    *,
    header: str = "Authorization",
    value: str,
    version: str = "3.0.3",
) -> dict[str, Any]:
    """Return an MCPHub config with an ``apiKey`` security placeholder."""

    if not value or "YOUR_" not in value:
        raise ValueError("MCPHub token values must use an obvious YOUR_... placeholder")

    return {
        "mcpServers": {
            server_name: {
                "type": "openapi",
                "openapi": {
                    "url": spec_url,
                    "version": version,
                    "security": {
                        "type": "apiKey",
                        "apiKey": {
                            "name": header,
                            "in": "header",
                            "value": value,
                        },
                    },
                },
                "enabled": True,
            }
        }
    }
