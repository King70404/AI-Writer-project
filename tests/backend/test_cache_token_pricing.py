"""Reported inclusive cache details and frozen-price arithmetic; no network."""

import pytest
from tests.backend.test_ai_workflow import TEXT, create_run, workflow
from tests.backend.test_usage_ledger import (
    discard,
    real_provider,
    send_generation,
    transport,
    usage,
)

from aiwebnovel.ai_writing.application.models import GeneratedText, ProviderUsage

__all__ = ["workflow"]

from aiwebnovel.ai_writing.application.models import parse_provider_usage
from aiwebnovel.usage.budget import AttemptCost, Price, cache_cost_is_upper, settled_cost, summarize


@pytest.mark.parametrize(
    ("details", "status", "cached", "written"),
    [
        ({"cached_tokens": 60}, "reported", 60, None),
        ({"cached_tokens": 60, "cache_write_tokens": 20}, "reported", 60, 20),
        ({"cached_tokens": 0}, "reported", 0, None),
        ({"cached_tokens": -1}, "invalid", None, None),
        ({"cached_tokens": True}, "invalid", None, None),
        ({"cached_tokens": "20"}, "invalid", None, None),
        ({"cached_tokens": 101}, "invalid", 101, None),
        ({"cached_tokens": 60, "cache_creation_tokens": 50}, "invalid", 60, 50),
        ({"cache_creation_tokens": 20, "cache_write_tokens": 21}, "invalid", None, 20),
        ([], "invalid", None, None),
        (None, "invalid", None, None),
        ({"audio_tokens": 10}, "not_reported", None, None),
    ],
)
def test_cache_details_are_reported_without_guessing(details, status, cached, written):
    usage = parse_provider_usage(
        {"usage": {"prompt_tokens": 100, "completion_tokens": 10, "prompt_tokens_details": details}}
    )
    assert usage is not None
    assert (usage.cache_details_status, usage.cached_input_tokens, usage.cache_write_tokens) == (
        status,
        cached,
        written,
    )


def test_absent_and_incompatible_provider_cache_shapes_are_distinct():
    missing = parse_provider_usage({"usage": {"prompt_tokens": 100}})
    incompatible = parse_provider_usage(
        {"usage": {"input_tokens": 100, "cache_read_input_tokens": 40}}
    )
    assert missing is not None and missing.cache_details_status == "not_reported"
    assert incompatible is not None and incompatible.cache_details_status == "invalid"
    mixed = parse_provider_usage(
        {
            "usage": {
                "input_tokens": 100,
                "cache_read_input_tokens": 40,
                "input_tokens_details": {"cached_tokens": 5},
            }
        }
    )
    assert mixed is not None and mixed.cache_details_status == "invalid"
    inconsistent = parse_provider_usage(
        {
            "usage": {
                "prompt_tokens": 100,
                "prompt_tokens_details": {"cached_tokens": 2},
                "input_tokens_details": {"cached_tokens": 3},
            }
        }
    )
    assert inconsistent is not None and inconsistent.cache_details_status == "invalid"


@pytest.mark.parametrize(
    ("cached", "written", "read_rate", "write_rate", "status", "expected"),
    [
        (60, 20, 1_000_000, 3_000_000, "reported", 200),
        (60, 20, None, None, "reported", 240),
        (0, 0, 0, 0, "reported", 240),
        (60, 20, 0, 0, "reported", 80),
        (None, None, 1_000_000, 3_000_000, "not_reported", 340),
        (60, 50, 1_000_000, 3_000_000, "invalid", None),
    ],
)
def test_cache_is_part_of_inclusive_input_not_added_twice(
    cached, written, read_rate, write_rate, status, expected
):
    row = AttemptCost(
        "completed",
        100,
        10,
        110,
        999,
        "CNY",
        2_000_000,
        4_000_000,
        cached,
        written,
        read_rate,
        write_rate,
        status,
    )
    assert settled_cost(row) == expected
    spend = summarize([row], "CNY")
    upper = expected is not None and cache_cost_is_upper(row)
    assert spend.settled_micros == (0 if upper else (expected or 0))
    assert spend.pending_micros == (999 if expected is None else (expected if upper else 0))


