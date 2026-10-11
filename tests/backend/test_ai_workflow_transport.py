"""Real cloud workflow HTTP chain with owned storage and a controlled wire transport."""

import http.client
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.character_http_support import issue_write_headers
from tests.backend.factories import create_test_app
from tests.backend.test_model_gateway import FakeProtector
from tests.backend.test_novel_structure_migration import migrated_novel_structure_database_context

from aiwebnovel.model_gateway import provider

TEXT = "测试候选:旅人收起雨伞，沿着青石小路走向渡口。" * 10
KEY = "isolated-transport-placeholder-key"


@pytest.mark.parametrize(
    "status,code,persisted",
    [
        (200, None, None),
        (401, "AI_PROVIDER_AUTH_FAILED", "AIProviderAuthFailed"),
        (402, "AI_PROVIDER_PAYMENT_REQUIRED", "AIProviderPaymentRequired"),
        (403, "AI_PROVIDER_ACCESS_DENIED", "AIProviderAccessDenied"),
        (404, "AI_PROVIDER_ENDPOINT_INVALID", "AIProviderEndpointInvalid"),
        (422, "AI_PROVIDER_REQUEST_REJECTED", "AIProviderRequestRejected"),
        (429, "AI_PROVIDER_RATE_LIMITED", "AIProviderRateLimited"),
        (500, "AI_PROVIDER_UNAVAILABLE", "AIProviderUnavailable"),
    ],
)
def test_cloud_task_reaches_http_provider_and_recovers_only_on_author_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    code: str | None,
    persisted: str | None,
) -> None:
    received = []
    responses = [status, 200]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            payload = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, dict(self.headers), json.loads(payload)))
            response_status = responses.pop(0)
            body = json.dumps(
                {"choices": [{"message": {"content": TEXT}}]}
                if response_status == 200
                else {"error": {"message": "PRIVATE_UPSTREAM_DETAIL"}}
            ).encode()
            self.send_response(response_status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    worker.start()

    def test_connection(host, port, *, timeout):
        assert host == "api.example.com" and port == 443
        return http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=timeout)

    # Only test wiring substitutes the network destination; the application's
    # cloud validation, model snapshot, credentials, payload and workflow stay real.
    monkeypatch.setattr(provider, "_PublicHTTPSConnection", test_connection)
    try:
        with migrated_novel_structure_database_context(tmp_path) as database:
            app = create_test_app(
                data_root=tmp_path / "app",
                database_url=str(URL.create("sqlite+pysqlite", database=database.path.as_posix())),
                environment="production",
            )
            with TestClient(app) as client:
                headers = issue_write_headers(client)
                app.state.model_gateway_service._protector = FakeProtector()
                profile = client.post(
                    "/api/v1/ai/models",
                    headers=headers,
                    json={
                        "name": "隔离云端模型",
                        "kind": "cloud",
                        "base_url": "https://api.example.com/v1/chat/completions/",
                        "model": "isolated-cloud-model",
                        "max_output_tokens": 2048,
                        "api_key": KEY,
                    },
                )
                assert profile.status_code == 201, profile.text
                assert KEY not in profile.text
                project = client.post(
                    "/api/v1/projects", headers=headers, json={"title": "隔离请求测试"}
                )
                assert project.status_code == 201
                project_path = f"/api/v1/projects/{project.json()['project_id']}"
                volume = client.post(
                    project_path + "/volumes",
                    headers=headers,
                    json={
                        "title": "测试卷",
                        "summary": "",
                        "position": 1,
                    },
                )
                assert volume.status_code == 201
                chapter = client.post(
                    project_path + f"/volumes/{volume.json()['volume_id']}/chapters",
                    headers=headers,
                    json={"title": "测试章", "summary": "", "position": 1},
                )
                assert chapter.status_code == 201
                base = f"/api/v1/chapters/{chapter.json()['chapter_id']}"
                initial = "仅测试使用的正文。"
                saved = client.put(
                    base + "/content",
                    headers={**headers, "If-Match": chapter.headers["ETag"]},
                    json={"content": initial},
                )
                assert saved.status_code == 200
                prepared = client.post(
                    base + "/ai/runs",
                    headers=headers,
                    json={
                        "profile_id": profile.json()["id"],
                        "instruction": "增加现场感",
                        "max_steps": 2,
                        "max_output_characters": 600,
                    },
                )
                assert prepared.status_code == 201, prepared.text
                task_path = base + f"/ai/runs/{prepared.json()['run_id']}"
                assert received == []
                result = client.post(task_path + "/generate", headers=headers, json={})
                assert len(received) == 1
                path, outgoing_headers, payload = received[0]
                assert path == "/v1/chat/completions"
                assert outgoing_headers["Authorization"] == f"Bearer {KEY}"
                assert payload["model"] == "isolated-cloud-model"
                assert payload["max_tokens"] == 2048 and payload["stream"] is False
                assert initial in json.dumps(payload, ensure_ascii=False)
                assert "增加现场感" in json.dumps(payload, ensure_ascii=False)
                assert KEY not in json.dumps(payload)
                assert client.get(base + "/content").json()["content"] == initial
                if status != 200:
                    assert result.status_code == 502
                    assert result.json()["error"]["code"] == code
                    assert "PRIVATE_UPSTREAM_DETAIL" not in result.text
                    interrupted = client.get(task_path).json()
                    assert interrupted["status"] == "paused"
                    assert interrupted["last_error"] == persisted
                    assert interrupted["generated_steps"] == 1
                    assert interrupted["candidates"] == []
                    assert len(received) == 1
                    resumed = client.post(task_path + "/resume", headers=headers, json={})
                    assert resumed.status_code == 200
                    assert resumed.json()["status"] == "ready"
                    assert len(received) == 1
                    result = client.post(task_path + "/generate", headers=headers, json={})
                    assert len(received) == 2
                assert result.status_code == 200, result.text
                candidate = result.json()["candidates"][0]
                assert candidate["status"] == "pending" and candidate["text"] == TEXT
                assert client.get(task_path).json() == result.json()
                assert client.get(base + "/content").json()["content"] == initial
                assert KEY not in result.text
                assert (
                    client.post(task_path + "/generate", headers=headers, json={}).status_code
                    == 409
                )
                assert len(received) == (1 if status == 200 else 2)
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()
        assert not worker.is_alive()
