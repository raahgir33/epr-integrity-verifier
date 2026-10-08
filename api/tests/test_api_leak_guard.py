"""Ground-truth leak guard for T11 (same spirit as tests/test_agent_leak_
guard.py's T10 version): no API response may ever contain a seeded-issue
evaluation label. The real processors table only has issue_types/
hard_negatives/site_validated columns because scripts/load_dossiers.py
writes them from ground_truth.json's generator-only knowledge — this test
uses the REAL processors.json row (unfiltered, including those columns) as
what app/store/cache._fetch_rows returns, deliberately feeding every
endpoint's underlying data the widest possible row shape, and asserts the
API's response models still strip every evaluation-only field. shipments/
certificates also get is_f8/verified/true_verifiable_t-style markers
injected directly (BigQuery's real shipments/certificates tables never
carry these columns at all — see app/store/bq.py's SCHEMAS — so this is
deliberately testing a worse case than what can occur today, the same
defense-in-depth discipline tests/test_agent_leak_guard.py already uses).
"""

import copy
import datetime
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.store import cache

REPO_ROOT = Path(__file__).resolve().parents[2]
_SEED_DIR = REPO_ROOT / "data" / "synthetic" / "seed-42"
_PROCESSORS = json.loads((_SEED_DIR / "processors.json").read_text(encoding="utf-8"))

_LEAK_MARKERS = [
    "is_f8",
    "issue_types",
    "hard_negatives",
    "site_validated",
    "true_verifiable_t",
    "placement_note",
    '"canonical"',
    '"label"',
    "affected_certificate_ids",
]
# Whole-word only — a real finding_type/explanation string could
# coincidentally contain "H1"/"F8" as a substring of an unrelated word;
# none of this codebase's real prompts ever emit the F/H taxonomy (T10),
# so this is a belt-and-suspenders check, not an expected hit.
_TAXONOMY_CODE_RE = re.compile(r"\b[FH][1-8]\b")


def _parse_ddmmyyyy(printed: str) -> datetime.date:
    day, month, year = (int(x) for x in printed.split("/"))
    return datetime.date(year, month, day)


def _real_processor_row(processor_id: str) -> dict:
    """processors.json's real row, unfiltered — includes issue_types/
    hard_negatives/site_validated exactly as scripts/load_dossiers.py
    writes them to BigQuery. consent dates converted to datetime.date,
    matching what the real BigQuery client hands back for a DATE column
    (processors.json itself stores them pre-formatted as strings)."""
    row = next(p for p in _PROCESSORS if p["processor_id"] == processor_id).copy()
    row["consent_valid_from"] = _parse_ddmmyyyy(row["consent_valid_from"])
    row["consent_valid_to"] = _parse_ddmmyyyy(row["consent_valid_to"])
    return row


_PWP08 = _real_processor_row("PWP-08")  # the F8-only processor — richest case
_PWP09 = _real_processor_row("PWP-09")  # F5/F6, site_validated already false

_SHIPMENT = {
    "shipment_id": "PWP-08-SHP-001",
    "processor_id": "PWP-08",
    "month": "2026-01",
    "invoice_doc_id": "DOC-INV-1",
    "eway_doc_id": "DOC-EWB-1",
    "weighbridge_doc_id": "DOC-WB-1",
    "invoice_qty_t": 10.0,
    "weighbridge_net_t": 10.0,
    "match_status": "matched",
    "ewb_no": "123456789012",
    "vehicle_no": "HR-01-AB-1234",
    "distance_km": 50.0,
    "eway_generated_at": datetime.datetime(2026, 1, 14, 6, 20, tzinfo=datetime.UTC),
    "eway_valid_until": datetime.datetime(2026, 1, 15, 18, 29, tzinfo=datetime.UTC),
    "weighbridge_in_time": datetime.datetime(2026, 1, 14, 10, 0, tzinfo=datetime.UTC),
    "invoice_no": "YAMUNA/25-26/0001",
    "supplier_gstin": "27BBBBB0000B1Z5",
    "weighbridge_ticket_no": "WB-08-00001",
    # Ground-truth-only evaluation knowledge — never a real BigQuery
    # shipments column (app/store/bq.py's SCHEMAS has no is_f8/verified),
    # injected here anyway as a defense-in-depth check.
    "is_f8": True,
    "verified": True,
}

