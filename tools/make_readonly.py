#!/usr/bin/env python3
"""Generate the GET-only variant of every spec.

``openapi.readonly.json`` is always generated, never hand-edited. Use
``--check`` in CI to fail when it drifts from ``openapi.json``.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.lib import writer  # noqa: E402

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
READ_METHODS = ("get", "head", "options")


def to_readonly(document: dict) -> dict:
    """Return a copy with only GET/HEAD/OPTIONS operations."""

    readonly = copy.deepcopy(document)
    readonly["paths"] = {}
    for path, path_item in document.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        methods = {
            method: copy.deepcopy(path_item[method])
            for method in READ_METHODS
            if isinstance(path_item.get(method), dict)
        }
        if not methods:
            continue
        converted = {
            key: copy.deepcopy(value)
            for key, value in path_item.items()
            if key not in HTTP_METHODS
        }
        converted.update(methods)
        readonly["paths"][path] = converted
    return readonly


def discover(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            matches = sorted(path.glob("*/openapi.json"))
            if not matches:
                matches = sorted(path.rglob("openapi.json"))
            found.extend(matches)
        else:
            found.append(path)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="source spec files or directories (default: specs/*/openapi.json)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if an existing read-only file is missing or stale",
    )
    args = parser.parse_args()

    targets = discover(args.paths or [REPO_ROOT / "specs"])
    if not targets:
        print("no specs found", file=sys.stderr)
        return 1

    stale = False
    for source in targets:
        destination = source.with_name("openapi.readonly.json")
        document = writer.read_json(source)
        readonly = to_readonly(document)
        expected = writer.dumps(readonly)

        if args.check:
            if not destination.exists():
                print(f"missing: {destination}")
                stale = True
            elif destination.read_text(encoding="utf-8") != expected:
                print(f"stale: {destination} (run tools/make_readonly.py)")
                stale = True
            else:
                print(f"ok: {destination}")
        else:
            writer.write_json(destination, readonly)
            print(f"wrote {destination}")

    if args.check and stale:
        print("\nread-only variants are out of date", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
