"""Connection probes use fake transport only."""

import socket
import ssl
from unittest.mock import Mock

import pytest
from tests.backend.test_ai_workflow import workflow

__all__ = ["workflow"]

from aiwebnovel.model_gateway import connection
from aiwebnovel.model_gateway.models import ModelProfile

PROFILE = ModelProfile("probe", "probe", "local", "http://127.0.0.1:1234/v1", "test", 512, False)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "unauthorized"),
        (403, "forbidden"),
        (404, "unsupported"),
        (405, "unsupported"),
        (500, "unavailable"),
        (200, "verified"),
    ],
)
def test_status(monkeypatch, status, expected):
    transport = Mock()
    transport.getresponse.return_value.status = status
    transport.getresponse.return_value.read.return_value = b'{"data":[{"id":"test"}]}'
    monkeypatch.setattr(connection.http.client, "HTTPConnection", Mock(return_value=transport))
    result = connection.check_metadata(PROFILE, None, "version")
    assert result.status == expected
    assert result.configuration_version == "version"
    assert transport.request.call_args.args[:2] == ("GET", "/v1/models")
    transport.close.assert_called_once()


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (TimeoutError(), "timeout"),
        (socket.gaierror(), "dns_error"),
        (ssl.SSLError(), "certificate_error"),
        (OSError(), "unavailable"),
    ],
)
def test_failures(monkeypatch, failure, expected):
    transport = Mock()
    transport.request.side_effect = failure
    monkeypatch.setattr(connection.http.client, "HTTPConnection", Mock(return_value=transport))
    assert connection.check_metadata(PROFILE, None, "version").status == expected
    transport.close.assert_called_once()


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"{}",
        b"null",
        b'{"data":null}',
        b'{"data":[{}]}',
        b'{"data":[{"id":1}]}',
        b"x" * (connection.MAX_RESPONSE_BYTES + 1),
    ],
    ids=["json", "missing", "null", "data-null", "missing-id", "bad-id", "oversize"],
)
def test_bad_metadata(monkeypatch, raw):
    transport = Mock()
    transport.getresponse.return_value.status = 200
    transport.getresponse.return_value.read.return_value = raw
    monkeypatch.setattr(connection.http.client, "HTTPConnection", Mock(return_value=transport))
    assert connection.check_metadata(PROFILE, None, "version").status == "invalid_response"


def test_missing_cloud_key_never_connects(monkeypatch):
    from dataclasses import replace

    factory = Mock()
    monkeypatch.setattr(connection, "_PublicHTTPSConnection", factory)
    cloud = replace(PROFILE, kind="cloud", base_url="https://api.example.com/v1")
    assert connection.check_metadata(cloud, None, "version").status == "missing_key"
    factory.assert_not_called()


def test_configuration_and_key_changes_get_new_versions(tmp_path, monkeypatch):
    from tests.backend.test_model_gateway import CLOUD, KEY, FakeProtector

    from aiwebnovel.model_gateway import service as service_module
    from aiwebnovel.model_gateway.service import ModelGatewayService

    probe = Mock(
        side_effect=lambda profile, key, version: connection.ConnectionResult(
            "verified", version, True
        )
    )
    monkeypatch.setattr(service_module, "check_metadata", probe)
    service = ModelGatewayService(tmp_path, protector=FakeProtector())
    profile = service.create_profile(**CLOUD, api_key=KEY)
    first = service.check_connection(profile.id)
    assert service.check_connection(profile.id) == first
    service.update_profile(profile.id, **{**CLOUD, "model": "changed"})
    second = service.check_connection(profile.id)
    assert second.configuration_version != first.configuration_version
    service.update_profile(profile.id, **CLOUD, api_key="replacement-fake-key")
    third = service.check_connection(profile.id)
    assert third.configuration_version not in {
        first.configuration_version,
        second.configuration_version,
    }
    assert KEY not in repr(first)
    assert service.get_profile(profile.id).has_key


