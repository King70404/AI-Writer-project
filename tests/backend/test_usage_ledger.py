"""Real migrated SQLite and HTTP prove the settle-once model usage ledger (B1 / F06).

Requests are intercepted at the gateway transport (``generate_text``), so the real
composed provider, attribution, ledger rows and read API are exercised; no network.
"""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tests.backend.test_ai_workflow import TEXT, create_run, workflow
from tests.backend.test_story_memory import prepare, send
from tests.backend.test_writing_studio import analysis_data, analyze, create_reference, studio

from aiwebnovel.ai_writing.application.models import (
    GeneratedText,
    GenerationMessage,
    ProviderUsage,
    parse_provider_usage,
)
from aiwebnovel.ai_writing.errors import (
    AIProviderAuthFailed,
    AIProviderInvalidResponse,
    AIProviderTimeout,
)
from aiwebnovel.core.errors import AppError
from aiwebnovel.model_gateway.models import ModelProfile
from aiwebnovel.usage.attribution import current_usage_attribution, usage_attribution
from aiwebnovel.usage.models import UsageAttributionMissing, UsageLedgerUnavailable
from aiwebnovel.usage.persistence import AttemptOutcome, AttemptStart, SqlAlchemyUsageLedger
from aiwebnovel.usage.service import UsageLedgerService
from aiwebnovel.usage.web import get_usage_service

__all__ = ["studio", "workflow"]

PROFILE = ModelProfile("default-local", "本地", "local", "http://127.0.0.1:1", "m", 64, False)


def transport(monkeypatch, *results):
    """Replace only the outgoing HTTP call; each result is returned or raised in order."""
    calls = []
    queue = list(results)

    def fake(profile, messages, *, api_key, max_output_tokens):
        calls.append((profile.model, messages, current_usage_attribution()))
        result = queue.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr("aiwebnovel.model_gateway.service.generate_text", fake)
    return calls


def real_provider(w):
    # The workflow fixture swaps the workflow provider; story memory keeps the composed one.
    w.service._provider = w.app.state.story_memory_service._provider


def usage(w, expected=200, **params):
    response = w.client.get(f"/api/v1/projects/{w.project}/usage", params=params)
    assert response.status_code == expected, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def rows(w):
    with closing(sqlite3.connect(w.db)) as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute("SELECT * FROM model_usage_attempts ORDER BY rowid")
        ]


def send_generation(w, run, expected):
    response = w.client.post(
        w.base + f"/ai/runs/{run['run_id']}/generate", headers=w.headers, json={}
    )
    assert response.status_code == expected, response.text
    return response.json()


def discard(w, run):
    pending = next(item for item in run["candidates"] if item["status"] == "pending")
    response = w.client.post(
        w.base + f"/ai/candidates/{pending['candidate_id']}/discard", headers=w.headers, json={}
    )
    assert response.status_code == 200, response.text
    return response.json()


def resume(w, run):
    response = w.client.post(
        w.base + f"/ai/runs/{run['run_id']}/resume", headers=w.headers, json={}
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}, (10, 5, 15)),
        ({"usage": {"input_tokens": 7, "output_tokens": 3}}, (7, 3, None)),
        ({"usage": {"completion_tokens": 4}}, (None, 4, None)),
        ({"usage": {"prompt_tokens": -1, "completion_tokens": True, "total_tokens": "9"}}, None),
        ({"usage": {"prompt_tokens": 2_000_000_000}}, None),
        ({"usage": None}, None),
        ({"usage": []}, None),
        ({}, None),
        ([], None),
    ],
)
def test_provider_usage_is_read_exactly_and_never_guessed(data, expected):
    parsed = parse_provider_usage(data)
    if expected is None:
        assert parsed is None
    else:
        assert parsed == ProviderUsage(*expected)


def test_generated_text_rejects_untyped_usage():
    with pytest.raises(AIProviderInvalidResponse):
        GeneratedText("正文", "m", {"prompt_tokens": 1})  # type: ignore[arg-type]
    assert GeneratedText("正文", "m").usage is None


