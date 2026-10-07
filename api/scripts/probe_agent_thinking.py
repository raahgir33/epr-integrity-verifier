"""One-off probe: no thinking config vs thinking_level="low" for the T10
agent loop, across all 10 processors, 2 runs per config (4 full runs
total) — measures which config wins on cited-shipment accuracy against
ground truth, and whether a config is consistent run-to-run.

This is the T10 acceptance run (docs/BUILD_PLAN.md): confirms F8 is
detected (with the right shipments cited) on the two seeded F8
processors, confirms no false findings appear elsewhere, and reports the
real token/cost totals from llm_calls.

Reads ground_truth.json only for scoring (is_f8 / true_verifiable_t) —
never for building what the agents themselves see; that boundary is
scripts/run_pipeline.py's fetch_agent_inputs()/build_processor_context(),
reused here unchanged (see tests/test_agent_leak_guard.py).

Never send thinking_budget, or thinking_level="minimal", to Gemini 3.x
models (developer instruction; enforced in app/llm.py) — this script only
ever tries "low" against the no-thinking default.

Run by the developer — never by the agent (hits real Vertex AI,
BigQuery, Cloud Storage). Requires --stage normalize/checks/site to have
already been run for this seed (agent context is read from their output
tables).

Usage: uv run python scripts/probe_agent_thinking.py
       uv run python scripts/probe_agent_thinking.py --processors PWP-01,PWP-03,PWP-07 \\
           --configs no_thinking --runs-per-config 1   # canary, before the full acceptance pair
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from app.agents.orchestrator import run_agent_loop
from app.agents.scorer import (
    build_disputed_finding_check_result,
    build_no_own_evidence_finding_check_result,
    build_systemic_finding_check_result,
    score_processor,
)
from app.checks import params
from app.ingest.normalize import TRUTH
from app.llm import GeminiClient
from app.store import bq, gcs
from scripts.cost_report import estimate_cost_usd
from scripts.run_pipeline import build_processor_context, fetch_agent_inputs, load_ground_truth

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = 42
CONFIGS = [("no_thinking", None), ("low_thinking", "low")]
RUNS_PER_CONFIG = 2
OUTPUT_DIR = REPO_ROOT / "data" / "synthetic" / f"seed-{SEED}" / "agent_probe_runs"


def _ground_truth_processor(ground_truth: dict, processor_id: str) -> dict:
    return next(p for p in ground_truth["processors"] if p["processor_id"] == processor_id)


def _ground_truth_f8_shipment_ids(ground_truth: dict, processor_id: str) -> set[str]:
    gt_processor = _ground_truth_processor(ground_truth, processor_id)
    return {s["shipment_id"] for s in gt_processor["shipments"] if s.get("is_f8")}


def _cited_shipment_ids(processor_record: dict) -> set[str]:
    return {
        sid
        for finding in processor_record["confirmed_findings"]
        for sid in finding["cited_shipment_ids"]
    }


def _precision_recall_f1(cited: set[str], true_positive: set[str]) -> dict:
    tp = len(cited & true_positive)
    fp = len(cited - true_positive)
    fn = len(true_positive - cited)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def run_one(
    config_name: str,
    thinking_level: str | None,
    run_index: int,
    inputs: dict,
    gcs_client,
) -> dict:
    """Runs the full agent loop for every processor in `inputs`, once,
    under one thinking config. Returns a fully JSON-serializable record —
    no Pydantic model instances survive past this function."""
    llm_client = GeminiClient()
    processors_record = {}

    print(f"\n=== {config_name} run {run_index}: {len(inputs['processors'])} processor(s) ===")
    for processor in inputs["processors"]:
        pid = processor["processor_id"]
        processor_context, check_result_models = build_processor_context(
            inputs, processor, gcs_client
        )
        deadline = time.monotonic() + params.AGENT_TIMEOUT_S
        loop_result = run_agent_loop(
            processor_context, llm_client, deadline, thinking_level=thinking_level
        )

        # Own-evidence rule + systemic-finding guard + Hypothesis/Critic
        # agreement rule (docs/PROGRESS.md) — see scripts/run_pipeline.py's
        # run_agents() for the same split; kept identical here so this
        # probe's scoring matches the real pipeline's. excluded_shipment_ids
        # is the ready-made deduction set from app/agents/orchestrator.py's
        # _classify_findings, not re-derived from cited_shipment_ids here.
        score_check_results = list(check_result_models)
        if loop_result["systemic_findings"]:
            score_check_results.append(
                build_systemic_finding_check_result(loop_result["systemic_findings"])
            )
        if loop_result["no_evidence_findings"]:
            score_check_results.append(
                build_no_own_evidence_finding_check_result(loop_result["no_evidence_findings"])
            )
        if loop_result["review_flag_findings"]:
            score_check_results.append(
                build_disputed_finding_check_result(loop_result["review_flag_findings"])
            )
        score = score_processor(
            processor,
            processor_context["certificates"],
            processor_context["shipments"],
            processor_context["duplicate_keys"],
            score_check_results,
            inputs["as_of_month"],
            excluded_shipment_ids=loop_result["excluded_shipment_ids"],
        )

        processors_record[pid] = {
            "agent_status": loop_result["agent_status"],
            "tool_cap_reached": loop_result["tool_cap_reached"],
            "conclusions": [c.model_dump() for c in loop_result["conclusions"]],
            "hypothesis_findings": [f.model_dump() for f in loop_result["hypothesis_findings"]],
            "verdicts": [v.model_dump() for v in loop_result["verdicts"]],
            "objections": [o.model_dump() for o in loop_result["objections"]],
            "revisions": [r.model_dump() for r in loop_result["revisions"]],
            "hypothesis_finding_responses": [
                r.model_dump() for r in loop_result["hypothesis_finding_responses"]
            ],
            "confirmed_findings": [f.model_dump() for f in loop_result["confirmed_findings"]],
            "review_flag_findings": [f.model_dump() for f in loop_result["review_flag_findings"]],
            "withdrawn_findings": [f.model_dump() for f in loop_result["withdrawn_findings"]],
            "deductible_findings": [f.model_dump() for f in loop_result["deductible_findings"]],
            "systemic_findings": [f.model_dump() for f in loop_result["systemic_findings"]],
            "no_evidence_findings": [f.model_dump() for f in loop_result["no_evidence_findings"]],
            "trail": loop_result["trail"],
            "score": score,
        }
        print(
            f"  {pid}: agent_status={loop_result['agent_status']} "
            f"confirmed_findings={len(loop_result['confirmed_findings'])} "
            f"(deductible={len(loop_result['deductible_findings'])}, "
            f"systemic={len(loop_result['systemic_findings'])}, "
            f"no_evidence={len(loop_result['no_evidence_findings'])}, "
            f"review_flag={len(loop_result['review_flag_findings'])}, "
            f"withdrawn={len(loop_result['withdrawn_findings'])}) "
            f"verifiable={score['verifiable_t']:.2f}t risk={score['risk_band']}"
        )

    return {
        "config_name": config_name,
        "thinking_level": thinking_level,
        "run_index": run_index,
        "as_of_month": inputs["as_of_month"],
        "processors": processors_record,
        "call_log": llm_client.flush_call_log(),
    }


def _f5_processor_ids(ground_truth: dict) -> set[str]:
    """docs/DATA_SPEC.md §7's cited-shipment scoring rule: F5 (ghost site)
    has no shipment-level manifestation — it's a site-level finding caught
    by C8 — so any shipment citation the agent produces on an F5 processor
    is excluded from the F8 precision/recall metric entirely, rather than
    counted as a false F8 citation."""
    return {
        p["processor_id"] for p in ground_truth["processors"] if "F5" in p.get("issue_types", [])
    }


def _f7_target_month(ground_truth_processor: dict) -> str | None:
    """The seeded F7 low-energy anomaly's month, found from the data
    itself — the month with minimum kwh in this processor's own
    energy_monthly — rather than re-deriving the generator's own
    f7_target_month selection (docs/DATA_SPEC.md §7)."""
    energy_monthly = ground_truth_processor.get("energy_monthly") or []
    if not energy_monthly:
        return None
    return min(energy_monthly, key=lambda r: r["kwh"])["month"]


def _f7_neutral_shipment_ids(ground_truth: dict, processor_id: str) -> set[str]:
    """docs/DATA_SPEC.md §7's cited-shipment scoring rule: a citation of a
    shipment in an F7 processor's own seeded low-energy month is neutral —
    like F5, it never counts as a false F8 citation — but only that one
    month's shipments are excluded, not the whole processor: unlike F5,
    F7 doesn't invalidate every other month's citation-worthiness."""
    gt_processor = _ground_truth_processor(ground_truth, processor_id)
    if "F7" not in gt_processor.get("issue_types", []):
        return set()
    target_month = _f7_target_month(gt_processor)
    if target_month is None:
        return set()
    return {s["shipment_id"] for s in gt_processor["shipments"] if s.get("month") == target_month}


def compute_run_metrics(run_record: dict, ground_truth: dict) -> dict:
    per_processor = {}
    agg_tp = agg_fp = agg_fn = 0
    verifiable_errors = []
    false_citations = []
    f5_processor_ids = _f5_processor_ids(ground_truth)

    for pid, record in run_record["processors"].items():
        true_f8 = _ground_truth_f8_shipment_ids(ground_truth, pid)
        cited = _cited_shipment_ids(record)
        f7_neutral = _f7_neutral_shipment_ids(ground_truth, pid)
        cited_for_metric = cited - f7_neutral
        pr = _precision_recall_f1(cited_for_metric, true_f8)
        true_verifiable_t = _ground_truth_processor(ground_truth, pid)["true_verifiable_t"]
        abs_error = abs(record["score"]["verifiable_t"] - true_verifiable_t)
        excluded_from_f8_metric = pid in f5_processor_ids

        per_processor[pid] = {
            "cited_shipment_ids": sorted(cited),
            "f7_neutral_shipment_ids": sorted(f7_neutral),
            "true_f8_shipment_ids": sorted(true_f8),
            **pr,
            "excluded_from_f8_metric": excluded_from_f8_metric,
            "verifiable_t": record["score"]["verifiable_t"],
            "true_verifiable_t": true_verifiable_t,
            "verifiable_t_abs_error": abs_error,
        }
        verifiable_errors.append(abs_error)
        if not excluded_from_f8_metric:
            agg_tp += pr["tp"]
            agg_fp += pr["fp"]
            agg_fn += pr["fn"]
            false_citations.extend(
                {"processor_id": pid, "shipment_id": sid}
                for sid in sorted(cited_for_metric - true_f8)
            )

    overall_precision = agg_tp / (agg_tp + agg_fp) if (agg_tp + agg_fp) else 1.0
    overall_recall = agg_tp / (agg_tp + agg_fn) if (agg_tp + agg_fn) else 1.0
    overall_f1 = (
        2 * overall_precision * overall_recall / (overall_precision + overall_recall)
        if (overall_precision + overall_recall)
        else 0.0
    )
    agent_status_counts: dict[str, int] = {}
    for record in run_record["processors"].values():
        agent_status_counts[record["agent_status"]] = (
            agent_status_counts.get(record["agent_status"], 0) + 1
        )

    return {
        "per_processor": per_processor,
        "overall_precision": overall_precision,
        "overall_recall": overall_recall,
        "overall_f1": overall_f1,
        "mean_verifiable_t_abs_error": (
            sum(verifiable_errors) / len(verifiable_errors) if verifiable_errors else 0.0
        ),
        "false_citations": false_citations,
        "agent_status_counts": agent_status_counts,
    }


def compute_run_to_run_agreement(run_a: dict, run_b: dict) -> dict:
    per_processor = {}
    jaccards = []
    for pid in run_a["processors"]:
        cited_a = _cited_shipment_ids(run_a["processors"][pid])
        cited_b = _cited_shipment_ids(run_b["processors"][pid])
        union = cited_a | cited_b
        jaccard = len(cited_a & cited_b) / len(union) if union else 1.0
        jaccards.append(jaccard)
        per_processor[pid] = {
            "cited_a": sorted(cited_a),
            "cited_b": sorted(cited_b),
            "jaccard": jaccard,
            "verifiable_t_a": run_a["processors"][pid]["score"]["verifiable_t"],
            "verifiable_t_b": run_b["processors"][pid]["score"]["verifiable_t"],
        }
    return {
        "per_processor": per_processor,
        "mean_jaccard": sum(jaccards) / len(jaccards) if jaccards else 1.0,
    }


def _run_cost_usd(run_record: dict) -> float:
    return sum(
        estimate_cost_usd(r["input_tokens"], r["output_tokens"], r["thinking_tokens"])
        for r in run_record["call_log"]
    )


def _write_run_to_bigquery(bq_client, run_record: dict) -> None:
    """Same shape/idempotency as scripts/run_pipeline.py's run_agents() —
    deliberately duplicated here only for the write, not the fetch (the
    fetch is already shared via fetch_agent_inputs/build_processor_context)."""
    agent_run_rows = []
    assessment_rows = []
    for pid, record in run_record["processors"].items():
        for step in record["trail"]:
            agent_run_rows.append(
                {
                    "seed": SEED,
                    "facts_source": TRUTH,
                    "processor_id": pid,
                    "computed_at": run_record["computed_at"],
                    "step_index": step["step_index"],
                    "step_type": step["step_type"],
                    "tool_name": step["tool_name"],
                    "tool_args_json": step["tool_args_json"],
                    "input_summary": step["input_summary"],
                    "output_json": step["output_json"],
                    "latency_ms": None,
                    "input_tokens": None,
                    "output_tokens": None,
                    "thinking_tokens": None,
                }
            )
        assessment_rows.append(
            {
                "seed": SEED,
                "facts_source": TRUTH,
                "stage": "full",
                "computed_at": run_record["computed_at"],
                "agent_status": record["agent_status"],
                **record["score"],
            }
        )

    bq.delete_by_seed_and_source(bq_client, "agent_runs", SEED, TRUTH)
    bq.load_rows(bq_client, "agent_runs", agent_run_rows)
    bq.delete_assessments_by_stage(bq_client, SEED, TRUTH, "full")
    bq.load_rows(bq_client, "assessments", assessment_rows)


def _print_finding(f: dict, label: str) -> None:
    print(f"  finding_type: {f['finding_type']} [{label}]")
    print(f"  cited_shipment_ids: {f['cited_shipment_ids']}")
    print(f"  evidence_ids: {f['evidence_ids']}")
    print(f"  explanation: {f['explanation']}")
    print()


def _print_every_finding(all_runs: list[dict]) -> None:
    """Every finding from every agreement path (docs/PROGRESS.md's
    Hypothesis-findings restructure): confirmed (further split into
    deductible/systemic/no-own-evidence, same as before), review-flagged
    (the agents disagreed — kept visible, never deducted), and withdrawn
    (the Hypothesis itself retracted it after the Critic disputed it —
    trail-only, shown here anyway for full transparency rather than
    silently dropped)."""
    print("\n=== Every finding, in full ===")
    for run_record in all_runs:
        for pid, record in run_record["processors"].items():
            has_any = (
                record["confirmed_findings"]
                or record["review_flag_findings"]
                or record["withdrawn_findings"]
            )
            if not has_any:
                continue
            print(f"{run_record['config_name']} run {run_record['run_index']} / {pid}:")
            systemic_findings = record["systemic_findings"]
            no_evidence_findings = record["no_evidence_findings"]
            for f in record["confirmed_findings"]:
                if f in no_evidence_findings:
                    label = "confirmed, no own evidence (not deducted)"
                elif f in systemic_findings:
                    label = "confirmed, systemic (not deducted)"
                else:
                    label = "confirmed, deductible"
                _print_finding(f, label)
            for f in record["review_flag_findings"]:
                _print_finding(f, "review flag (agents disagreed, not deducted)")
            for f in record["withdrawn_findings"]:
                _print_finding(f, "withdrawn (trail only, no scoring effect)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--processors",
        help="Comma-separated processor_ids to restrict this run to (e.g. a canary run "
        "on PWP-01,PWP-03,PWP-07). Default: all processors.",
    )
    parser.add_argument(
        "--configs",
        default="no_thinking,low_thinking",
        help="Comma-separated subset of configs to run. Default: both.",
    )
    parser.add_argument(
        "--runs-per-config",
        type=int,
        default=RUNS_PER_CONFIG,
        help="Default: 2 (needed for the run-to-run agreement metric). A canary run "
        "should pass 1 — the decision/winner step is skipped whenever fewer than both "
        "configs x 2 runs are present.",
    )
    args = parser.parse_args()

    configs = [c for c in CONFIGS if c[0] in args.configs.split(",")]
    runs_per_config = args.runs_per_config
    requested_processors = set(args.processors.split(",")) if args.processors else None

    ground_truth = load_ground_truth(SEED)
    bq_client = bq.get_client()
    gcs_client = gcs.get_client()
    inputs = fetch_agent_inputs(bq_client, SEED, TRUTH, processor_filter=None)
    if inputs is None:
        print("Nothing to probe — run --stage normalize/checks/site first.")
        return
    if requested_processors is not None:
        inputs["processors"] = [
            p for p in inputs["processors"] if p["processor_id"] in requested_processors
        ]
        missing = requested_processors - {p["processor_id"] for p in inputs["processors"]}
        if missing:
            print(f"Warning: requested processor(s) not found, skipping: {sorted(missing)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_runs = []
    for config_name, thinking_level in configs:
        for run_index in range(1, runs_per_config + 1):
            run_record = run_one(config_name, thinking_level, run_index, inputs, gcs_client)
            run_record["computed_at"] = datetime.now(UTC).isoformat()
            run_record["metrics"] = compute_run_metrics(run_record, ground_truth)
            run_record["cost_usd"] = _run_cost_usd(run_record)
            all_runs.append(run_record)

            out_path = OUTPUT_DIR / f"{config_name}_run{run_index}.json"
            out_path.write_text(json.dumps(run_record, indent=2, default=str), encoding="utf-8")
            print(f"Saved: {out_path}")

            # Write as it goes (visible progress on a long run); the
            # winning config's run is re-written at the end if it wasn't
            # the last one written.
            _write_run_to_bigquery(bq_client, run_record)

    print("\n=== Per-run summary ===")
    for run_record in all_runs:
        m = run_record["metrics"]
        print(
            f"{run_record['config_name']} run {run_record['run_index']}: "
            f"F1={m['overall_f1']:.3f} precision={m['overall_precision']:.3f} "
            f"recall={m['overall_recall']:.3f} "
            f"mean_verifiable_t_abs_error={m['mean_verifiable_t_abs_error']:.2f}t "
            f"false_citations={len(m['false_citations'])} "
            f"agent_status={m['agent_status_counts']} "
            f"cost=${run_record['cost_usd']:.4f}"
        )
        if m["false_citations"]:
            print(f"    false citations: {m['false_citations']}")

    _print_every_finding(all_runs)

    is_full_acceptance_shape = len(configs) == len(CONFIGS) and runs_per_config == 2
    if not is_full_acceptance_shape:
        print(
            "\nPartial run (canary or single-config) — skipping the run-to-run agreement "
            "and winner decision, which need both configs x 2 runs each. Review the "
            "findings above, then run the full acceptance pair when ready."
        )
        return

    print("\n=== Run-to-run agreement within each config ===")
    config_scores = {}
    for config_name, _ in CONFIGS:
        runs = [r for r in all_runs if r["config_name"] == config_name]
        agreement = compute_run_to_run_agreement(runs[0], runs[1])
        print(f"{config_name}: mean_jaccard={agreement['mean_jaccard']:.3f}")
        avg_f1 = sum(r["metrics"]["overall_f1"] for r in runs) / len(runs)
        total_cost = sum(r["cost_usd"] for r in runs)
        config_scores[config_name] = {
            "avg_f1": avg_f1,
            "mean_jaccard": agreement["mean_jaccard"],
            "total_cost_usd": total_cost,
            "runs": runs,
        }
        print(f"{config_name}: avg_f1={avg_f1:.3f} total_cost=${total_cost:.4f}")

    no_thinking = config_scores["no_thinking"]
    low_thinking = config_scores["low_thinking"]
    if low_thinking["avg_f1"] > no_thinking["avg_f1"]:
        winner = "low_thinking"
    else:
        # Strictly greater required to beat the default — a tie (or
        # worse) keeps no_thinking, per the approved T10 plan.
        winner = "no_thinking"

    print(f"\n=== Decision: {winner} ===")
    winning_runs = config_scores[winner]["runs"]
    last_written_config = all_runs[-1]["config_name"]
    if last_written_config != winner:
        print(
            f"Last run written to BigQuery was {last_written_config!r}, not the winner — "
            "re-writing the winning run now."
        )
        _write_run_to_bigquery(bq_client, winning_runs[-1])
    else:
        print("The winning config's run is already the last one written to BigQuery.")

    summary_path = OUTPUT_DIR / "summary.json"
    summary = {
        "winner": winner,
        "configs": {
            name: {
                "avg_f1": scores["avg_f1"],
                "mean_jaccard": scores["mean_jaccard"],
                "total_cost_usd": scores["total_cost_usd"],
            }
            for name, scores in config_scores.items()
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSaved decision summary: {summary_path}")


if __name__ == "__main__":
    main()
