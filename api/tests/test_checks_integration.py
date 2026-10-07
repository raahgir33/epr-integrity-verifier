"""T8 acceptance gate: runs every implemented check (C1, C2a, C2b, C3a,
C3b, C4, C5, C6, C7) plus the deterministic scorer, in truth mode, against
the committed seed-42 ground_truth.json and processors.json. No BigQuery,
no scripts/dossier_gen import — only ground_truth.json and processors.json
are read, exactly like test_normalize.py's existing cross-check tests.

C8 (T9, Earth Engine) is included: site_assessments_by_processor() loads
scripts/run_pipeline.py --stage site's local JSON snapshot
(data/synthetic/seed-42/site_assessments.json, committed like
ground_truth.json/processors.json) and folds each processor's result into
its check list before scoring — see that fixture's docstring. The real
Earth Engine data showed PWP-04's and PWP-09's fictional coordinates were
both placed inaccurately relative to real imagery (PWP-04's point sat in a
lake; PWP-09's "farmland" point sat inside a real village settlement) —
both were nudged in data/synthetic/site_coordinates.json after visually
reviewing the thumbnails (see docs/PROGRESS.md), not by changing any
check/threshold code.

Two things are asserted for every one of the 10 processors:
1. The exact status (pass/fail/warn/not_evaluable) of every implemented
   check, against a hand-verified fixture (EXPECTED_STATUSES below).
2. Computed verifiable tonnes == true_verifiable_t_checks_only exactly —
   the number the generator itself computes as what a checks-only system
   (no agents) should find, for every processor without exception (unlike
   true_verifiable_t, which also subtracts T10's agent-only findings).
"""

import json
from pathlib import Path

import pytest

from app.agents.scorer import score_processor
from app.checks.duplicates import find_duplicate_keys
from app.checks.runner import run_checks_for_processor
from app.geo.site import site_assessment_to_check_result
from app.ingest.normalize import energy_from_truth, outputs_from_truth, shipments_from_truth

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = 42
AS_OF_MONTH = "2026-03"
IMPLEMENTED_CHECK_IDS = {"C1", "C2a", "C2b", "C3a", "C3b", "C4", "C5", "C6", "C7", "C8"}

