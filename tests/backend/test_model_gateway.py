"""Isolated credentials, atomic configuration, SSRF and real HTTP contracts."""

import http.client
import json
import os
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from tests.backend.character_http_support import isolated_app, issue_write_headers
from tests.backend.test_ai_writing_provider import mock_server

from aiwebnovel.ai_writing.application.models import GenerationMessage
from aiwebnovel.ai_writing.errors import (
    AIProviderAccessDenied,
    AIProviderAuthFailed,
    AIProviderEndpointInvalid,
    AIProviderInvalidResponse,
    AIProviderNotConfigured,
    AIProviderPaymentRequired,
    AIProviderRateLimited,
    AIProviderRequestRejected,
    AIProviderTimeout,
    AIProviderUnavailable,
    InvalidAIInput,
)
from aiwebnovel.model_gateway import credentials, provider
from aiwebnovel.model_gateway.credentials import WindowsDPAPIProtector, credential_scope
from aiwebnovel.model_gateway.errors import (
    InvalidModelProfile,
    ModelConfigurationUnavailable,
    ModelCredentialUnavailable,
    ModelProfileNotFound,
)
from aiwebnovel.model_gateway.models import ModelProfile
from aiwebnovel.model_gateway.provider import endpoint_for, generate_text
from aiwebnovel.model_gateway.service import ModelGatewayService
from aiwebnovel.model_gateway.web import ProfileInput, create_model_gateway_router

KEY = "test-gateway-key-never-persist-plain"
MESSAGES = (GenerationMessage("user", "隔离测试正文"),)
CLOUD = {
    "name": "测试云服务",
    "kind": "cloud",
    "base_url": "https://api.example.com/v1",
    "model": "test-model",
    "max_output_tokens": 2048,
}
LOCAL = {
    "name": "本地服务",
    "kind": "local",
    "base_url": "http://127.0.0.1:1234/v1",
    "model": "local-model",
    "max_output_tokens": 512,
}


class FakeProtector:
    """Opaque test ciphertext; real DPAPI also receives a round-trip test below."""

    def __init__(self) -> None:
        self.values: dict[bytes, tuple[bytes, bytes]] = {}

    def protect(self, value: bytes, scope: bytes) -> bytes:
        token = f"protected-{len(self.values)}".encode()
        self.values[token] = (value, scope)
        return token

    def unprotect(self, value: bytes, scope: bytes) -> bytes:
        if value not in self.values or self.values[value][1] != scope:
            raise ModelCredentialUnavailable
        return self.values[value][0]


def test_profile_restart_edit_delete_preserves_no_plaintext(tmp_path: Path) -> None:
    protector = FakeProtector()
    service = ModelGatewayService(tmp_path, protector=protector)
    profile = service.create_profile(**CLOUD, api_key=KEY)
    assert profile.has_key and KEY not in repr(profile)
    assert len(list((tmp_path / "config/model-gateway").glob("*.key"))) == 1
    for file in (tmp_path / "config/model-gateway").iterdir():
        assert KEY.encode() not in file.read_bytes()
    restarted = ModelGatewayService(tmp_path, protector=protector)
    assert restarted.list_profiles() == (profile,)
    updated = restarted.update_profile(profile.id, **{**CLOUD, "name": "新名称"})
    assert updated.has_key and updated.name == "新名称"
    replaced = restarted.update_profile(profile.id, **CLOUD, api_key="replacement-test-key")
    assert replaced.has_key
    assert len(list((tmp_path / "config/model-gateway").glob("*.key"))) == 1
    cleared = restarted.update_profile(profile.id, **CLOUD, clear_key=True)
    assert not cleared.has_key
    assert not list((tmp_path / "config/model-gateway").glob("*.key"))
    restarted.remove_profile(profile.id)
    assert ModelGatewayService(tmp_path).list_profiles() == ()
    with pytest.raises(ModelProfileNotFound):
        restarted.get_profile(profile.id)


def test_config_and_credentials_are_scoped_to_data_root_and_profile(tmp_path: Path) -> None:
    first = credential_scope(tmp_path / "first", "a")
    assert first != credential_scope(tmp_path / "second", "a")
    assert first != credential_scope(tmp_path / "first", "b")
    protector = FakeProtector()
    source = ModelGatewayService(tmp_path / "first", protector=protector)
    profile = source.create_profile(**CLOUD, api_key=KEY)
    other = ModelGatewayService(tmp_path / "second", protector=protector)
    assert other.list_profiles() == ()
    copy_to = tmp_path / "second/config/model-gateway"
    copy_to.mkdir(parents=True)
    for file in (tmp_path / "first/config/model-gateway").iterdir():
        (copy_to / file.name).write_bytes(file.read_bytes())
    with pytest.raises(ModelCredentialUnavailable):
        other.generate(profile.id, MESSAGES)


