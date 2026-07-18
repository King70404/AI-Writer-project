"""Public, side-effect-free security configuration diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from aiwebnovel.core.config import Settings
from aiwebnovel.security.csrf import CSRFMiddleware
from aiwebnovel.security.headers import SecurityHeadersMiddleware
from aiwebnovel.security.health import (
    REQUIRED_SECURITY_MIDDLEWARE,
    SecurityHealthSnapshot,
    check_security_health,
)
from aiwebnovel.security.host import HostValidationMiddleware
from aiwebnovel.security.request_limits import RequestLimitsMiddleware
from aiwebnovel.security.sessions import InMemorySessionManager


async def _terminal_app(scope: Scope, receive: Receive, send: Send) -> None:
    del scope, receive, send


@dataclass(frozen=True, slots=True)
class SecurityConfigurationDiagnostic:
    """Non-secret result of assembling and validating the local security stack."""

    default_loopback: bool
    proxy_headers_disabled: bool
    trusted_hosts_safe: bool
    cors_safe: bool
    production_docs_closed: bool
    request_limit_valid: bool
    middleware_assembled: bool

    @property
    def ready(self) -> bool:
        """Return whether every security configuration invariant passed."""
        return all(
            (
                self.default_loopback,
                self.proxy_headers_disabled,
                self.trusted_hosts_safe,
                self.cors_safe,
                self.production_docs_closed,
                self.request_limit_valid,
                self.middleware_assembled,
            )
        )


def diagnose_security_configuration(
    settings: Settings,
    production_settings: Settings,
) -> SecurityConfigurationDiagnostic:
    """Assemble every security middleware inside its owning layer and validate it."""
    manager = InMemorySessionManager(
        ttl_seconds=settings.session_ttl_seconds,
        max_entries=settings.session_max_entries,
    )
    middleware_names: set[str] = set()
    try:
        application: ASGIApp = _terminal_app
        application = CORSMiddleware(
            application,
            allow_origins=list(settings.cors_allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "HEAD", "OPTIONS"],
        )
        middleware_names.add("cors")
        application = CSRFMiddleware(
            application,
            session_manager=manager,
            allowed_origins=settings.cors_allowed_origins,
            cookie_name=settings.session_cookie_name,
            csrf_header_name=settings.csrf_header_name,
            session_path=f"{settings.api_prefix}/security/session",
        )
        middleware_names.add("csrf")
        application = RequestLimitsMiddleware(
            application,
            max_body_bytes=settings.max_request_body_bytes,
        )
        middleware_names.add("request_limits")
        application = HostValidationMiddleware(
            application,
            trusted_hosts=settings.trusted_hosts,
        )
        middleware_names.add("host_validation")
        application = SecurityHeadersMiddleware(application)
        middleware_names.add("security_headers")

        health = SecurityHealthSnapshot(
            host=settings.host,
            trusted_hosts=settings.trusted_hosts,
            cors_allowed_origins=settings.cors_allowed_origins,
            cors_allow_credentials=False,
            max_request_body_bytes=settings.max_request_body_bytes,
            session_cookie_name=settings.session_cookie_name,
            session_ttl_seconds=settings.session_ttl_seconds,
            session_max_entries=settings.session_max_entries,
            csrf_header_name=settings.csrf_header_name,
            environment=production_settings.environment,
            expose_api_docs=production_settings.expose_api_docs,
            middleware_names=frozenset(middleware_names),
            proxy_headers_trusted=False,
        )
        check_security_health(health)
        middleware_assembled = application is not None and REQUIRED_SECURITY_MIDDLEWARE.issubset(
            middleware_names
        )
    finally:
        manager.clear()

    return SecurityConfigurationDiagnostic(
        default_loopback=settings.host == "127.0.0.1",
        proxy_headers_disabled=True,
        trusted_hosts_safe=bool(settings.trusted_hosts)
        and all("*" not in host for host in settings.trusted_hosts),
        cors_safe=bool(settings.cors_allowed_origins)
        and all("*" not in origin for origin in settings.cors_allowed_origins),
        production_docs_closed=production_settings.expose_api_docs is False,
        request_limit_valid=settings.max_request_body_bytes > 0,
        middleware_assembled=middleware_assembled,
    )
