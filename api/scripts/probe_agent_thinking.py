"""One-off probe: model-default thinking (no thinking config sent) vs
thinking_level="low" for the T10 agent loop, across all 10 processors,
2 runs per config (4 full runs total) — measures which config wins on
cited-shipment accuracy against ground truth, and whether a config is
consistent run-to-run.

This is the T10 acceptance run (docs/BUILD_PLAN.md): confirms F8 is
detected (with the right shipments cited) on the two seeded F8
processors, confirms no false findings appear elsewhere, and reports the
real token/cost totals from llm_calls.

Reads ground_truth.json only for scoring (is_f8 / is_f9 / true_verifiable_t) —
never for building what the agents themselves see; that boundary is
scripts/run_pipeline.py's fetch_agent_inputs()/build_processor_context(),
reused here unchanged (see tests/test_agent_leak_guard.py) for either
--facts-source.

Never send thinking_budget, or thinking_level="minimal", to Gemini 3.x
models (developer instruction; enforced in app/llm.py) — this script only
ever tries "low" against model-default thinking.

Run by the developer — never by the agent (hits real Vertex AI,
BigQuery, Cloud Storage). Requires --stage normalize/checks/site to have
already been run for this seed (agent context is read from their output
tables) — and, for --facts-source extracted, --stage extract too.

--seed defaults to 42 (the development set); T14's held-out evaluation
passes --seed 7 — every output path (agent_probe_runs/) and BigQuery
write (agent_runs/assessments) is seed-scoped, so the two never collide.

Usage: uv run python scripts/probe_agent_thinking.py
       uv run python scripts/probe_agent_thinking.py --processors PWP-01,PWP-03,PWP-07 \\
           --configs no_thinking --runs-per-config 1   # canary, before the full acceptance pair
       uv run python scripts/probe_agent_thinking.py --facts-source extracted \\
           --configs no_thinking --runs-per-config 2
       uv run python scripts/probe_agent_thinking.py --seed 7 --facts-source extracted \\
           --configs no_thinking --runs-per-config 3   # T14: 3 independent runs for stability
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.agents.orchestrator import classify_confirmed_findings, run_agent_loop_with_retry
from app.agents.scorer import (
    build_disputed_finding_check_result,
    build_no_own_evidence_finding_check_result,
    build_systemic_finding_check_result,
    score_processor,
)
from app.checks import params
from app.eval.evaluate import (
    cited_shipment_ids as _cited_shipment_ids,
)
from app.eval.evaluate import (
    f5_processor_ids as _f5_processor_ids,
)
from app.eval.evaluate import (
    f7_neutral_shipment_ids as _f7_neutral_shipment_ids,
)
from app.eval.evaluate import (
    ground_truth_processor as _ground_truth_processor,
)
from app.eval.evaluate import (
    ground_truth_true_positive_shipment_ids as _ground_truth_true_positive_shipment_ids,
)
from app.eval.evaluate import (
    precision_recall_f1 as _precision_recall_f1,
)
from app.ingest.normalize import EXTRACTED, TRUTH
from app.llm import GeminiClient
from app.models.agent import Objection
from app.models.checks import CheckResult
from app.store import bq, gcs
from scripts.cost_report import estimate_cost_usd
from scripts.run_pipeline import build_processor_context, fetch_agent_inputs, load_ground_truth

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS = [("no_thinking", None), ("low_thinking", "low")]
RUNS_PER_CONFIG = 2


def run_one(
    config_name: str,
    thinking_level: str | None,
    run_index: int,
    inputs: dict,
    gcs_client,
    facts_source: str = TRUTH,
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
        loop_result, attempts = run_agent_loop_with_retry(
            processor_context, llm_client, params.AGENT_TIMEOUT_S, thinking_level=thinking_level
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
            "concurs_with_check_findings": [
                f.model_dump() for f in loop_result["concurs_with_check_findings"]
            ],
            "trail": loop_result["trail"],
            "attempts": attempts,
            "score": score,
        }
        retried_note = f" (retried, {len(attempts)} attempts)" if len(attempts) > 1 else ""
        print(
            f"  {pid}: agent_status={loop_result['agent_status']}{retried_note} "
            f"confirmed_findings={len(loop_result['confirmed_findings'])} "
            f"(deductible={len(loop_result['deductible_findings'])}, "
            f"systemic={len(loop_result['systemic_findings'])}, "
            f"no_evidence={len(loop_result['no_evidence_findings'])}, "
            f"concurs_with_check={len(loop_result['concurs_with_check_findings'])}, "
            f"review_flag={len(loop_result['review_flag_findings'])}, "
            f"withdrawn={len(loop_result['withdrawn_findings'])}) "
            f"verifiable={score['verifiable_t']:.2f}t risk={score['risk_band']}"
        )

    return {
        "config_name": config_name,
        "thinking_level": thinking_level,
        "run_index": run_index,
        "facts_source": facts_source,
        "as_of_month": inputs["as_of_month"],
        "processors": processors_record,
        "call_log": llm_client.flush_call_log(),
    }


def compute_run_metrics(run_record: dict, ground_truth: dict) -> dict:
    per_processor = {}
    agg_tp = agg_fp = agg_fn = 0
    verifiable_errors = []
    false_citations = []
    f5_processor_ids = _f5_processor_ids(ground_truth)

    for pid, record in run_record["processors"].items():
        true_positive_ids = _ground_truth_true_positive_shipment_ids(ground_truth, pid)
        cited = _cited_shipment_ids(record)
        f7_neutral = _f7_neutral_shipment_ids(ground_truth, pid)
        cited_for_metric = cited - f7_neutral
        pr = _precision_recall_f1(cited_for_metric, true_positive_ids)
        true_verifiable_t = _ground_truth_processor(ground_truth, pid)["true_verifiable_t"]
        abs_error = abs(record["score"]["verifiable_t"] - true_verifiable_t)
        excluded_from_f8_metric = pid in f5_processor_ids

        per_processor[pid] = {
            "cited_shipment_ids": sorted(cited),
            "f7_neutral_shipment_ids": sorted(f7_neutral),
            "true_f8_shipment_ids": sorted(true_positive_ids),
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
                for sid in sorted(cited_for_metric - true_positive_ids)
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


def _attempts_from_record(record: dict) -> list[dict]:
    """New runs (after the 2026-10-08 processor-level retry) store
    "attempts" directly. A --rescore of an already-saved pre-retry run
    (e.g. the acceptance pair's own saved JSON, written before this
    change landed) only has a flat "trail" — treated as a single
    attempt 1, so rescoring an old file still writes correctly tagged
    rows instead of KeyError-ing."""
    if "attempts" in record:
        return record["attempts"]
    return [{"attempt": 1, "trail": record["trail"]}]


def _write_run_to_bigquery(bq_client, run_record: dict, seed: int) -> None:
    """Same shape/idempotency as scripts/run_pipeline.py's run_agents() —
    deliberately duplicated here only for the write, not the fetch (the
    fetch is already shared via fetch_agent_inputs/build_processor_context).
    facts_source comes from the run_record itself (set by run_one), with a
    TRUTH fallback for runs saved before this field existed — same fallback
    pattern as _attempts_from_record below."""
    facts_source = run_record.get("facts_source", TRUTH)
    agent_run_rows = []
    assessment_rows = []
    for pid, record in run_record["processors"].items():
        for attempt in _attempts_from_record(record):
            for step in attempt["trail"]:
                agent_run_rows.append(
                    {
                        "seed": seed,
                        "facts_source": facts_source,
                        "processor_id": pid,
                        "attempt": attempt["attempt"],
                        "computed_at": run_record["computed_at"],
                        "step_index": step["step_index"],
                        "step_type": step["step_type"],
                        "tool_name": step["tool_name"],
                        "tool_args_json": step["tool_args_json"],
                        "input_summary": step["input_summary"],
                        "output_json": step["output_json"],
                        # Populated by run_agent_loop from GeminiClient.call_log
                        # (docs/PROGRESS.md) — None for steps with no
                        # underlying Gemini call.
                        "latency_ms": step.get("latency_ms"),
                        "input_tokens": step.get("input_tokens"),
                        "output_tokens": step.get("output_tokens"),
                        "thinking_tokens": step.get("thinking_tokens"),
                    }
                )
        assessment_rows.append(
            {
                "seed": seed,
                "facts_source": facts_source,
                "stage": "full",
                "computed_at": run_record["computed_at"],
                "agent_status": record["agent_status"],
                **record["score"],
            }
        )

    bq.delete_by_seed_and_source(bq_client, "agent_runs", seed, facts_source)
    bq.load_rows(bq_client, "agent_runs", agent_run_rows)
    bq.delete_assessments_by_stage(bq_client, seed, facts_source, "full")
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
            concurs_with_check_findings = record["concurs_with_check_findings"]
            for f in record["confirmed_findings"]:
                if f in concurs_with_check_findings:
                    label = "confirmed, concurs with check (not deducted, no additional bump)"
                elif f in no_evidence_findings:
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


def rescore_and_write(run_path: Path, inputs: dict, gcs_client, bq_client, seed: int) -> dict:
    """Re-applies classify_confirmed_findings (a scoring-rule change —
    docs/PROGRESS.md's concurs-with-check rule) to an already-saved run's
    confirmed_findings, against this processor's CURRENT check_results —
    no Gemini call, no re-running the agent loop at all. Overwrites
    run_path with the corrected record (trail/conclusions/objections/etc.
    untouched — only the classification buckets, excluded_shipment_ids
    and score change) and writes it to BigQuery as stage="full", the
    same write _write_run_to_bigquery always does. Used once, by hand,
    to land a scoring-rule fix without burning a second ~$3 Gemini run."""
    run_record = json.loads(run_path.read_text(encoding="utf-8"))
    processors_by_id = {p["processor_id"]: p for p in inputs["processors"]}

    for pid, record in run_record["processors"].items():
        processor_context, _ = build_processor_context(inputs, processors_by_id[pid], gcs_client)
        confirmed_findings = [Objection(**d) for d in record["confirmed_findings"]]
        classified = classify_confirmed_findings(confirmed_findings, processor_context)

        score_check_results = list(
            CheckResult(**{k: v for k, v in c.items() if k != "processor_id"})
            for c in processor_context["check_results"]
        )
        if classified["systemic_findings"]:
            score_check_results.append(
                build_systemic_finding_check_result(classified["systemic_findings"])
            )
        if classified["no_evidence_findings"]:
            score_check_results.append(
                build_no_own_evidence_finding_check_result(classified["no_evidence_findings"])
            )
        review_flag = [Objection(**d) for d in record["review_flag_findings"]]
        if review_flag:
            score_check_results.append(build_disputed_finding_check_result(review_flag))

        score = score_processor(
            processors_by_id[pid],
            processor_context["certificates"],
            processor_context["shipments"],
            processor_context["duplicate_keys"],
            score_check_results,
            inputs["as_of_month"],
            excluded_shipment_ids=classified["excluded_shipment_ids"],
        )

        record["deductible_findings"] = [f.model_dump() for f in classified["deductible_findings"]]
        record["systemic_findings"] = [f.model_dump() for f in classified["systemic_findings"]]
        record["no_evidence_findings"] = [
            f.model_dump() for f in classified["no_evidence_findings"]
        ]
        record["concurs_with_check_findings"] = [
            f.model_dump() for f in classified["concurs_with_check_findings"]
        ]
        record["score"] = score
        print(
            f"  {pid}: rescored — deductible={len(classified['deductible_findings'])} "
            f"systemic={len(classified['systemic_findings'])} "
            f"no_evidence={len(classified['no_evidence_findings'])} "
            f"concurs_with_check={len(classified['concurs_with_check_findings'])} "
            f"verifiable={score['verifiable_t']:.2f}t risk={score['risk_band']}"
        )

    run_record["computed_at"] = datetime.now(UTC).isoformat()
    run_record["metrics"] = compute_run_metrics(run_record, load_ground_truth(seed))
    run_path.write_text(json.dumps(run_record, indent=2, default=str), encoding="utf-8")
    print(f"Rescored, saved: {run_path}")
    _write_run_to_bigquery(bq_client, run_record, seed)
    print("Written to BigQuery as stage='full'.")
    return run_record


def _resolve_rescore_path(raw: str, output_dir: Path) -> Path:
    """--rescore accepts a bare filename or a path; resolved against the
    current working directory first (so an explicit relative/absolute
    path still works), then against output_dir (this seed's own
    agent_probe_runs directory) so a bare filename like
    "no_thinking_run2.json" works regardless of where this script is
    invoked from."""
    as_given = Path(raw)
    if as_given.exists():
        return as_given
    candidate = output_dir / as_given.name
    if candidate.exists():
        return candidate
    raise FileNotFoundError(
        f"--rescore {raw!r} not found as given ({as_given}) or under output_dir ({candidate})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Default: 42 (the development set). T14's held-out evaluation passes --seed 7.",
    )
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
    parser.add_argument(
        "--facts-source",
        choices=[TRUTH, EXTRACTED],
        default=TRUTH,
        help="Build agent context from ground truth or real extracted_facts (same meaning "
        "as scripts/run_pipeline.py's --stage agents --facts-source). Default: truth. "
        "Saved run files get a _extracted suffix for this mode, so they never collide "
        "with the committed truth-mode acceptance-pair files.",
    )
    parser.add_argument(
        "--rescore",
        help="An already-saved agent_probe_runs/*.json to re-classify under the CURRENT "
        "code (e.g. after a scoring-rule change) and write to BigQuery as stage='full' — "
        "no Gemini call at all, just a local reclassify + a BigQuery write. Takes either a "
        "bare filename (e.g. no_thinking_run2.json, resolved against this seed's own "
        "agent_probe_runs directory regardless "
        "of the current working directory) or a path, resolved relative to the current "
        "working directory (run this script from api/, same as every other command here). "
        "Mutually exclusive with running new probes.",
    )
    args = parser.parse_args()

    configs = [c for c in CONFIGS if c[0] in args.configs.split(",")]
    runs_per_config = args.runs_per_config
    requested_processors = set(args.processors.split(",")) if args.processors else None

    seed = args.seed
    output_dir = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}" / "agent_probe_runs"

    bq_client = bq.get_client()
    gcs_client = gcs.get_client()
    inputs = fetch_agent_inputs(bq_client, seed, args.facts_source, processor_filter=None)
    if inputs is None:
        print("Nothing to probe — run --stage normalize/checks/site first.")
        return

    if args.rescore:
        rescore_and_write(
            _resolve_rescore_path(args.rescore, output_dir), inputs, gcs_client, bq_client, seed
        )
        return

    ground_truth = load_ground_truth(seed)
    if requested_processors is not None:
        inputs["processors"] = [
            p for p in inputs["processors"] if p["processor_id"] in requested_processors
        ]
        missing = requested_processors - {p["processor_id"] for p in inputs["processors"]}
        if missing:
            print(f"Warning: requested processor(s) not found, skipping: {sorted(missing)}")

    output_dir.mkdir(parents=True, exist_ok=True)

    filename_suffix = "" if args.facts_source == TRUTH else f"_{args.facts_source}"

    all_runs = []
    for config_name, thinking_level in configs:
        for run_index in range(1, runs_per_config + 1):
            run_record = run_one(
                config_name,
                thinking_level,
                run_index,
                inputs,
                gcs_client,
                facts_source=args.facts_source,
            )
            run_record["computed_at"] = datetime.now(UTC).isoformat()
            run_record["metrics"] = compute_run_metrics(run_record, ground_truth)
            run_record["cost_usd"] = _run_cost_usd(run_record)
            all_runs.append(run_record)

            out_path = output_dir / f"{config_name}{filename_suffix}_run{run_index}.json"
            out_path.write_text(json.dumps(run_record, indent=2, default=str), encoding="utf-8")
            print(f"Saved: {out_path}")

            # Write as it goes (visible progress on a long run); the
            # winning config's run is re-written at the end if it wasn't
            # the last one written.
            _write_run_to_bigquery(bq_client, run_record, seed)

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
        _write_run_to_bigquery(bq_client, winning_runs[-1], seed)
    else:
        print("The winning config's run is already the last one written to BigQuery.")

    summary_path = output_dir / f"summary{filename_suffix}.json"
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