def test_real_windows_dpapi_or_unsupported_fail_closed(tmp_path: Path) -> None:
    protector = WindowsDPAPIProtector()
    scope = credential_scope(tmp_path, "profile")
    if os.name != "nt":
        with pytest.raises(ModelCredentialUnavailable):
            protector.protect(KEY.encode(), scope)
        return
    encrypted = protector.protect(KEY.encode(), scope)
    assert KEY.encode() not in encrypted
    assert protector.unprotect(encrypted, scope) == KEY.encode()
    with pytest.raises(ModelCredentialUnavailable):
        protector.unprotect(encrypted, credential_scope(tmp_path, "other-profile"))
    with pytest.raises(ModelCredentialUnavailable):
        protector.unprotect(b"corrupt", scope)


def test_unsupported_platform_does_not_write_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ModelGatewayService(tmp_path)
    monkeypatch.setattr(credentials, "os", SimpleNamespace(name="unsupported", path=os.path))
    with pytest.raises(ModelCredentialUnavailable):
        service.create_profile(**CLOUD, api_key=KEY)
    assert not (tmp_path / "config").exists()


def test_optional_defaults_are_lazy_and_deleted_seed_stays_deleted(tmp_path: Path) -> None:
    settings = {"default_base_url": LOCAL["base_url"], "default_model": "configured-model"}
    service = ModelGatewayService(tmp_path, **settings)
    assert not (tmp_path / "config").exists()
    assert service.list_profiles()[0].id == "default-local"
    service.remove_profile("default-local")
    assert ModelGatewayService(tmp_path, **settings).list_profiles() == ()
    assert ModelGatewayService(tmp_path / "unconfigured").list_profiles() == ()
    assert (
        ModelGatewayService(
            tmp_path / "bad-env", default_base_url="http://remote.example", default_model="model"
        ).list_profiles()
        == ()
    )


def test_new_endpoint_cannot_silently_receive_existing_key(tmp_path: Path) -> None:
    service = ModelGatewayService(tmp_path, protector=FakeProtector())
    profile = service.create_profile(**CLOUD, api_key=KEY)
    changed = {**CLOUD, "base_url": "https://other.example.com/v1"}
    with pytest.raises(InvalidModelProfile):
        service.update_profile(profile.id, **changed)
    assert service.get_profile(profile.id) == profile
    changed_profile = service.update_profile(profile.id, **changed, clear_key=True)
    assert not changed_profile.has_key


def test_failed_atomic_save_keeps_previous_profile_and_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ModelGatewayService(tmp_path, protector=FakeProtector())
    original = service.create_profile(**CLOUD, api_key=KEY)
    old_bytes = (tmp_path / "config/model-gateway/profiles.json").read_bytes()
    old_keys = set((tmp_path / "config/model-gateway").glob("*.key"))
    writer = service._write
    monkeypatch.setattr(service, "_write", Mock(side_effect=ModelConfigurationUnavailable))
    with pytest.raises(ModelConfigurationUnavailable):
        service.update_profile(original.id, **CLOUD, api_key="new-test-key")
    assert set((tmp_path / "config/model-gateway").glob("*.key")) == old_keys
    assert (tmp_path / "config/model-gateway/profiles.json").read_bytes() == old_bytes
    monkeypatch.setattr(service, "_write", writer)
    assert service.get_profile(original.id) == original


