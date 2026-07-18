"""Public security infrastructure for the local-only application boundary."""

from aiwebnovel.security.csrf import CSRFMiddleware, validate_csrf_header_name
from aiwebnovel.security.diagnostics import (
    SecurityConfigurationDiagnostic,
    diagnose_security_configuration,
)
from aiwebnovel.security.headers import SecurityHeadersMiddleware, apply_security_headers
from aiwebnovel.security.health import (
    REQUIRED_SECURITY_MIDDLEWARE,
    SecurityHealthError,
    SecurityHealthSnapshot,
    check_security_health,
    is_security_healthy,
)
from aiwebnovel.security.host import (
    HostValidationMiddleware,
    normalize_trusted_hosts,
    validate_loopback_bind_host,
)
from aiwebnovel.security.request_limits import RequestLimitsMiddleware
from aiwebnovel.security.sessions import (
    InMemorySessionManager,
    SessionStatus,
    create_security_router,
    validate_cookie_name,
)

__all__ = [
    "REQUIRED_SECURITY_MIDDLEWARE",
    "CSRFMiddleware",
    "HostValidationMiddleware",
    "InMemorySessionManager",
    "RequestLimitsMiddleware",
    "SecurityConfigurationDiagnostic",
    "SecurityHeadersMiddleware",
    "SecurityHealthError",
    "SecurityHealthSnapshot",
    "SessionStatus",
    "apply_security_headers",
    "check_security_health",
    "create_security_router",
    "diagnose_security_configuration",
    "is_security_healthy",
    "normalize_trusted_hosts",
    "validate_cookie_name",
    "validate_csrf_header_name",
    "validate_loopback_bind_host",
]
