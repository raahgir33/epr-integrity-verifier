"""T13 live-demo extra-shipment generation (api/scripts/dossier_gen/
demo_extra.py, api/scripts/generate_demo_extra_docs.py) — all against
real committed seed-42 data, no rendering (no Playwright/network).

Three things the developer specifically asked to be checked (docs/
PROGRESS.md's T13 plan, approved changes):
1. Every demo batch's period_month equals the dataset's own as_of_month
   (FY_MONTHS[-1], "2026-03") — never a literal next-calendar-month value
   that would start a disconnected new fiscal year (see
   scripts/dossier_gen/manifests.py's build_demo_batches docstring).
2. The new shipment's own dates fall inside that same month.
3. Adding the clean-pass batch (PWP-01) to its real existing shipments
   keeps C1 (capacity) and C2a (input balance) passing — the "clean
   batch that passes" demo must genuinely pass, not just claim to.
"""

import json
import random
from pathlib import Path

from app.agents.scorer import score_processor
from app.checks.duplicates import find_duplicate_keys
from app.checks.runner import run_checks_for_processor
from app.ingest.normalize import energy_from_truth, outputs_from_truth, shipments_from_truth
from scripts.dossier_gen.demo_extra import plan_demo_extra_shipment
from scripts.dossier_gen.manifests import build_demo_batches
from scripts.dossier_gen.rng import new_rng
from scripts.dossier_gen.shipments import FY_MONTHS
from scripts.dossier_gen.world import build_processors

REPO_ROOT = Path(__file__).resolve().parents[2]
_SEED_DIR = REPO_ROOT / "data" / "synthetic" / "seed-42"
_GROUND_TRUTH = json.loads((_SEED_DIR / "ground_truth.json").read_text(encoding="utf-8"))
_PROCESSORS_JSON = {
    p["processor_id"]: p
    for p in json.loads((_SEED_DIR / "processors.json").read_text(encoding="utf-8"))
}
_SUPPLIERS = json.loads((_SEED_DIR / "suppliers.json").read_text(encoding="utf-8"))
_GT_BY_ID = {p["processor_id"]: p for p in _GROUND_TRUTH["processors"]}
_AS_OF_MONTH = FY_MONTHS[-1]

# (processor_id, remark_hi) — mirrors scripts/generate_demo_extra_docs.py's
# own DEMO_EXTRA_PLAN; duplicated here deliberately (a small constant,
# not logic) so this test doesn't import a script module just for it.
_DEMO_EXTRA_PLAN = [("PWP-01", None), ("PWP-03", "माल नहीं उतारा")]


def test_build_demo_batches_period_month_is_the_datasets_as_of_month():
    processors = build_processors(new_rng(42))
    batches = build_demo_batches(processors, _GT_BY_ID)
    assert batches, "expected at least one demo batch"
    for batch in batches:
        assert batch["period_month"] == _AS_OF_MONTH, batch


def test_demo_extra_shipment_dates_fall_within_the_as_of_month():
    month_start, month_end = _AS_OF_MONTH, _AS_OF_MONTH  # "YYYY-MM" prefix compare
    for processor_id, remark_hi in _DEMO_EXTRA_PLAN:
        rng = random.Random(f"42-{processor_id}-demo")
        documents, shipment = plan_demo_extra_shipment(
            _PROCESSORS_JSON[processor_id],
            _SUPPLIERS,
            _GROUND_TRUTH["documents"],
            rng,
            _AS_OF_MONTH,
            remark_hi,
        )
        assert shipment["month"] == _AS_OF_MONTH
        for doc in documents:
            for field_name in ("date", "generated_at", "in_time", "out_time"):
                field = doc["fields"].get(field_name)
                if field is None:
                    continue
                assert field["canonical"][:7] == _AS_OF_MONTH, (
                    f"{processor_id}/{doc['doc_type']}.{field_name}={field['canonical']} "
                    f"not in {month_start}..{month_end}"
                )


def test_demo_extra_clean_pass_batch_keeps_c1_and_c2a_passing():
    """PWP-01 (no remark_hi) is the "clean batch that passes" demo — this
    confirms it genuinely does, against the real current data, not an
    assumption."""
    processor_id = "PWP-01"
    rng = random.Random(f"42-{processor_id}-demo")
    documents, shipment = plan_demo_extra_shipment(
        _PROCESSORS_JSON[processor_id],
        _SUPPLIERS,
        _GROUND_TRUTH["documents"],
        rng,
        _AS_OF_MONTH,
        None,
    )

    pe = _GT_BY_ID[processor_id]
    real_shipments = shipments_from_truth(
        42, processor_id, pe["shipments"], _GROUND_TRUTH["documents"]
    )
    all_shipments = [*real_shipments, shipment]
    processor = {**_PROCESSORS_JSON[processor_id], "processor_id": processor_id}
    certificates = [
        {
            "certificate_id": "EXISTING",
            "processor_id": processor_id,
            "category": processor["permitted_categories"][0],
            "quantity_t": pe["certified_t"],
            "period_month": _AS_OF_MONTH,
            "generation_date": "31/03/2026",
        },
        {
            "certificate_id": "CERT-DEMO",
            "processor_id": processor_id,
            "category": processor["permitted_categories"][0],
            "quantity_t": shipment["invoice_qty_t"],
            "period_month": _AS_OF_MONTH,
            "generation_date": "31/03/2026",
        },
    ]
    outputs = outputs_from_truth(42, processor_id, pe["outputs"])
    energy = energy_from_truth(42, processor_id, pe["energy_monthly"])
    duplicate_keys = find_duplicate_keys(all_shipments)

    results = run_checks_for_processor(
        processor, all_shipments, outputs, energy, certificates, duplicate_keys, _AS_OF_MONTH
    )
    by_id = {r.check_id: r for r in results}
    assert by_id["C1"].status == "pass", by_id["C1"].explanation
    assert by_id["C2a"].status == "pass", by_id["C2a"].explanation

    score = score_processor(
        processor, certificates, all_shipments, duplicate_keys, results, _AS_OF_MONTH
    )
    assert score["unverifiable_t"] < 0.5, "a clean-pass demo batch should deduct ~nothing"
