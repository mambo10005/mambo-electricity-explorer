"""Credential redaction for anything that may be logged, raised, displayed, or archived."""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import quote, quote_plus

MARK = "[REDACTED]"
_QUERY = re.compile(r"(?i)(api_key=)[^&\s\"'<>]+")
_JSON = re.compile(r'(?i)("api_key"\s*:\s*)("(?:[^"\\]|\\.)*"|[^,}\s]+)')


def redact(text: str, secrets: Iterable[str | None] = ()) -> str:
    for secret in secrets:
        if not secret:
            continue
        for form in sorted({secret, quote(secret, safe=""), quote_plus(secret)}, key=len)[::-1]:
            text = text.replace(form, MARK)
    text = _QUERY.sub(rf"\1{MARK}", text)
    return _JSON.sub(rf'\1"{MARK}"', text)


def redact_bytes(body: bytes, secrets: Iterable[str | None] = ()) -> tuple[bytes, bool]:
    """Return (sanitized bytes, whether anything changed).

    Non-UTF-8 bodies are rejected rather than stored unchecked.
    """
    text = body.decode("utf-8")
    cleaned = redact(text, secrets)
    return cleaned.encode("utf-8"), cleaned != text
