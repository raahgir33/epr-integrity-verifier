"""Generator-level robustness check (docs/PROGRESS.md has the diagnosis and
the before/after sweep across dev seeds):

1. No honest-basis processor (clean, H1-H4, or any processor whose only
   issue types are F4-F8 — none of these touch certified/shipment
   quantities) ever fails C2a or C4 from independent per-shipment
   weighbridge noise alone. The generator now derives these processors'
   certificates from the month's actual verified weighbridge net, rounded
   down (scripts/dossier_gen/shipments.py), so certified tonnage can no
   longer drift from verified tonnage by chance — this used to fail on
   roughly 1 in 10 (seed, processor) pairs before that fix.
2. Every seeded F1/F2/F3 issue still fires its intended check, in every
   seed: F1 -> C1 and C2a; F2 -> C2a; F3 -> C1, C2a and C4 (seed-42's only
   F3 instance is paired with F1, which also fails C1/C2a).

Seeds 1-20, excluding 7 — 7 is the held-out test set (the internal engineering
notes: "--seed 7 (held-out test set)") and is never generated or inspected here,
directly or indirectly, even for a robustness check like this one.

scripts/dossier_gen's processor-to-issue-type assignment is a fixed
catalog, not seed-dependent (only quantities/noise vary by seed), so which
processor_ids fall into each group below is the same across every seed.
"""

import pytest

from app.checks.duplicates import find_duplicate_keys
from app.checks.runner import run_checks_for_processor
from app.ingest.normalize import energy_from_truth, outputs_from_truth, shipments_from_truth
from scripts.dossier_gen.manifests import processors_to_json
from scripts.generate_dossiers import run_data_pipeline

AS_OF_MONTH = "2026-03"
DEV_SEEDS = [s for s in range(1, 21) if s != 7]

# No F1/F2/F3 — certificates are derived from verified weighbridge net.
HONEST_BASIS_PROCESSOR_IDS = {"PWP-01", "PWP-02", "PWP-03", "PWP-04", "PWP-08", "PWP-09", "PWP-10"}

# Expected-to-fail checks for each F1/F2/F3-carrying processor, regardless
# of seed (the mismatch these issues create is large relative to any
# per-shipment noise, confirmed across every dev seed).
MISMATCH_EXPECTATIONS = {
    "PWP-05": {"C1": "fail", "C2a": "fail"},  # F1 + F8
    "PWP-06": {"C1": "fail", "C2a": "fail", "C4": "fail"},  # F1 + F3
    "PWP-07": {"C2a": "fail"},  # F2 + F7
}


def _run_all_checks(seed):
    pipeline = run_data_pipeline(seed)
    ground_truth = pipeline["ground_truth"]
    processors_meta = {p["processor_id"]: p for p in processors_to_json(pipeline["processors"])}

    shipments_by_processor = {
        p["processor_id"]: shipments_from_truth(
            seed, p["processor_id"], p["shipments"], ground_truth["documents"]
        )
        for p in ground_truth["processors"]
    }
    all_shipments = [s for rows in shipments_by_processor.values() for s in rows]
    duplicate_keys = find_duplicate_keys(all_shipments)

    results_by_processor = {}
    for p in ground_truth["processors"]:
        pid = p["processor_id"]
        meta = processors_meta[pid]
        shipments = shipments_by_processor[pid]
        outputs = outputs_from_truth(seed, pid, p["outputs"])
        energy = energy_from_truth(seed, pid, p["energy_monthly"])
        results = run_checks_for_processor(
            meta, shipments, outputs, energy, p["certificates"], duplicate_keys, AS_OF_MONTH
        )
        results_by_processor[pid] = {r.check_id: r for r in results}
    return results_by_processor


@pytest.mark.parametrize("seed", DEV_SEEDS)
def test_honest_basis_processors_never_fail_c2a_or_c4(seed):
    results_by_processor = _run_all_checks(seed)
    for pid in HONEST_BASIS_PROCESSOR_IDS:
        for check_id in ("C2a", "C4"):
            result = results_by_processor[pid][check_id]
            assert result.status != "fail", (
                f"seed {seed}/{pid}/{check_id}: failed on an honest-basis processor "
                f"(affected {result.affected_tonnes} t, {result.explanation}) — noise "
                "alone should never trip this check"
            )


@pytest.mark.parametrize("seed", DEV_SEEDS)
def test_f1_f2_f3_still_fire_every_seed(seed):
    results_by_processor = _run_all_checks(seed)
    for pid, expected in MISMATCH_EXPECTATIONS.items():
        for check_id, expected_status in expected.items():
            actual = results_by_processor[pid][check_id].status
            assert actual == expected_status, (
                f"seed {seed}/{pid}/{check_id}: expected {expected_status!r}, got "
                f"{actual!r} — a seeded F1/F2/F3 issue stopped firing"
            )
