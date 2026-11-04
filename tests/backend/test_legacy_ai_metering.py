"""B-1: legacy /ai/continue and /ai/rewrite share the workflow ledger and budget rules.

Only the outgoing HTTP call is faked, so attribution, budget check, reservation and
ledger settlement all run through the composed provider.
"""

import pytest
from tests.backend.test_ai_workflow import TEXT, workflow
from tests.backend.test_candidate_edits_budget import put_budget, put_price
from tests.backend.test_usage_ledger import real_provider, rows, transport

from aiwebnovel.ai_writing.application.models import GeneratedText, ProviderUsage
from aiwebnovel.ai_writing.application.services import AIWritingService
from aiwebnovel.ai_writing.composition import UnmeteredSendRefused
from aiwebnovel.ai_writing.errors import AIProviderTimeout
from aiwebnovel.usage.models import UsageLedgerUnavailable

__all__ = ["workflow"]


def legacy(w, operation, expected, **body):
    response = w.client.post(w.base + f"/ai/{operation}", headers=w.headers, json=body)
    assert response.status_code == expected, response.text
    return response.json()


def test_legacy_continue_and_rewrite_are_recorded_once_with_reported_usage(workflow, monkeypatch):
    w = workflow
    real_provider(w)
    calls = transport(
        monkeypatch,
        GeneratedText(TEXT, "workflow-test", ProviderUsage(90, 40, 130)),
        GeneratedText(TEXT, "workflow-test"),
    )
    continued = legacy(w, "continue", 200)
    rewritten = legacy(w, "rewrite", 200, text="雨😀雨。")
    # Response fields stay compatible with old clients.
    assert continued["text"] == TEXT and continued["operation"] == "continue"
    assert rewritten["operation"] == "rewrite" and "context" in rewritten
    assert len(calls) == 2
    assert all(call[2].operation == "generation" for call in calls)
    assert all(call[2].chapter_id == w.chapter for call in calls)
    assert calls[0][2].task_id != calls[1][2].task_id
    stored = rows(w)
    assert [row["status"] for row in stored] == ["completed", "completed"]
    assert [row["usage_source"] for row in stored] == ["provider_reported", "unknown"]
    assert stored[0]["reported_total_tokens"] == 130
    usage = w.client.get(f"/api/v1/projects/{w.project}/usage").json()
    assert usage["totals"]["attempts"] == 2


def test_legacy_failure_and_timeout_settle_their_rows(workflow, monkeypatch):
    w = workflow
    real_provider(w)
    calls = transport(monkeypatch, AIProviderTimeout())
    assert legacy(w, "continue", 504)["error"]["code"] == "AI_PROVIDER_TIMEOUT"
    assert len(calls) == 1
    assert [row["status"] for row in rows(w)] == ["timeout"]


def test_strict_budget_refuses_legacy_requests_before_sending(workflow, monkeypatch):
    w = workflow
    real_provider(w)
    calls = transport(monkeypatch)
    put_budget(w, task_limit="1")
    refused = legacy(w, "continue", 409)
    assert refused["error"]["code"] == "AI_BUDGET_REFUSED"
    assert legacy(w, "rewrite", 409, text="雨")["error"]["code"] == "AI_BUDGET_REFUSED"
    assert calls == [] and rows(w) == []
    put_price(w, inp="1000", out="1000")
    put_budget(w, version=1, task_limit="0.01")
    assert legacy(w, "continue", 409)["error"]["code"] == "AI_BUDGET_REFUSED"
    assert calls == [] and rows(w) == []


def test_legacy_service_without_ledger_never_sends(workflow):
    w = workflow
    service = AIWritingService(
        w.app.state.ai_writing_service._context_builder, UnmeteredSendRefused()
    )
    with pytest.raises(UsageLedgerUnavailable):
        service.continue_chapter(w.chapter)
    assert not w.calls


def test_gateway_errors_keep_their_contract_on_legacy_routes():
    from aiwebnovel.ai_writing.web import map_error
    from aiwebnovel.model_gateway.errors import ModelCredentialUnavailable

    mapped = map_error(ModelCredentialUnavailable())
    assert mapped.status_code == 503 and mapped.code == "MODEL_CREDENTIAL_UNAVAILABLE"
