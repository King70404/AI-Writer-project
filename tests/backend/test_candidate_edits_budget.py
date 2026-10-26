"""B2: immutable author candidate edits, author-entered prices, budgets and drafts isolation.

Real migrated SQLite and HTTP. Outgoing model requests are intercepted at the gateway
transport, so the composed provider, budget check, reservation and ledger all run; no
network request is made and no test sends anything the budget refuses.
"""

import json
import os
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.backend.test_ai_workflow import TEXT, create_run, generate, workflow
from tests.backend.test_usage_ledger import real_provider, rows, send_generation, transport
from tests.backend.test_writing_studio import analysis_data, analyze, create_reference, studio

from aiwebnovel.ai_writing.application.models import (
    GeneratedText,
    GenerationMessage,
    ProviderUsage,
)
from aiwebnovel.ai_writing.application.workflow import AIWorkflowService
from aiwebnovel.ai_writing.errors import AIContextChanged, InvalidAIInput
from aiwebnovel.core.errors import AppError
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.storage.instance import StorageInstanceService, StorageInstanceUnavailable
from aiwebnovel.storage.instance_web import create_storage_instance_router
from aiwebnovel.usage.attribution import UsageAttribution
from aiwebnovel.usage.budget import (
    AttemptCost,
    Budget,
    BudgetInputInvalid,
    BudgetRefused,
    Price,
    SendRequest,
    Spend,
    cost_micros,
    evaluate,
    format_amount,
    input_tokens_upper,
    parse_amount,
    parse_currency,
    settled_cost,
    summarize,
)
from aiwebnovel.usage.budget_persistence import SqlAlchemyBudgetStore, month_start
from aiwebnovel.usage.budget_web import get_budget_service
from aiwebnovel.usage.composition import compose_usage_ledger
from aiwebnovel.usage.models import UsageLedgerUnavailable
from aiwebnovel.usage.persistence import SqlAlchemyUsageLedger
from aiwebnovel.usage.records import AttemptStart

__all__ = ["studio", "workflow"]

EDITED = "作者改过，" + TEXT[:120]


def pending(run):
    return next(item for item in run["candidates"] if item["status"] == "pending")


def edit(w, candidate_id, text, parent=None, expected=201):
    response = w.client.post(
        w.base + f"/ai/candidates/{candidate_id}/edits",
        headers=w.headers,
        json={"text": text, "parent_edit_id": parent},
    )
    assert response.status_code == expected, response.text
    return response.json()


def adopt(w, candidate_id, key, version, edit_id=None, expected=200):
    response = w.client.post(
        w.base + f"/ai/candidates/{candidate_id}/adopt",
        headers={**w.headers, "If-Match": f'"{version}"'},
        json={"idempotency_key": key, "edit_id": edit_id},
    )
    assert response.status_code == expected, response.text
    return response.json()


def content(w):
    return w.client.get(w.base + "/content")


def count(w, table):
    with closing(sqlite3.connect(w.db)) as connection:
        return connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def put_price(
    w, version=0, currency="CNY", inp="2", out="8", expected=200, profile="default-local"
):
    response = w.client.put(
        f"/api/v1/ai/models/{profile}/price",
        headers=w.headers,
        json={
            "expected_version": version,
            "currency": currency,
            "input_per_million": inp,
            "output_per_million": out,
        },
    )
    assert response.status_code == expected, response.text
    return response.json()


def put_budget(w, version=0, expected=200, **values):
    body = {"expected_version": version, "mode": "strict", "currency": "CNY", **values}
    response = w.client.put(f"/api/v1/projects/{w.project}/budget", headers=w.headers, json=body)
    assert response.status_code == expected, response.text
    return response.json()


def estimate(w, run, expected=200):
    response = w.client.get(w.base + f"/ai/runs/{run['run_id']}/estimate")
    assert response.status_code == expected, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


# -- candidate edits ---------------------------------------------------------------------


