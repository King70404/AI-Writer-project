"""Real loopback HTTP protocol plus deterministic transport failures; no model required."""

import http.client
import json
import socket
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from unittest.mock import Mock

import pytest

from aiwebnovel.ai_writing.application.models import GenerationMessage
from aiwebnovel.ai_writing.errors import (
    AIProviderConfigurationInvalid,
    AIProviderInvalidResponse,
    AIProviderNotConfigured,
    AIProviderTimeout,
    AIProviderUnavailable,
)
from aiwebnovel.ai_writing.provider import (
    MAX_RESPONSE_BYTES,
    LocalOpenAICompatibleProvider,
    local_endpoint,
)
from aiwebnovel.core.config import Settings

MESSAGES = (GenerationMessage("system", "规则"), GenerationMessage("user", "测试正文"))


@contextmanager
def mock_server(body: bytes, status: int = 200):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            data = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, dict(self.headers), json.loads(data)))
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Location", "http://192.168.1.10:1234/forbidden")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 5
    worker = Thread(target=server.handle_request)
    worker.start()
    try:
        yield f"http://localhost:{server.server_port}/v1", received
    finally:
        worker.join(timeout=6)
        server.server_close()
        assert not worker.is_alive()


def test_real_adapter_loopback_protocol_and_no_environment_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://192.168.1.10:1234")
    body = json.dumps({"choices": [{"message": {"content": "生成\r\n正文"}}]}).encode()
    with mock_server(body) as (url, received):
        result = LocalOpenAICompatibleProvider(url, "local-model").generate(MESSAGES)
    assert result.text == "生成\n正文" and result.model == "local-model"
    assert result.usage is None
    assert len(received) == 1
    path, headers, payload = received[0]
    assert path == "/v1/chat/completions"
    assert payload == {
        "model": "local-model",
        "messages": [
            {"role": "system", "content": "规则"},
            {"role": "user", "content": "测试正文"},
        ],
        "stream": False,
    }
    assert "Authorization" not in headers
    assert headers["Host"].startswith("127.0.0.1:")


def test_real_adapter_reads_provider_usage_without_guessing() -> None:
    body = json.dumps(
        {"choices": [{"message": {"content": "正文"}}], "usage": {"completion_tokens": 3}}
    ).encode()
    with mock_server(body) as (url, _received):
        result = LocalOpenAICompatibleProvider(url, "local-model").generate(MESSAGES)
    assert result.usage is not None
    assert (result.usage.input_tokens, result.usage.output_tokens) == (None, 3)


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"{}",
        b"[]",
        b'{"choices":[]}',
        b'{"choices":[{}]}',
        b'{"choices":[{"message":{}}]}',
        b'{"choices":[{"message":{"content":null}}]}',
    ],
)
def test_real_invalid_responses_are_safe(body: bytes) -> None:
    with mock_server(body) as (url, received), pytest.raises(AIProviderInvalidResponse) as caught:
        LocalOpenAICompatibleProvider(url, "model").generate(MESSAGES)
    assert str(caught.value) == AIProviderInvalidResponse.message
    assert len(received) == 1


@pytest.mark.parametrize("status", [301, 302, 307, 308, 400, 401, 429, 500])
def test_real_upstream_errors_and_redirects_never_follow(status: int) -> None:
    with (
        mock_server(b"", status) as (url, received),
        pytest.raises(AIProviderUnavailable) as caught,
    ):
        LocalOpenAICompatibleProvider(url, "model").generate(MESSAGES)
    assert str(caught.value) == AIProviderUnavailable.message
    assert len(received) == 1


