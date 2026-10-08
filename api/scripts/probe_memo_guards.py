"""Diagnostic probe for app/agents/memo.py's clarification-memo guards:
runs each requested processor's attempt 1 (and, if it fails, attempt 2
with the real corrective note) against real Gemini, and reports exactly
which guard tripped, on which field, and the exact offending token(s) —
not just the final guard_status run_memo()'s console summary gives.

Built to diagnose the 2026-10-09 --stage memo run, where 5 of 7
clarification memos fell back to template with no record of why. Never
writes to BigQuery (read-only on assessments/agent_runs/shipments/etc,
same tables --stage memo reads) — the only write is a local JSON dump
per processor under data/synthetic/seed-<seed>/memo_probe_runs/, so a
later fixture test can replay the exact real inputs and real raw
response(s) without a second live call.

Run by the developer — never by the agent (hits real Vertex AI,
BigQuery).

Usage: uv run python scripts/probe_memo_guards.py \\
           --processors PWP-02,PWP-05,PWP-06,PWP-07,PWP-09 --facts-source extracted
"""

import argparse
import json

from app.agents import memo
from app.llm import GeminiClient
from app.store import bq
from scripts.run_pipeline import (
    REPO_ROOT,
    build_memo_context_for_processor,
    fetch_agent_inputs,
    fetch_memo_extras,
)

TRUTH = "truth"
EXTRACTED = "extracted"


def _generate_attempt_fn(doc_type: str):
    return (
        memo.attempt_clarification_memo
        if doc_type == "clarification_memo"
        else memo.attempt_verification_statement
    )


def _print_issue_rows(processor_id: str, doc_type: str, attempt: int, issues: list[dict]) -> None:
    if not issues:
        print(f"  {processor_id} [{doc_type}] attempt {attempt}: guard-clean")
        return
    for issue in issues:
        text_preview = (issue["text"] or "")[:160]
        print(
            f"  {processor_id} [{doc_type}] attempt {attempt}: "
            f"guard={issue['guard']:15s} field={issue['field']:30s} "
            f"offending={issue['offending']!r}\n"
            f"      text: {text_preview!r}"
        )


def probe_processor(
    seed: int, facts_source: str, memo_context: dict, llm_client: GeminiClient
) -> dict:
    pid = memo_context["processor"]["processor_id"]
    doc_type = memo_context["doc_type"]
    attempt_fn = _generate_attempt_fn(doc_type)

    candidate1, issues1 = attempt_fn(memo_context, llm_client)
    _print_issue_rows(pid, doc_type, 1, issues1)
    attempts = [
        {
            "attempt": 1,
            "corrective": None,
            "raw_response": candidate1.model_dump(),
            "issues": issues1,
        }
    ]

    final_status = "ok"
    if issues1:
        corrective = memo.corrective_note(issues1)
        candidate2, issues2 = attempt_fn(memo_context, llm_client, corrective=corrective)
        _print_issue_rows(pid, doc_type, 2, issues2)
        attempts.append(
            {
                "attempt": 2,
                "corrective": corrective,
                "raw_response": candidate2.model_dump(),
                "issues": issues2,
            }
        )
        final_status = "regenerated" if not issues2 else "template_fallback"

    return {
        "processor_id": pid,
        "doc_type": doc_type,
        "seed": seed,
        "facts_source": facts_source,
        "inputs": {
            "processor": memo_context["processor"],
            "assessment": memo_context["assessment"],
            "check_results": memo_context["check_results"],
            "findings": memo_context["findings"],
            "shipments_by_id": memo_context["shipments_by_id"],
            "documents_by_id": memo_context["documents_by_id"],
            "certificates": memo_context["certificates"],
            "as_of_month": memo_context["as_of_month"],
        },
        "attempts": attempts,
        "final_guard_status": final_status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--facts-source", choices=[TRUTH, EXTRACTED], default=EXTRACTED)
    parser.add_argument(
        "--processors", required=True, help="Comma-separated processor_ids, e.g. PWP-02,PWP-05"
    )
    parser.add_argument("--as-of-month", help="Override; default is fetch_agent_inputs()'s own.")
    args = parser.parse_args()
    requested = set(args.processors.split(","))

    bq_client = bq.get_client()
    inputs = fetch_agent_inputs(bq_client, args.seed, args.facts_source, processor_filter=None)
    if inputs is None:
        print("Nothing to probe — run --stage normalize/checks/agents first.")
        return
    if args.as_of_month:
        inputs["as_of_month"] = args.as_of_month

    processors = [p for p in inputs["processors"] if p["processor_id"] in requested]
    missing = requested - {p["processor_id"] for p in processors}
    if missing:
        print(f"Warning: requested processor(s) not found, skipping: {sorted(missing)}")

    assessments_by_processor, trail_by_processor = fetch_memo_extras(
        bq_client, args.seed, args.facts_source, processor_filter=None
    )

    output_dir = REPO_ROOT / "data" / "synthetic" / f"seed-{args.seed}" / "memo_probe_runs"
    output_dir.mkdir(parents=True, exist_ok=True)

    llm_client = GeminiClient()
    results = []
    for processor in processors:
        pid = processor["processor_id"]
        memo_context = build_memo_context_for_processor(
            processor, inputs, assessments_by_processor, trail_by_processor
        )
        if memo_context is None:
            print(f"  {pid}: skipped — no assessment yet")
            continue
        result = probe_processor(args.seed, args.facts_source, memo_context, llm_client)
        results.append(result)
        out_path = output_dir / f"{pid}_{args.facts_source}.json"
        out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"  -> wrote {out_path}")

    call_log = llm_client.flush_call_log()  # not written to BigQuery — this script is read-only
    total_calls = len(call_log)
    print(
        f"\nProbed {len(results)} processor(s), {total_calls} Gemini call(s), "
        "nothing written to BigQuery."
    )


if __name__ == "__main__":
    main()