def test_author_edit_is_immutable_isolated_and_adopted_only_on_confirmation(workflow):
    w = workflow
    run = generate(w, create_run(w, max_steps=1, max_output_characters=300))
    candidate = pending(run)
    before = count(w, "chapter_revisions")
    first = edit(w, candidate["candidate_id"], EDITED)
    saved = pending(first)
    assert saved["text"] == TEXT  # The model's original candidate never changes.
    assert saved["edit_count"] == 1 and saved["adopted_edit_id"] is None
    latest = saved["latest_edit"]
    assert latest["text"] == EDITED and latest["source"] == "author"
    assert latest["sequence"] == 1 and latest["parent_edit_id"] is None
    assert latest["base_version"] == 2
    assert latest["character_count"] == sum(not c.isspace() for c in EDITED)
    # Saving an edit never touches the manuscript.
    assert count(w, "chapter_revisions") == before
    assert content(w).json()["content"] == "雨😀雨。"
    # A re-read (refresh or restart) recovers the edit and its provenance.
    reread = w.client.get(w.base + f"/ai/runs/{run['run_id']}").json()
    assert pending(reread)["latest_edit"] == latest
    second = pending(edit(w, candidate["candidate_id"], EDITED + "又改", latest["edit_id"]))
    history = w.client.get(w.base + f"/ai/candidates/{candidate['candidate_id']}/edits").json()
    assert [item["sequence"] for item in history] == [1, 2]
    assert history[1]["parent_edit_id"] == latest["edit_id"]
    # Only the newest edit may be adopted; the older one is stale.
    adopt(w, candidate["candidate_id"], "stale-edit-key", 2, latest["edit_id"], expected=409)
    adopted = adopt(
        w, candidate["candidate_id"], "edit-adopt-key", 2, second["latest_edit"]["edit_id"]
    )
    item = adopted["candidates"][0]
    assert item["status"] == "adopted" and item["text"] == TEXT
    assert item["adopted_edit_id"] == second["latest_edit"]["edit_id"]
    assert content(w).json()["content"] == "雨😀雨。\n\n" + EDITED + "又改"
    assert count(w, "chapter_revisions") == before + 1
    # A retried request with the same receipt does not append twice.
    again = adopt(
        w, candidate["candidate_id"], "edit-adopt-key", 2, second["latest_edit"]["edit_id"]
    )
    assert again == adopted and count(w, "chapter_revisions") == before + 1
    # The same receipt with a different text choice conflicts instead of guessing.
    adopt(w, candidate["candidate_id"], "edit-adopt-key", 2, None, expected=409)
    # An adopted candidate cannot gain new edits.
    edit(w, candidate["candidate_id"], "再改一次", second["latest_edit"]["edit_id"], expected=409)


def test_edit_validation_conflicts_and_limits(workflow):
    w = workflow
    run = generate(w, create_run(w, max_steps=1, max_output_characters=300))
    candidate_id = pending(run)["candidate_id"]
    error = edit(w, candidate_id, TEXT, expected=422)  # identical to the original
    assert error["error"]["code"] == "AI_CANDIDATE_EDIT_INVALID"
    edit(w, candidate_id, "   \n ", expected=422)
    edit(w, candidate_id, "字" * 3001, expected=422)
    edit(w, candidate_id, "改", parent="not-a-uuid-not-a-uuid-not-a-uuid-123", expected=422)
    first = pending(edit(w, candidate_id, "改"))["latest_edit"]["edit_id"]
    stale = edit(w, candidate_id, "另一个窗口", expected=409)  # parent must be the newest
    assert stale["error"]["code"] == "AI_WORKFLOW_CONFLICT"
    edit(w, candidate_id, "改", first, expected=422)  # no-op against the newest edit
    parent = first
    for number in range(2, 51):
        parent = pending(edit(w, candidate_id, f"改{number}", parent))["latest_edit"]["edit_id"]
    edit(w, candidate_id, "第五十一次", parent, expected=422)
    missing = w.client.get(w.base + "/ai/candidates/00000000-0000-0000-0000-000000000000/edits")
    assert missing.status_code == 404
    bad = w.client.post(
        w.base + f"/ai/candidates/{candidate_id}/adopt",
        headers={**w.headers, "If-Match": '"2"'},
        json={"idempotency_key": "bad-edit-id", "edit_id": "x" * 36},
    )
    assert bad.status_code == 422
    with pytest.raises(InvalidAIInput):
        w.service.edit_candidate(w.chapter, candidate_id, "改", "bad")
    discarded = w.client.post(
        w.base + f"/ai/candidates/{candidate_id}/discard", headers=w.headers, json={}
    )
    assert discarded.status_code == 200
    edit(w, candidate_id, "丢弃后", parent, expected=409)


