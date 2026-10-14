"""Isolated real persistence/HTTP for source study and confirmed rule versions."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.character_http_support import issue_write_headers
from tests.backend.factories import create_test_app
from tests.backend.test_novel_structure_migration import migrated_novel_structure_database_context

from aiwebnovel.ai_writing.application.models import GeneratedText
from aiwebnovel.ai_writing.errors import AIProviderRateLimited
from aiwebnovel.writing_studio.application.models import (
    WritingConflict,
    WritingInputInvalid,
    WritingNotFound,
    WritingOutputInvalid,
    WritingRule,
)
from aiwebnovel.writing_studio.application.service import parse_analysis, split_reference


def analysis_data(units):
    return {
        "units": [
            {
                "unit_id": unit["id"],
                "quote": unit["text"],
                "function": "延迟信息揭示",
                "effect": "等待回答时动作仍在继续",
                "rationale": "可能让迟疑成为可见动作",
                "transfer": "新情节先放动作再给有限回答",
            }
            for unit in units
        ],
        "long_form_notes": "每章保留一至三个重点，重要冲突留出铺垫和后果，短摘录无法证明全书一致性。",
        "rules": [
            {
                "name": "动作承接",
                "instruction": "重大动作变化之前写明身体或位置的过渡。",
                "applies_to": "动作场景，转场可压缩。",
            }
        ],
    }


@pytest.fixture
def studio(tmp_path: Path):
    with migrated_novel_structure_database_context(tmp_path) as database:
        settings = dict(
            data_root=tmp_path / "app",
            database_url=str(URL.create("sqlite+pysqlite", database=database.path.as_posix())),
            ai_base_url="http://127.0.0.1:18123",
            ai_model="study-test",
            environment="production",
        )
        app = create_test_app(**settings)
        with TestClient(app) as client:
            headers = issue_write_headers(client)
            result = client.post(
                "/api/v1/projects", headers=headers, json={"title": "范文研究隔离小说"}
            )
            assert result.status_code == 201
            project = result.json()["project_id"]
            service = app.state.writing_studio_service
            assert service is not None
            real_provider = service._provider
            calls = []

            def provider(profile, messages, maximum, snapshot):
                calls.append((profile, messages, maximum, snapshot))
                data = json.loads(messages[1].content)
                return GeneratedText(
                    json.dumps(analysis_data(data["units"]), ensure_ascii=False), "study-test"
                )

            service._provider = provider
            yield SimpleNamespace(
                client=client,
                headers=headers,
                project=project,
                app=app,
                base=f"/api/v1/projects/{project}/writing",
                service=service,
                calls=calls,
                real_provider=real_provider,
                settings=settings,
                db=database.path,
            )


def create_reference(w, **changes):
    response = w.client.post(
        w.base + "/references",
        headers=w.headers,
        json={
            "title": "停在门前",
            "text": "他停住脚步。\n她没有立刻回答，手仍搭在门栓上。",
            "granularity": "sentence",
            "profile_id": "default-local",
            **changes,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def analyze(w, reference, **changes):
    return w.client.post(
        w.base + f"/references/{reference['id']}/analyze",
        headers=w.headers,
        json={"expected_version": reference["version"], "cloud_consent": False, **changes},
    )


def test_preview_exact_payload_persists_analysis_and_author_confirmed_versions(studio):
    w = studio
    reference = create_reference(w)
    assert reference["status"] == "ready" and reference["attempts"] == 0
    assert w.calls == []
    assert w.client.get(w.base + "/references").json() == [reference]
    for unit in reference["units"]:
        assert reference["text"][unit["start"] : unit["end"]] == unit["text"]
    response = analyze(w, reference)
    assert response.status_code == 200, response.text
    completed = response.json()
    assert completed["status"] == "analyzed" and completed["attempts"] == 1
    assert completed["version"] == 3
    assert completed["analysis"]["units"][0]["quote"] == "他停住脚步。"
    assert [{"role": m.role, "content": m.content} for m in w.calls[0][1]] == reference["messages"]
    assert w.calls[0][3].model == "study-test"
    assert analyze(w, completed).status_code == 409
    assert len(w.calls) == 1
    assert w.client.get(w.base + f"/references/{reference['id']}").json() == completed
    assert w.client.get(w.base + "/rules").json() == []
    payload = {
        "title": "长篇动作规则",
        "reference_id": reference["id"],
        "rules": completed["analysis"]["rules"],
        "confirmed": False,
    }
    assert w.client.post(w.base + "/rules", headers=w.headers, json=payload).status_code == 422
    payload["confirmed"] = True
    created = w.client.post(w.base + "/rules", headers=w.headers, json=payload)
    assert created.status_code == 201
    first = created.json()
    revised = w.client.post(
        w.base + f"/rules/{first['rule_id']}/versions",
        headers=w.headers,
        json={**payload, "title": "加入后果", "expected_version": 1},
    )
    assert revised.status_code == 201
    second = revised.json()
    assert second["id"] != first["id"] and second["version"] == 2
    assert w.client.get(w.base + "/rules").json() == [first, second]
    selected = w.service.get_rules(w.project, (second["id"], first["id"]))
    assert [v.version for v in selected] == [2, 1]
    stale = w.client.post(
        w.base + f"/rules/{first['rule_id']}/versions",
        headers=w.headers,
        json={**payload, "expected_version": 1},
    )
    assert stale.status_code == 409


def test_cloud_consent_is_for_frozen_model_and_no_prepare_call(studio):
    w = studio
    reader = w.service._model_reader
    w.service._model_reader = lambda profile: replace(
        reader(profile), kind="cloud", base_url="https://example.org/v1"
    )
    reference = create_reference(w)
    assert analyze(w, reference).json()["error"]["code"] == "WRITING_CONSENT_REQUIRED"
    assert w.calls == []
    assert w.service.get_reference(w.project, reference["id"]).version == 1
    assert analyze(w, reference, cloud_consent=True).status_code == 200
    assert w.calls[0][3].kind == "cloud"


def test_changed_model_configuration_rejects_transmission_and_preserves_preview(
    studio, monkeypatch
):
    w = studio
    reference = create_reference(w)
    profile = reference["model_snapshot"]
    changed = w.client.put(
        "/api/v1/ai/models/" + profile["id"],
        headers=w.headers,
        json={
            "name": profile["name"],
            "kind": profile["kind"],
            "base_url": profile["base_url"],
            "model": "different-test-model",
            "max_output_tokens": profile["max_output_tokens"],
        },
    )
    assert changed.status_code == 200
    network = Mock(side_effect=AssertionError("Changed configuration must not transmit"))
    monkeypatch.setattr("aiwebnovel.model_gateway.service.generate_text", network)
    w.service._provider = w.real_provider
    response = analyze(w, reference)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AI_CONTEXT_CHANGED"
    stored = w.client.get(w.base + f"/references/{reference['id']}").json()
    assert stored["status"] == "failed" and stored["last_error"] == "AIContextChanged"
    assert stored["attempts"] == 1
    assert stored["messages"] == reference["messages"]
    assert stored["model_snapshot"] == profile and stored["analysis"] is None
    network.assert_not_called()


@pytest.mark.parametrize(
    "error", [AIProviderRateLimited(), RuntimeError("secret must not be reflected")]
)
def test_failure_persisted_bounded_explicit_retry_and_safe_errors(studio, error):
    w = studio
    reference = create_reference(w)
    calls = []

    def fail(*args):
        calls.append(args)
        raise error

    w.service._provider = fail
    for attempt in range(1, 4):
        response = analyze(w, reference)
        assert response.status_code == 502
        assert "secret" not in response.text
        reference = w.client.get(w.base + f"/references/{reference['id']}").json()
        assert reference["status"] == "failed" and reference["attempts"] == attempt
        assert reference["last_error"] in ("AIProviderRateLimited", "AIProviderUnavailable")
        assert len(calls) == attempt
    assert analyze(w, reference).status_code == 409
    assert len(calls) == 3


def test_output_rejects_unanchored_analysis_and_preserves_source(studio):
    w = studio
    reference = create_reference(w)
    data = analysis_data(reference["units"])
    data["units"][0]["quote"] = "模型编造了一句原文"
    w.service._provider = lambda *args: GeneratedText(json.dumps(data), "study-test")
    response = analyze(w, reference)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "WRITING_OUTPUT_INVALID"
    stored = w.client.get(w.base + f"/references/{reference['id']}").json()
    assert stored["text"] == reference["text"] and stored["analysis"] is None
    assert stored["last_error"] == "WritingOutputInvalid"
    assert w.client.get(w.base + "/rules").json() == []


def test_recovery_never_retransmits_and_concurrent_claims_are_exclusive(studio):
    w = studio
    reference = create_reference(w)
    repository = w.service._repository

    def claim():
        try:
            return repository.claim(w.project, reference["id"], 1)
        except WritingConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim(), range(2)))
    assert sum(result is not None for result in results) == 1
    w.service.recover_interrupted()
    current = w.service.get_reference(w.project, reference["id"])
    assert current.status == "failed" and current.last_error == "WritingAnalysisInterrupted"
    assert current.attempts == 1 and w.calls == []
    repository.fail(w.project, reference["id"], "IgnoredAlreadyFailed")
    assert (
        w.service.get_reference(w.project, reference["id"]).last_error
        == "WritingAnalysisInterrupted"
    )
    with pytest.raises(WritingConflict):
        repository.finish(
            w.project,
            reference["id"],
            parse_analysis(json.dumps(analysis_data(reference["units"])), current.units),
        )


def test_cross_project_missing_and_unanalyzed_rule_sources_are_rejected(studio):
    w = studio
    reference = create_reference(w)
    other = w.client.post(
        "/api/v1/projects", headers=w.headers, json={"title": "另一本隔离小说"}
    ).json()["project_id"]
    assert (
        w.client.get(f"/api/v1/projects/{other}/writing/references/{reference['id']}").status_code
        == 404
    )
    payload = {
        "title": "方法",
        "reference_id": reference["id"],
        "confirmed": True,
        "rules": [{"name": "动作", "instruction": "连接动作", "applies_to": "冲突场景"}],
    }
    assert w.client.post(w.base + "/rules", headers=w.headers, json=payload).status_code == 409
    assert (
        w.client.post(
            f"/api/v1/projects/{other}/writing/rules", headers=w.headers, json=payload
        ).status_code
        == 404
    )
    payload["reference_id"] = None
    result = w.client.post(w.base + "/rules", headers=w.headers, json=payload)
    assert result.status_code == 201
    with pytest.raises(WritingNotFound):
        w.service.get_rules(other, (result.json()["id"],))
    with pytest.raises(WritingInputInvalid):
        w.service.get_rules(w.project, (result.json()["id"],) * 2)
    missing = w.client.post(
        w.base + "/rules/missing/versions",
        headers=w.headers,
        json={**payload, "expected_version": 1},
    )
    assert missing.status_code == 404
    assert w.client.get("/api/v1/projects/invalid/writing/references").status_code == 422


@pytest.mark.parametrize(
    "changes",
    [
        {"text": " "},
        {"title": " "},
        {"text": "句。" * 41},
        {"text": "长" * 8001},
        {"granularity": "word"},
        {"profile_id": "not/a/model"},
        {"unexpected": True},
    ],
)
def test_reference_input_boundaries(studio, changes):
    response = studio.client.post(
        studio.base + "/references",
        headers=studio.headers,
        json={
            "title": "方法",
            "text": "有原文。",
            "granularity": "sentence",
            "profile_id": "default-local",
            **changes,
        },
    )
    assert response.status_code == 422
    assert studio.calls == []


@pytest.mark.parametrize(
    "text,granularity,expected",
    [
        ("  雨😀。\n   风停。  ", "sentence", ("雨😀。", "风停。")),
        ("  第一段。还有后续。\n\n 第二段。 ", "paragraph", ("第一段。还有后续。", "第二段。")),
        ("!\n  ?", "sentence", ("!", "?")),
        ("他说\uff1a“去。”她没动。", "sentence", ("他说\uff1a“去。”", "她没动。")),
        (
            "他问\uff1a\u2018走吗\uff1f\u2019\uff08风停了。\uff09门仍关着。",
            "sentence",
            ("他问\uff1a\u2018走吗\uff1f\u2019", "\uff08风停了。\uff09", "门仍关着。"),
        ),
        (
            "  「雨😀\uff01」\n  『风停了\uff1f』\r\n她摇头。 ",
            "sentence",
            ("「雨😀\uff01」", "『风停了\uff1f』", "她摇头。"),
        ),
        (
            '她喊\uff1a"快\uff01"他答\uff1a"好。"',
            "sentence",
            ('她喊\uff1a"快\uff01"', '他答\uff1a"好。"'),
        ),
    ],
)
def test_source_offsets_are_codepoints_and_exact(text, granularity, expected):
    units = split_reference(text, granularity)
    assert tuple(unit.text for unit in units) == expected
    assert all(text[unit.start : unit.end] == unit.text for unit in units)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: None,
        lambda data: {**data, "extra": "unexpected"},
        lambda data: {**data, "units": []},
        lambda data: {**data, "units": ["invalid"]},
        lambda data: {**data, "units": [{**data["units"][0], "unit_id": "u2"}]},
        lambda data: {**data, "units": [{**data["units"][0], "quote": "unanchored"}]},
        lambda data: {**data, "units": [{**data["units"][0], "effect": " "}]},
        lambda data: {**data, "rules": "invalid"},
        lambda data: {**data, "rules": [None]},
        lambda data: {**data, "rules": []},
    ],
)
def test_analysis_contract_rejects_incomplete_or_untrusted_shape(mutation):
    units = split_reference("门开了。", "sentence")
    data = analysis_data([{"id": "u1", "text": "门开了。"}])
    with pytest.raises(WritingOutputInvalid):
        parse_analysis(json.dumps(mutation(data)), units)


def test_invalid_json_rules_and_empty_source_raise_fixed_errors(studio):
    with pytest.raises(WritingOutputInvalid):
        parse_analysis("not json", ())
    with pytest.raises(WritingInputInvalid):
        split_reference(" \n ", "sentence")
    with pytest.raises(WritingInputInvalid):
        studio.service.save_rules(
            studio.project,
            title="规则",
            reference_id=None,
            rules=(WritingRule("方法", "行动", "全部"),),
            confirmed=True,
            rule_id="existing",
            expected_version=None,
        )
    with pytest.raises(WritingInputInvalid):
        studio.service.create_reference(
            studio.project,
            title="方法",
            text="句子",
            granularity="word",
            profile_id="default-local",
        )


def test_saved_references_rules_and_interrupted_analysis_survive_actual_restart(studio):
    w = studio
    completed = analyze(w, create_reference(w)).json()
    saved = w.client.post(
        w.base + "/rules",
        headers=w.headers,
        json={
            "title": "长期方法",
            "reference_id": completed["id"],
            "confirmed": True,
            "rules": completed["analysis"]["rules"],
        },
    ).json()
    interrupted = create_reference(w, title="中断示例")
    w.service._repository.claim(w.project, interrupted["id"], 1)
    w.app.state.ai_workflow_runtime.close()
    with TestClient(create_test_app(**w.settings)) as restarted:
        assert restarted.get(w.base + f"/references/{completed['id']}").json() == completed
        assert restarted.get(w.base + "/rules").json() == [saved]
        recovered = restarted.get(w.base + f"/references/{interrupted['id']}").json()
        assert recovered["status"] == "failed"
        assert recovered["last_error"] == "WritingAnalysisInterrupted"
        assert recovered["attempts"] == 1
    assert len(w.calls) == 1


def test_confirmed_rule_versions_are_immutable_in_database(studio):
    w = studio
    result = w.client.post(
        w.base + "/rules",
        headers=w.headers,
        json={
            "title": "作者规则",
            "reference_id": None,
            "confirmed": True,
            "rules": [
                {"name": "方法", "instruction": "重要动作必须衔接", "applies_to": "冲突场景"}
            ],
        },
    )
    assert result.status_code == 201
    saved = result.json()
    with closing(sqlite3.connect(w.db)) as connection:
        for statement in (
            "UPDATE writing_rule_versions SET version=2 WHERE id=?",
            "DELETE FROM writing_rule_versions WHERE id=?",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(statement, (saved["id"],))
            connection.rollback()
    assert w.client.get(w.base + "/rules").json() == [saved]


def test_project_ownership_query_runs_while_competing_writers_are_excluded(studio, monkeypatch):
    w = studio
    reference = create_reference(w)
    repository = w.service._repository
    read_project = repository._projects.get_project
    checked = []

    def query_under_write_lock(query):
        with (
            closing(sqlite3.connect(w.db, timeout=0)) as competing_writer,
            pytest.raises(sqlite3.OperationalError, match="locked"),
        ):
            competing_writer.execute("BEGIN IMMEDIATE")
        checked.append(query.project_id)
        return read_project(query)

    monkeypatch.setattr(repository._projects, "get_project", query_under_write_lock)
    claimed = repository.claim(w.project, reference["id"], reference["version"])
    assert claimed.status == "analyzing"
    assert checked == [w.project]


def test_deleted_project_hides_references_and_rules_without_erasing_versions(studio):
    w = studio
    reference = analyze(w, create_reference(w)).json()
    payload = {
        "title": "方法",
        "reference_id": reference["id"],
        "confirmed": True,
        "rules": reference["analysis"]["rules"],
    }
    saved = w.client.post(w.base + "/rules", headers=w.headers, json=payload).json()
    interrupted = create_reference(w, title="删除前正在分析")
    w.service._repository.claim(w.project, interrupted["id"], interrupted["version"])
    with closing(sqlite3.connect(w.db)) as connection:
        before = {
            table: connection.execute(f"SELECT * FROM {table}").fetchall()
            for table in ("writing_references", "writing_rule_versions")
        }
    project = w.client.get(f"/api/v1/projects/{w.project}")
    deleted = w.client.post(
        f"/api/v1/projects/{w.project}/delete",
        headers={**w.headers, "If-Match": project.headers["etag"]},
    )
    assert deleted.status_code == 200
    w.service.recover_interrupted()
    for suffix in ("/references", f"/references/{reference['id']}", "/rules"):
        response = w.client.get(w.base + suffix)
        assert response.status_code == 404 and reference["text"] not in response.text
    assert analyze(w, reference).status_code == 404
    assert w.client.post(w.base + "/rules", headers=w.headers, json=payload).status_code == 404
    with pytest.raises(WritingNotFound):
        w.service.get_rules(w.project, (saved["id"],))
    with closing(sqlite3.connect(w.db)) as connection:
        assert {
            table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in before
        } == before


def test_http_guards_service_readiness_and_model_errors_are_safe(studio):
    from aiwebnovel.model_gateway.errors import ModelProfileNotFound

    w = studio
    payload = {"title": "示例", "text": "门响了。", "profile_id": "default-local"}
    assert w.client.post(w.base + "/references", json=payload).status_code == 403
    assert (
        w.client.post(
            w.base + "/references",
            headers={**w.headers, "Origin": "https://attacker.example"},
            json=payload,
        ).status_code
        == 403
    )
    assert (
        w.client.post(
            w.base + "/references",
            headers={**w.headers, "Content-Type": "text/plain"},
            content=json.dumps(payload),
        ).status_code
        == 415
    )
    w.app.state.ai_workflow_schema_required = True
    response = w.client.get(w.base + "/references")
    assert (
        response.status_code == 503
        and response.json()["error"]["code"] == "AI_WORKFLOW_SCHEMA_REQUIRED"
    )
    w.app.state.ai_workflow_schema_required = False
    w.app.state.writing_studio_service = None
    assert (
        w.client.get(w.base + "/references").json()["error"]["code"] == "WRITING_STUDIO_UNAVAILABLE"
    )
    w.app.state.writing_studio_service = w.service

    def missing(profile):
        raise ModelProfileNotFound

    w.service._model_reader = missing
    response = w.client.post(w.base + "/references", headers=w.headers, json=payload)
    assert response.status_code == 404
    assert w.calls == []
