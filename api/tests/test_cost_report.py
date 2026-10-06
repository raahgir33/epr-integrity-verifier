"""Tests for scripts/cost_report.py's pure functions — no BigQuery calls."""

from scripts.cost_report import aggregate, estimate_cost_usd


def test_estimate_cost_usd_matches_the_quoted_rates():
    # 1M input tokens @ $1.50/M, 1M output tokens @ $9/M
    cost = estimate_cost_usd(1_000_000, 1_000_000, 0)
    assert cost == 1.50 + 9.00


def test_thinking_tokens_billed_as_output():
    with_thinking = estimate_cost_usd(0, 0, 1_000_000)
    as_output = estimate_cost_usd(0, 1_000_000, 0)
    assert with_thinking == as_output


def test_estimate_cost_usd_handles_none():
    assert estimate_cost_usd(None, None, None) == 0.0


def test_aggregate_sums_by_purpose_and_by_day():
    rows = [
        {
            "purpose": "extract:cto",
            "call_date": "2026-10-07",
            "calls": 2,
            "input_tokens": 100,
            "output_tokens": 50,
            "thinking_tokens": 0,
            "total_tokens": 150,
        },
        {
            "purpose": "extract:cto",
            "call_date": "2026-10-08",
            "calls": 1,
            "input_tokens": 50,
            "output_tokens": 25,
            "thinking_tokens": 0,
            "total_tokens": 75,
        },
        {
            "purpose": "extract:inbound_invoice",
            "call_date": "2026-10-07",
            "calls": 3,
            "input_tokens": 300,
            "output_tokens": 150,
            "thinking_tokens": 10,
            "total_tokens": 460,
        },
    ]

    by_purpose, by_day = aggregate(rows)

    assert by_purpose["extract:cto"]["calls"] == 3
    assert by_purpose["extract:cto"]["input_tokens"] == 150
    assert by_purpose["extract:inbound_invoice"]["calls"] == 3

    assert by_day["2026-10-07"]["calls"] == 5
    assert by_day["2026-10-08"]["calls"] == 1

    for group in (*by_purpose.values(), *by_day.values()):
        assert "cost_usd" in group
        assert group["cost_usd"] >= 0