def test_manuscript_change_rejects_old_edit_and_triggers_keep_rows_immutable(workflow):
    w = workflow
    run = generate(w, create_run(w, max_steps=1, max_output_characters=300))
    candidate_id = pending(run)["candidate_id"]
    edited = pending(edit(w, candidate_id, EDITED))["latest_edit"]
    current = content(w)
    manual = w.client.put(
        w.base + "/content",
        headers={**w.headers, "If-Match": current.headers["ETag"]},
        json={"content": "另一个窗口改了正文"},
    )
    assert manual.status_code == 200
    refused = adopt(w, candidate_id, "changed-manuscript", 3, edited["edit_id"], expected=409)
    assert refused["error"]["code"] == "AI_CONTEXT_CHANGED"
    # Even if the run were brought forward, the edit's own base must still match.
    with closing(sqlite3.connect(w.db)) as connection:
        head = connection.execute(
            "SELECT revision_id FROM chapter_heads WHERE chapter_id = ?", (w.chapter,)
        ).fetchone()[0]
        payload = json.loads(
            connection.execute(
                "SELECT payload FROM ai_workflow_runs WHERE id = ?", (run["run_id"],)
            ).fetchone()[0]
        )
        payload.update(current_revision_id=head, current_version=3)
        connection.execute(
            "UPDATE ai_workflow_runs SET payload = ? WHERE id = ?",
            (json.dumps(payload), run["run_id"]),
        )
        connection.commit()
    with pytest.raises(AIContextChanged):
        w.service.adopt(w.chapter, candidate_id, 3, "base-mismatch", edited["edit_id"])
    assert content(w).json()["content"] == "另一个窗口改了正文"
    # The edit is still kept for comparison and can be re-saved against the new text.
    resaved = pending(edit(w, candidate_id, EDITED, edited["edit_id"]))["latest_edit"]
    assert resaved["base_version"] == 3 and resaved["text"] == EDITED
    edit(w, candidate_id, EDITED, resaved["edit_id"], expected=422)  # same base: no-op
    with closing(sqlite3.connect(w.db)) as connection:
        for statement in (
            "UPDATE ai_workflow_candidates SET text = 'x'",
            "UPDATE ai_candidate_edits SET text = 'x'",
            "DELETE FROM ai_candidate_edits",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)
        # Status bookkeeping on the candidate row stays possible.
        connection.execute(
            "UPDATE ai_workflow_candidates SET status = status WHERE id = ?", (candidate_id,)
        )


def test_rewrite_adopts_the_author_edit_in_the_original_selection(workflow):
    w = workflow
    run = create_run(
        w,
        operation="rewrite",
        selected_text="雨😀",
        selection_start=0,
        selection_end=3,
        max_steps=1,
        max_output_characters=300,
    )
    run = generate(w, run)
    candidate_id = pending(run)["candidate_id"]
    edit_id = pending(edit(w, candidate_id, "细雨"))["latest_edit"]["edit_id"]
    adopt(w, candidate_id, "rewrite-edit", 2, edit_id)
    assert content(w).json()["content"] == "细雨雨。"


# -- prices, budgets and estimates ----------------------------------------------------


