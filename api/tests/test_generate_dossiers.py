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


def test_every_f1_through_f8_appears_at_least_once(processors_by_id):
    all_issue_types = {t for p in processors_by_id.values() for t in p.issue_types}
    for f in [f"F{i}" for i in range(1, 9)]:
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


def test_at_least_one_f8_instance_uses_the_hindi_description(pipeline):
    f8_docs = [
        doc
        for dossier in pipeline["dossiers"].values()
        for doc in dossier.documents
        if doc["doc_type"] == "inbound_invoice"
        and doc["fields"]["item_description"]["printed"] in {"प्राइम ग्रेड दाना"}
    ]
    assert f8_docs, "no F8 invoice uses the Hindi semantic-contradiction wording"


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


def test_all_h1_through_h4_are_assigned(processors_by_id):
    all_hard_negatives = {h for p in processors_by_id.values() for h in p.hard_negatives}
    for h in ["H1", "H2", "H3", "H4"]:
        assert h in all_hard_negatives


def test_f4_original_holder_pwp01_stays_clean(processors_by_id):
    assert processors_by_id["PWP-01"].issue_types == []


def test_four_clean_and_six_issue_processors(processors_by_id):
    clean = [pid for pid, p in processors_by_id.items() if not p.issue_types]
    issues = [pid for pid, p in processors_by_id.items() if p.issue_types]
    assert len(clean) == 4
    assert len(issues) == 6


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