_CERTIFICATE = {
    "certificate_id": "CERT-08-0001",
    "processor_id": "PWP-08",
    "brand_id": "BR-01",
    "category": "I",
    "quantity_t": 100.0,
    "generation_date": datetime.date(2026, 1, 15),
    "period_month": "2026-01",
    # Same defense-in-depth injection as above.
    "true_verifiable_t": 42.0,
    "label": "issues",
}

FAKE_DB = {
    "processors": [_PWP08, _PWP09],
    "brands": [{"brand_id": "BR-01", "name": "Example Brand"}],
    "certificates": [_CERTIFICATE],
    "shipments": [_SHIPMENT],
    "check_results": [
        {
            "processor_id": "PWP-08",
            "check_id": "C1",
            "status": "pass",
            "severity": "hard",
            "measured": 100.0,
            "threshold": 160.0,
            "affected_tonnes": 0.0,
            "evidence_ids": [],
            "explanation": "within capacity",
        }
    ],
    "assessments": [
        {
            "stage": "checks_only",
            "processor_id": "PWP-08",
            "certified_t": 100.0,
            "verified_inbound_t": 100.0,
            "capacity_limit_t": 160.0,
            "verifiable_t": 100.0,
            "unverifiable_t": 0.0,
            "risk_band": "Low",
            "agent_status": None,
        },
        {
            "stage": "checks_only",
            "processor_id": "PWP-09",
            "certified_t": 355.58,
            "verified_inbound_t": 347.96,
            "capacity_limit_t": 2000.0,
            "verifiable_t": 347.96,
            "unverifiable_t": 7.62,
            "risk_band": "Medium",
            "agent_status": None,
        },
    ],
    "site_assessments": [
        {
            "processor_id": "PWP-09",
            "status": "warn",
            "severity": "soft",
            "measured": None,
            "threshold": 10.0,
            "building_count": 0,
            "total_footprint_m2": 0.0,
            "thumbnail_gcs_path": "seed-42/site/PWP-09.png",
            "thumb_bbox_w": 76.59,
            "thumb_bbox_s": 27.54,
            "thumb_bbox_e": 76.60,
            "thumb_bbox_n": 27.55,
            "thumb_crs": "EPSG:3857",
            "explanation": "no building footprint detected within 150 m of the coordinates",
        }
    ],
    "documents": [
        {
            "doc_id": "DOC-INV-1",
            "processor_id": "PWP-08",
            "doc_type": "inbound_invoice",
            "lang": "hi",
            "gcs_path": "seed-42/PWP-08/DOC-INV-1.pdf",
            "mime_type": "application/pdf",
        }
    ],
    "extracted_facts": [],
    "extraction_results": [],
    "agent_runs": [],
}


def _fake_fetch_rows(client, table, columns, seed, facts_source=None):
    return copy.deepcopy(FAKE_DB.get(table, []))


def test_no_endpoint_leaks_ground_truth_only_fields(monkeypatch):
    monkeypatch.setattr(cache, "preload", lambda seed, facts_source: None)
    monkeypatch.setattr(cache, "_fetch_rows", _fake_fetch_rows)
    monkeypatch.setattr(cache.bq, "get_client", lambda: object())

    with TestClient(app) as client:
        responses = [
            client.get("/processors"),
            client.get("/processors/PWP-08"),
            client.get("/processors/PWP-09"),
            client.get("/processors/PWP-08/documents"),
            client.get("/processors/PWP-08/reasoning"),
            client.get("/processors/PWP-09/site"),
            client.get("/portfolio/BR-01"),
            client.get("/evaluation"),
            client.get("/alerts"),
        ]

    for response in responses:
        assert response.status_code == 200, response.text
        body_text = response.text
        for marker in _LEAK_MARKERS:
            assert marker not in body_text, f"leak marker {marker!r} found in {response.url}"
        taxonomy_hit = _TAXONOMY_CODE_RE.search(body_text)
        assert taxonomy_hit is None, f"taxonomy code {taxonomy_hit} found in {response.url}"