def test_pre_send_reserves_highest_input_rate_and_total_only_stays_conservative():
    price = Price("p", "profile", 1, "CNY", 2_000_000, 4_000_000, "now", 1_000_000, 6_000_000)
    assert price.cost(100, 10) == 640
    row = AttemptCost(
        "completed",
        None,
        None,
        110,
        999,
        "CNY",
        2_000_000,
        4_000_000,
        None,
        None,
        1_000_000,
        6_000_000,
    )
    assert settled_cost(row) == 660


def test_frozen_cache_price_is_exposed_per_attempt_and_never_repriced(workflow, monkeypatch):
    w = workflow
    real_provider(w)
    price_url = "/api/v1/ai/models/default-local/price"
    payload = {
        "expected_version": 0,
        "currency": "CNY",
        "input_per_million": "2",
        "output_per_million": "4",
        "cached_input_per_million": "1",
        "cache_write_per_million": "3",
    }
    first = w.client.put(price_url, headers=w.headers, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["current"]["cached_input_per_million"] == "1.00"
    calls = transport(
        monkeypatch,
        GeneratedText(
            TEXT, "m", ProviderUsage(1000000, 100000, 1100000, 600000, 200000, "reported")
        ),
        GeneratedText(TEXT, "m", None),
    )
    run = create_run(w, max_steps=1)
    run = send_generation(w, run, 200)
    first_row = usage(w)["items"][0]
    assert first_row["amount"] == "2.00"
    assert first_row["amount_basis"] == "reported_tokens"
    assert first_row["price_version"] == 1
    assert first_row["cached_input_tokens"] == 600000
    discard(w, run)
    payload.update(
        expected_version=1,
        currency="USD",
        input_per_million="10",
        cached_input_per_million=None,
        cache_write_per_million=None,
    )
    assert w.client.put(price_url, headers=w.headers, json=payload).status_code == 200
    send_generation(w, create_run(w, max_steps=1), 200)
    items = usage(w)["items"]
    old = next(item for item in items if item["id"] == first_row["id"])
    assert old == first_row
    new = next(item for item in items if item["id"] != first_row["id"])
    assert new["currency"] == "USD" and new["price_version"] == 2
    assert new["amount_basis"] == "reserved_upper" and new["amount"] is not None
    assert new["cached_input_tokens"] is None
    assert len(calls) == 2


def test_unreported_premium_cache_is_explicit_upper_bound(workflow, monkeypatch):
    w = workflow
    real_provider(w)
    price_url = "/api/v1/ai/models/default-local/price"
    payload = {
        "expected_version": 0,
        "currency": "CNY",
        "input_per_million": "2",
        "output_per_million": "4",
        "cache_write_per_million": "6",
    }
    assert w.client.put(price_url, headers=w.headers, json=payload).status_code == 200
    budget_url = f"/api/v1/projects/{w.project}/budget"
    assert (
        w.client.put(
            budget_url,
            headers=w.headers,
            json={"expected_version": 0, "mode": "warn", "currency": "CNY", "monthly_limit": "100"},
        ).status_code
        == 200
    )
    calls = transport(
        monkeypatch, GeneratedText(TEXT, "m", ProviderUsage(1_000_000, 100_000, 1_100_000))
    )
    send_generation(w, create_run(w, max_steps=1), 200)
    item = usage(w)["items"][0]
    assert item["amount"] == "6.40" and item["amount_basis"] == "cache_upper"
    assert item["cache_write_tokens"] is None and item["cache_details_status"] == "not_reported"
    month = w.client.get(budget_url).json()["month"]
    assert month["pending"] == "6.40" and month["settled"] == "0.00"
    assert len(calls) == 1
