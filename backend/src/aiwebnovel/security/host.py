"""Loopback binding and exact HTTP Host validation."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from dataclasses import dataclass

from starlette.types import ASGIApp, Receive, Scope, Send

from aiwebnovel.security.responses import send_security_error

_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_LOOPBACK_BIND_HOSTS = frozenset({"127.0.0.1", "::1"})


class HostConfigurationError(ValueError):
    """Raised when trusted host or bind host configuration is unsafe."""


@dataclass(frozen=True, slots=True)
class ParsedHost:
    """A validated Host authority split into canonical host and optional port."""

    host: str
    port: int | None


def validate_loopback_bind_host(value: str) -> str:
    """Accept only explicit IP loopback bindings; never rewrite an unsafe value."""
    normalized = value.strip()
    if normalized not in _LOOPBACK_BIND_HOSTS:
        raise HostConfigurationError("application host must be an explicit loopback address")
    return normalized


def _normalize_host_name(value: str) -> str:
    if not value or any(character.isspace() or ord(character) < 32 for character in value):
        raise HostConfigurationError("host must contain safe visible characters")
    if any(character in value for character in "*\\/@?#,[]"):
        raise HostConfigurationError("host must not contain authority or wildcard syntax")

    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        if len(value) > 253 or value.endswith("."):
            raise HostConfigurationError("host name is invalid") from None
        labels = value.split(".")
        if not labels or any(_HOST_LABEL.fullmatch(label) is None for label in labels):
            raise HostConfigurationError("host name is invalid") from None
        return value.lower()
    return address.compressed.lower()


def normalize_trusted_hosts(values: Iterable[str]) -> tuple[str, ...]:
    """Validate host-only allow-list entries and return canonical unique values."""
    if isinstance(values, str):
        raise HostConfigurationError("trusted_hosts must be a collection of hosts")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise HostConfigurationError("trusted host entries must be text")
        raw = value.strip()
        if ":" in raw and raw != "::1":
            raise HostConfigurationError("trusted host entries must not include ports")
        candidate = _normalize_host_name(raw)
        if candidate in normalized:
            raise HostConfigurationError("trusted host entries must be unique")
        normalized.append(candidate)
    if not normalized:
        raise HostConfigurationError("trusted_hosts must not be empty")
    return tuple(normalized)


def parse_host_header(value: bytes) -> ParsedHost:
    """Parse one raw Host value without accepting ambiguous authority syntax."""
    try:
        text = value.decode("ascii")
    except UnicodeDecodeError as exc:
        raise HostConfigurationError("Host must be ASCII") from exc
    if not text or text != text.strip() or any(ord(character) < 32 for character in text):
        raise HostConfigurationError("Host contains invalid characters")
    if any(character in text for character in "\\/@?#,"):
        raise HostConfigurationError("Host contains ambiguous authority syntax")

    port: int | None = None
    if text.startswith("["):
        closing = text.find("]")
        if closing <= 1:
            raise HostConfigurationError("Host has an invalid IP literal")
        host_text = text[1:closing]
        suffix = text[closing + 1 :]
        if suffix:
            if not suffix.startswith(":") or not suffix[1:]:
                raise HostConfigurationError("Host has an invalid port")
            port_text = suffix[1:]
        else:
            port_text = ""
        try:
            address = ipaddress.IPv6Address(host_text)
        except ValueError as exc:
            raise HostConfigurationError("Host has an invalid IP literal") from exc
        host = address.compressed.lower()
    else:
        if "[" in text or "]" in text or text.count(":") > 1:
            raise HostConfigurationError("Host has invalid bracket or port syntax")
        host_text, separator, port_text = text.rpartition(":")
        if not separator:
            host_text = text
            port_text = ""
        elif not host_text or not port_text:
            raise HostConfigurationError("Host has an invalid port")
        host = _normalize_host_name(host_text)

    if port_text:
        if not port_text.isascii() or not port_text.isdecimal():
            raise HostConfigurationError("Host has an invalid port")
        port = int(port_text)
        if not 1 <= port <= 65535:
            raise HostConfigurationError("Host has an invalid port")
    return ParsedHost(host=host, port=port)


def host_from_scope(scope: Scope) -> ParsedHost:
    """Extract exactly one Host header from an ASGI HTTP scope."""
    values = [value for name, value in scope.get("headers", ()) if name.lower() == b"host"]
    if len(values) != 1:
        raise HostConfigurationError("request must contain exactly one Host header")
    return parse_host_header(values[0])


class HostValidationMiddleware:
    """Reject every HTTP request whose exact Host is not explicitly trusted."""

    def __init__(self, app: ASGIApp, *, trusted_hosts: Iterable[str]) -> None:
        self.app = app
        self.trusted_hosts = frozenset(normalize_trusted_hosts(trusted_hosts))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            parsed = host_from_scope(scope)
        except HostConfigurationError:
            parsed = None
        if parsed is None or parsed.host not in self.trusted_hosts:
            await send_security_error(
                scope,
                send,
                status_code=400,
                code="INVALID_HOST",
                message="The request Host is not trusted.",
            )
            return
        await self.app(scope, receive, send)
