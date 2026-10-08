"""Tests for app/store/cache.py — the generic TTL cache mechanics and the
read functions' join/formatting logic. BigQuery itself is never touched:
cache._fetch_rows is monkeypatched to return canned rows from a small fake
table dict, shaped exactly like what the real BigQuery client would hand
back (datetime.date/datetime for DATE/TIMESTAMP columns).
"""

import copy
import datetime

import pytest

from app.store import cache

SEED = 42
FACTS_SOURCE = "truth"


@pytest.fixture(autouse=True)
def _clear_cache():
    """The cache is module-level global state — never let one test's
    cached values leak into the next."""
    cache.invalidate()
    yield
    cache.invalidate()


FAKE_DB = {
    "processors": [
        {
            "processor_id": "PWP-01",
            "name": "Alpha Recyclers",
            "type": "Recycler",
            "permitted_categories": ["I", "II"],
            "capacity_t_per_year": 1200.0,
            "consent_no": "CTO-01",
            "consent_valid_from": datetime.date(2022, 4, 1),
            "consent_valid_to": datetime.date(2028, 3, 31),
            "registration_no": "REG-01",
            "gstin": "27AAAAA0000A1Z5",
            "address": "Plot 12, Industrial Area, Maharashtra",
            "lat": 19.076123,
            "lon": 72.877456,
        }
    ],
    "brands": [{"brand_id": "BR-01", "name": "Example Brand"}],
    "certificates": [
        {
            "certificate_id": "CERT-01-0001",
            "processor_id": "PWP-01",
            "brand_id": "BR-01",
            "category": "I",
            "quantity_t": 100.0,
            "generation_date": datetime.date(2026, 1, 15),
            "period_month": "2026-01",
        }
    ],
    "shipments": [
        {
            "shipment_id": "PWP-01-SHP-001",
            "processor_id": "PWP-01",
            "month": "2026-01",
            "invoice_doc_id": "DOC-INV-1",
            "eway_doc_id": "DOC-EWB-1",
            "weighbridge_doc_id": "DOC-WB-1",
            "invoice_qty_t": 100.0,
            "weighbridge_net_t": 100.0,
            "match_status": "matched",
            "ewb_no": "123456789012",
            "vehicle_no": "MH-01-AB-1234",
            "distance_km": 80.0,
            "eway_generated_at": datetime.datetime(2026, 1, 14, 6, 20, tzinfo=datetime.UTC),
            "eway_valid_until": datetime.datetime(2026, 1, 15, 18, 29, tzinfo=datetime.UTC),
            "weighbridge_in_time": datetime.datetime(2026, 1, 14, 10, 0, tzinfo=datetime.UTC),
            "invoice_no": "ALPHA/25-26/0001",
            "supplier_gstin": "27BBBBB0000B1Z5",
            "weighbridge_ticket_no": "WB-01-00001",
        }
    ],
    "check_results": [
        {
            "processor_id": "PWP-01",
            "check_id": "C1",
            "status": "pass",
            "severity": "hard",
            "measured": 100.0,
            "threshold": 1200.0,
            "affected_tonnes": 0.0,
            "evidence_ids": [],
            "explanation": "within capacity",
        }
    ],
    "assessments": [
        {
            "stage": "checks_only",
            "processor_id": "PWP-01",
            "certified_t": 100.0,
            "verified_inbound_t": 100.0,
            "capacity_limit_t": 1200.0,
            "verifiable_t": 100.0,
            "unverifiable_t": 0.0,
            "risk_band": "Low",
            "agent_status": None,
        },
        {
            "stage": "full",
            "processor_id": "PWP-01",
            "certified_t": 100.0,
            "verified_inbound_t": 100.0,
            "capacity_limit_t": 1200.0,
            "verifiable_t": 95.0,
            "unverifiable_t": 5.0,
            "risk_band": "Low",
            "agent_status": "ok",
        },
    ],
    "site_assessments": [
        {
            "processor_id": "PWP-01",
            "status": "pass",
            "severity": "soft",
            "measured": 1.5,
            "threshold": 10.0,
            "building_count": 12,
            "total_footprint_m2": 800.123,
            "thumbnail_gcs_path": "seed-42/site/PWP-01.png",
            "thumb_bbox_w": 72.870123,
            "thumb_bbox_s": 19.070123,
            "thumb_bbox_e": 72.880123,
            "thumb_bbox_n": 19.080123,
            "thumb_crs": "EPSG:3857",
            "explanation": "within ceiling",
        }
    ],
    "documents": [
        {
            "doc_id": "DOC-INV-1",
            "processor_id": "PWP-01",
            "doc_type": "inbound_invoice",
            "lang": "en",
            "gcs_path": "seed-42/PWP-01/DOC-INV-1.pdf",
            "mime_type": "application/pdf",
        },
        {
            "doc_id": "DOC-WB-1",
            "processor_id": "PWP-01",
            "doc_type": "weighbridge_slip",
            "lang": "en",
            "gcs_path": "seed-42/PWP-01/DOC-WB-1.png",
            "mime_type": "image/png",
        },
    ],
    "extracted_facts": [
        {
            "doc_id": "DOC-INV-1",
            "field_name": "invoice_no",
            "printed_value": "ALPHA/25-26/0001",
            "confidence": 0.98,
            "page": 1,
        }
    ],
    "extraction_results": [{"doc_id": "DOC-INV-1", "status": "ok", "error_message": None}],
    "agent_runs": [],
}


