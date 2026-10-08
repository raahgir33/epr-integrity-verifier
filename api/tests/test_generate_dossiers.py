"""Tests the synthetic data generator's data pipeline via
scripts.generate_dossiers.run_data_pipeline — the same function `--no-render`
uses, so the suite can't drift from the real CLI path. Rendering itself
(Playwright/Chromium output) is visually checked by the developer, not
asserted on here. See docs/BUILD_PLAN.md T4 and docs/DATA_SPEC.md §5.
"""

import json

import pytest

from scripts.dossier_gen.manifests import brands_to_json, build_certificates_csv, suppliers_to_json
from scripts.generate_dossiers import run_data_pipeline

SEED = 42

HARD_ISSUE_TYPES = {"F1", "F2", "F3", "F4", "F6"}


@pytest.fixture(scope="module")
def pipeline():
    return run_data_pipeline(SEED)


@pytest.fixture(scope="module")
def processors_by_id(pipeline):
    return {p.processor_id: p for p in pipeline["processors"]}


def test_two_runs_produce_byte_identical_ground_truth():
    gt1 = run_data_pipeline(SEED)["ground_truth"]
    gt2 = run_data_pipeline(SEED)["ground_truth"]
    text1 = json.dumps(gt1, sort_keys=True, ensure_ascii=False)
    text2 = json.dumps(gt2, sort_keys=True, ensure_ascii=False)
    assert text1 == text2


def test_two_runs_produce_byte_identical_manifests():
    run1 = run_data_pipeline(SEED)
    run2 = run_data_pipeline(SEED)

    assert json.dumps(suppliers_to_json(run1["suppliers"]), sort_keys=True) == json.dumps(
        suppliers_to_json(run2["suppliers"]), sort_keys=True
    )
    assert json.dumps(brands_to_json(run1["brands"]), sort_keys=True) == json.dumps(
        brands_to_json(run2["brands"]), sort_keys=True
    )
    csv1 = build_certificates_csv(run1["processors"], run1["dossiers"], run1["brands"])
    csv2 = build_certificates_csv(run2["processors"], run2["dossiers"], run2["brands"])
    assert csv1 == csv2


def test_every_f1_through_f9_appears_at_least_once(processors_by_id):
    all_issue_types = {t for p in processors_by_id.values() for t in p.issue_types}
    for f in [f"F{i}" for i in range(1, 10)]:
        assert f in all_issue_types, f"{f} is not assigned to any processor"


def test_f1_appears_on_exactly_two_processors(processors_by_id):
    carriers = [pid for pid, p in processors_by_id.items() if "F1" in p.issue_types]
    assert len(carriers) == 2


def test_f8_appears_on_exactly_two_processors(processors_by_id):
    carriers = [pid for pid, p in processors_by_id.items() if "F8" in p.issue_types]
    assert len(carriers) == 2


def test_exactly_one_processor_is_f8_only(processors_by_id):
    f8_only = [pid for pid, p in processors_by_id.items() if p.issue_types == ["F8"]]
    assert f8_only == ["PWP-08"]


def test_f9_appears_on_exactly_one_processor(processors_by_id):
    carriers = [pid for pid, p in processors_by_id.items() if "F9" in p.issue_types]
    assert len(carriers) == 1


def test_exactly_one_processor_is_f9_only(processors_by_id):
    f9_only = [pid for pid, p in processors_by_id.items() if p.issue_types == ["F9"]]
    assert f9_only == ["PWP-02"]


def test_at_least_one_f8_instance_uses_the_hindi_description(pipeline):
    f8_docs = [
        doc
        for dossier in pipeline["dossiers"].values()
        for doc in dossier.documents
        if doc["doc_type"] == "inbound_invoice"
        and doc["fields"]["item_description"]["printed"] in {"प्राइम ग्रेड दाना"}
    ]
    assert f8_docs, "no F8 invoice uses the Hindi semantic-contradiction wording"


def test_f9_instance_has_the_handwritten_remark_text(pipeline):
    f9_remarks = [
        doc["fields"]["remarks"]["printed"]
        for dossier in pipeline["dossiers"].values()
        for doc in dossier.documents
        if doc["doc_type"] == "weighbridge_slip"
    ]
    assert "माल वापस भेजा" in f9_remarks, "no weighbridge slip carries the F9 remark text"


