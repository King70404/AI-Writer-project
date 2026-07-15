"""Same-origin and double-secret CSRF enforcement for unsafe local API calls."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

from aiwebnovel.security.host import HostConfigurationError, host_from_scope
from aiwebnovel.security.responses import send_security_error
from aiwebnovel.security.sessions import (
    InMemorySessionManager,
    SessionStatus,
    validate_cookie_name,
)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_HTTP_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


class CSRFConfigurationError(ValueError):
    """Raised when an Origin, cookie, or header boundary is ambiguous."""


def validate_csrf_header_name(value: str) -> str:
    """Require a syntactically safe HTTP field name."""
    if not isinstance(value, str) or _HTTP_TOKEN.fullmatch(value) is None:
        raise CSRFConfigurationError("CSRF header name must be a safe HTTP token")
    return value


def _normalize_origin(value: str) -> tuple[str, str, int]:
    if not value or value == "null" or value != value.strip():
        raise CSRFConfigurationError("Origin must be an explicit HTTP origin")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise CSRFConfigurationError("Origin has an invalid port") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise CSRFConfigurationError("Origin must contain only scheme, host, and optional port")
    try:
        host = ipaddress.ip_address(parsed.hostname).compressed.lower()
    except ValueError:
        host = parsed.hostname.lower()
    effective_port = port if port is not None else (443 if parsed.scheme == "https" else 80)
    return parsed.scheme, host, effective_port


def normalize_allowed_origins(values: Iterable[str]) -> frozenset[tuple[str, str, int]]:
    """Normalize explicit non-wildcard development origins."""
    if isinstance(values, str):
        raise CSRFConfigurationError("allowed origins must be a collection")
    origins: set[tuple[str, str, int]] = set()
    for value in values:
        if not isinstance(value, str) or "*" in value:
            raise CSRFConfigurationError("allowed origins must be explicit")
        normalized = _normalize_origin(value)
        if normalized in origins:
            raise CSRFConfigurationError("allowed origins must be unique")
        origins.add(normalized)
    return frozenset(origins)


def _header(scope: Scope, name: bytes) -> bytes | None:
    values = [value for key, value in scope.get("headers", ()) if key.lower() == name]
    return values[0] if len(values) == 1 else None


def _has_header(scope: Scope, name: bytes) -> bool:
    return any(key.lower() == name for key, _ in scope.get("headers", ()))


def _origin_for_scope(scope: Scope) -> tuple[str, str, int] | None:
    values = [value for key, value in scope.get("headers", ()) if key.lower() == b"origin"]
    if not values:
        return None
    if len(values) != 1:
        raise CSRFConfigurationError("request must contain at most one Origin header")
    raw = values[0]
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CSRFConfigurationError("Origin must be ASCII") from exc
    return _normalize_origin(value)


def _request_origin(scope: Scope) -> tuple[str, str, int]:
    parsed_host = host_from_scope(scope)
    scheme = str(scope.get("scheme", "http")).lower()
    if scheme not in {"http", "https"}:
        raise CSRFConfigurationError("request scheme is not supported")
    port = parsed_host.port if parsed_host.port is not None else (443 if scheme == "https" else 80)
    return scheme, parsed_host.host, port


def _cookie_value(scope: Scope, cookie_name: str) -> str | None:
    raw_headers = [value for key, value in scope.get("headers", ()) if key.lower() == b"cookie"]
    if not raw_headers:
        return None
    try:
        combined = b"; ".join(raw_headers).decode("latin-1")
        cookie_name_count = sum(
            1 for segment in combined.split(";") if segment.partition("=")[0].strip() == cookie_name
        )
        if cookie_name_count != 1:
            return None
        parsed = SimpleCookie()
        parsed.load(combined)
    except (CookieError, UnicodeError):
        return None
    morsel = parsed.get(cookie_name)
    return morsel.value if morsel is not None else None


class CSRFMiddleware:
    """Require an allowed Origin and matching process-local session for unsafe APIs."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        session_manager: InMemorySessionManager,
        allowed_origins: Iterable[str],
        cookie_name: str = "aiwebnovel_session",
        csrf_header_name: str = "X-CSRF-Token",
        api_prefix: str = "/api",
        session_path: str = "/api/v1/security/session",
    ) -> None:
        self.app = app
        self.session_manager = session_manager
        self.allowed_origins = normalize_allowed_origins(allowed_origins)
        self.cookie_name = validate_cookie_name(cookie_name)
        self.csrf_header_name = validate_csrf_header_name(csrf_header_name).lower().encode("ascii")
        self.api_prefix = api_prefix
        self.session_path = session_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET")).upper()
        if not (path == self.api_prefix or path.startswith(f"{self.api_prefix}/")):
            await self.app(scope, receive, send)
            return
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        if method in SAFE_METHODS:
            if path != self.session_path or not _has_header(scope, b"origin"):
                await self.app(scope, receive, send)
                return
            if not self._origin_is_allowed(scope):
                await self._reject_origin(scope, send)
                return
            await self.app(scope, receive, send)
            return
        if method not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return
        if not self._origin_is_allowed(scope):
            await self._reject_origin(scope, send)
            return

        session_id = _cookie_value(scope, self.cookie_name)
        session_status = self.session_manager.status(session_id)
        if session_status is SessionStatus.MISSING:
            await self._reject(
                scope, send, "SESSION_REQUIRED", "A valid local session is required."
            )
            return
        if session_status is SessionStatus.EXPIRED:
            await self._reject(scope, send, "SESSION_EXPIRED", "The local session has expired.")
            return

        raw_csrf = _header(scope, self.csrf_header_name)
        if raw_csrf is None:
            await self._reject(scope, send, "CSRF_TOKEN_REQUIRED", "A CSRF token is required.")
            return
        try:
            csrf_token = raw_csrf.decode("ascii")
        except UnicodeDecodeError:
            csrf_token = ""
        validation = self.session_manager.validate_csrf(session_id, csrf_token)
        if validation is SessionStatus.EXPIRED:
            await self._reject(scope, send, "SESSION_EXPIRED", "The local session has expired.")
            return
        if validation is not SessionStatus.ACTIVE:
            await self._reject(scope, send, "CSRF_TOKEN_INVALID", "The CSRF token is invalid.")
            return
        await self.app(scope, receive, send)

    def _origin_is_allowed(self, scope: Scope) -> bool:
        try:
            supplied_origin = _origin_for_scope(scope)
            current_origin = _request_origin(scope)
        except (CSRFConfigurationError, HostConfigurationError):
            return False
        return supplied_origin is not None and (
            supplied_origin == current_origin or supplied_origin in self.allowed_origins
        )

    @staticmethod
    async def _reject_origin(scope: Scope, send: Send) -> None:
        await CSRFMiddleware._reject(
            scope,
            send,
            "ORIGIN_NOT_ALLOWED",
            "The request Origin is not allowed.",
        )

    @staticmethod
    async def _reject(scope: Scope, send: Send, code: str, message: str) -> None:
        await send_security_error(
            scope,
            send,
            status_code=403,
            code=code,
            message=message,
        )