def test_prices_and_budgets_are_author_entered_versioned_and_validated(workflow):
    w = workflow
    empty = w.client.get("/api/v1/ai/models/default-local/price").json()
    assert empty == {"profile_id": "default-local", "current": None, "history": []}
    saved = put_price(w, inp="1.5", out="0.000001")
    assert saved["current"]["input_per_million"] == "1.50"
    assert saved["current"]["output_per_million"] == "0.000001"
    put_price(w, version=0, expected=409)
    second = put_price(w, version=1, currency="USD", inp="3", out="4")
    assert [item["version"] for item in second["history"]] == [2, 1]
    for amount in ("-1", "01", "1.1234567", "1e3", "abc", "1000000000"):
        assert put_price(w, version=2, inp=amount, expected=422)["error"]["code"] in (
            "BUDGET_INPUT_INVALID",
            "VALIDATION_ERROR",
        )
    put_price(w, version=2, currency="usd", expected=422)
    assert put_price(w, profile="0" * 32, expected=404)
    put_price(w, profile="BAD", expected=422)
    budget = w.client.get(f"/api/v1/projects/{w.project}/budget").json()
    assert budget["version"] == 0 and budget["mode"] == "off"
    assert budget["month"]["upper"] == "0.00" and budget["month"]["attempts"] == 0
    put_budget(w, currency=None, task_limit="1", expected=422)
    put_budget(w, expected=422)  # strict needs at least one limit
    put_budget(w, mode="off", currency=None)
    saved_budget = put_budget(w, version=1, task_limit="0.5", monthly_limit="10")
    assert saved_budget["version"] == 2 and saved_budget["task_limit"] == "0.50"
    put_budget(w, version=1, monthly_limit="1", expected=409)
    assert w.client.get("/api/v1/projects/nope/budget").status_code == 422
    with closing(sqlite3.connect(w.db)) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE model_price_revisions SET currency = 'EUR'")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM project_budget_revisions")
    assert w.calls == []  # Viewing and saving prices or budgets never calls a model.


def test_estimate_is_conservative_and_strict_budget_refuses_before_sending(workflow, monkeypatch):
    w = workflow
    real_provider(w)
    calls = transport(
        monkeypatch, GeneratedText(TEXT, "workflow-test", ProviderUsage(100, 50, 150))
    )
    run = create_run(w, max_steps=3, max_output_characters=900)
    preview = estimate(w, run)
    assert preview["price"] is None and preview["estimated_cost_upper"] is None
    assert preview["decision"] == "allowed" and preview["budget_mode"] == "off"
    messages = AIWorkflowService._messages(w.service.get(w.chapter, run["run_id"]), 300)
    assert preview["input_tokens_upper"] == input_tokens_upper(messages)
    assert preview["input_tokens_upper"] > preview["input_characters"]  # CJK: 3 bytes each
    assert preview["output_tokens_upper"] == 2048
    put_budget(w, task_limit="1")
    refused = estimate(w, run)
    assert refused["decision"] == "refused" and refused["reasons"] == ["PRICE_MISSING"]
    response = send_generation(w, run, 409)
    assert response["error"]["code"] == "AI_BUDGET_REFUSED"
    assert calls == [] and rows(w) == []  # Nothing sent, nothing recorded.
    reread = w.client.get(w.base + f"/ai/runs/{run['run_id']}").json()
    assert reread["status"] == "ready" and reread["generated_steps"] == 0
    assert reread["last_error"] == "BudgetRefused"
    put_price(w, inp="2", out="8")
    priced = estimate(w, run)
    expected = cost_micros(priced["input_tokens_upper"], 2_000_000) + cost_micros(2048, 8_000_000)
    assert priced["estimated_cost_upper"] == format_amount(expected)
    assert priced["decision"] == "allowed" and priced["currency"] == "CNY"
    run = send_generation(w, run, 200)
    assert len(calls) == 1
    with closing(sqlite3.connect(w.db)) as connection:
        reserved = connection.execute(
            "SELECT reserved_micros, currency, task_id FROM model_budget_reservations"
        ).fetchall()
    assert reserved[0][1:] == ("CNY", run["run_id"])
    budget = w.client.get(f"/api/v1/projects/{w.project}/budget").json()
    settled = cost_micros(100, 2_000_000) + cost_micros(50, 8_000_000)
    assert budget["month"]["settled"] == format_amount(settled)
    assert budget["month"]["pending"] == "0.00" and budget["month"]["attempts"] == 1
    # A limit smaller than settled + the next conservative estimate refuses the next step.
    put_budget(w, version=1, task_limit=format_amount(settled + expected - 1))
    w.client.post(
        w.base + f"/ai/candidates/{pending(run)['candidate_id']}/discard",
        headers=w.headers,
        json={},
    )
    assert estimate(w, run)["reasons"] == ["TASK_LIMIT_EXCEEDED"]
    send_generation(w, run, 409)
    assert len(calls) == 1