def test_h5_instance_has_the_benign_remark_text(pipeline):
    h5_remarks = [
        doc["fields"]["remarks"]["printed"]
        for dossier in pipeline["dossiers"].values()
        for doc in dossier.documents
        if doc["doc_type"] == "weighbridge_slip"
    ]
    assert "तिरपाल फटा" in h5_remarks, "no weighbridge slip carries the H5 remark text"


def test_f9_shipment_is_flagged_and_normal_weight(pipeline):
    pwp02 = next(p for p in pipeline["ground_truth"]["processors"] if p["processor_id"] == "PWP-02")
    f9_shipments = [s for s in pwp02["shipments"] if s.get("is_f9")]
    assert len(f9_shipments) == 1
    shipment = f9_shipments[0]
    assert shipment["verified"] is True, "F9 isn't caught by any deterministic check"
    ratio = shipment["weighbridge_net_t"] / shipment["invoice_qty_t"]
    assert 0.98 <= ratio <= 1.02, f"F9 shipment's net weight looks abnormal (ratio={ratio:.3f})"


def test_h5_shipment_on_pwp04_is_not_the_h3_shipment(pipeline):
    # Regression guard for the seeded-random index reservation (docs/
    # PROGRESS.md): H3 (fixed index, ratio ~0.985 — just outside the
    # normal 0.988-1.012 noise band) and H5 both land on PWP-04 and must
    # never be the same shipment. No is_h3/is_h5 flag exists, so this
    # checks it indirectly via the weighbridge-net/invoice-qty ratio: if
    # the H5-remark shipment's ratio is inside the normal band, it can't
    # be the one H3's reduced-ratio formula produced.
    pwp04 = next(p for p in pipeline["ground_truth"]["processors"] if p["processor_id"] == "PWP-04")
    docs_by_id = {d["doc_id"]: d for d in pipeline["ground_truth"]["documents"]}
    h5_shipments = [
        s
        for s in pwp04["shipments"]
        if s.get("weighbridge_doc_id")
        and docs_by_id[s["weighbridge_doc_id"]]["fields"]["remarks"]["printed"] == "तिरपाल फटा"
    ]
    assert len(h5_shipments) == 1
    shipment = h5_shipments[0]
    ratio = shipment["weighbridge_net_t"] / shipment["invoice_qty_t"]
    assert 0.988 <= ratio <= 1.012, (
        f"H5 shipment's ratio ({ratio:.4f}) looks like H3's reduced-ratio shipment — "
        "index reservation may have collided"
    )


def test_every_f5_carrier_also_carries_a_hard_issue_type(processors_by_id):
    for pid, p in processors_by_id.items():
        if "F5" in p.issue_types:
            assert HARD_ISSUE_TYPES & set(p.issue_types), (
                f"{pid} carries F5 (soft) with no paired hard issue: {p.issue_types}"
            )


def test_f7_and_h4_only_land_on_recyclers(processors_by_id):
    for pid, p in processors_by_id.items():
        if "F7" in p.issue_types or "H4" in p.hard_negatives:
            assert p.type == "recycler", f"{pid} carries F7/H4 but is type {p.type}"


def test_all_h1_through_h5_are_assigned(processors_by_id):
    all_hard_negatives = {h for p in processors_by_id.values() for h in p.hard_negatives}
    for h in ["H1", "H2", "H3", "H4", "H5"]:
        assert h in all_hard_negatives


def test_f4_original_holder_pwp01_stays_clean(processors_by_id):
    assert processors_by_id["PWP-01"].issue_types == []


def test_three_clean_and_seven_issue_processors(processors_by_id):
    # F9 (added to PWP-02, previously clean) brings this to 3/7 (was 4/6).
    clean = [pid for pid, p in processors_by_id.items() if not p.issue_types]
    issues = [pid for pid, p in processors_by_id.items() if p.issue_types]
    assert len(clean) == 3
    assert len(issues) == 7


def test_eight_recyclers_two_end_of_life(processors_by_id):
    recyclers = [pid for pid, p in processors_by_id.items() if p.type == "recycler"]
    end_of_life = [pid for pid, p in processors_by_id.items() if p.type == "end_of_life"]
    assert len(recyclers) == 8
    assert len(end_of_life) == 2


def test_clean_processors_have_no_tonnage_shortfall(pipeline):
    for entry in pipeline["ground_truth"]["processors"]:
        if entry["label"] == "clean":
            assert entry["true_verifiable_t"] == entry["certified_t"]
            assert entry["risk_band"] == "Low"