# Hand-verified against the committed seed-42 data (see docs/PROGRESS.md
# for the per-processor narrative). Processors carrying no issue_types are
# PWP-01..04 (PWP-03/04 are H1-H4 hard negatives) — every implemented
# check passes there, confirming no false positive on a hard negative.
#
# C3a/C3b never fail anywhere in this table: no seeded issue type or hard
# negative in this dataset pushes transit speed above the ceiling or
# weighbridge arrival past e-way bill validity (the generator always draws
# average speed from a fixed 30-48 km/h range, including for H2's 900 km
# long-haul case) — see docs/PROGRESS.md.
#
# PWP-08 (F8 only) passes C2a, matching its documented "agents only (no
# deterministic check)" status in DATA_SPEC.md §5. This used to be a
# marginal pass (0.53% shortfall, inside params.C2A_SHORTFALL_TOL=0.02 by
# luck of this seed's draw) before the generator fix logged in
# docs/PROGRESS.md: certificates for any processor without F1/F2/F3 are
# now derived from the month's actual verified weighbridge net, so
# certified and verified tonnage match exactly (shortfall 0.00) by
# construction, not by chance — confirmed never to fail across seeds 1-20
# (excluding 7) in test_c2a_noise_robustness.py. C2A_SHORTFALL_TOL stays
# at 0.02 regardless (materiality threshold, not a noise-absorption
# margin).
EXPECTED_STATUSES = {
    "PWP-01": {
        "C1": "pass",
        "C2a": "pass",
        "C2b": "pass",
        "C3a": "pass",
        "C3b": "pass",
        "C4": "pass",
        "C5": "pass",
        "C6": "pass",
        "C7": "pass",
        "C8": "pass",
    },
    "PWP-02": {
        "C1": "pass",
        "C2a": "pass",
        "C2b": "pass",
        "C3a": "pass",
        "C3b": "pass",
        "C4": "pass",
        "C5": "pass",
        "C6": "pass",
        "C7": "pass",
        "C8": "pass",
    },
    "PWP-03": {  # H1 (95% capacity), H2 (900 km long-haul, plausible timing)
        "C1": "pass",
        "C2a": "pass",
        "C2b": "pass",
        "C3a": "pass",
        "C3b": "pass",
        "C4": "pass",
        "C5": "pass",
        "C6": "pass",
        "C7": "pass",
        "C8": "pass",
    },
    "PWP-04": {  # H3 (quantity inside tolerance), H4 (shutdown month)
        "C1": "pass",
        "C2a": "pass",
        "C2b": "pass",
        "C3a": "pass",
        "C3b": "pass",
        "C4": "pass",
        "C5": "pass",
        "C6": "pass",
        "C7": "pass",
        "C8": "pass",
    },
    "PWP-05": {  # F1 capacity inflation, F8 (agents only)
        "C1": "fail",
        "C2a": "fail",
        "C2b": "pass",
        "C3a": "pass",
        "C3b": "pass",
        "C4": "pass",
        "C5": "pass",
        "C6": "pass",
        "C7": "pass",
        "C8": "pass",
    },
    "PWP-06": {  # F1 capacity inflation, F3 quantity inflation
        "C1": "fail",
        "C2a": "fail",
        "C2b": "pass",
        "C3a": "pass",
        "C3b": "pass",
        "C4": "fail",
        "C5": "pass",
        "C6": "pass",
        "C7": "pass",
        "C8": "pass",
    },
    "PWP-07": {  # F2 phantom inbound, F7 energy implausibility
        "C1": "pass",
        "C2a": "fail",
        "C2b": "pass",
        "C3a": "pass",
        "C3b": "pass",
        "C4": "pass",
        "C5": "pass",
        "C6": "pass",
        "C7": "warn",
        "C8": "pass",
    },
    "PWP-08": {  # F8 only (agents only, no deterministic check — see note above)
        "C1": "pass",
        "C2a": "pass",
        "C2b": "pass",
        "C3a": "pass",
        "C3b": "pass",
        "C4": "pass",
        "C5": "pass",
        "C6": "pass",
        "C7": "pass",
        "C8": "pass",
    },
    "PWP-09": {  # F5 ghost site (C8 warn, 0 buildings within 150 m), F6 breach; end-of-life
        "C1": "pass",
        "C2a": "pass",
        "C2b": "not_evaluable",
        "C3a": "pass",
        "C3b": "pass",
        "C4": "pass",
        "C5": "pass",
        "C6": "fail",
        "C7": "not_evaluable",
        "C8": "warn",
    },
    "PWP-10": {  # F4 double use; end-of-life
        "C1": "pass",
        "C2a": "pass",
        "C2b": "not_evaluable",
        "C3a": "pass",
        "C3b": "pass",
        "C4": "pass",
        "C5": "fail",
        "C6": "pass",
        "C7": "not_evaluable",
        "C8": "pass",
    },
}


@pytest.fixture(scope="module")
def ground_truth():
    path = REPO_ROOT / "data" / "synthetic" / f"seed-{SEED}" / "ground_truth.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def processors_meta():
    path = REPO_ROOT / "data" / "synthetic" / f"seed-{SEED}" / "processors.json"
    return {p["processor_id"]: p for p in json.loads(path.read_text(encoding="utf-8"))}


@pytest.fixture(scope="module")
def site_assessments_by_processor():
    """scripts/run_pipeline.py --stage site writes a local JSON snapshot
    (data/synthetic/seed-42/site_assessments.json) alongside its BigQuery
    rows, precisely so this local/offline test can pick up real C8
    results once they exist, the same "committed local artifact" pattern
    ground_truth.json/processors.json already use. Empty dict (C8 simply
    absent from every processor's results) until that file exists."""
    path = REPO_ROOT / "data" / "synthetic" / f"seed-{SEED}" / "site_assessments.json"
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {row["processor_id"]: row for row in rows}


@pytest.fixture(scope="module")
def results_by_processor(ground_truth, processors_meta, site_assessments_by_processor):
    shipments_by_processor = {
        p["processor_id"]: shipments_from_truth(
            SEED, p["processor_id"], p["shipments"], ground_truth["documents"]
        )
        for p in ground_truth["processors"]
    }
    all_shipments = [s for rows in shipments_by_processor.values() for s in rows]
    duplicate_keys = find_duplicate_keys(all_shipments)

    out = {}
    for p in ground_truth["processors"]:
        pid = p["processor_id"]
        meta = processors_meta[pid]
        shipments = shipments_by_processor[pid]
        outputs = outputs_from_truth(SEED, pid, p["outputs"])
        energy = energy_from_truth(SEED, pid, p["energy_monthly"])
        results = run_checks_for_processor(
            meta, shipments, outputs, energy, p["certificates"], duplicate_keys, AS_OF_MONTH
        )
        site_row = site_assessments_by_processor.get(pid)
        if site_row is not None:
            results = [*results, site_assessment_to_check_result(site_row)]
        score = score_processor(
            meta, p["certificates"], shipments, duplicate_keys, results, AS_OF_MONTH
        )
        out[pid] = {"results": results, "score": score, "truth": p}
    return out