@pytest.mark.parametrize(
    "url,host",
    [
        ("http://127.0.0.1:1234", "127.0.0.1"),
        ("http://localhost:1234/v1/", "127.0.0.1"),
        ("http://[::1]:1234/v1", "::1"),
        ("https://127.0.0.1:1234/v1", "127.0.0.1"),
    ],
)
def test_allowed_loopback_endpoints(url: str, host: str) -> None:
    scheme, actual, port, path = local_endpoint(url)
    assert scheme in {"http", "https"} and actual == host and port == 1234
    assert path.endswith("/chat/completions")


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com",
        "http://example.com",
        "http://192.168.1.10:1234",
        "http://10.0.0.1",
        "http://" + "user:password" + "@localhost:1234",
        "http://localhost",
        "http://localhost:0",
        "http://localhost:65536",
        "http://localhost:bad",
        "http://localhost:12/?x=1",
        "http://localhost:12/#x",
        "http://localhost:12/../other",
        "http://localhost:12/%2e%2e",
        "http://localhost:12\n",
        "http://[::1",
        "file://localhost:1234",
        "http://127.1:1234",
        "http://2130706433:1234",
        "http://localhost.example.com:1234",
        "http://[::ffff:127.0.0.1]:1234",
    ],
)
def test_invalid_urls_fail_before_connection(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    connection = Mock()
    monkeypatch.setattr(http.client, "HTTPConnection", connection)
    with pytest.raises(AIProviderConfigurationInvalid):
        LocalOpenAICompatibleProvider(url, "model").generate(MESSAGES)
    connection.assert_not_called()


@pytest.mark.parametrize(
    "url,model",
    [
        (None, None),
        (None, "model"),
        ("http://localhost:1234", None),
        ("", "model"),
        ("http://localhost:1234", ""),
    ],
)
def test_missing_configuration_is_safe(url: str | None, model: str | None) -> None:
    with pytest.raises(AIProviderNotConfigured):
        LocalOpenAICompatibleProvider(url, model).generate(MESSAGES)


def test_invalid_model_configuration() -> None:
    with pytest.raises(AIProviderConfigurationInvalid):
        LocalOpenAICompatibleProvider("http://localhost:1234", "bad\nmodel").generate(MESSAGES)


def test_real_connection_refused_is_safe() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        with pytest.raises(AIProviderUnavailable):
            LocalOpenAICompatibleProvider(f"http://127.0.0.1:{port}", "model").generate(MESSAGES)


@pytest.mark.parametrize(
    "error,expected",
    [
        (TimeoutError(), AIProviderTimeout),
        (http.client.BadStatusLine("private"), AIProviderUnavailable),
        (OSError("private"), AIProviderUnavailable),
    ],
)
def test_transport_errors_close_connection(
    error: Exception, expected: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = Mock()
    conn.getresponse.side_effect = error
    monkeypatch.setattr(http.client, "HTTPSConnection", Mock(return_value=conn))
    with pytest.raises(expected) as caught:
        LocalOpenAICompatibleProvider("https://[::1]:1234", "model").generate(MESSAGES)
    assert "private" not in str(caught.value)
    conn.close.assert_called_once()


def test_response_size_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = Mock()
    conn.getresponse.return_value.status = 200
    conn.getresponse.return_value.read.return_value = b"x" * (MAX_RESPONSE_BYTES + 1)
    monkeypatch.setattr(http.client, "HTTPConnection", Mock(return_value=conn))
    with pytest.raises(AIProviderInvalidResponse):
        LocalOpenAICompatibleProvider("http://127.0.0.1:1234", "model").generate(MESSAGES)
    conn.getresponse.return_value.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)
    conn.close.assert_called_once()


def test_ai_environment_configuration_is_optional_and_deferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AIWEBNOVEL_AI_BASE_URL", raising=False)
    monkeypatch.delenv("AIWEBNOVEL_AI_MODEL", raising=False)
    settings = Settings()
    assert settings.ai_base_url is None and settings.ai_model is None
    monkeypatch.setenv("AIWEBNOVEL_AI_BASE_URL", "http://example.com:1234")
    monkeypatch.setenv("AIWEBNOVEL_AI_MODEL", "configured-model")
    configured = Settings()
    assert configured.ai_base_url == "http://example.com:1234"
    assert configured.ai_model == "configured-model"
    provider = LocalOpenAICompatibleProvider(configured.ai_base_url, configured.ai_model)
    with pytest.raises(AIProviderConfigurationInvalid):
        provider.generate(MESSAGES)