def test_reported_unknown_failed_and_timeout_attempts_are_recorded_once(workflow, monkeypatch):
    w = workflow
    real_provider(w)
    calls = transport(
        monkeypatch,
        GeneratedText(TEXT, "workflow-test", ProviderUsage(120, 80, 200)),
        GeneratedText(TEXT, "workflow-test"),
        AIProviderAuthFailed(),
        AIProviderTimeout(),
    )
    empty = usage(w)
    assert empty["totals"]["attempts"] == 0 and empty["items"] == []
    assert empty["estimate_method"] == "local_characters_v1"
    run = create_run(w, max_steps=4, max_output_characters=1200)
    assert rows(w) == []  # Preparing a task never sends or records a request.
    first = send_generation(w, run, 200)
    discard(w, first)
    discard(w, send_generation(w, first, 200))
    failed = send_generation(w, first, 502)
    assert failed["error"]["code"] == "AI_PROVIDER_AUTH_FAILED"
    timed_out = send_generation(w, resume(w, run), 504)
    assert timed_out["error"]["code"] == "AI_PROVIDER_TIMEOUT"
    assert len(calls) == 4
    assert all(item[2].operation == "generation" for item in calls)
    assert all(item[2].task_id == run["run_id"] for item in calls)

    stored = rows(w)
    assert [row["status"] for row in stored] == ["completed", "completed", "failed", "timeout"]
    assert [row["usage_source"] for row in stored] == [
        "provider_reported",
        "unknown",
        "unknown",
        "unknown",
    ]
    assert (stored[0]["reported_input_tokens"], stored[0]["reported_output_tokens"]) == (120, 80)
    assert stored[0]["reported_total_tokens"] == 200
    assert all(row["reported_output_tokens"] is None for row in stored[1:])
    assert [row["error_code"] for row in stored] == [
        None,
        None,
        "AIProviderAuthFailed",
        "AIProviderTimeout",
    ]
    assert stored[0]["output_characters"] == len(TEXT) and stored[2]["output_characters"] is None
    assert all(row["chapter_id"] == w.chapter for row in stored)
    assert all(row["project_id"] == w.project for row in stored)
    assert all(
        row["model_name"] == "workflow-test" and row["model_kind"] == "local" for row in stored
    )
    sent = calls[0][1]
    assert stored[0]["input_characters"] == sum(len(item.content) for item in sent)
    # No prose, prompt or response is persisted in the ledger.
    assert TEXT[:20] not in json.dumps(stored, ensure_ascii=False)

    page = usage(w)
    totals = page["totals"]
    assert totals["attempts"] == 4 and totals["completed"] == 2
    assert (totals["failed"], totals["timeout"], totals["running"]) == (1, 1, 0)
    assert (totals["reported_attempts"], totals["unknown_attempts"]) == (1, 3)
    # Unknown attempts never count as zero tokens; sums cover reported values only.
    assert totals["reported_input_tokens"] == 120 and totals["reported_output_tokens"] == 80
    assert totals["incomplete_reports"] == 0
    assert totals["output_characters"] == 2 * len(TEXT)
    assert [item["operation"] for item in page["by_operation"]] == ["generation"]
    assert page["by_model"][0]["model_name"] == "workflow-test"
    assert [item["status"] for item in page["items"]] == [
        "timeout",
        "failed",
        "completed",
        "completed",
    ]
    assert page["total"] == 4 and page["next_offset"] is None
    assert all(item["duration_ms"] is not None for item in page["items"])

    paged = usage(w, limit=3)
    assert len(paged["items"]) == 3 and paged["next_offset"] == 3
    rest = usage(w, offset=3, limit=3)
    assert len(rest["items"]) == 1 and rest["next_offset"] is None
    chapter = usage(w, chapter_id=w.chapter)
    assert chapter["chapter_id"] == w.chapter and chapter["totals"]["attempts"] == 4
    task = usage(w, task_id=run["run_id"])
    assert task["task_id"] == run["run_id"] and task["totals"]["attempts"] == 4
    assert usage(w, task_id="00000000-0000-0000-0000-000000000000")["totals"]["attempts"] == 0

    with closing(sqlite3.connect(w.db)) as connection:
        for statement in (
            "UPDATE model_usage_attempts SET reported_input_tokens = 1",
            "UPDATE model_usage_attempts SET status = 'running', finished_at = NULL,"
            " duration_ms = NULL, output_characters = NULL, error_code = NULL,"
            " usage_source = 'unknown', reported_input_tokens = NULL,"
            " reported_output_tokens = NULL, reported_total_tokens = NULL",
            "DELETE FROM model_usage_attempts",
        ):
            with pytest.raises(sqlite3.DatabaseError):
                connection.execute(statement)
    assert rows(w) == stored


def test_local_pre_send_failures_write_no_ledger_row(workflow, monkeypatch):
    w = workflow
    real_provider(w)
    network = Mock(side_effect=AssertionError("must not transmit"))
    monkeypatch.setattr("aiwebnovel.model_gateway.service.generate_text", network)
    run = create_run(w)
    with pytest.raises(UsageAttributionMissing):
        w.service._provider("default-local", (GenerationMessage("user", "x"),), 300, None)
    with (
        usage_attribution("generation", run["run_id"], chapter_id=w.chapter),
        pytest.raises(Exception) as raised,
    ):
        w.service._provider("missing-profile", (GenerationMessage("user", "x"),), 300, None)
    assert type(raised.value).__name__ == "ModelProfileNotFound"
    network.assert_not_called()
    assert rows(w) == []


