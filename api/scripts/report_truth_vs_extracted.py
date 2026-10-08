"""Developer-run, read-only comparison report: --facts-source truth vs
extracted precompute results for the same seed, per processor — check
statuses, verifiable_t (checks_only and full), and agent findings.
Differences are printed with a short cause (the measured values that
drove a check's status, or which side a finding only appeared on).

Reads through app/store/cache.py's existing public accessors (the same
ones app/main.py's routes use) — never writes anything, never calls
Gemini. Requires --stage normalize/checks/agents to have already been run
for BOTH --facts-source truth and extracted on this seed; a processor
missing an assessment on either side is reported as missing, not skipped
silently.

Run by the developer — never by the agent (hits real BigQuery).

Usage: uv run python scripts/report_truth_vs_extracted.py --seed 42
"""

import argparse

from app.ingest.normalize import EXTRACTED, TRUTH
from app.store import cache

VERIFIABLE_T_TOLERANCE = 0.01  # float-rounding noise only, not a materiality threshold


def diff_verifiable_t(truth_stage: dict | None, extracted_stage: dict | None) -> dict | None:
    """truth_stage/extracted_stage: a get_processor_assessments()["checks_only"
    or "full"] value, or None if that stage hasn't been scored on that
    side. Returns a diff dict if the two sides disagree beyond float
    noise (including either side missing entirely), else None. Pure —
    no I/O — so it's unit-testable without BigQuery."""
    if truth_stage is None or extracted_stage is None:
        if truth_stage is None and extracted_stage is None:
            return None
        return {
            "truth_verifiable_t": truth_stage["verifiable_t"] if truth_stage else None,
            "extracted_verifiable_t": extracted_stage["verifiable_t"] if extracted_stage else None,
            "truth_risk_band": truth_stage["risk_band"] if truth_stage else None,
            "extracted_risk_band": extracted_stage["risk_band"] if extracted_stage else None,
            "cause": f"missing on the {'extracted' if truth_stage else 'truth'} side — "
            "that stage hasn't been scored for this facts_source",
        }
    delta = extracted_stage["verifiable_t"] - truth_stage["verifiable_t"]
    same_risk_band = truth_stage["risk_band"] == extracted_stage["risk_band"]
    if abs(delta) <= VERIFIABLE_T_TOLERANCE and same_risk_band:
        return None
    return {
        "truth_verifiable_t": truth_stage["verifiable_t"],
        "extracted_verifiable_t": extracted_stage["verifiable_t"],
        "truth_risk_band": truth_stage["risk_band"],
        "extracted_risk_band": extracted_stage["risk_band"],
        "cause": f"verifiable_t delta {delta:+.2f}t — see check/finding diffs below for the driver",
    }


def diff_check_results(truth_checks: list[dict], extracted_checks: list[dict]) -> list[dict]:
    """truth_checks/extracted_checks: get_check_results() rows for one
    processor. Returns one entry per check_id whose status differs
    between the two sides (including a check present on only one side),
    with both sides' measured/threshold as the cause. Pure — no I/O."""
    by_id_truth = {c["check_id"]: c for c in truth_checks}
    by_id_extracted = {c["check_id"]: c for c in extracted_checks}
    diffs = []
    for check_id in sorted(set(by_id_truth) | set(by_id_extracted)):
        t = by_id_truth.get(check_id)
        e = by_id_extracted.get(check_id)
        t_status = t["status"] if t else "missing"
        e_status = e["status"] if e else "missing"
        if t_status == e_status:
            continue
        diffs.append(
            {
                "check_id": check_id,
                "truth_status": t_status,
                "extracted_status": e_status,
                "cause": (
                    f"measured truth={t['measured'] if t else None!r} "
                    f"extracted={e['measured'] if e else None!r} "
                    f"threshold={(t or e)['threshold']!r}"
                ),
            }
        )
    return diffs


def _normalize_shipment_id(shipment_id: str) -> str:
    """Extracted-mode shipment_ids carry an extra "EXT-" segment
    (app/ingest/normalize.py's match_shipments_from_extracted:
    f"{processor_id}-EXT-SHP-{i:03d}") that truth-mode's own
    f"{processor_id}-SHP-{i:03d}" (shipments_from_truth, copied straight
    from ground_truth.json) doesn't carry — both modes enumerate a
    processor's inbound invoices 1-indexed in the same order, so
    stripping "EXT-" makes the two sides' IDs directly comparable.
    Without this, EVERY finding looked like it only existed on one
    side, since "PWP-06-EXT-SHP-003" and "PWP-06-SHP-003" never
    compared equal — confirmed as the dominant source of noise in the
    first real --facts-source extracted comparison (2026-10-09)."""
    return shipment_id.replace("EXT-", "", 1)


