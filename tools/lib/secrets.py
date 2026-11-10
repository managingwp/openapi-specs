"""Detect values that look like real credentials before a spec is published.

The check is intentionally conservative: a false positive is cheap (rename the
example), while a leaked token in a public repository is not. Placeholders and
documentation example domains are allowed.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

#: Documentation-only domains that are safe to publish.
EXAMPLE_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "example.test",
    "example.invalid",
    "yourdomain.com",
    "your-domain.com",
    "domain.example",
}

#: Words that mark a nearby value as a placeholder rather than a secret.
PLACEHOLDER_MARKERS = (
    "your",
    "example",
    "placeholder",
    "changeme",
    "redacted",
    "xxx",
    "<",
    ">",
)

_HEX_TOKEN = re.compile(r"\b[0-9a-fA-F]{40,}\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "GitHub token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Stripe key", re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
)


class SecretError(ValueError):
    """Raised when a document contains a value that looks like a real secret."""

    def __init__(self, problems: list[dict[str, str]], source: str = "document") -> None:
        self.problems = problems
        self.source = source
        lines = [f"{source} contains {len(problems)} value(s) that look like secrets:"]
        for problem in problems:
            lines.append(
                f"  - {problem['path']}: {problem['kind']} ({problem['preview']})"
            )
        lines.append("Replace them with documented placeholders before publishing.")
        super().__init__("\n".join(lines))


def _iter_strings(value: Any, path: str = "$") -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _iter_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_strings(child, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def _has_placeholder_near(text: str, start: int, end: int, window: int = 40) -> bool:
    context = text[max(0, start - window) : min(len(text), end + window)].lower()
    return any(marker in context for marker in PLACEHOLDER_MARKERS)


def _mask(kind: str, value: str, match: re.Match[str]) -> str:
    if kind == "email address":
        local, _, domain = value.partition("@")
        return f"{local[:1]}***@{domain}"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-2:]}"


def find_secrets(document: Any) -> list[dict[str, str]]:
    """Return every value in ``document`` that resembles a real secret."""

    problems: list[dict[str, str]] = []

    for path, text in _iter_strings(document):
        for kind, pattern in _SECRET_PATTERNS:
            for match in pattern.finditer(text):
                if _has_placeholder_near(text, match.start(), match.end()):
                    continue
                problems.append(
                    {
                        "path": path,
                        "kind": kind,
                        "preview": _mask(kind, match.group(0), match),
                    }
                )

        for match in _HEX_TOKEN.finditer(text):
            if _has_placeholder_near(text, match.start(), match.end()):
                continue
            problems.append(
                {
                    "path": path,
                    "kind": "long hexadecimal token",
                    "preview": _mask("long hexadecimal token", match.group(0), match),
                }
            )

        for match in _EMAIL.finditer(text):
            domain = match.group(1).lower()
            if domain in EXAMPLE_EMAIL_DOMAINS:
                continue
            value = match.group(0)
            if _has_placeholder_near(text, match.start(), match.end()):
                continue
            problems.append(
                {
                    "path": path,
                    "kind": "email address",
                    "preview": _mask("email address", value, match),
                }
            )

    return problems


def assert_clean(document: Any, source: str = "document") -> None:
    """Raise :class:`SecretError` when ``document`` looks like it leaks secrets."""

    problems = find_secrets(document)
    if problems:
        raise SecretError(problems, source=source)