def test_http_check_requires_session_and_redacts_upstream(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from tests.backend.character_http_support import isolated_app, issue_write_headers
    from tests.backend.test_model_gateway import LOCAL, FakeProtector

    from aiwebnovel.model_gateway.service import ModelGatewayService
    from aiwebnovel.model_gateway.web import create_model_gateway_router

    app = isolated_app(tmp_path)
    if not any(getattr(route, "path", "") == "/api/v1/ai/models" for route in app.routes):
        app.include_router(create_model_gateway_router(api_prefix="/api/v1"))
    service = ModelGatewayService(tmp_path / "models", protector=FakeProtector())
    app.state.model_gateway_service = service
    profile = service.create_profile(**LOCAL)
    transport = Mock()
    transport.getresponse.return_value.status = 401
    monkeypatch.setattr(connection.http.client, "HTTPConnection", Mock(return_value=transport))
    path = f"/api/v1/ai/models/{profile.id}/connection-check"
    with TestClient(app) as client:
        assert client.post(path, json={}).status_code == 403
        transport.request.assert_not_called()
        result = client.post(path, json={}, headers=issue_write_headers(client))
        assert result.status_code == 200
        assert result.json()["status"] == "unauthorized"
        assert result.headers["cache-control"] == "no-store"
        assert set(result.json()) == {"status", "configuration_version", "model_available"}
        transport.getresponse.return_value.read.assert_not_called()
        assert service.get_profile(profile.id) == profile


def test_confirmed_fallback_is_metered_and_configuration_bound(tmp_path, monkeypatch):
    from tests.backend.test_model_gateway import LOCAL

    from aiwebnovel.ai_writing.errors import AIContextChanged
    from aiwebnovel.model_gateway.service import ModelGatewayService
    from aiwebnovel.usage.service import UsageLedgerService

    service = ModelGatewayService(tmp_path)
    profile = service.create_profile(**LOCAL)
    metadata = Mock()
    metadata.getresponse.return_value.status = 404
    generation = Mock()
    generation.getresponse.return_value.status = 200
    generation.getresponse.return_value.read.return_value = b'{"choices":[{"message":{"content":"OK"}}],"usage":{"prompt_tokens":3,"completion_tokens":1,"total_tokens":4}}'
    factory = Mock(return_value=metadata)
    monkeypatch.setattr(connection.http.client, "HTTPConnection", factory)
    probe = service.check_connection(profile.id)
    ledger = Mock()
    ledger.start.return_value = "attempt"
    metering = UsageLedgerService(ledger)
    with pytest.raises(AIContextChanged):
        service.test_connection(profile.id, "stale", "project", metering)
    ledger.start.assert_not_called()
    factory.side_effect = [metadata, generation]
    result = service.test_connection(profile.id, probe.configuration_version, "project", metering)
    assert result.status == "verified"
    attempt = ledger.start.call_args.args[0]
    assert attempt.attribution.operation == "connection_check"
    assert attempt.attribution.project_id == "project"
    assert b'"max_tokens": 1' in generation.request.call_args.kwargs["body"]
    ledger.settle.assert_called_once()


@pytest.fixture
def connection_workflow(workflow):
    return workflow


def test_confirmed_http_uses_real_ledger_and_strict_budget(connection_workflow, monkeypatch):
    from tests.backend.test_candidate_edits_budget import put_budget, put_price
    from tests.backend.test_usage_ledger import rows, transport

    from aiwebnovel.ai_writing.application.models import GeneratedText, ProviderUsage
    from aiwebnovel.model_gateway import service as gateway_module

    w = connection_workflow
    monkeypatch.setattr(
        gateway_module,
        "check_metadata",
        lambda profile, key, version: connection.ConnectionResult("unsupported", version),
    )
    profile = w.app.state.model_gateway_service.list_profiles()[0]
    path = f"/api/v1/ai/models/{profile.id}/connection-check"
    probe = w.client.post(path, json={}, headers=w.headers)
    assert probe.status_code == 200, probe.text
    confirmation = {
        "confirm_test_message": True,
        "configuration_version": probe.json()["configuration_version"],
        "project_id": w.project,
    }
    calls = transport(monkeypatch, GeneratedText("OK", profile.model, ProviderUsage(3, 1, 4)))
    put_budget(w, task_limit="1")
    refused = w.client.post(path, json=confirmation, headers=w.headers)
    assert refused.status_code == 409, refused.text
    assert calls == [] and rows(w) == []
    put_price(w, inp="1", out="1")
    put_budget(w, version=1, task_limit="1")
    success = w.client.post(path, json=confirmation, headers=w.headers)
    assert success.status_code == 200, success.text
    assert success.json()["status"] == "verified"
    assert len(calls) == 1 and calls[0][2].operation == "connection_check"
    stored = rows(w)
    assert len(stored) == 1 and stored[0]["status"] == "completed"
    assert stored[0]["reported_total_tokens"] == 4
    assert w.client.get(f"/api/v1/projects/{w.project}/usage").status_code == 200
    # Re-run the migration against a populated parent ledger and its budget reservation.
    import sqlite3
    from contextlib import closing

    from tests.backend.test_novel_structure_migration import _run_alembic

    with closing(sqlite3.connect(w.db)) as database:
        reservations = database.execute("SELECT * FROM model_budget_reservations").fetchall()
        triggers = database.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name IN ('model_usage_attempts','model_budget_reservations') ORDER BY name"
        ).fetchall()
        database.execute("UPDATE alembic_version SET version_num='0017_add_writing_job_budgets'")
        database.commit()
    migrated = _run_alembic(w.db, "upgrade", "0018_add_connection_check_usage")
    assert migrated.returncode == 0, migrated.stderr
    assert rows(w) == stored
    with closing(sqlite3.connect(w.db)) as database:
        assert (
            database.execute("SELECT * FROM model_budget_reservations").fetchall() == reservations
        )
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            database.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name IN ('model_usage_attempts','model_budget_reservations') ORDER BY name"
            ).fetchall()
            == triggers
        )
        with pytest.raises(sqlite3.IntegrityError):
            database.execute("DELETE FROM model_usage_attempts")