def test_unknown_usage_is_pending_unpriced_history_and_currency_block_strict(workflow, monkeypatch):
    w = workflow
    real_provider(w)
    calls = transport(
        monkeypatch,
        GeneratedText(TEXT, "workflow-test"),  # sent before any price: unpriced
        GeneratedText(TEXT, "workflow-test"),  # priced but no usage: pending
    )
    run = create_run(w, max_steps=3, max_output_characters=900)
    run = send_generation(w, run, 200)
    w.client.post(
        w.base + f"/ai/candidates/{pending(run)['candidate_id']}/discard",
        headers=w.headers,
        json={},
    )
    put_price(w)
    put_budget(w, mode="warn", monthly_limit="100")
    warned = estimate(w, run)
    assert warned["decision"] == "warning" and warned["reasons"] == ["UNPRICED_HISTORY"]
    assert warned["unpriced_attempts"] == 1
    run = send_generation(w, run, 200)  # warn mode informs; the author's send confirms
    budget = w.client.get(f"/api/v1/projects/{w.project}/budget").json()
    assert budget["month"]["unpriced_attempts"] == 1
    assert budget["month"]["pending"] != "0.00"  # unknown usage keeps its reserved bound
    put_budget(w, version=1, monthly_limit="100")
    assert estimate(w, run)["decision"] == "refused"
    put_budget(w, version=2, currency="USD", monthly_limit="100")
    mismatch = estimate(w, run)
    assert "CURRENCY_MISMATCH" in mismatch["reasons"]
    assert len(calls) == 2


def test_reference_analysis_is_also_refused_by_a_strict_budget(studio, monkeypatch):
    w = studio
    w.service._provider = w.real_provider
    calls = transport(monkeypatch)
    put_budget(w, task_limit="1")
    reference = create_reference(w)
    response = analyze(w, reference)
    assert response.status_code == 409 and response.json()["error"]["code"] == "AI_BUDGET_REFUSED"
    assert calls == []
    assert analysis_data([])["units"] == []


def test_concurrent_reservations_cannot_overspend_a_strict_budget(workflow):
    w = workflow
    put_price(w, inp="1", out="1")
    run = create_run(w)
    sessions = w.app.state.database_session_factory
    projects = w.app.state.project_query_service
    store = SqlAlchemyBudgetStore(sessions, projects)
    ledger = SqlAlchemyUsageLedger(sessions, projects, budgets=store)
    request = SendRequest(None, w.chapter, run["run_id"], "default-local", 10, 500_000, 500_000)
    put_budget(w, task_limit="1.5")  # room for exactly one 1.00 reservation

    def start(_):
        try:
            return ledger.start(
                AttemptStart(
                    UsageAttribution("generation", run["run_id"], None, w.chapter),
                    "default-local",
                    "local",
                    "m",
                    10,
                    request,
                )
            )
        except BudgetRefused:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(start, range(4)))
    assert sum(result is not None for result in results) == 1
    assert count(w, "model_budget_reservations") == 1
    with pytest.raises(BudgetInputInvalid):
        store.estimate(SendRequest(None, "chp_01HZZZZZZZZZZZZZZZZZZZZZZZ", "t", "p", 0, 0, 0))


def test_budget_service_is_required(workflow):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(AppError) as error:
        get_budget_service(request)  # type: ignore[arg-type]
    assert error.value.code == "USAGE_BUDGET_UNAVAILABLE"
    request.app.state.ai_workflow_schema_required = True
    with pytest.raises(AppError) as error:
        get_budget_service(request)  # type: ignore[arg-type]
    assert error.value.code == "AI_WORKFLOW_SCHEMA_REQUIRED"


# -- pure arithmetic ---------------------------------------------------------------------


