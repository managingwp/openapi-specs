"""Make vendor prose readable: HTML to Markdown, credential scrubbing, lists."""

from __future__ import annotations

import html
import re
from typing import Any

#: Only real HTML tags are converted, so literal values such as
#: ``<your-token>`` survive untouched.
HTML_TAG = re.compile(
    r"(?is)</?(?:p|div|span|strong|b|em|i|code|pre|ul|ol|li|h[1-6]|br|a|"
    r"blockquote|table|thead|tbody|tr|th|td|hr|img)(?:\s[^>]*)?/?>"
)

_TYPO_FIXES: tuple[tuple[str, str], ...] = (
    (r"(?i)\bsearch by search by\b", "Search by"),
    (r"(?i)\bDmarc Report\b", "DMARC Report"),
    (r"(?i)\bIn_days\b", "in days"),
)

_CREDENTIAL_PATTERNS: tuple[tuple[str, str], ...] = (
    # Authorization: Token token=<value> and Authorization: Bearer <value>
    (
        r"(?i)\b(Authorization\s*:\s*(?:Token\s+token|Bearer)\s+)"
        r"(?!<)[A-Za-z0-9._~+/-]{8,}",
        r"\1<your-token>",
    ),
    # token=<value>, token: <value>
    (r"(?i)\b(token\s*[:=]\s*)(?!<)[A-Za-z0-9._~+/-]{16,}", r"\1<your-token>"),
    # api_key=<value>
    (
        r"(?i)\b(api[_-]?key\s*[:=]\s*)(?!<)[A-Za-z0-9._~+/-]{16,}",
        r"\1<your-api-key>",
    ),
)


def strip_example_credentials(text: str) -> str:
    """Replace token-shaped examples with documented placeholders."""

    cleaned = text
    for pattern, replacement in _CREDENTIAL_PATTERNS:
        cleaned = re.sub(pattern, replacement, cleaned)
    return cleaned


def html_to_markdown(text: str) -> str:
    """Convert the simple HTML used by API documentation into Markdown."""

    value = text
    value = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", "", value)
    value = re.sub(
        r"(?is)<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a\s*>",
        r"[\2](\1)",
        value,
    )
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(
        r"(?i)<h([1-6])[^>]*>",
        lambda match: "\n\n" + "#" * int(match.group(1)) + " ",
        value,
    )
    value = re.sub(r"(?i)</h[1-6]\s*>", "\n\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n\n", value)
    value = re.sub(r"(?i)<p[^>]*>", "", value)
    value = re.sub(r"(?i)<li[^>]*>", "\n- ", value)
    value = re.sub(r"(?i)</li\s*>", "", value)
    value = re.sub(r"(?i)</?(?:ul|ol)[^>]*>", "\n", value)
    value = re.sub(r"(?i)<(?:strong|b)\s*>", "**", value)
    value = re.sub(r"(?i)</(?:strong|b)\s*>", "**", value)
    value = re.sub(r"(?i)<(?:em|i)\s*>", "*", value)
    value = re.sub(r"(?i)</(?:em|i)\s*>", "*", value)
    value = re.sub(r"(?i)<code[^>]*>", "`", value)
    value = re.sub(r"(?i)</code\s*>", "`", value)
    value = re.sub(r"(?i)</?pre[^>]*>", "\n\n", value)
    value = re.sub(r"(?i)<hr\s*/?>", "\n\n---\n\n", value)
    value = re.sub(r"(?i)<blockquote[^>]*>", "\n\n> ", value)
    value = re.sub(r"(?i)</blockquote\s*>", "\n\n", value)
    value = re.sub(r"(?i)<img[^>]*alt=[\"']([^\"']*)[\"'][^>]*>", r"![\1]()", value)
    value = re.sub(r"(?is)<(?:tr|thead|tbody)[^>]*>", "\n", value)
    value = re.sub(r"(?i)</t[hd]\s*>", " | ", value)
    value = HTML_TAG.sub("", value)
    value = html.unescape(value)
    return _normalize(value)


def resplit_flattened_lists(text: str) -> str:
    """Turn prose like ``Response includes: - `a` ... - `b` ...`` into bullets."""

    rebuilt: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("- "):
            rebuilt.append(line)
            continue

        # "The PDF includes: - Executive summary - Compliance overview" is a
        # list that lost its line breaks.
        if ": - " in line:
            header, rest = line.split(": - ", 1)
            items = [item.strip() for item in rest.split(" - ")]
            if len(items) >= 2:
                rebuilt.append(f"{header.strip()}:")
                rebuilt.extend(f"- {item}" for item in items if item)
                continue

        # Shorter lists that use inline code or "A:" style labels.
        if "`" not in line and not re.search(r"\s+-\s+[A-Z][A-Za-z0-9 _.-]{0,24}:", line):
            rebuilt.append(line)
            continue
        parts = re.split(r"\s+-\s+(?=(?:`|[A-Z][A-Za-z0-9 _.-]{0,24}:))", line)
        if len(parts) == 1:
            rebuilt.append(line)
            continue
        rebuilt.append(parts[0].rstrip())
        rebuilt.extend(f"- {part.strip()}" for part in parts[1:])
    return "\n".join(rebuilt)


def _normalize(text: str) -> str:
    text = text.replace("\u00a0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_description(text: str) -> str:
    """Apply every prose fix to one description or summary."""

    if not isinstance(text, str):
        return text
    cleaned = strip_example_credentials(text)
    if HTML_TAG.search(cleaned):
        cleaned = html_to_markdown(cleaned)
    cleaned = resplit_flattened_lists(cleaned)
    for pattern, replacement in _TYPO_FIXES:
        cleaned = re.sub(pattern, replacement, cleaned)
    return _normalize(cleaned)


def clean_document(document: Any, *, keys: tuple[str, ...] = ("description", "summary")) -> Any:
    """Walk a document and clean every description/summary string."""

    if isinstance(document, dict):
        for key, value in document.items():
            if key in keys and isinstance(value, str):
                document[key] = clean_description(value)
            else:
                clean_document(value, keys=keys)
    elif isinstance(document, list):
        for value in document:
            clean_document(value, keys=keys)
    return document