def test_reference_analysis_and_story_review_are_attributed(studio, monkeypatch):
    w = studio
    w.service._provider = w.real_provider
    reference = create_reference(w)
    units = json.loads(reference["messages"][1]["content"])["units"]
    calls = transport(
        monkeypatch,
        GeneratedText(
            json.dumps(analysis_data(units), ensure_ascii=False),
            "study-test",
            ProviderUsage(None, 42, None),
        ),
    )
    response = analyze(w, reference)
    assert response.status_code == 200, response.text
    assert calls[0][2].operation == "reference_analysis"
    page = usage(w)
    item = page["items"][0]
    assert item["operation"] == "reference_analysis" and item["chapter_id"] is None
    assert item["task_id"] == reference["id"]
    assert item["usage_source"] == "provider_reported"
    assert (item["reported_input_tokens"], item["reported_output_tokens"]) == (None, 42)
    assert page["totals"]["incomplete_reports"] == 1
    assert page["by_operation"][0]["operation"] == "reference_analysis"


def test_story_review_is_attributed_to_its_chapter(workflow, monkeypatch):
    w = workflow
    review = prepare(w)
    result = json.dumps({"summary": "无问题", "facts": [], "findings": []}, ensure_ascii=False)
    calls = transport(monkeypatch, GeneratedText(result, "workflow-test"))
    response = send(w, review)
    assert response.status_code == 200, response.text
    attribution = calls[0][2]
    assert attribution.operation == "story_review"
    assert (attribution.project_id, attribution.chapter_id) == (w.project, w.chapter)
    item = usage(w, chapter_id=w.chapter)["items"][0]
    assert item["operation"] == "story_review" and item["task_id"] == review["id"]
    assert item["usage_source"] == "unknown"


def test_interrupted_rows_are_recovered_and_settle_only_once(workflow):
    w = workflow
    ledger = SqlAlchemyUsageLedger(
        w.app.state.workbench_service._repository._sessions,
        w.app.state.workbench_service._repository._projects,
    )
    with usage_attribution("generation", "task-1", chapter_id=w.chapter) as attribution:
        first = ledger.start(AttemptStart(attribution, "p", "local", "m", 10))
        second = ledger.start(AttemptStart(attribution, "p", "cloud", "m", 5))
    assert usage(w)["totals"]["running"] == 2
    outcome = AttemptOutcome("completed", None, ProviderUsage(1, 2, 3), 4)
    assert ledger.settle(first, outcome) is True
    assert ledger.settle(first, AttemptOutcome("failed", "X", None, None)) is False
    assert ledger.settle("missing", outcome) is False
    assert ledger.recover_interrupted() == 1
    assert ledger.recover_interrupted() == 0
    stored = {row["id"]: row for row in rows(w)}
    assert stored[first]["status"] == "completed" and stored[first]["reported_total_tokens"] == 3
    assert stored[second]["status"] == "interrupted"
    assert stored[second]["usage_source"] == "unknown"
    assert ledger.settle(second, outcome) is False
    page = usage(w)
    assert page["totals"]["interrupted"] == 1 and page["totals"]["unknown_attempts"] == 1
    assert {item["model_kind"] for item in page["by_model"]} == {"local", "cloud"}


def test_ledger_start_rejects_unresolvable_attribution(workflow):
    w = workflow
    repository = w.app.state.workbench_service._repository
    ledger = SqlAlchemyUsageLedger(repository._sessions, repository._projects)
    other = w.client.post("/api/v1/projects", headers=w.headers, json={"title": "另一本"})
    cases = [
        usage_attribution("generation", "t"),
        usage_attribution("generation", "t", chapter_id="chp_00000000000000000000000000"),
        usage_attribution(
            "generation", "t", project_id=other.json()["project_id"], chapter_id=w.chapter
        ),
        usage_attribution("generation", "t", chapter_id="not-a-chapter"),
        usage_attribution("reference_analysis", "t", project_id="prj_00000000000000000000000000"),
    ]
    for case in cases:
        with case as attribution, pytest.raises(UsageLedgerUnavailable):
            ledger.start(AttemptStart(attribution, "p", "local", "m", 1))
    assert rows(w) == []