# Only "deductible" findings (docs/DATA_SPEC.md §4a) subtract tonnage from
# verified_inbound_t — systemic/no_own_evidence/concurs_with_check/
# review_flag/withdrawn are all kept visible but never deducted. A
# finding-only-on-one-side diff in any of those classifications is real
# (the agent genuinely raised something the other side didn't) but can
# never be the driver of a verifiable_t delta, so the report labels it
# as such rather than leaving the reader to chase a non-existent
# tonnage effect.
_DEDUCTIBLE_CLASSIFICATIONS = {"deductible"}


def _finding_signature(finding: dict) -> tuple:
    """(normalised cited-shipment set, classification) — not
    finding_type, which is free text the model writes itself and can
    describe the same underlying finding differently between a
    truth-mode and an extracted-mode run (docs/PROGRESS.md: confirmed
    as the second dominant source of false "only on one side" diffs in
    the first real comparison, 2026-10-09)."""
    normalized = frozenset(_normalize_shipment_id(s) for s in finding["cited_shipment_ids"])
    return (normalized, finding["classification"])


def diff_findings(truth_findings: list[dict], extracted_findings: list[dict]) -> tuple[list, list]:
    """truth_findings/extracted_findings: get_findings() rows for one
    processor. Returns (only_in_truth, only_in_extracted), matched by
    (normalised cited_shipment_ids, classification) — see
    _finding_signature/_normalize_shipment_id. Pure — no I/O."""
    truth_by_sig = {_finding_signature(f): f for f in truth_findings}
    extracted_by_sig = {_finding_signature(f): f for f in extracted_findings}
    only_truth = [f for sig, f in truth_by_sig.items() if sig not in extracted_by_sig]
    only_extracted = [f for sig, f in extracted_by_sig.items() if sig not in truth_by_sig]
    return only_truth, only_extracted


def _print_processor_diff(
    seed: int, pid: str, truth_entry: dict | None, extracted_entry: dict | None
) -> bool:
    print(f"\n=== {pid} ===")
    if truth_entry is None or extracted_entry is None:
        side = "extracted" if truth_entry else "truth"
        print(f"  MISSING assessment on the {side} side — pipeline not scored there for this seed.")
        return True

    had_any_diff = False
    for stage in ("checks_only", "full"):
        stage_diff = diff_verifiable_t(truth_entry[stage], extracted_entry[stage])
        if stage_diff is None:
            continue
        had_any_diff = True
        print(
            f"  verifiable_t ({stage}): truth={stage_diff['truth_verifiable_t']} "
            f"extracted={stage_diff['extracted_verifiable_t']} "
            f"risk truth={stage_diff['truth_risk_band']} "
            f"extracted={stage_diff['extracted_risk_band']} "
            f"-- cause: {stage_diff['cause']}"
        )

    check_diffs = diff_check_results(
        cache.get_check_results(seed, TRUTH, pid), cache.get_check_results(seed, EXTRACTED, pid)
    )
    for d in check_diffs:
        had_any_diff = True
        print(
            f"  check {d['check_id']}: truth={d['truth_status']} extracted={d['extracted_status']} "
            f"-- cause: {d['cause']}"
        )

    only_truth, only_extracted = diff_findings(
        cache.get_findings(seed, TRUTH, pid), cache.get_findings(seed, EXTRACTED, pid)
    )
    for f in only_truth:
        had_any_diff = True
        effect = (
            ""
            if f["classification"] in _DEDUCTIBLE_CLASSIFICATIONS
            else " (no tonnage effect — classification doesn't deduct)"
        )
        print(
            f"  finding only in truth: {f['finding_type']} classification={f['classification']} "
            f"cited={f['cited_shipment_ids']}{effect} "
            "-- cause: the agent's own reasoning over this source's evidence didn't confirm "
            "(or wasn't reached on) the matching extracted-mode shipment/document"
        )
    for f in only_extracted:
        had_any_diff = True
        effect = (
            ""
            if f["classification"] in _DEDUCTIBLE_CLASSIFICATIONS
            else " (no tonnage effect — classification doesn't deduct)"
        )
        print(
            f"  finding only in extracted: {f['finding_type']} "
            f"classification={f['classification']} "
            f"cited={f['cited_shipment_ids']}{effect} "
            "-- cause: only surfaced when reasoning over Gemini's own extraction "
            "(e.g. an OCR/extraction artifact, or a real document detail truth mode's "
            "ground-truth shortcut never exercises)"
        )

    if not had_any_diff:
        print("  no differences")
    return had_any_diff


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    seed = args.seed

    truth_by_pid = {p["processor_id"]: p for p in cache.list_processors(seed, TRUTH)}
    extracted_by_pid = {p["processor_id"]: p for p in cache.list_processors(seed, EXTRACTED)}
    all_pids = sorted(set(truth_by_pid) | set(extracted_by_pid))

    if not all_pids:
        print(f"No scored processors found for seed {seed} on either facts_source.")
        return

    any_diff = False
    for pid in all_pids:
        if _print_processor_diff(seed, pid, truth_by_pid.get(pid), extracted_by_pid.get(pid)):
            any_diff = True

    print("\n" + ("Differences found above." if any_diff else "No differences anywhere."))


if __name__ == "__main__":
    main()
