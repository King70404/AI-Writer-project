"""Deterministic runtime security-baseline readiness checks."""

from __future__ import annotations

from dataclasses import dataclass

from aiwebnovel.security.csrf import CSRFConfigurationError, validate_csrf_header_name
from aiwebnovel.security.host import (
    HostConfigurationError,
    normalize_trusted_hosts,
    validate_loopback_bind_host,
)
from aiwebnovel.security.sessions import SessionConfigurationError, validate_cookie_name

REQUIRED_SECURITY_MIDDLEWARE = frozenset(
    {"cors", "host_validation", "request_limits", "csrf", "security_headers"}
)


class SecurityHealthError(RuntimeError):
    """A deliberately detail-free signal that the baseline is not ready."""


@dataclass(frozen=True, slots=True)
class SecurityHealthSnapshot:
    """Non-secret settings and runtime markers needed for readiness."""

    host: str
    trusted_hosts: tuple[str, ...]
    cors_allowed_origins: tuple[str, ...]
    cors_allow_credentials: bool
    max_request_body_bytes: int
    session_cookie_name: str
    session_ttl_seconds: int
    session_max_entries: int
    csrf_header_name: str
    environment: str
    expose_api_docs: bool
    middleware_names: frozenset[str]
    proxy_headers_trusted: bool
    api_docs_explicitly_configured: bool = False


def check_security_health(snapshot: SecurityHealthSnapshot) -> None:
    """Raise one generic signal unless every required runtime invariant holds."""
    try:
        validate_loopback_bind_host(snapshot.host)
        normalize_trusted_hosts(snapshot.trusted_hosts)
        validate_cookie_name(snapshot.session_cookie_name)
        validate_csrf_header_name(snapshot.csrf_header_name)
    except (HostConfigurationError, SessionConfigurationError, CSRFConfigurationError) as exc:
        raise SecurityHealthError("security baseline check failed") from exc

    valid = (
        bool(snapshot.cors_allowed_origins)
        and all("*" not in origin for origin in snapshot.cors_allowed_origins)
        and snapshot.cors_allow_credentials is False
        and isinstance(snapshot.max_request_body_bytes, int)
        and not isinstance(snapshot.max_request_body_bytes, bool)
        and snapshot.max_request_body_bytes > 0
        and isinstance(snapshot.session_ttl_seconds, int)
        and not isinstance(snapshot.session_ttl_seconds, bool)
        and snapshot.session_ttl_seconds > 0
        and isinstance(snapshot.session_max_entries, int)
        and not isinstance(snapshot.session_max_entries, bool)
        and snapshot.session_max_entries > 0
        and not (
            snapshot.environment.strip().lower() == "production"
            and snapshot.expose_api_docs
            and not snapshot.api_docs_explicitly_configured
        )
        and REQUIRED_SECURITY_MIDDLEWARE.issubset(snapshot.middleware_names)
        and snapshot.proxy_headers_trusted is False
    )
    if not valid:
        raise SecurityHealthError("security baseline check failed")


def is_security_healthy(snapshot: SecurityHealthSnapshot) -> bool:
    """Return a non-diagnostic readiness result suitable for an API check."""
    try:
        check_security_health(snapshot)
    except SecurityHealthError:
        return False
    return True
