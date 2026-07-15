"""Deterministic ready-check tests for the runtime security snapshot."""

from dataclasses import replace

import pytest

from aiwebnovel.security.health import (
    REQUIRED_SECURITY_MIDDLEWARE,
    SecurityHealthError,
    SecurityHealthSnapshot,
    check_security_health,
    is_security_healthy,
)

pytestmark = pytest.mark.unit


def _healthy_snapshot() -> SecurityHealthSnapshot:
    return SecurityHealthSnapshot(
        host="127.0.0.1",
        trusted_hosts=("127.0.0.1", "localhost"),
        cors_allowed_origins=("http://127.0.0.1:5173",),
        cors_allow_credentials=False,
        max_request_body_bytes=1_048_576,
        session_cookie_name="aiwebnovel_session",
        session_ttl_seconds=28_800,
        session_max_entries=16,
        csrf_header_name="X-CSRF-Token",
        environment="production",
        expose_api_docs=False,
        middleware_names=REQUIRED_SECURITY_MIDDLEWARE,
        proxy_headers_trusted=False,
    )


def test_valid_runtime_security_snapshot_is_ready() -> None:
    snapshot = _healthy_snapshot()
    check_security_health(snapshot)
    assert is_security_healthy(snapshot) is True


@pytest.mark.parametrize(
    "changes",
    (
        {"host": "0.0.0.0"},
        {"trusted_hosts": ("*",)},
        {"cors_allowed_origins": ("*",)},
        {"cors_allowed_origins": ()},
        {"cors_allow_credentials": True},
        {"max_request_body_bytes": 0},
        {"max_request_body_bytes": True},
        {"session_cookie_name": "bad cookie"},
        {"session_ttl_seconds": 0},
        {"session_ttl_seconds": True},
        {"session_max_entries": 0},
        {"session_max_entries": True},
        {"csrf_header_name": "bad header"},
        {"expose_api_docs": True},
        {"middleware_names": frozenset({"host_validation"})},
        {"proxy_headers_trusted": True},
    ),
)
def test_each_critical_failure_marks_security_not_ready(changes: dict[str, object]) -> None:
    snapshot = replace(_healthy_snapshot(), **changes)
    with pytest.raises(SecurityHealthError, match="security baseline check failed"):
        check_security_health(snapshot)
    assert is_security_healthy(snapshot) is False


def test_development_may_explicitly_expose_docs() -> None:
    snapshot = replace(_healthy_snapshot(), environment="development", expose_api_docs=True)
    check_security_health(snapshot)


def test_production_may_expose_docs_only_when_explicitly_configured() -> None:
    snapshot = replace(
        _healthy_snapshot(),
        expose_api_docs=True,
        api_docs_explicitly_configured=True,
    )
    check_security_health(snapshot)


def test_health_error_does_not_expose_invalid_configuration_value() -> None:
    sensitive_value = "evil-host-value.example"
    snapshot = replace(_healthy_snapshot(), host=sensitive_value)
    with pytest.raises(SecurityHealthError) as captured:
        check_security_health(snapshot)
    assert sensitive_value not in str(captured.value)