def test_amounts_currency_and_upper_bounds():
    assert parse_amount("0", maximum=10) == 0
    assert parse_amount("1.000001", maximum=2_000_000) == 1_000_001
    with pytest.raises(BudgetInputInvalid):
        parse_amount("2", maximum=1_000_000)
    with pytest.raises(BudgetInputInvalid):
        parse_amount(1, maximum=10)
    assert format_amount(0) == "0.00" and format_amount(1_500_000) == "1.50"
    assert format_amount(1) == "0.000001"
    assert parse_currency("CNY") == "CNY"
    with pytest.raises(BudgetInputInvalid):
        parse_currency("CN")
    assert cost_micros(1, 1) == 1  # rounds up, never down
    assert input_tokens_upper((GenerationMessage("user", "雨"),)) == 8 + 3 + 8


def test_spend_summary_never_counts_unknown_as_zero():
    full = AttemptCost("completed", 1_000_000, 1_000_000, None, 99, "CNY", 1, 2)
    total = AttemptCost("completed", None, None, 1_000_000, 99, "CNY", 1, 2)
    partial = AttemptCost("completed", 5, None, None, 7, "CNY", 1, 2)
    failed = AttemptCost("failed", None, None, None, 11, "CNY", 1, 2)
    unpriced = AttemptCost("completed", 1, 1, 2, None, None, None, None)
    other = AttemptCost("completed", 1, 1, 2, 5, "USD", 1, 1)
    assert settled_cost(full) == 3 and settled_cost(total) == 2
    assert settled_cost(partial) is None and settled_cost(failed) is None
    assert settled_cost(unpriced) is None
    spend = summarize([full, total, partial, failed, unpriced, other], "CNY")
    assert spend == Spend(6, 5, 18, 1, 1)
    assert spend.upper_micros == 23 and not spend.bounded
    assert summarize([full], None).other_currency_attempts == 1


def test_evaluate_covers_every_decision():
    price = Price("r", "p", 1, "CNY", 1, 1, "t")
    clean = Spend()
    strict = Budget("p", 1, "strict", "CNY", 10, 20, "t")
    warn = Budget("p", 1, "warn", "CNY", None, 20, "t")
    assert evaluate(None, None, None, clean, clean) == ("allowed", ())
    assert evaluate(Budget("p", 1, "off", None, None, None, "t"), None, None, clean, clean)[0] == (
        "allowed"
    )
    assert evaluate(strict, price, 10, clean, clean) == ("allowed", ())
    assert evaluate(strict, price, 11, clean, clean) == ("refused", ("TASK_LIMIT_EXCEEDED",))
    assert evaluate(strict, price, 5, clean, Spend(1, 16, 0)) == (
        "refused",
        ("MONTHLY_LIMIT_EXCEEDED",),
    )
    assert evaluate(warn, None, None, clean, clean) == ("warning", ("PRICE_MISSING",))
    usd = Price("r", "p", 1, "USD", 1, 1, "t")
    assert evaluate(strict, usd, 1, Spend(1, 0, 0, 1), Spend(1, 0, 0, 1)) == (
        "refused",
        ("CURRENCY_MISMATCH", "UNPRICED_HISTORY"),
    )


def test_month_start_uses_the_local_calendar():
    zone = timezone(timedelta(hours=8))
    now = datetime(2026, 10, 31, 17, 0, tzinfo=UTC)  # already 1 November in UTC+8
    assert month_start(now, zone) == datetime(2026, 10, 31, 16, 0, tzinfo=UTC)
    assert month_start(datetime(2026, 10, 15, tzinfo=UTC), UTC) == datetime(2026, 10, 1, tzinfo=UTC)


# -- storage instance for draft isolation ----------------------------------------------


def directory_redirect(link: Path, target: Path) -> None:
    """Exercise a real directory redirect without requiring Windows symlink privileges."""
    if os.name == "nt":

        def quote(value: Path) -> str:
            return str(value).replace("'", "''")

        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"New-Item -ItemType Junction -Path '{quote(link)}' "
                f"-Target '{quote(target)}' -ErrorAction Stop | Out-Null",
            ],
            check=True,
            capture_output=True,
        )
        assert link.is_junction()
    else:
        link.symlink_to(target, target_is_directory=True)
        assert link.is_symlink()


