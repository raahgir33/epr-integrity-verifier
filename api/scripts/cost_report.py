"""Reports Gemini call counts, token usage and estimated cost from the
llm_calls table, broken down by purpose and by day.

Run by the developer — never by the agent (reads real BigQuery). Requires
the input_tokens/output_tokens/thinking_tokens/total_tokens columns added
to llm_calls (see docs/PROGRESS.md for the ALTER TABLE statement).

Usage: uv run python scripts/cost_report.py
"""

from collections import defaultdict

from app.config import settings
from app.store import bq


def estimate_cost_usd(
    input_tokens: int | None, output_tokens: int | None, thinking_tokens: int | None
) -> float:
    """Thinking tokens are billed as output tokens."""
    output_billed = (output_tokens or 0) + (thinking_tokens or 0)
    return (
        (input_tokens or 0) / 1_000_000 * settings.gemini_input_price_per_million
        + output_billed / 1_000_000 * settings.gemini_output_price_per_million
    )


def fetch_rows(client) -> list[dict]:
    query = f"""
        SELECT
          purpose,
          DATE(called_at) AS call_date,
          COUNT(*) AS calls,
          SUM(input_tokens) AS input_tokens,
          SUM(output_tokens) AS output_tokens,
          SUM(thinking_tokens) AS thinking_tokens,
          SUM(total_tokens) AS total_tokens
        FROM `{settings.gcp_project}.{settings.bq_dataset}.llm_calls`
        GROUP BY purpose, call_date
        ORDER BY call_date, purpose
    """
    job = client.query(query, location=settings.vertex_location)
    return [dict(row) for row in job.result()]


def _empty_group() -> dict:
    return {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "total_tokens": 0,
    }


def _add_row(group: dict, row: dict) -> None:
    group["calls"] += row["calls"] or 0
    group["input_tokens"] += row["input_tokens"] or 0
    group["output_tokens"] += row["output_tokens"] or 0
    group["thinking_tokens"] += row["thinking_tokens"] or 0
    group["total_tokens"] += row["total_tokens"] or 0


def aggregate(rows: list[dict]) -> tuple[dict, dict]:
    """Returns (by_purpose, by_day), each {key: totals dict including cost_usd}."""
    by_purpose: dict[str, dict] = defaultdict(_empty_group)
    by_day: dict[str, dict] = defaultdict(_empty_group)

    for row in rows:
        _add_row(by_purpose[row["purpose"]], row)
        _add_row(by_day[str(row["call_date"])], row)

    for group in (*by_purpose.values(), *by_day.values()):
        group["cost_usd"] = estimate_cost_usd(
            group["input_tokens"], group["output_tokens"], group["thinking_tokens"]
        )

    return dict(by_purpose), dict(by_day)


def print_table(title: str, groups: dict[str, dict]) -> float:
    print(f"\n{title}")
    header = (
        f"  {'key':20s} {'calls':>7s} {'input':>10s} {'output':>10s} "
        f"{'thinking':>10s} {'cost (USD)':>12s}"
    )
    print(header)
    total_cost = 0.0
    for key in sorted(groups):
        g = groups[key]
        total_cost += g["cost_usd"]
        print(
            f"  {key:20s} {g['calls']:7d} {g['input_tokens']:10d} "
            f"{g['output_tokens']:10d} {g['thinking_tokens']:10d} {g['cost_usd']:12.4f}"
        )
    print(f"  {'TOTAL':20s} {'':>7s} {'':>10s} {'':>10s} {'':>10s} {total_cost:12.4f}")
    return total_cost


def main() -> None:
    client = bq.get_client()
    rows = fetch_rows(client)
    if not rows:
        print("No rows in llm_calls.")
        return

    by_purpose, by_day = aggregate(rows)
    print_table("By purpose", by_purpose)
    total = print_table("By day", by_day)
    print(f"\nEstimated total cost: ${total:.4f}")
    print(
        f"(rates: ${settings.gemini_input_price_per_million:.2f}/M input, "
        f"${settings.gemini_output_price_per_million:.2f}/M output — thinking billed as output)"
    )


if __name__ == "__main__":
    main()
