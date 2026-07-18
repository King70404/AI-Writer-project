"""Consistent path and secret redaction for text and JSON diagnostics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|set-cookie|cookie|x[-_]?csrf[-_]?token|csrf(?:[-_]?token)?|"
    r"password|passwd|pwd|secret|client[_-]?secret|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|id[_-]?token|token)\b\s*[:=]\s*[^\r\n]*"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN(?:\s+[A-Z0-9]+)?\s+PRIVATE\s+KEY-----.*?"
    r"(?:-----END(?:\s+[A-Z0-9]+)?\s+PRIVATE\s+KEY-----|\Z)",
    re.DOTALL,
)
_TOKEN = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{12,}|"
    r"AKIA[0-9A-Z]{16})\b"
)
_LOCAL_PATH = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(?:[A-Z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+)"
    r"[^\r\n\"'<>|,;)]*"
)


@dataclass(frozen=True, slots=True)
class _Replacement:
    value: str
    placeholder: str


class DiagnosticRedactor:
    """Redact known local paths and credentials without exposing raw values."""

    def __init__(
        self,
        *,
        repository_root: Path,
        virtual_environment: Path,
        user_home: Path | None = None,
        username: str | None = None,
        local_app_data: Path | None = None,
        temporary_data_root: Path | None = None,
        sensitive_values: tuple[str, ...] = (),
    ) -> None:
        candidates = (
            (temporary_data_root, "<temp-data-root>"),
            (virtual_environment, "<venv>"),
            (repository_root, "<repo>"),
            (local_app_data, "<localappdata>"),
            (user_home, "<user-home>"),
        )
        replacements: list[_Replacement] = []
        for path, placeholder in candidates:
            if path is None:
                continue
            raw = str(path)
            if raw:
                replacements.append(_Replacement(raw, placeholder))
                alternate = raw.replace("\\", "/")
                if alternate != raw:
                    replacements.append(_Replacement(alternate, placeholder))
        replacements.sort(key=lambda item: len(item.value), reverse=True)
        self._path_replacements = tuple(replacements)
        self._username = username.strip() if username and username.strip() else None
        self._sensitive_values = tuple(
            sorted(
                {value for value in sensitive_values if value},
                key=len,
                reverse=True,
            )
        )

    @staticmethod
    def _replace_case_insensitive(text: str, value: str, replacement: str) -> str:
        return re.sub(re.escape(value), lambda _match: replacement, text, flags=re.IGNORECASE)

    def redact_text(self, value: object) -> str:
        """Return one safe printable value."""
        safe = str(value)
        for replacement in self._path_replacements:
            safe = self._replace_case_insensitive(
                safe,
                replacement.value,
                replacement.placeholder,
            )
        if self._username is not None:
            safe = self._replace_case_insensitive(safe, self._username, "<user>")
        for sensitive_value in self._sensitive_values:
            safe = safe.replace(sensitive_value, "<redacted>")
        safe = _PRIVATE_KEY.sub("<redacted-private-key>", safe)
        safe = _ASSIGNMENT.sub(lambda match: f"{match.group(1)}=<redacted>", safe)
        safe = _BEARER.sub("Bearer <redacted>", safe)
        safe = _TOKEN.sub("<redacted-token>", safe)
        return _LOCAL_PATH.sub("<local-path>", safe)
