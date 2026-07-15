"""Immutable secret redaction tests with non-printing canary assertions."""

import json
import logging
import secrets
import sys

import pytest

from aiwebnovel.core.logging import JsonFormatter
from aiwebnovel.security.redaction import (
    CYCLE,
    REDACTED,
    UNSERIALIZABLE,
    is_sensitive_key,
    redact,
    redact_text,
    safe_exception_details,
    safe_request_path,
)

pytestmark = pytest.mark.unit


def test_nested_mapping_and_header_names_are_redacted_case_insensitively() -> None:
    canary = secrets.token_urlsafe(24)
    original = {
        "Authorization": canary,
        "headers": {
            "COOKIE": canary,
            "Set-Cookie": canary,
            "x-CsRf-ToKeN": canary,
        },
        "details": {
            "aiwebnovel_session": canary,
            "access_token": canary,
            "refresh_token": canary,
            "PASSWORD": canary,
            "secret": canary,
            "api-key": canary,
        },
        "safe": "visible",
    }
    result = redact(original)
    serialized = json.dumps(result)
    if canary in serialized:
        pytest.fail("redaction leaked a canary secret")
    assert original["Authorization"] == canary
    assert result["Authorization"] == REDACTED  # type: ignore[index]
    assert result["safe"] == "visible"  # type: ignore[index]


def test_recognized_key_value_text_is_fully_replaced_without_prefix_or_suffix() -> None:
    canary = secrets.token_urlsafe(24)
    message = f"Authorization: Bearer {canary}\npassword={canary}\nordinary=value"
    redacted = redact_text(message)
    if canary in redacted:
        pytest.fail("text redaction leaked a canary secret")
    assert redacted.count(REDACTED) == 2
    assert "ordinary=value" in redacted


def test_non_finite_numbers_are_replaced_with_json_safe_placeholder() -> None:
    assert redact({"nan": float("nan"), "infinity": float("inf")}) == {
        "nan": UNSERIALIZABLE,
        "infinity": UNSERIALIZABLE,
    }


def test_json_shaped_log_text_redacts_quoted_sensitive_keys() -> None:
    canary = secrets.token_urlsafe(24)
    redacted = redact_text(
        json.dumps({"Authorization": f"Bearer {canary}", "access_token": canary})
    )
    if canary in redacted:
        pytest.fail("JSON-shaped text redaction leaked a canary secret")
    assert REDACTED in redacted


def test_unserializable_cycles_and_depth_never_crash_or_call_arbitrary_repr() -> None:
    cyclic: list[object] = []
    cyclic.append(cyclic)

    class Dangerous:
        def __repr__(self) -> str:
            raise AssertionError("repr must not be called")

    assert redact(cyclic) == [CYCLE]
    assert redact(Dangerous()) == UNSERIALIZABLE
    assert redact([[["deep"]]], max_depth=2) == [[UNSERIALIZABLE]]
    with pytest.raises(ValueError):
        redact({}, max_depth=0)


def test_safe_path_drops_queries_fragments_and_invalid_values() -> None:
    assert safe_request_path("/api/v1/items?access_token=secret#fragment") == "/api/v1/items"
    assert safe_request_path("relative?secret=value") == "/"
    assert safe_request_path("/bad\npath") == "/"
    assert safe_request_path("/" + "a" * 2048) == "/"


def test_exception_details_never_include_message_or_arguments() -> None:
    canary = secrets.token_urlsafe(24)
    details = safe_exception_details(RuntimeError(canary))
    assert details == {"error_type": "RuntimeError"}
    if canary in json.dumps(details):
        pytest.fail("exception redaction leaked a canary secret")


def test_json_log_formatter_redacts_messages_and_exception_text() -> None:
    canary = secrets.token_urlsafe(24)
    try:
        raise RuntimeError(f"api_key={canary}")
    except RuntimeError:
        exception_info = sys.exc_info()

    record = logging.LogRecord(
        name="aiwebnovel.security-test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=f"Cookie=session={canary}",
        args=(),
        exc_info=exception_info,
    )
    rendered = JsonFormatter(redact_text).format(record)

    if canary in rendered:
        pytest.fail("JSON logging leaked a canary secret")
    payload = json.loads(rendered)
    assert REDACTED in payload["message"]
    assert payload["exception"] == {"error_type": "RuntimeError"}


@pytest.mark.parametrize(
    "key",
    (
        "Authorization",
        "Cookie",
        "Set-Cookie",
        "X-CSRF-Token",
        "aiwebnovel_session",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "api_key",
    ),
)
def test_required_sensitive_keys_are_recognized(key: str) -> None:
    assert is_sensitive_key(key) is True
