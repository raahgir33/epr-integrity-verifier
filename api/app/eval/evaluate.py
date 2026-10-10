"""Metrics vs ground truth. Extraction field accuracy (T6's gate) plus
T14's held-out-evaluation metrics: issue-type recall, check/agent finding
precision, false flags on clean/hard-negative processors, risk-band
accuracy, verifiable-tonnes error, run-to-run finding-set agreement
(pooled Jaccard) and outcome stability (risk_band/unverifiable_t held
identical across runs), and whether a missed planted issue (F5/F7) at
least surfaced as a review flag. Every function here is pure (no I/O) —
scripts/evaluate.py and scripts/probe_agent_thinking.py are the callers
that fetch real data and write results.
"""

import itertools
import math

from app.agents.scorer import risk_band

# docs/DATA_SPEC.md §5: which deterministic check(s) are documented as
# catching each seeded issue type. F8/F9 have no entry — agent-only, no
# deterministic check behind either (see issue_recall_F8/F9's own
# computation in scripts/evaluate.py, via cited-shipment precision/recall
# instead of a check status). C2/C3 are split into C2a/C3a/C3b in the
# actual check implementations (app/checks/{mass_balance,transport}.py);
# "any of the mapped check IDs fails" is treated as the issue being caught,
# matching the table's own looser "C2, C3" phrasing rather than picking one
# sub-check arbitrarily.
CHECK_IDS_BY_ISSUE_TYPE: dict[str, set[str]] = {
    "F1": {"C1"},
    "F2": {"C2a", "C3a", "C3b"},
    "F3": {"C2a", "C4"},
    "F4": {"C5"},
    "F5": {"C8"},
    "F6": {"C6"},
    "F7": {"C7"},
}

# Every field except free-text ones (item_description, address, names,
# categories, remarks) — the "key numeric and ID fields" the T6 gate is
# measured against (docs/BUILD_PLAN.md T6).
KEY_FIELDS_BY_DOC_TYPE: dict[str, set[str]] = {
    "cto": {"consent_no", "capacity_t_per_year", "valid_from", "valid_to"},
    "epr_registration": {"registration_no", "capacity_t_per_year"},
    "inbound_invoice": {
        "invoice_no",
        "date",
        "supplier_gstin",
        "buyer_gstin",
        "hsn",
        "quantity_t",
        "rate",
        "value",
    },
    "eway_bill": {
        "ewb_no",
        "generated_at",
        "valid_until",
        "from_gstin",
        "to_gstin",
        "from_pin",
        "to_pin",
        "distance_km",
        "vehicle_no",
        "hsn",
        "quantity_t",
        "value",
        "invoice_no",
    },
    "weighbridge_slip": {
        "ticket_no",
        "vehicle_no",
        "gross_kg",
        "tare_kg",
        "net_kg",
        "in_time",
        "out_time",
    },
    "outbound_invoice": {"invoice_no", "date", "hsn", "quantity_t"},
    "electricity_bill": {"billing_month", "units_consumed_kwh", "connected_load_kw"},
}