def test_storage_instance_is_stable_per_root_and_new_for_copies(tmp_path: Path):
    first = StorageInstanceService(tmp_path / "root")
    identifier = first.get()
    assert len(identifier) == 32 and int(identifier, 16) >= 0
    assert StorageInstanceService(tmp_path / "root").get() == identifier  # restart
    stored = (tmp_path / "root/config/storage-instance.json").read_bytes()
    assert b"root" in stored and os.fspath(tmp_path).encode() not in stored
    copy = tmp_path / "copy/config"
    copy.mkdir(parents=True)
    (copy / "storage-instance.json").write_bytes(stored)
    assert StorageInstanceService(tmp_path / "copy").get() != identifier  # moved/copied
    (tmp_path / "root/config/storage-instance.json").write_text("{broken")
    assert StorageInstanceService(tmp_path / "root").get() != identifier  # unreadable
    linked = tmp_path / "linked"
    linked.mkdir()
    directory_redirect(linked / "config", tmp_path / "root/config")
    with pytest.raises(StorageInstanceUnavailable):
        StorageInstanceService(linked).get()


def test_storage_instance_endpoint(workflow, tmp_path: Path):
    w = workflow
    response = w.client.get("/api/v1/storage-instance")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    identifier = response.json()["storage_instance_id"]
    assert w.client.get("/api/v1/storage-instance").json()["storage_instance_id"] == identifier
    router = create_storage_instance_router(api_prefix="/x")
    endpoint = router.routes[0].endpoint  # type: ignore[attr-defined]
    response_stub = SimpleNamespace(headers={})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(storage_initialized=False)))
    with pytest.raises(AppError) as error:
        endpoint(request, response_stub)
    assert error.value.code == "STORAGE_INSTANCE_UNAVAILABLE"
    state = w.app.state
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    directory_redirect(blocked / "config", tmp_path)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                storage_initialized=True,
                storage_paths=type(state.storage_paths).from_root(blocked),
            )
        )
    )
    with pytest.raises(AppError):
        endpoint(request, response_stub)


def test_remaining_budget_guards(workflow, monkeypatch, tmp_path: Path):
    w = workflow
    unknown = str(ProjectId.new())
    assert w.client.get(f"/api/v1/projects/{unknown}/budget").status_code == 404
    service = w.app.state.usage_budget_service
    with pytest.raises(BudgetInputInvalid):
        service.put_budget(
            w.project,
            expected_version=True,
            mode="off",
            currency=None,
            task_limit=None,
            monthly_limit=None,
        )
    with pytest.raises(BudgetInputInvalid):
        service.put_budget(
            w.project,
            expected_version=0,
            mode="never",
            currency=None,
            task_limit=None,
            monthly_limit=None,
        )

    def broken(*_args, **_kwargs):
        raise UsageLedgerUnavailable

    monkeypatch.setattr(service, "budget_view", broken)
    response = w.client.get(f"/api/v1/projects/{w.project}/budget")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "USAGE_BUDGET_UNAVAILABLE"
    bare = AIWorkflowService(w.service._repository, None, None, None)  # type: ignore[arg-type]
    run = create_run(w)
    with pytest.raises(UsageLedgerUnavailable):
        bare.estimate(w.chapter, run["run_id"])
    sessions = w.app.state.database_session_factory
    ledger, budgets = compose_usage_ledger(sessions, w.app.state.project_query_service)
    assert budgets is None and ledger is not None


def test_storage_instance_write_failure_is_reported_without_paths(tmp_path: Path, monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("disk full at a private path")

    monkeypatch.setattr("aiwebnovel.storage.instance.os.replace", fail)
    with pytest.raises(StorageInstanceUnavailable) as error:
        StorageInstanceService(tmp_path / "root").get()
    assert "private" not in str(error.value)
    assert list((tmp_path / "root/config").iterdir()) == []  # the temporary file is removed
