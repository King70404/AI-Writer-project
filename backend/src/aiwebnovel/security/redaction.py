"""Central immutable redaction helpers for structured diagnostics and log text."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

REDACTED: Final = "[REDACTED]"
UNSERIALIZABLE: Final = "[UNSERIALIZABLE]"
CYCLE: Final = "[CYCLE]"

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "set_cookie",
        "x_csrf_token",
        "aiwebnovel_session",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "api_key",
    }
)
_SENSITIVE_HEADER_TEXT = re.compile(
    r"(?i)(?P<quote>[\"']?)(?P<key>authorization|set-cookie|cookie|x-csrf-token)(?P=quote)"
    r"(?P<separator>\s*[=:]\s*)"
    r"(?P<value>[^\r\n]*)"
)
_SENSITIVE_VALUE_TEXT = re.compile(
    r"(?i)(?P<quote>[\"']?)(?P<key>aiwebnovel_session|access_token|refresh_token|password|secret|api_key)(?P=quote)"
    r"(?P<separator>\s*[=:]\s*)"
    r"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;}\r\n]+)"
)


def _normalized_key(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def is_sensitive_key(value: object) -> bool:
    """Return whether a mapping/header field name is sensitive."""
    return isinstance(value, str) and _normalized_key(value) in _SENSITIVE_KEYS


def redact_text(value: str) -> str:
    """Replace recognizable key/value secrets without preserving any token fragment."""
    headers_redacted = _SENSITIVE_HEADER_TEXT.sub(
        lambda match: (
            f"{match.group('quote')}{match.group('key')}{match.group('quote')}"
            f"{match.group('separator')}{REDACTED}"
        ),
        value,
    )
    return _SENSITIVE_VALUE_TEXT.sub(
        lambda match: (
            f"{match.group('quote')}{match.group('key')}{match.group('quote')}"
            f"{match.group('separator')}{REDACTED}"
        ),
        headers_redacted,
    )


def redact(value: object, *, max_depth: int = 12) -> object:
    """Return a JSON-safe redacted copy without mutating or stringifying unknown objects."""
    if max_depth < 1:
        raise ValueError("max_depth must be positive")
    return _redact(value, depth=0, max_depth=max_depth, active=set())


def _redact(value: object, *, depth: int, max_depth: int, active: set[int]) -> object:
    if depth >= max_depth:
        return UNSERIALIZABLE
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else UNSERIALIZABLE
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, bytes):
        return UNSERIALIZABLE

    identity = id(value)
    if identity in active:
        return CYCLE
    if isinstance(value, Mapping):
        active.add(identity)
        try:
            result: dict[str, object] = {}
            for key, item in value.items():
                safe_key = key if isinstance(key, str) else f"<{type(key).__name__}>"
                result[safe_key] = (
                    REDACTED
                    if is_sensitive_key(key)
                    else _redact(item, depth=depth + 1, max_depth=max_depth, active=active)
                )
            return result
        except Exception:  # noqa: BLE001 - diagnostic objects are untrusted.
            return UNSERIALIZABLE
        finally:
            active.discard(identity)
    if isinstance(value, Sequence):
        active.add(identity)
        try:
            return [
                _redact(item, depth=depth + 1, max_depth=max_depth, active=active) for item in value
            ]
        except Exception:  # noqa: BLE001 - diagnostic objects are untrusted.
            return UNSERIALIZABLE
        finally:
            active.discard(identity)
    return UNSERIALIZABLE


def safe_request_path(path: str) -> str:
    """Keep only a bounded printable URL path; never retain query or fragment data."""
    candidate = path.split("?", 1)[0].split("#", 1)[0]
    if (
        not candidate.startswith("/")
        or len(candidate) > 2048
        or any(ord(character) < 32 for character in candidate)
    ):
        return "/"
    return candidate


def safe_exception_details(exc: BaseException) -> dict[str, Any]:
    """Expose only an exception type, never arbitrary exception text or arguments."""
    return {"error_type": type(exc).__name__}