def extraction_field_accuracy(extracted_rows: list[dict], ground_truth_docs: list[dict]) -> dict:
    """extracted_rows: extracted_facts-shaped dicts (doc_id, field_name,
    printed_value, ...). ground_truth_docs: ground_truth.json's "documents"
    list (doc_id, doc_type, fields: {name: {printed, canonical}}).

    Returns {doc_type: {correct, total, accuracy}, ..., "overall": {...}}.
    Pure function — no I/O — so it's unit-testable without BigQuery.
    """
    gt_by_doc = {d["doc_id"]: d for d in ground_truth_docs}
    rows_by_doc: dict[str, list[dict]] = {}
    for row in extracted_rows:
        rows_by_doc.setdefault(row["doc_id"], []).append(row)

    per_type: dict[str, dict[str, int]] = {}
    for doc_id, rows in rows_by_doc.items():
        gt_doc = gt_by_doc.get(doc_id)
        if gt_doc is None:
            continue
        doc_type = gt_doc["doc_type"]
        key_fields = KEY_FIELDS_BY_DOC_TYPE.get(doc_type, set())
        gt_fields = gt_doc["fields"]
        extracted_by_field = {r["field_name"]: r["printed_value"] for r in rows}

        stats = per_type.setdefault(doc_type, {"correct": 0, "total": 0})
        for field_name in key_fields:
            if field_name not in gt_fields:
                continue
            gt_value = gt_fields[field_name]["printed"]
            extracted_value = extracted_by_field.get(field_name)
            stats["total"] += 1
            if extracted_value is not None and extracted_value.strip() == gt_value.strip():
                stats["correct"] += 1

    report: dict[str, dict] = {}
    overall_correct = 0
    overall_total = 0
    for doc_type, stats in per_type.items():
        accuracy = stats["correct"] / stats["total"] if stats["total"] else None
        report[doc_type] = {
            "correct": stats["correct"],
            "total": stats["total"],
            "accuracy": accuracy,
        }
        overall_correct += stats["correct"]
        overall_total += stats["total"]

    report["overall"] = {
        "correct": overall_correct,
        "total": overall_total,
        "accuracy": overall_correct / overall_total if overall_total else None,
    }
    return report


def extraction_field_mismatches(
    extracted_rows: list[dict], ground_truth_docs: list[dict]
) -> list[dict]:
    """Same inputs/matching rules as extraction_field_accuracy, but returns
    the actual mismatched (doc_id, field_name) pairs instead of just
    counts — one dict per mismatch: {doc_id, processor_id, doc_type,
    field_name, extracted_value, truth_value}. extracted_value is None
    when the field is a key field but Gemini's output didn't include it
    at all (as opposed to a wrong value). Pure function — no I/O."""
    gt_by_doc = {d["doc_id"]: d for d in ground_truth_docs}
    rows_by_doc: dict[str, list[dict]] = {}
    for row in extracted_rows:
        rows_by_doc.setdefault(row["doc_id"], []).append(row)

    mismatches: list[dict] = []
    for doc_id, rows in rows_by_doc.items():
        gt_doc = gt_by_doc.get(doc_id)
        if gt_doc is None:
            continue
        doc_type = gt_doc["doc_type"]
        key_fields = KEY_FIELDS_BY_DOC_TYPE.get(doc_type, set())
        gt_fields = gt_doc["fields"]
        extracted_by_field = {r["field_name"]: r["printed_value"] for r in rows}

        for field_name in key_fields:
            if field_name not in gt_fields:
                continue
            gt_value = gt_fields[field_name]["printed"]
            extracted_value = extracted_by_field.get(field_name)
            if extracted_value is not None and extracted_value.strip() == gt_value.strip():
                continue
            mismatches.append(
                {
                    "doc_id": doc_id,
                    "processor_id": gt_doc.get("processor_id"),
                    "doc_type": doc_type,
                    "field_name": field_name,
                    "extracted_value": extracted_value,
                    "truth_value": gt_value,
                }
            )
    return mismatches


def format_accuracy_pct(correct: int, total: int) -> str:
    """2-decimal-place percentage, truncated (never rounded) so a
    not-quite-perfect ratio can never print as "100.00%" — e.g. 5521/5523
    (99.9638...%) must read "99.96%", not round up at either the 1- or
    2-decimal boundary. Exact equality is the only path to "100.00%"."""
    if total == 0:
        return "n/a"
    if correct == total:
        return "100.00%"
    pct = correct / total * 100
    truncated = math.floor(pct * 100) / 100
    return f"{truncated:.2f}%"


# ---------- shared ground-truth/finding helpers (T14) ----------
#
# Moved here from scripts/probe_agent_thinking.py (T10) so
# scripts/evaluate.py can reuse the exact same F5/F7 exclusion rules
# without a second, divergent copy — these are subtle (docs/DATA_SPEC.md
# §7's cited-shipment scoring rule) and must stay identical between a
# probe run's own scoring and the held-out evaluation's. probe_agent_
# thinking.py keeps its own underscore-prefixed names as thin aliases to
# these, so its existing tests and call sites are unchanged.