@pytest.mark.parametrize("processor_id", sorted(EXPECTED_STATUSES))
def test_exact_check_status_matrix(results_by_processor, processor_id):
    actual = {r.check_id: r.status for r in results_by_processor[processor_id]["results"]}
    assert set(actual) == IMPLEMENTED_CHECK_IDS, f"{processor_id}: unexpected check set {actual}"
    expected = EXPECTED_STATUSES[processor_id]
    for check_id, expected_status in expected.items():
        assert actual[check_id] == expected_status, (
            f"{processor_id}/{check_id}: expected {expected_status!r}, got {actual[check_id]!r}"
        )


@pytest.mark.parametrize("processor_id", sorted(EXPECTED_STATUSES))
def test_verifiable_tonnes_match_checks_only_ground_truth(results_by_processor, processor_id):
    entry = results_by_processor[processor_id]
    assert entry["score"]["verifiable_t"] == pytest.approx(
        entry["truth"]["true_verifiable_t_checks_only"], abs=0.01
    ), f"{processor_id}: verifiable tonnes do not match true_verifiable_t_checks_only"


def test_h1_through_h4_processors_never_fail(results_by_processor):
    """H1-H4 live on PWP-03 (H1, H2) and PWP-04 (H3, H4) per
    docs/DATA_SPEC.md §5 — no implemented check may fail (not_evaluable is
    fine; a hard negative is "looks like an issue but isn't")."""
    for processor_id in ("PWP-03", "PWP-04"):
        for result in results_by_processor[processor_id]["results"]:
            assert result.status != "fail", (
                f"{processor_id}/{result.check_id}: false positive on a hard-negative processor"
            )


def test_pwp09_unverifiable_tonnes_uses_raw_certified_not_eligible(results_by_processor):
    """PWP-09 (F6: one certificate in a non-permitted category) is the
    direct test of scorer.py's unverifiable_t = certified_t (raw) -
    verifiable_t, not eligible_certified_t - verifiable_t: if unverifiable
    were computed from the eligible figure instead, the F6-excluded
    tonnage would silently vanish from both verifiable_t and
    unverifiable_t rather than surfacing as unverifiable, and the risk
    band would never reflect the consent breach at all."""
    score = results_by_processor["PWP-09"]["score"]
    assert score["certified_t"] == pytest.approx(342.15)
    assert score["verifiable_t"] == pytest.approx(302.65)
    assert score["unverifiable_t"] == pytest.approx(39.50)
    assert score["unverifiable_t"] == pytest.approx(score["certified_t"] - score["verifiable_t"])
    # C8's soft-signal bump (F5 ghost site, real Earth Engine data) raises
    # this from Medium to High — see test_c8_risk_band_matches_full_system
    # for why that's not a coincidence.
    assert score["risk_band"] == "High"


def test_c8_risk_band_matches_full_system_ground_truth(results_by_processor):
    """PWP-09 carries no F8 (agent-only), so true_verifiable_t ==
    true_verifiable_t_checks_only exactly — the generator's own full-system
    risk_band (which always folds in F5's soft signal, agent-independent;
    see scripts/dossier_gen/ground_truth.py's _SOFT_ISSUE_TYPES) should
    therefore equal this checks-only scorer's risk_band exactly too, now
    that C8 is wired in. Before T9, this was Medium vs ground truth's
    High — a real gap that real Earth Engine data (not threshold tuning)
    has now closed."""
    entry = results_by_processor["PWP-09"]
    assert entry["truth"]["true_verifiable_t"] == pytest.approx(
        entry["truth"]["true_verifiable_t_checks_only"]
    )
    assert entry["score"]["risk_band"] == entry["truth"]["risk_band"] == "High"


def test_no_seeded_scenario_fails_c3a_or_c3b(results_by_processor):
    """Confirms (rather than assumes) that this dataset never exercises a
    C3a/C3b failure — see the module docstring and docs/PROGRESS.md."""
    for processor_id, entry in results_by_processor.items():
        for result in entry["results"]:
            if result.check_id in ("C3a", "C3b"):
                assert result.status == "pass", (
                    f"{processor_id}/{result.check_id}: expected this dataset to never fail "
                    "C3a/C3b — update docs/PROGRESS.md if a new seed changes this"
                )
