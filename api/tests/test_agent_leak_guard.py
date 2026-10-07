"""Ground-truth leak guard (T10, docs/ARCHITECTURE.md §4 / docs/PROGRESS.md):
the agent loop must reason over exactly what a real auditor would see —
never a field that only exists because this is a synthetic test with a
known answer key. Builds the real context pack and every tool's output
from real seed-42 data, via the same production functions
scripts/run_pipeline.py's --stage agents uses, and asserts none of
ground_truth.json's (or processors.json's) evaluation-only fields or
values survive into what the model sees.
"""

import json
from pathlib import Path

from app.agents.orchestrator import build_context_pack
from app.agents.tools import build_tools
from app.checks.duplicates import find_duplicate_keys
from app.ingest.normalize import shipments_from_truth
from scripts.run_pipeline import _documents_from_truth

REPO_ROOT = Path(__file__).resolve().parents[2]
_SEED_DIR = REPO_ROOT / "data" / "synthetic" / "seed-42"
_GROUND_TRUTH = json.loads((_SEED_DIR / "ground_truth.json").read_text(encoding="utf-8"))
_PROCESSORS = json.loads((_SEED_DIR / "processors.json").read_text(encoding="utf-8"))

# Field names and values that exist only because this is a synthetic
# dataset with a known answer key — never derivable from a document or a
# deterministic check result. Checked by substring against the full
# serialized output, not just top-level dict keys.
_LEAK_MARKERS = [
    "is_f8",
    '"verified"',
    "issue_types",
    "hard_negatives",
    "true_verifiable_t",
    "verified_inbound_t_full_system",
    "placement_note",
    "site_validated",
    '"canonical"',
    '"label"',
    "affected_certificate_ids",
]


def _real_processor_context(processor_id: str) -> dict:
    """Built the same way scripts/run_pipeline.py's run_agents() builds
    it: the full processors.json row (deliberately NOT pre-filtered —
    this is exactly what would leak if build_context_pack or build_tools
    ever widened their own whitelists), real seed-42 shipments/documents
    through the production truth-mode transforms."""
    processor = next(p for p in _PROCESSORS if p["processor_id"] == processor_id)
    gt_processor = next(p for p in _GROUND_TRUTH["processors"] if p["processor_id"] == processor_id)
    shipments = shipments_from_truth(
        seed=42,
        processor_id=processor_id,
        truth_shipments=gt_processor["shipments"],
        documents=_GROUND_TRUTH["documents"],
    )
    duplicate_keys = find_duplicate_keys(shipments)
    documents = _documents_from_truth(42, _GROUND_TRUTH, processor_id)
    return {
        "processor": processor,
        "certificates": gt_processor["certificates"],
        "shipments": shipments,
        "duplicate_keys": duplicate_keys,
        "check_results": [],
        "site_assessment": None,
        "documents": documents,
    }


def test_context_pack_excludes_ground_truth_only_fields():
    # PWP-08 is one of the two seeded F8 processors — the richest case:
    # its ground truth carries is_f8/verified on shipments and
    # issue_types/hard_negatives/site_validated on the processor itself.
    context = _real_processor_context("PWP-08")

    context_pack = build_context_pack(context)
    serialized = json.dumps(context_pack, default=str)

    for marker in _LEAK_MARKERS:
        assert marker not in serialized, f"leak guard failed: {marker!r} found in context pack"


def test_tools_exclude_ground_truth_only_fields():
    context = _real_processor_context("PWP-08")
    tool_context = {
        "check_results": context["check_results"],
        "shipments": context["shipments"],
        "site_assessment": context["site_assessment"],
        "documents": context["documents"],
    }
    tools_by_name = {fn.__name__: fn for fn in build_tools(tool_context)}

    all_shipment_ids = [s["shipment_id"] for s in context["shipments"]]
    all_doc_ids = [d["doc_id"] for d in context["documents"]]

    outputs = [
        tools_by_name["get_shipments"](all_shipment_ids)[0],
        *[tools_by_name["get_document_facts"](doc_id)[0] for doc_id in all_doc_ids],
        tools_by_name["get_site_assessment"]()[0],
    ]

    for output in outputs:
        for marker in _LEAK_MARKERS:
            assert marker not in output, f"leak guard failed: {marker!r} found in tool output"


def test_shipments_from_truth_strips_is_f8_and_verified():
    # Direct check of the T7 boundary this guard relies on: the
    # production shipment shape never carries the generator's own
    # per-shipment evaluation labels, for every processor, not just PWP-08.
    for gt_processor in _GROUND_TRUTH["processors"]:
        shipments = shipments_from_truth(
            seed=42,
            processor_id=gt_processor["processor_id"],
            truth_shipments=gt_processor["shipments"],
            documents=_GROUND_TRUTH["documents"],
        )
        for s in shipments:
            assert "is_f8" not in s
            assert "verified" not in s


def test_documents_from_truth_exposes_only_printed_values_never_canonical():
    documents = _documents_from_truth(42, _GROUND_TRUTH, "PWP-08")
    assert documents, "expected PWP-08 to have documents in seed-42"
    for doc in documents:
        serialized = json.dumps(doc, default=str)
        assert "canonical" not in serialized