def ground_truth_processor(ground_truth: dict, processor_id: str) -> dict:
    return next(p for p in ground_truth["processors"] if p["processor_id"] == processor_id)


def ground_truth_true_positive_shipment_ids(ground_truth: dict, processor_id: str) -> set[str]:
    """F8 and F9 are both agent-only (no deterministic check sees either),
    so both count as true positives for this shipment-citation metric."""
    gt_processor = ground_truth_processor(ground_truth, processor_id)
    return {s["shipment_id"] for s in gt_processor["shipments"] if s.get("is_f8") or s.get("is_f9")}


def cited_shipment_ids(processor_record: dict) -> set[str]:
    """processor_record: a probe run's own per-processor record (raw
    Objection dicts, with confirmed_findings/concurs_with_check_findings
    as separate lists) — scripts/probe_agent_thinking.py's run shape.
    Excludes concurs_with_check_findings: a finding that only restates
    what a deterministic check already caught is neutral for this metric,
    neither a true nor a false citation."""
    concurs_with_check = processor_record["concurs_with_check_findings"]
    return {
        sid
        for finding in processor_record["confirmed_findings"]
        if finding not in concurs_with_check
        for sid in finding["cited_shipment_ids"]
    }


def cited_shipment_ids_from_findings(findings: list[dict]) -> set[str]:
    """Same exclusion as cited_shipment_ids, for the API/cache's
    FindingOut-shaped list (app/store/cache.py's get_findings) instead of
    a probe run's raw record — each finding already carries its own
    `classification`, so no separate concurs_with_check_findings list is
    needed here."""
    return {
        sid
        for f in findings
        if f["classification"] != "concurs_with_check"
        for sid in f["cited_shipment_ids"]
    }


def precision_recall_f1(cited: set[str], true_positive: set[str]) -> dict:
    tp = len(cited & true_positive)
    fp = len(cited - true_positive)
    fn = len(true_positive - cited)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def f5_processor_ids(ground_truth: dict) -> set[str]:
    """docs/DATA_SPEC.md §7: F5 (ghost site) has no shipment-level
    manifestation — it's a site-level finding caught by C8 — so any
    shipment citation on an F5 processor is excluded from the F8/F9
    citation metric entirely, rather than counted as a false citation."""
    return {
        p["processor_id"] for p in ground_truth["processors"] if "F5" in p.get("issue_types", [])
    }


def f7_target_month(ground_truth_processor_row: dict) -> str | None:
    """The seeded F7 low-energy anomaly's month, found from the data
    itself — the month with minimum kwh in this processor's own
    energy_monthly."""
    energy_monthly = ground_truth_processor_row.get("energy_monthly") or []
    if not energy_monthly:
        return None
    return min(energy_monthly, key=lambda r: r["kwh"])["month"]


def f7_neutral_shipment_ids(ground_truth: dict, processor_id: str) -> set[str]:
    """docs/DATA_SPEC.md §7: a citation of a shipment in an F7 processor's
    own seeded low-energy month is neutral too — per-month, not
    per-processor like F5."""
    gt_processor = ground_truth_processor(ground_truth, processor_id)
    if "F7" not in gt_processor.get("issue_types", []):
        return set()
    target_month = f7_target_month(gt_processor)
    if target_month is None:
        return set()
    return {s["shipment_id"] for s in gt_processor["shipments"] if s.get("month") == target_month}


# ---------- T14 held-out evaluation metrics ----------


def _check_fires_for_issue(check_results: list[dict], issue_code: str) -> bool:
    check_ids = CHECK_IDS_BY_ISSUE_TYPE.get(issue_code, set())
    return any(r["check_id"] in check_ids and r["status"] == "fail" for r in check_results)


