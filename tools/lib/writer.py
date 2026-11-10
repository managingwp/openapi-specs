"""Deterministic JSON output for generated specs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .secrets import assert_clean


def read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def dumps(document: Any) -> str:
    """Pretty-print with two spaces and a trailing newline."""

    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def write_json(path: str | Path, document: Any, *, scrub: bool = True) -> Path:
    """Write ``document`` as pretty JSON, refusing secret-shaped values."""

    destination = Path(path)
    if scrub:
        assert_clean(document, source=str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(dumps(document), encoding="utf-8")
    return destination