@pytest.mark.parametrize(
    "value",
    [b"invalid-json", b"{}", b"x" * 131_073],
    ids=["invalid-json", "invalid-schema", "oversized"],
)
def test_corrupt_configuration_is_safe(tmp_path: Path, value: bytes) -> None:
    directory = tmp_path / "config/model-gateway"
    directory.mkdir(parents=True)
    (directory / "profiles.json").write_bytes(value)
    with pytest.raises(ModelConfigurationUnavailable) as caught:
        ModelGatewayService(tmp_path).list_profiles()
    assert "invalid-json" not in str(caught.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.com/v1",
        "https://secret@api.example.com/v1",
        "https://api.example.com/v1?key=secret",
        "https://api.example.com/v1#secret",
        "https://127.0.0.1/v1",
        "https://10.0.0.1/v1",
        "https://169.254.169.254/latest",
        "https://[::1]/v1",
        "https://localhost/v1",
        "https://api.local/v1",
        "https://2130706433/v1",
        "https://127.1/v1",
        "https://api.example.com:0/v1",
        "https://api.example.com:65536/v1",
        "https://api.example.com/%2e%2e/secret",
        "https://api.example.com/v1\n",
    ],
)
def test_cloud_endpoint_rejects_unsafe_urls_without_network(url: str) -> None:
    with pytest.raises(InvalidModelProfile):
        endpoint_for("cloud", url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1"])
def test_private_or_mixed_dns_never_connects(address: str, monkeypatch: pytest.MonkeyPatch) -> None:
    conn = provider._PublicHTTPSConnection("api.example.com", 443, timeout=30)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        Mock(
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)),
            ]
        ),
    )
    socket_factory = Mock()
    monkeypatch.setattr(socket, "socket", socket_factory)
    with pytest.raises(AIProviderUnavailable):
        conn.connect()
    socket_factory.assert_not_called()


def test_cloud_dns_is_pinned_and_tls_uses_configured_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = provider._PublicHTTPSConnection("api.example.com", 443, timeout=30)
    resolver = Mock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    raw_socket = Mock()
    monkeypatch.setattr(socket, "socket", Mock(return_value=raw_socket))
    context = Mock()
    monkeypatch.setattr(conn, "_tls_context", context)
    conn.connect()
    resolver.assert_called_once_with("api.example.com", 443, type=socket.SOCK_STREAM)
    raw_socket.connect.assert_called_once_with(("8.8.8.8", 443))
    context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="api.example.com")
    conn.close()


def test_real_local_generation_sends_cap_without_proxy_or_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://192.168.1.1:1234")
    response = json.dumps({"choices": [{"message": {"content": "隔离生成结果"}}]}).encode()
    service = ModelGatewayService(tmp_path)
    with mock_server(response) as (url, received):
        profile = service.create_profile(**{**LOCAL, "base_url": url})
        result = service.generate(profile.id, MESSAGES, max_output_tokens=128)
    assert result.text == "隔离生成结果"
    path, headers, payload = received[0]
    assert path == "/v1/chat/completions" and payload["max_tokens"] == 128
    assert payload["stream"] is False and "Authorization" not in headers
    with pytest.raises(InvalidAIInput):
        service.generate(profile.id, MESSAGES, max_output_tokens=513)


def test_cloud_key_only_reaches_authorization_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ModelGatewayService(tmp_path, protector=FakeProtector())
    profile = service.create_profile(**CLOUD, api_key=KEY)
    connection = Mock()
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.read.return_value = (
        b'{"choices":[{"message":{"content":"ok"}}]}'
    )
    monkeypatch.setattr(provider, "_PublicHTTPSConnection", Mock(return_value=connection))
    assert service.generate(profile.id, MESSAGES).text == "ok"
    arguments = connection.request.call_args
    assert arguments.kwargs["headers"]["Authorization"] == f"Bearer {KEY}"
    assert KEY.encode() not in arguments.kwargs["body"]
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "failure,expected",
    [
        (TimeoutError("private-key"), AIProviderTimeout),
        (OSError("private-key"), AIProviderUnavailable),
        (http.client.BadStatusLine("private-key"), AIProviderUnavailable),
    ],
)
def test_transport_failures_are_safe_and_closed(
    failure: Exception, expected: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = Mock()
    connection.getresponse.side_effect = failure
    monkeypatch.setattr(provider, "_PublicHTTPSConnection", Mock(return_value=connection))
    profile = ModelProfile("a" * 32, "Cloud", "cloud", CLOUD["base_url"], "model", 2048, True)
    with pytest.raises(expected) as caught:
        generate_text(profile, MESSAGES, api_key=KEY, max_output_tokens=100)
    assert "private-key" not in str(caught.value)
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "status,expected",
    [
        (301, AIProviderUnavailable),
        (307, AIProviderUnavailable),
        (400, AIProviderRequestRejected),
        (401, AIProviderAuthFailed),
        (402, AIProviderPaymentRequired),
        (403, AIProviderAccessDenied),
        (404, AIProviderEndpointInvalid),
        (405, AIProviderEndpointInvalid),
        (422, AIProviderRequestRejected),
        (429, AIProviderRateLimited),
        (500, AIProviderUnavailable),
        (503, AIProviderUnavailable),
    ],
)
def test_cloud_redirect_or_upstream_failure_is_never_followed(
    status: int, expected: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = Mock()
    connection.getresponse.return_value.status = status
    factory = Mock(return_value=connection)
    monkeypatch.setattr(provider, "_PublicHTTPSConnection", factory)
    profile = ModelProfile("a" * 32, "Cloud", "cloud", CLOUD["base_url"], "model", 2048, True)
    with pytest.raises(expected):
        generate_text(profile, MESSAGES, api_key=KEY, max_output_tokens=100)
    assert factory.call_count == 1 and connection.request.call_count == 1
    connection.getresponse.return_value.read.assert_not_called()
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    "path,expected",
    [
        ("", "/chat/completions"),
        ("/", "/chat/completions"),
        ("/v1", "/v1/chat/completions"),
        ("/v1/", "/v1/chat/completions"),
        ("/chat/completions", "/chat/completions"),
        ("/v1/chat/completions/", "/v1/chat/completions"),
    ],
)
def test_cloud_full_endpoint_is_not_appended_twice(path: str, expected: str) -> None:
    endpoint = endpoint_for("cloud", "https://api.example.com" + path)
    assert endpoint.host == "api.example.com"
    assert endpoint.scheme == "https" and endpoint.port == 443
    assert endpoint.path == expected