@pytest.fixture(autouse=True)
def _fake_fetch_rows(monkeypatch):
    def fake(client, table, columns, seed, facts_source=None):
        assert seed == SEED
        return copy.deepcopy(FAKE_DB.get(table, []))

    monkeypatch.setattr(cache, "_fetch_rows", fake)
    monkeypatch.setattr(cache.bq, "get_client", lambda: object())


# ---------- generic TTL cache ----------


def test_get_or_load_caches_within_ttl():
    calls = []

    def loader():
        calls.append(1)
        return "value"

    assert cache.get_or_load("k1", loader, ttl=60) == "value"
    assert cache.get_or_load("k1", loader, ttl=60) == "value"
    assert len(calls) == 1


def test_get_or_load_reloads_after_ttl_expiry():
    calls = []

    def loader():
        calls.append(1)
        return len(calls)

    assert cache.get_or_load("k2", loader, ttl=0) == 1
    assert cache.get_or_load("k2", loader, ttl=0) == 2


def test_invalidate_specific_key():
    calls = []

    def loader():
        calls.append(1)
        return "value"

    cache.get_or_load("k3", loader, ttl=60)
    cache.invalidate("k3")
    cache.get_or_load("k3", loader, ttl=60)
    assert len(calls) == 2


def test_invalidate_all():
    cache.get_or_load("k4", lambda: "a", ttl=60)
    cache.get_or_load("k5", lambda: "b", ttl=60)
    cache.invalidate()
    assert cache._store == {}


# ---------- list_processors / get_processor_profile ----------


def test_list_processors_joins_both_assessment_stages():
    result = cache.list_processors(SEED, FACTS_SOURCE)
    assert len(result) == 1
    row = result[0]
    assert row["processor_id"] == "PWP-01"
    assert row["checks_only"]["risk_band"] == "Low"
    assert row["full"]["verifiable_t"] == 95.0
    assert row["agent_status"] == "ok"


def test_get_processor_profile_rounds_coordinates_and_formats_dates():
    profile = cache.get_processor_profile(SEED, "PWP-01")
    assert profile is not None
    assert profile["lat"] == 19.08
    assert profile["lon"] == 72.88
    assert profile["consent_valid_from"] == "01/04/2022"
    assert profile["consent_valid_to"] == "31/03/2028"


def test_get_processor_profile_returns_none_for_unknown_processor():
    assert cache.get_processor_profile(SEED, "PWP-99") is None


# ---------- check results / documents / facts ----------


def test_get_check_results_attaches_source_label():
    results = cache.get_check_results(SEED, FACTS_SOURCE, "PWP-01")
    assert len(results) == 1
    assert results[0]["check_id"] == "C1"
    assert "tunable threshold" in results[0]["source"]


def test_get_document_facts_not_extracted_for_unknown_doc():
    facts = cache.get_document_facts(SEED, "DOC-DOES-NOT-EXIST")
    assert facts["extraction_status"] == "not_extracted"
    assert facts["fields"] == []


def test_get_document_facts_returns_extracted_fields():
    facts = cache.get_document_facts(SEED, "DOC-INV-1")
    assert facts["extraction_status"] == "ok"
    assert facts["fields"][0]["field_name"] == "invoice_no"


def test_get_documents_for_processor_defaults_extraction_status():
    docs = {d["doc_id"]: d for d in cache.get_documents_for_processor(SEED, "PWP-01")}
    assert docs["DOC-INV-1"]["extraction_status"] == "ok"
    assert docs["DOC-WB-1"]["extraction_status"] == "not_extracted"


def test_get_document_validates_against_seed():
    assert cache.get_document(SEED, "DOC-INV-1") is not None
    assert cache.get_document(SEED, "DOC-DOES-NOT-EXIST") is None


# ---------- monthly flow ----------


def test_get_monthly_flow_computes_per_month_totals():
    rows = cache.get_monthly_flow(SEED, FACTS_SOURCE, "PWP-01")
    assert rows == [{"month": "2026-01", "certified_t": 100.0, "verified_inbound_t": 100.0}]


# ---------- site ----------


def test_get_site_assessment_found_and_missing():
    assert cache.get_site_assessment(SEED, "PWP-01") is not None
    assert cache.get_site_assessment(SEED, "PWP-99") is None


# ---------- portfolio ----------


def test_get_certificates_for_brand():
    certs = cache.get_certificates_for_brand(SEED, "BR-01")
    assert len(certs) == 1
    assert certs[0]["processor_id"] == "PWP-01"