def issue_type_recall(
    check_results_by_processor: dict[str, list[dict]], ground_truth: dict, issue_code: str
) -> dict:
    """Share of processors with `issue_code` planted (docs/DATA_SPEC.md §5)
    where the mapped deterministic check(s) actually failed. F1-F7 only —
    F8/F9 have no deterministic check, scored separately via cited-shipment
    precision/recall. Returns {"numerator", "denominator"}."""
    planted = [p for p in ground_truth["processors"] if issue_code in p.get("issue_types", [])]
    detected = sum(
        1
        for p in planted
        if _check_fires_for_issue(check_results_by_processor.get(p["processor_id"], []), issue_code)
    )
    return {"numerator": detected, "denominator": len(planted)}


def missed_planted_processors(
    check_results_by_processor: dict[str, list[dict]], ground_truth: dict, issue_code: str
) -> list[str]:
    """issue_type_recall's own misses, broken out by processor_id: ids
    where `issue_code` was planted but the mapped deterministic check(s)
    never failed."""
    planted = [p for p in ground_truth["processors"] if issue_code in p.get("issue_types", [])]
    return [
        p["processor_id"]
        for p in planted
        if not _check_fires_for_issue(
            check_results_by_processor.get(p["processor_id"], []), issue_code
        )
    ]


def issue_surfaced_as_review_flag(
    missed_processor_ids: list[str], findings_by_processor: dict[str, list[dict]]
) -> dict:
    """Of the processors where a planted issue was missed by the
    deterministic check (missed_planted_processors), the share where the
    agent raised it anyway as a review_flag finding (docs/DATA_SPEC.md §4a:
    review_flag findings are kept visible but never deducted — this
    checks whether that visibility actually happened for a miss, rather
    than the issue vanishing from the report entirely). findings_by_
    processor: the API/cache's FindingOut-shaped list (get_findings)."""
    surfaced = sum(
        1
        for pid in missed_processor_ids
        if any(f["classification"] == "review_flag" for f in findings_by_processor.get(pid, []))
    )
    return {"numerator": surfaced, "denominator": len(missed_processor_ids)}


def finding_precision_checks(
    check_results_by_processor: dict[str, list[dict]], ground_truth: dict
) -> dict:
    """Precision of every F1-F7-mapped check's "fail" verdicts across every
    processor: a fail is a true positive if that processor's ground truth
    actually plants one of the issue types the failing check maps to."""
    planted_by_processor = {
        p["processor_id"]: set(p.get("issue_types", [])) for p in ground_truth["processors"]
    }
    tracked_check_ids = {c for checks in CHECK_IDS_BY_ISSUE_TYPE.values() for c in checks}
    reverse_map: dict[str, set[str]] = {}
    for issue_code, check_ids in CHECK_IDS_BY_ISSUE_TYPE.items():
        for check_id in check_ids:
            reverse_map.setdefault(check_id, set()).add(issue_code)

    tp = fp = 0
    for pid, results in check_results_by_processor.items():
        planted = planted_by_processor.get(pid, set())
        for r in results:
            if r["check_id"] not in tracked_check_ids or r["status"] != "fail":
                continue
            if reverse_map.get(r["check_id"], set()) & planted:
                tp += 1
            else:
                fp += 1
    return {"numerator": tp, "denominator": tp + fp}


def processor_wrongly_flagged(check_results: list[dict], findings: list[dict]) -> bool:
    """True if any deterministic check failed, or any confirmed agent
    finding fired (other than one that only concurs with a check already
    counted) — the shared "was this processor flagged at all" predicate
    for the false-flag metrics below."""
    checks_failed = any(r["status"] == "fail" for r in check_results)
    new_agent_findings = any(f["classification"] != "concurs_with_check" for f in findings)
    return checks_failed or new_agent_findings


def _false_flag_rate(
    processor_ids: list[str],
    check_results_by_processor: dict[str, list[dict]],
    findings_by_processor: dict[str, list[dict]],
) -> dict:
    flagged = sum(
        1
        for pid in processor_ids
        if processor_wrongly_flagged(
            check_results_by_processor.get(pid, []), findings_by_processor.get(pid, [])
        )
    )
    return {"numerator": flagged, "denominator": len(processor_ids)}