@pytest.mark.parametrize(
    "raw",
    [b"invalid", b"{}", b"x" * 1_048_577],
    ids=["invalid-json", "invalid-schema", "oversized"],
)
def test_cloud_invalid_or_oversized_response(raw: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    connection = Mock()
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.read.return_value = raw
    monkeypatch.setattr(provider, "_PublicHTTPSConnection", Mock(return_value=connection))
    profile = ModelProfile("a" * 32, "Cloud", "cloud", CLOUD["base_url"], "model", 2048, True)
    with pytest.raises(AIProviderInvalidResponse):
        generate_text(profile, MESSAGES, api_key=KEY, max_output_tokens=100)
    connection.getresponse.return_value.read.assert_called_once_with(1_048_577)


def test_missing_key_does_not_make_cloud_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ModelGatewayService(tmp_path)
    profile = service.create_profile(**CLOUD)
    factory = Mock()
    monkeypatch.setattr(provider, "_PublicHTTPSConnection", factory)
    with pytest.raises(AIProviderNotConfigured):
        service.generate(profile.id, MESSAGES)
    factory.assert_not_called()


def test_http_profile_lifecycle_csrf_and_secret_redaction(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    if not any(getattr(route, "path", "") == "/api/v1/ai/models" for route in app.routes):
        app.include_router(create_model_gateway_router(api_prefix="/api/v1"))
    service = ModelGatewayService(tmp_path / "model-root", protector=FakeProtector())
    app.state.model_gateway_service = service
    payload = {**CLOUD, "api_key": KEY}
    assert KEY not in repr(ProfileInput(**payload))
    with TestClient(app) as client:
        assert client.post("/api/v1/ai/models", json=payload).status_code == 403
        headers = issue_write_headers(client)
        created = client.post("/api/v1/ai/models", json=payload, headers=headers)
        assert created.status_code == 201
        assert KEY not in created.text and "api_key" not in created.json()
        assert created.json()["has_key"] is True
        assert created.headers["cache-control"] == "no-store"
        profile_id = created.json()["id"]
        listed = client.get("/api/v1/ai/models")
        assert listed.json()["items"] == [created.json()]
        assert KEY not in listed.text
        updated = client.put(
            f"/api/v1/ai/models/{profile_id}", json={**CLOUD, "clear_key": True}, headers=headers
        )
        assert updated.status_code == 200 and updated.json()["has_key"] is False
        invalid = client.post(
            "/api/v1/ai/models", json={**payload, "api_key": KEY + "\n"}, headers=headers
        )
        assert invalid.status_code == 422 and KEY not in invalid.text
        deleted = client.delete(f"/api/v1/ai/models/{profile_id}", headers=headers)
        assert deleted.status_code == 204
        assert client.get("/api/v1/ai/models").json() == {"items": []}
