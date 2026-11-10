#!/usr/bin/env python3
"""Lint OpenAPI specs against the constraints MCP clients impose on tools.

Fails on missing/duplicate/unsafe operationIds, invalid parameter or body
property names, missing or localhost servers, no security scheme, and
secret-shaped values. Prints operation counts and warnings per spec.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.lib import operation_ids, parameters, secrets, servers  # noqa: E402

MAX_OPERATION_ID = 64
WARN_OPERATION_ID = 40
OPERATION_ID = re.compile(r"^[a-zA-Z0-9_-]+$")
READ_METHODS = {"get", "head", "options"}


def discover(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            matches = sorted(path.glob("*/openapi*.json"))
            if not matches:
                matches = sorted(path.rglob("openapi*.json"))
            found.extend(matches)
        else:
            found.append(path)
    return found


def lint_document(document: dict) -> tuple[list[str], list[str], int, int]:
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(servers.validate_servers(document))

    schemes = document.get("components", {}).get("securitySchemes")
    if not isinstance(schemes, dict) or not schemes:
        errors.append("no security scheme in components.securitySchemes")
    if not document.get("security"):
        warnings.append("no top-level security requirement; operations default to unauthenticated")

    seen: dict[str, tuple[str, str]] = {}
    total = 0
    read = 0
    for path, method, operation in operation_ids.iter_operations(document):
        total += 1
        if method in READ_METHODS:
            read += 1

        operation_id = operation.get("operationId")
        location = f"{method.upper()} {path}"
        if not operation_id:
            errors.append(f"{location}: missing operationId")
        else:
            operation_id = str(operation_id)
            if not OPERATION_ID.match(operation_id):
                errors.append(
                    f"{location}: operationId {operation_id!r} contains characters outside "
                    "[a-zA-Z0-9_-]"
                )
            if len(operation_id) > MAX_OPERATION_ID:
                errors.append(
                    f"{location}: operationId {operation_id!r} is {len(operation_id)} "
                    f"characters (max {MAX_OPERATION_ID})"
                )
            elif len(operation_id) > WARN_OPERATION_ID:
                warnings.append(
                    f"{location}: operationId {operation_id!r} is {len(operation_id)} "
                    f"characters (recommended max {WARN_OPERATION_ID})"
                )
            if operation_id in seen:
                first_path, first_method = seen[operation_id]
                errors.append(
                    f"{location}: duplicate operationId {operation_id!r} "
                    f"(also used by {first_method.upper()} {first_path})"
                )
            else:
                seen[operation_id] = (path, method)

    errors.extend(parameters.invalid_property_names(document))

    for problem in secrets.find_secrets(document):
        errors.append(
            f"{problem['path']}: looks like {problem['kind']} ({problem['preview']})"
        )

    return errors, warnings, total, total - read


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="spec files or directories (default: specs/)",
    )
    args = parser.parse_args()

    targets = discover(args.paths or [REPO_ROOT / "specs"])
    if not targets:
        print("no specs found", file=sys.stderr)
        return 1

    failed = False
    for target in targets:
        print(target.relative_to(REPO_ROOT) if target.is_relative_to(REPO_ROOT) else target)
        try:
            with target.open(encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            print(f"  error: {error}")
            failed = True
            continue

        errors, warnings, total, writes = lint_document(document)
        print(f"  operations: {total} ({total - writes} read, {writes} write)")

        for warning in warnings:
            print(f"  warning: {warning}")
        for error in errors:
            print(f"  error: {error}")

        if errors:
            failed = True
        else:
            print("  OK")

    if failed:
        print("\nMCP lint failed", file=sys.stderr)
        return 1
    print("\nMCP lint passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