def false_flags_on_clean(
    check_results_by_processor: dict[str, list[dict]],
    findings_by_processor: dict[str, list[dict]],
    ground_truth: dict,
) -> dict:
    """Count of "clean" (no planted issue) processors wrongly flagged."""
    clean_ids = [p["processor_id"] for p in ground_truth["processors"] if p.get("label") == "clean"]
    return _false_flag_rate(clean_ids, check_results_by_processor, findings_by_processor)


def false_flags_on_hard_negatives(
    check_results_by_processor: dict[str, list[dict]],
    findings_by_processor: dict[str, list[dict]],
    ground_truth: dict,
) -> dict:
    """docs/DATA_SPEC.md §7: count of H1-H4-carrying processors wrongly
    flagged (H5 is excluded here — it's scored via the agent-citation
    precision metric instead, since it only ever manifests as a shipment
    citation, never a check failure)."""
    hard_case_ids = [
        p["processor_id"]
        for p in ground_truth["processors"]
        if set(p.get("hard_negatives", [])) & {"H1", "H2", "H3", "H4"}
    ]
    return _false_flag_rate(hard_case_ids, check_results_by_processor, findings_by_processor)


def _normalize_shipment_id(shipment_id: str) -> str:
    """Extracted-mode shipment_ids carry an extra "EXT-" segment
    (app/ingest/normalize.py's match_shipments_from_extracted:
    f"{processor_id}-EXT-SHP-{i:03d}") that ground_truth.json's own
    f"{processor_id}-SHP-{i:03d}" doesn't carry — both modes enumerate a
    processor's inbound invoices 1-indexed in the same order, so
    stripping "EXT-" makes a finding's cited_shipment_ids directly
    comparable to ground truth regardless of facts_source. Same fix as
    scripts/report_truth_vs_extracted.py's own helper of the same name;
    duplicated rather than imported since that script never ships to the
    deployed container. Without this, every extracted-mode citation
    metric scored near zero recall/precision purely from the ID mismatch,
    never from the agent's own citations being wrong."""
    return shipment_id.replace("EXT-", "", 1)


def agent_citation_metrics(
    findings_by_processor: dict[str, list[dict]], ground_truth: dict
) -> dict:
    """F8/F9 recall and precision (docs/DATA_SPEC.md §7's cited-shipment
    scoring rule), aggregated across every processor except F5 processors
    (excluded entirely) and minus each processor's own F7-neutral-month
    shipments. findings_by_processor: processor_id -> the API/cache's
    FindingOut-shaped confirmed-findings list (app/store/cache.py's
    get_findings)."""
    f5_ids = f5_processor_ids(ground_truth)
    agg_tp = agg_fp = agg_fn = 0
    for p in ground_truth["processors"]:
        pid = p["processor_id"]
        if pid in f5_ids:
            continue
        true_positive = ground_truth_true_positive_shipment_ids(ground_truth, pid)
        cited = {
            _normalize_shipment_id(sid)
            for sid in cited_shipment_ids_from_findings(findings_by_processor.get(pid, []))
        } - f7_neutral_shipment_ids(ground_truth, pid)
        pr = precision_recall_f1(cited, true_positive)
        agg_tp += pr["tp"]
        agg_fp += pr["fp"]
        agg_fn += pr["fn"]
    return {
        "recall": {"numerator": agg_tp, "denominator": agg_tp + agg_fn},
        "precision": {"numerator": agg_tp, "denominator": agg_tp + agg_fp},
    }