def test_get_brand_found_and_missing():
    assert cache.get_brand(SEED, "BR-01") is not None
    assert cache.get_brand(SEED, "BR-99") is None


# ---------- preload ----------


def test_preload_populates_every_expected_key():
    cache.preload(SEED, FACTS_SOURCE)
    expected_prefixes = [
        f"processors:{SEED}",
        f"brands:{SEED}",
        f"certificates:{SEED}",
        f"shipments:{SEED}:{FACTS_SOURCE}",
        f"check_results:{SEED}:{FACTS_SOURCE}",
        f"assessments:{SEED}:{FACTS_SOURCE}",
        f"site_assessments:{SEED}",
        f"documents:{SEED}",
        f"extracted_facts:{SEED}",
        f"extraction_results:{SEED}",
        f"agent_runs:{SEED}:{FACTS_SOURCE}",
    ]
    for key in expected_prefixes:
        assert key in cache._store, f"missing cache key after preload: {key}"


# ---------- consistency guard ----------
#
# check_consistency's own dependencies (build_reconstruction_context,
# reconstruct_agent_findings, score_processor) are each tested in their
# own module (test_orchestrator.py, test_scorer.py) — these tests isolate
# check_consistency's own orchestration logic (which processors to check,
# how the comparison is made, what gets returned/logged) by monkeypatching
# those dependencies directly, rather than re-deriving a full realistic
# agent-run scenario through _fetch_rows.


def test_check_consistency_ok_when_recomputed_matches_stored(monkeypatch):
    monkeypatch.setattr(
        cache,
        "_assessments_by_processor",
        lambda seed, fs: {
            "PWP-01": {"full": {"verifiable_t": 50.0, "certified_t": 100.0}},
            "PWP-02": {},  # no "full" stage at all — must be skipped, not crash
        },
    )
    monkeypatch.setattr(
        cache,
        "get_processor_profile",
        lambda seed, pid: {
            "processor_id": pid,
            "capacity_t_per_year": 1200.0,
            "permitted_categories": ["I"],
            "consent_valid_from": "01/04/2022",
            "consent_valid_to": "31/03/2028",
        },
    )
    monkeypatch.setattr(
        cache,
        "build_reconstruction_context",
        lambda seed, fs, pid: {"check_results": [], "shipments": [], "duplicate_keys": {}},
    )
    monkeypatch.setattr(cache, "get_agent_trail", lambda seed, fs, pid: [])
    monkeypatch.setattr(cache, "get_certificates_for_processor", lambda seed, pid: [])
    monkeypatch.setattr(
        cache,
        "reconstruct_agent_findings",
        lambda trail, ctx: {"excluded_shipment_ids": frozenset({"PWP-01-SHP-002"})},
    )
    monkeypatch.setattr(cache, "score_processor", lambda *args, **kwargs: {"verifiable_t": 50.0})

    result = cache.check_consistency(SEED, FACTS_SOURCE)

    assert result == {"ok": True, "mismatches": []}


def test_check_consistency_detects_and_logs_a_mismatch(monkeypatch, caplog):
    monkeypatch.setattr(
        cache,
        "_assessments_by_processor",
        lambda seed, fs: {"PWP-05": {"full": {"verifiable_t": 100.0, "certified_t": 100.0}}},
    )
    monkeypatch.setattr(
        cache,
        "get_processor_profile",
        lambda seed, pid: {
            "processor_id": pid,
            "capacity_t_per_year": 1200.0,
            "permitted_categories": ["I"],
            "consent_valid_from": "01/04/2022",
            "consent_valid_to": "31/03/2028",
        },
    )
    monkeypatch.setattr(
        cache,
        "build_reconstruction_context",
        lambda seed, fs, pid: {"check_results": [], "shipments": [], "duplicate_keys": {}},
    )
    monkeypatch.setattr(cache, "get_agent_trail", lambda seed, fs, pid: [])
    monkeypatch.setattr(cache, "get_certificates_for_processor", lambda seed, pid: [])
    monkeypatch.setattr(
        cache,
        "reconstruct_agent_findings",
        lambda trail, ctx: {"excluded_shipment_ids": frozenset()},
    )
    # Recomputed score disagrees with the stored "full" verifiable_t (100.0).
    monkeypatch.setattr(cache, "score_processor", lambda *args, **kwargs: {"verifiable_t": 80.0})

    with caplog.at_level("ERROR"):
        result = cache.check_consistency(SEED, FACTS_SOURCE)

    assert result["ok"] is False
    assert result["mismatches"] == [
        {
            "processor_id": "PWP-05",
            "stored_verifiable_t": 100.0,
            "recomputed_verifiable_t": 80.0,
        }
    ]
    assert any("consistency check failed" in record.message for record in caplog.records)


def test_get_as_of_month_uses_max_period_month_across_all_certificates():
    assert cache.get_as_of_month(SEED) == "2026-01"
