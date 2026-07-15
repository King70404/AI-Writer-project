"""Unit tests for defensive validators exposed by the security layer."""

import pytest

from aiwebnovel.security.csrf import (
    CSRFConfigurationError,
    normalize_allowed_origins,
    validate_csrf_header_name,
)
from aiwebnovel.security.host import (
    HostConfigurationError,
    normalize_trusted_hosts,
    validate_loopback_bind_host,
)
from aiwebnovel.security.request_limits import (
    RequestLimitConfigurationError,
    RequestLimitsMiddleware,
)
from aiwebnovel.security.sessions import (
    InMemorySessionManager,
    SessionConfigurationError,
    validate_cookie_name,
)

pytestmark = pytest.mark.unit


async def _unused_app(scope: object, receive: object, send: object) -> None:
    del scope, receive, send


def test_loopback_bind_validator_never_rewrites_unsafe_hosts() -> None:
    assert validate_loopback_bind_host("127.0.0.1") == "127.0.0.1"
    assert validate_loopback_bind_host("::1") == "::1"
    for value in ("0.0.0.0", "::", "192.168.1.9", "example.test", "localhost"):
        with pytest.raises(HostConfigurationError):
            validate_loopback_bind_host(value)


def test_trusted_host_validation_is_explicit_and_host_only() -> None:
    assert normalize_trusted_hosts(("127.0.0.1", "LOCALHOST")) == (
        "127.0.0.1",
        "localhost",
    )
    for values in ((), ("*",), ("localhost:8000",), ("http://localhost",), ("a?b",)):
        with pytest.raises(HostConfigurationError):
            normalize_trusted_hosts(values)
    with pytest.raises(HostConfigurationError):
        normalize_trusted_hosts(("localhost", "LOCALHOST"))
    with pytest.raises(HostConfigurationError):
        normalize_trusted_hosts("localhost")


def test_cookie_csrf_and_origin_validators_reject_unsafe_syntax() -> None:
    assert validate_cookie_name("aiwebnovel_session") == "aiwebnovel_session"
    assert validate_csrf_header_name("X-CSRF-Token") == "X-CSRF-Token"
    assert normalize_allowed_origins(("http://127.0.0.1:5173",)) == frozenset(
        {("http", "127.0.0.1", 5173)}
    )

    for value in ("", "cookie name", "cookie;name"):
        with pytest.raises(SessionConfigurationError):
            validate_cookie_name(value)
    for value in ("", "X CSRF", "X-CSRF:\nvalue"):
        with pytest.raises(CSRFConfigurationError):
            validate_csrf_header_name(value)
    for origins in (
        ("*",),
        ("file://localhost",),
        ("http://user@localhost",),
        ("http://localhost/path",),
        ("http://localhost", "http://LOCALHOST:80"),
    ):
        with pytest.raises(CSRFConfigurationError):
            normalize_allowed_origins(origins)


def test_runtime_objects_reject_non_positive_limits_without_side_effects() -> None:
    for value in (0, -1, True):
        with pytest.raises(RequestLimitConfigurationError):
            RequestLimitsMiddleware(_unused_app, max_body_bytes=value)
        with pytest.raises(SessionConfigurationError):
            InMemorySessionManager(ttl_seconds=value, max_entries=1)
        with pytest.raises(SessionConfigurationError):
            InMemorySessionManager(ttl_seconds=1, max_entries=value)

    middleware = RequestLimitsMiddleware(_unused_app, max_body_bytes=1)
    manager = InMemorySessionManager(ttl_seconds=1, max_entries=1)
    assert middleware.max_body_bytes == 1
    assert len(manager) == 0