def risk_band_accuracy(assessments_by_processor: dict[str, dict], ground_truth: dict) -> dict:
    """assessments_by_processor: processor_id -> a StageAssessment-shaped
    dict (risk_band, certified_t) for one stage/facts_source. Ground-truth-
    implied band is computed from (certified_t - true_verifiable_t) /
    certified_t via app.agents.scorer.risk_band — the same frozen scoring
    function the pipeline itself uses, called read-only here, never
    re-implemented."""
    correct = 0
    total = 0
    for p in ground_truth["processors"]:
        row = assessments_by_processor.get(p["processor_id"])
        if row is None:
            continue
        certified_t = p["certified_t"]
        true_share = (certified_t - p["true_verifiable_t"]) / certified_t if certified_t else 0.0
        total += 1
        if row["risk_band"] == risk_band(true_share):
            correct += 1
    return {"numerator": correct, "denominator": total}


def verifiable_t_error(assessments_by_processor: dict[str, dict], ground_truth: dict) -> dict:
    """Mean absolute error (scaled to whole kilograms, so it fits an
    INTEGER eval_metrics numerator) and mean percentage error (scaled to
    millionths, denominator 1_000_000) between assessed verifiable_t and
    ground truth's true_verifiable_t, across every processor with a row in
    assessments_by_processor."""
    abs_errors_kg: list[float] = []
    pct_errors: list[float] = []
    for p in ground_truth["processors"]:
        row = assessments_by_processor.get(p["processor_id"])
        if row is None:
            continue
        true_verifiable_t = p["true_verifiable_t"]
        abs_error_t = abs(row["verifiable_t"] - true_verifiable_t)
        abs_errors_kg.append(abs_error_t * 1000.0)
        if true_verifiable_t:
            pct_errors.append(abs_error_t / true_verifiable_t)

    mean_abs_error_kg = sum(abs_errors_kg) / len(abs_errors_kg) if abs_errors_kg else 0.0
    mean_pct_error = sum(pct_errors) / len(pct_errors) if pct_errors else 0.0
    return {
        "abs_error_kg": round(mean_abs_error_kg),
        "pct_error_micro": round(mean_pct_error * 1_000_000),
    }


_ISSUE_LABELS = {
    "F1": "F1 capacity inflation",
    "F2": "F2 phantom inbound",
    "F3": "F3 quantity inflation",
    "F4": "F4 double use",
    "F5": "F5 ghost site",
    "F6": "F6 consent breach",
    "F7": "F7 energy implausibility",
}


def _split_facts_source_suffix(rest: str) -> tuple[str, str]:
    """ "checks_only_truth" -> ("checks_only", "truth") — a plain rsplit
    on "_" would break on a stage name ("checks_only") that itself
    contains an underscore, so this matches the two known facts_source
    suffixes ("truth", "extracted") directly instead."""
    for facts_source in ("extracted", "truth"):
        suffix = f"_{facts_source}"
        if rest.endswith(suffix):
            return rest[: -len(suffix)], facts_source
    return rest, ""


def describe_misses(rows: list[dict]) -> list[str]:
    """One honest, human-readable line per miss (a detection shortfall or
    a false flag) found in a dataset_label's eval_metrics rows — scoped to
    the metric families the T14 brief calls "misses": issue-type recall,
    agent-only (F8/F9) citation recall, false flags on clean/hard-negative
    processors, and risk-band accuracy. rows: eval_metrics-shaped dicts
    (metric, numerator, denominator) for one dataset_label — every number
    quoted here is one of those rows' own numerator/denominator, never
    invented. Pure function — no I/O, so the API/web layer calling this
    can't drift from what's actually stored."""
    misses: list[str] = []
    for row in rows:
        metric, num, den = row["metric"], row["numerator"], row["denominator"]

        if metric.startswith("issue_recall_"):
            issue_code, facts_source = _split_facts_source_suffix(metric[len("issue_recall_") :])
            if den and num < den:
                label = _ISSUE_LABELS.get(issue_code, issue_code)
                misses.append(
                    f"{label}: detected {num}/{den} planted instance(s) under {facts_source} facts."
                )

        elif metric.startswith("agent_citation_recall_"):
            facts_source = metric[len("agent_citation_recall_") :]
            if den and num < den:
                misses.append(
                    f"F8/F9 (agent-only, no deterministic check): recalled {num}/{den} true "
                    f"shipment citation(s) under {facts_source} facts."
                )

        elif metric.startswith("false_flags_clean_processors_"):
            facts_source = metric[len("false_flags_clean_processors_") :]
            if num > 0:
                misses.append(
                    f"{num}/{den} clean processor(s) wrongly flagged under {facts_source} facts."
                )

        elif metric.startswith("false_flags_hard_negatives_"):
            facts_source = metric[len("false_flags_hard_negatives_") :]
            if num > 0:
                misses.append(
                    f"{num}/{den} hard-negative processor(s) wrongly flagged under "
                    f"{facts_source} facts."
                )

        elif metric.startswith("risk_band_accuracy_"):
            stage, facts_source = _split_facts_source_suffix(metric[len("risk_band_accuracy_") :])
            if den and num < den:
                stage_label = "checks only" if stage == "checks_only" else "checks + agents"
                misses.append(
                    f"Risk band ({stage_label}, {facts_source} facts): {num}/{den} processor(s) "
                    "matched the ground-truth band."
                )

    return misses


