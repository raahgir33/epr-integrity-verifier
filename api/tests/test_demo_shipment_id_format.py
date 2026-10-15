"""T17: the demo shipment's id shape must survive every place a shipment
id can appear.

app/ingest/normalize.py gives a demo-extra shipment its own namespace,
"PWP-03-DEMO-SHP-001", rather than taking an -EXT-SHP- number off the
dossier. Nothing in the codebase pattern-matches a shipment id today —
every consumer either tests exact-string membership or renders the id
opaquely — so the new shape works by construction. These tests pin that
down, because the invariant is invisible: a regex added later would break
the demo quietly, and only at demo time.

The web-side equivalents (resolveEvidence, FindingCard) are covered in
web/lib/evidence.test.ts.
"""

import re

from app.agents import memo
from app.agents.orchestrator import _filter_objection
from app.eval.evaluate import _normalize_shipment_id
from app.models.agent import Objection
from app.validation import DOC_ID_PATTERN

PID = "PWP-03"
DEMO_SHIPMENT_ID = f"{PID}-DEMO-SHP-001"
DEMO_DOC_IDS = [
    f"{PID}-DEMO-INBOUND_INVOICE-001",
    f"{PID}-DEMO-EWAY_BILL-001",
    f"{PID}-DEMO-WEIGHBRIDGE_SLIP-001",
]

# tests/test_api_leak_guard.py's own taxonomy-code detector, which every
# API response body is scanned against.
_TAXONOMY_CODE_RE = re.compile(r"\b[FH][1-9]\b")


def test_demo_document_ids_pass_the_route_id_pattern():
    """The three demo documents are reachable through GET /documents/
    {doc_id}/file and /files/[docId], both of which validate against
    DOC_ID_PATTERN before anything else runs."""
    for doc_id in DEMO_DOC_IDS:
        assert re.match(DOC_ID_PATTERN, doc_id), doc_id


def test_the_demo_shipment_id_is_not_mistaken_for_a_taxonomy_code():
    assert _TAXONOMY_CODE_RE.search(DEMO_SHIPMENT_ID) is None
    for doc_id in DEMO_DOC_IDS:
        assert _TAXONOMY_CODE_RE.search(doc_id) is None


def test_eval_shipment_id_normalisation_leaves_it_alone():
    """_normalize_shipment_id strips one "EXT-" segment so an extracted
    id lines up with ground_truth.json's own. A demo id has no such
    segment and must pass through untouched — in particular the "-DEMO-"
    infix must not be eaten."""
    assert _normalize_shipment_id(DEMO_SHIPMENT_ID) == DEMO_SHIPMENT_ID
    # The behaviour it exists for, unchanged.
    assert _normalize_shipment_id(f"{PID}-EXT-SHP-014") == f"{PID}-SHP-014"


def test_the_agents_may_cite_the_demo_shipment():
    """orchestrator.py (frozen) filters a finding's cited_shipment_ids by
    set membership in verified_shipment_ids, never by shape — so a
    matched demo shipment is citable with no change to that file."""

    objection = Objection(
        finding_type="Goods Not Unloaded",
        effect="raises_concern",
        cited_shipment_ids=[DEMO_SHIPMENT_ID, f"{PID}-EXT-SHP-999"],
        evidence_ids=list(DEMO_DOC_IDS),
        explanation="handwritten remark on the weighbridge slip",
    )
    processor_context = {
        "documents": [{"doc_id": d} for d in DEMO_DOC_IDS],
        "check_results": [],
    }

    filtered = _filter_objection(objection, processor_context, frozenset({DEMO_SHIPMENT_ID}))

    # Kept, while the invented id alongside it is dropped.
    assert filtered is not None
    assert filtered.cited_shipment_ids == [DEMO_SHIPMENT_ID]


def test_the_memo_guard_reads_the_demo_shipment_id_as_an_identifier():
    """The number guard must not read "03", "001" or "8.45" out of
    "PWP-03-DEMO-SHP-001" as unsupported quantities.

    Two things make this work, and both are asserted here: the id is
    registered as an identifier because _known_identifiers takes
    shipments_by_id's keys verbatim, and _strip_known_identifiers removes
    identifiers longest-first — so the processor_id "PWP-03", which is a
    prefix of the shipment id, cannot be stripped first and leave
    "-DEMO-SHP-001" behind for the number extractor to find."""
    shipments_by_id = {
        DEMO_SHIPMENT_ID: {
            "shipment_id": DEMO_SHIPMENT_ID,
            "month": "2026-03",
            "match_status": "matched",
            "weighbridge_net_t": 8.49,
            "weighbridge_doc_id": DEMO_DOC_IDS[2],
        }
    }
    identifiers = memo._known_identifiers(
        processor={"processor_id": PID, "name": "Vishwamitri Plastics Recycling Co."},
        shipments_by_id=shipments_by_id,
        documents_by_id={d: {"doc_id": d, "doc_type": "weighbridge_slip"} for d in DEMO_DOC_IDS},
        allowed_evidence_ids=frozenset(DEMO_DOC_IDS),
        as_of_month="2026-03",
        certificates=[],
    )
    assert DEMO_SHIPMENT_ID in identifiers
    assert PID in identifiers, "the prefix case this test exists to cover"

    # Stripping leaves no digits from the id behind.
    prose = (
        f"Shipment {DEMO_SHIPMENT_ID} carries a handwritten remark on "
        f"{DEMO_DOC_IDS[2]}, so its tonnes are not verifiable."
    )
    assert memo._unsupported_numbers(prose, identifiers, frozenset()) == []

    # And the longest-first ordering is what does it: with only the
    # processor_id registered, the id's own digits do leak through, which
    # is the regression this guards.
    leaked = memo._unsupported_numbers(prose, frozenset({PID}), frozenset())
    assert leaked, "expected the id's digits to leak when it is not registered"


def test_the_memo_guard_still_allows_the_demo_shipments_tonnage():
    """The cited shipment's own weighbridge tonnage is an allowed number,
    so a memo may quote 8.49 t for it."""
    shipments_by_id = {
        DEMO_SHIPMENT_ID: {
            "shipment_id": DEMO_SHIPMENT_ID,
            "month": "2026-03",
            "match_status": "matched",
            "weighbridge_net_t": 8.49,
        }
    }
    allowed = memo._allowed_numbers(
        assessment={
            "certified_t": 135.17,
            "verified_inbound_t": 126.72,
            "verifiable_t": 126.72,
            "unverifiable_t": 8.45,
            "capacity_limit_t": 172.8,
        },
        check_results=[],
        findings=[
            {
                "classification": "deductible",
                "cited_shipment_ids": [DEMO_SHIPMENT_ID],
                "evidence_ids": list(DEMO_DOC_IDS),
                "explanation": "handwritten remark",
            }
        ],
        shipments_by_id=shipments_by_id,
        documents_by_id={},
        certificates=[],
        as_of_month="2026-03",
        observations=[],
        known_identifiers=frozenset({DEMO_SHIPMENT_ID, PID}),
    )
    assert any(abs(n - 8.49) <= 0.01 for n in allowed)