class _Ledger:
    def __init__(self, *, start_error=None, settle_error=None):
        self.started = []
        self.settled = []
        self.start_error = start_error
        self.settle_error = settle_error

    def start(self, attempt):
        if self.start_error:
            raise self.start_error
        self.started.append(attempt)
        return "a1"

    def settle(self, attempt_id, outcome):
        if self.settle_error:
            raise self.settle_error
        self.settled.append((attempt_id, outcome))
        return True

    def recover_interrupted(self):
        return 0

    def page(self, *args):
        raise AssertionError


def test_metering_fails_closed_before_send_and_keeps_paid_results():
    messages = (GenerationMessage("user", "一二三"),)
    blocked = UsageLedgerService(_Ledger(start_error=UsageLedgerUnavailable()))
    network = Mock()

    def send(before_send):
        before_send(PROFILE)
        network()
        return GeneratedText("结果", "m")

    with (
        usage_attribution("generation", "t", chapter_id="c"),
        pytest.raises(UsageLedgerUnavailable),
    ):
        blocked.metered(messages, send)
    network.assert_not_called()

    broken = _Ledger(settle_error=RuntimeError("disk"))
    with usage_attribution("generation", "t", chapter_id="c"):
        assert UsageLedgerService(broken).metered(messages, send).text == "结果"

    ledger = _Ledger()
    service = UsageLedgerService(ledger)
    with usage_attribution("generation", "t", chapter_id="c"):
        with pytest.raises(RuntimeError):
            service.metered(messages, lambda before: (before(PROFILE), _raise())[1])
        with pytest.raises(AIProviderAuthFailed):
            service.metered(messages, lambda before: _raise(AIProviderAuthFailed()))
        # A sender that never reaches the request opens and settles nothing.
        assert service.metered(messages, lambda before: GeneratedText("无", "m")).text == "无"
    assert ledger.started[0].input_characters == 3
    assert ledger.settled[0][1] == AttemptOutcome("failed", "AIProviderUnavailable", None, None)
    assert len(ledger.settled) == 1  # Failure before the request opened no row.
    assert current_usage_attribution() is None


def _raise(error=None):
    raise error or RuntimeError("secret text must not be stored")


def test_usage_http_query_guards_and_service_readiness(workflow):
    w = workflow
    base = f"/api/v1/projects/{w.project}/usage"
    for params in (
        {"limit": "0"},
        {"limit": "101"},
        {"offset": "-1"},
        {"offset": "1e3"},
        {"offset": ""},
        {"unknown": "1"},
        {"task_id": "x" * 37},
        {"task_id": "bad id"},
        {"chapter_id": "c" * 61},
        {"chapter_id": "not-a-chapter"},
    ):
        response = w.client.get(base, params=params)
        assert response.status_code == 422, params
        assert response.json()["error"]["code"] == "INVALID_USAGE_QUERY"
    assert w.client.get(base + "?limit=1&limit=2").status_code == 422
    assert w.client.get("/api/v1/projects/bad/usage").status_code == 422
    missing = w.client.get("/api/v1/projects/prj_00000000000000000000000000/usage")
    assert missing.status_code in {404, 422}
    deleted = w.client.post("/api/v1/projects", headers=w.headers, json={"title": "删"})
    deleted_id = deleted.json()["project_id"]
    removal = w.client.delete(
        f"/api/v1/projects/{deleted_id}",
        headers={**w.headers, "If-Match": deleted.headers["etag"]},
    )
    if removal.status_code in {200, 204}:
        assert w.client.get(f"/api/v1/projects/{deleted_id}/usage").status_code == 404

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(AppError) as unavailable:
        get_usage_service(request)  # type: ignore[arg-type]
    assert unavailable.value.code == "USAGE_LEDGER_UNAVAILABLE"
    request.app.state.ai_workflow_schema_required = True
    with pytest.raises(AppError) as schema:
        get_usage_service(request)  # type: ignore[arg-type]
    assert schema.value.code == "AI_WORKFLOW_SCHEMA_REQUIRED"


def test_settle_duration_uses_timezone_aware_clock(workflow):
    w = workflow
    repository = w.app.state.workbench_service._repository
    moments = iter(
        [datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC), datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC)]
    )
    ledger = SqlAlchemyUsageLedger(
        repository._sessions, repository._projects, lambda: next(moments)
    )
    with usage_attribution("generation", "t", chapter_id=w.chapter) as attribution:
        attempt = ledger.start(AttemptStart(attribution, "p", "local", "m", 1))
    ledger.settle(attempt, AttemptOutcome("failed", "E" * 200, None, None))
    stored = rows(w)[0]
    assert stored["duration_ms"] == 2000 and len(stored["error_code"]) == 80