def pooled_run_to_run_agreement(runs: list[dict]) -> dict:
    """runs: >=2 probe-run "processors" dicts (processor_id -> record, the
    same shape cited_shipment_ids takes). Pooled (micro-averaged) Jaccard
    agreement across every pairwise combination of runs: intersection/union
    counts are summed across every (pair, processor), not averaged per-
    processor-then-per-pair, so a few large-citation processors aren't
    diluted by many zero-citation ones. When both runs in a pair cite
    nothing for a processor, that pair/processor counts as full agreement
    (1/1) rather than an undefined 0/0 — same "nothing cited, nothing true,
    perfect" convention precision_recall_f1 uses. Deliberately a different
    definition from scripts/probe_agent_thinking.py's compute_run_to_run_
    agreement (which macro-averages one Jaccard per processor over exactly
    2 runs); this one generalizes to N>=2 runs for T14's 3-run stability
    check."""
    pids = runs[0].keys()
    total_intersection = 0
    total_union = 0
    for run_a, run_b in itertools.combinations(runs, 2):
        for pid in pids:
            cited_a = cited_shipment_ids(run_a[pid])
            cited_b = cited_shipment_ids(run_b[pid])
            union = cited_a | cited_b
            if not union:
                total_intersection += 1
                total_union += 1
            else:
                total_intersection += len(cited_a & cited_b)
                total_union += len(union)
    return {"numerator": total_intersection, "denominator": total_union}


def risk_band_stability(runs: list[dict]) -> dict:
    """Outcome-level stability companion to pooled_run_to_run_agreement's
    citation-set Jaccard: share of processors whose assessed risk_band
    (runs[i][pid]["score"]["risk_band"]) is identical across every run in
    `runs` (>=2 probe-run "processors" dicts). risk_band is the one number
    the processor page actually shows, so this is the metric a demo
    viewer would notice drifting even when citation-set agreement looks
    fine."""
    pids = runs[0].keys()
    stable = sum(1 for pid in pids if len({run[pid]["score"]["risk_band"] for run in runs}) == 1)
    return {"numerator": stable, "denominator": len(pids)}


def unverifiable_t_stability(runs: list[dict], tolerance_t: float = 0.01) -> dict:
    """Share of processors whose assessed unverifiable_t
    (runs[i][pid]["score"]["unverifiable_t"]) stays within `tolerance_t`
    tonnes of its own min/max across every run in `runs` — float-rounding
    noise only, not a materiality threshold (same tolerance
    scripts/report_truth_vs_extracted.py uses for the same reason)."""
    pids = runs[0].keys()
    stable = 0
    for pid in pids:
        values = [run[pid]["score"]["unverifiable_t"] for run in runs]
        if max(values) - min(values) <= tolerance_t:
            stable += 1
    return {"numerator": stable, "denominator": len(pids)}
