"""Tests for app/store/cache.py — the generic TTL cache mechanics and the
read functions' join/formatting logic. BigQuery itself is never touched:
cache._fetch_rows is monkeypatched to return canned rows from a small fake
table dict, shaped exactly like what the real BigQuery client would hand
back (datetime.date/datetime for DATE/TIMESTAMP columns).
"""

import copy
import datetime
import json

import pytest

from app.store import cache

SEED = 42
FACTS_SOURCE = "truth"


@pytest.fixture(autouse=True)
def _clear_cache():
    """The cache is module-level global state — never let one test's
    cached values leak into the next. Includes A2's file caches
    (get_document_file's LRU, get_site_image_bytes' eager dict), which
    live outside _store."""
    cache.invalidate()
    cache._document_file_cache.clear()
    cache._document_file_cache_bytes = 0
    cache._site_image_cache.clear()
    yield
    cache.invalidate()
    cache._document_file_cache.clear()
    cache._document_file_cache_bytes = 0
    cache._site_image_cache.clear()


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
    # Standing rule: never hit real GCP. preload() (A2) now also calls
    # get_site_image_bytes for every processor, which — without this —
    # would call the REAL gcs.download_bytes against this environment's
    # real configured bucket (this .env has genuine GCP settings) on
    # every test that exercises preload(). Found and fixed before this
    # went unnoticed: a local run of test_preload_populates_every_
    # expected_key actually reached storage.googleapis.com.
    monkeypatch.setattr(cache.gcs, "get_client", lambda: object())
    monkeypatch.setattr(
        cache.gcs, "download_bytes", lambda client, bucket, path: b"\x89PNG-fake-from-test"
    )


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


def test_get_or_load_with_no_expiry_never_reloads(monkeypatch):
    """A2: every preload-populated key uses ttl=cache.NO_EXPIRY so a
    later read — however long after startup — never re-triggers a live
    BigQuery query just because wall-clock time has passed."""
    calls = []

    def loader():
        calls.append(1)
        return len(calls)

    assert cache.get_or_load("k2b", loader, ttl=cache.NO_EXPIRY) == 1
    # Simulate a huge amount of elapsed time by moving the stored
    # timestamp far into the past — still must not reload.
    monkeypatch.setattr(cache.time, "monotonic", lambda: 10**9)
    assert cache.get_or_load("k2b", loader, ttl=cache.NO_EXPIRY) == 1
    assert len(calls) == 1


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


# ---------- agent trail (attempt filtering) ----------
#
# The 2026-10-08 processor-level retry (app/agents/orchestrator.py's
# run_agent_loop_with_retry) can write two attempts' worth of agent_runs
# rows for one processor — get_agent_trail must return only the latest
# attempt's rows, never a blend of both (step_index restarts at 0 per
# attempt, so sorting across both would interleave two unrelated trails).


def test_get_agent_trail_returns_only_the_latest_attempt(monkeypatch):
    monkeypatch.setattr(
        cache,
        "_agent_runs",
        lambda seed, fs: [
            {"processor_id": "PWP-05", "attempt": 1, "step_index": 0, "step_type": "hypothesis"},
            {"processor_id": "PWP-05", "attempt": 1, "step_index": 1, "step_type": "critic_final"},
            {"processor_id": "PWP-05", "attempt": 2, "step_index": 0, "step_type": "hypothesis"},
            {"processor_id": "PWP-01", "attempt": 1, "step_index": 0, "step_type": "hypothesis"},
        ],
    )
    trail = cache.get_agent_trail(SEED, FACTS_SOURCE, "PWP-05")
    assert [r["attempt"] for r in trail] == [2]
    assert trail[0]["step_type"] == "hypothesis"


def test_get_agent_trail_treats_null_attempt_as_one(monkeypatch):
    """Pre-retry rows (written before the ALTER TABLE/retry rollout) have
    attempt=NULL — must still read back as a normal single-attempt trail,
    not get dropped or mis-sorted."""
    monkeypatch.setattr(
        cache,
        "_agent_runs",
        lambda seed, fs: [
            {
                "processor_id": "PWP-01",
                "attempt": None,
                "step_index": 0,
                "step_type": "hypothesis",
            },
            {
                "processor_id": "PWP-01",
                "attempt": None,
                "step_index": 1,
                "step_type": "critic_final",
            },
        ],
    )
    trail = cache.get_agent_trail(SEED, FACTS_SOURCE, "PWP-01")
    assert [r["step_index"] for r in trail] == [0, 1]


def test_get_agent_trail_empty_for_unknown_processor(monkeypatch):
    monkeypatch.setattr(cache, "_agent_runs", lambda seed, fs: [])
    assert cache.get_agent_trail(SEED, FACTS_SOURCE, "PWP-99") == []


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


# ---------- A2: document file LRU cache ----------


def test_get_document_file_caches_after_first_fetch(monkeypatch):
    monkeypatch.setattr(
        cache,
        "get_document",
        lambda seed, doc_id: {
            "doc_id": doc_id,
            "gcs_path": f"{doc_id}.pdf",
            "mime_type": "application/pdf",
        },
    )
    calls = []

    def fake_download(client, bucket, path):
        calls.append(path)
        return b"fake-bytes"

    monkeypatch.setattr(cache.gcs, "download_bytes", fake_download)
    monkeypatch.setattr(cache.gcs, "get_client", lambda: object())

    first = cache.get_document_file(SEED, "DOC-A")
    second = cache.get_document_file(SEED, "DOC-A")

    assert first == second == (b"fake-bytes", "application/pdf")
    assert calls == ["DOC-A.pdf"]  # only one real download


def test_get_document_file_returns_none_for_unknown_doc_without_calling_gcs(monkeypatch):
    monkeypatch.setattr(cache, "get_document", lambda seed, doc_id: None)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("must not call gcs.download_bytes for an unknown doc_id")

    monkeypatch.setattr(cache.gcs, "download_bytes", _fail_if_called)

    assert cache.get_document_file(SEED, "DOC-DOES-NOT-EXIST") is None


def test_get_document_file_lru_evicts_least_recently_used_over_cap(monkeypatch):
    monkeypatch.setattr(cache, "_DOCUMENT_FILE_CACHE_MAX_BYTES", 10)
    monkeypatch.setattr(
        cache,
        "get_document",
        lambda seed, doc_id: {
            "doc_id": doc_id,
            "gcs_path": f"{doc_id}.pdf",
            "mime_type": "application/pdf",
        },
    )
    calls = []
    monkeypatch.setattr(
        cache.gcs,
        "download_bytes",
        lambda client, bucket, path: (calls.append(path), b"1234567")[1],
    )
    monkeypatch.setattr(cache.gcs, "get_client", lambda: object())

    cache.get_document_file(SEED, "DOC-A")  # 7 bytes — within the 10-byte cap
    cache.get_document_file(SEED, "DOC-B")  # 7+7=14 > 10 — evicts DOC-A (least recently used)

    assert "DOC-A" not in cache._document_file_cache
    assert "DOC-B" in cache._document_file_cache

    cache.get_document_file(SEED, "DOC-A")  # evicted — must re-download
    assert calls.count("DOC-A.pdf") == 2


def test_get_document_file_lru_touches_entry_on_cache_hit(monkeypatch):
    """A re-accessed entry moves to the back of the LRU, so it survives
    an eviction that an untouched entry of the same age wouldn't."""
    monkeypatch.setattr(cache, "_DOCUMENT_FILE_CACHE_MAX_BYTES", 14)
    monkeypatch.setattr(
        cache,
        "get_document",
        lambda seed, doc_id: {
            "doc_id": doc_id,
            "gcs_path": f"{doc_id}.pdf",
            "mime_type": "application/pdf",
        },
    )
    monkeypatch.setattr(cache.gcs, "download_bytes", lambda client, bucket, path: b"1234567")
    monkeypatch.setattr(cache.gcs, "get_client", lambda: object())

    cache.get_document_file(SEED, "DOC-A")  # 7 bytes
    cache.get_document_file(SEED, "DOC-B")  # 14 bytes total — exactly at cap, no eviction yet
    cache.get_document_file(SEED, "DOC-A")  # cache hit — touches DOC-A, moves it to the back
    cache.get_document_file(SEED, "DOC-C")  # 21 bytes > 14 — evicts the LEAST recently used: DOC-B

    assert "DOC-B" not in cache._document_file_cache
    assert "DOC-A" in cache._document_file_cache
    assert "DOC-C" in cache._document_file_cache


# ---------- A2: eager site-image cache ----------


def test_get_site_image_bytes_caches_after_first_fetch(monkeypatch):
    monkeypatch.setattr(
        cache,
        "get_site_assessment",
        lambda seed, pid: {"thumbnail_gcs_path": "seed-42/site/PWP-01.png"},
    )
    calls = []
    monkeypatch.setattr(
        cache.gcs,
        "download_bytes",
        lambda client, bucket, path: (calls.append(path), b"\x89PNG-fake")[1],
    )
    monkeypatch.setattr(cache.gcs, "get_client", lambda: object())

    first = cache.get_site_image_bytes(SEED, "PWP-01")
    second = cache.get_site_image_bytes(SEED, "PWP-01")

    assert first == second == b"\x89PNG-fake"
    assert len(calls) == 1


def test_get_site_image_bytes_none_when_no_thumbnail(monkeypatch):
    monkeypatch.setattr(cache, "get_site_assessment", lambda seed, pid: None)

    assert cache.get_site_image_bytes(SEED, "PWP-99") is None


# ---------- A2: reasoning trail reshape ----------


def _trail_row(step_index, step_type, tool_name=None, tool_args_json=None, output_json=None):
    return {
        "step_index": step_index,
        "step_type": step_type,
        "tool_name": tool_name,
        "tool_args_json": tool_args_json,
        "output_json": output_json,
        "latency_ms": None,
        "input_tokens": None,
        "output_tokens": None,
        "thinking_tokens": None,
    }


def test_compute_reasoning_steps_merges_tool_call_and_strips_internal_paths(monkeypatch):
    trail = [
        _trail_row(0, "hypothesis", output_json=json.dumps({"conclusions": []})),
        _trail_row(1, "critic_tool_call", tool_name="get_site_assessment", tool_args_json="{}"),
        _trail_row(
            2,
            "critic_tool_result",
            output_json=json.dumps(
                {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "result": json.dumps(
                                    {
                                        "status": "pass",
                                        "thumbnail_gcs_path": "seed-42/site/PWP-09.png",
                                    }
                                )
                            }
                        }
                    ],
                }
            ),
        ),
        _trail_row(
            3,
            "critic_model_turn",
            output_json=json.dumps({"role": "model", "parts": [{"text": "done"}]}),
        ),
        _trail_row(4, "critic_final", output_json=json.dumps({"verdicts": [], "objections": []})),
    ]
    monkeypatch.setattr(cache, "get_agent_trail", lambda seed, fs, pid: trail)
    monkeypatch.setattr(cache, "get_processor_assessments", lambda seed, fs, pid: None)

    steps = cache.get_reasoning_steps(SEED, FACTS_SOURCE, "PWP-09")

    assert [s["step_type"] for s in steps] == [
        "hypothesis",
        "critic_tool",
        "critic_model_turn",
        "critic_final",
        "revision",
    ]

    tool_step = steps[1]
    assert tool_step["tool_name"] == "get_site_assessment"
    assert tool_step["result"] == {"status": "pass"}  # thumbnail_gcs_path stripped
    assert "thumbnail_gcs_path" not in tool_step["result_summary"]
    assert tool_step["dedup_hit"] is False

    revision_step = steps[-1]
    assert "not needed" in revision_step["output"]["note"]


def test_compute_reasoning_steps_detects_dedup_hit(monkeypatch):
    dedup_message = "Already returned in call 1 — see that result, do not call this again."
    trail = [
        _trail_row(0, "critic_tool_call", tool_name="get_shipments", tool_args_json="{}"),
        _trail_row(
            1,
            "critic_tool_result",
            output_json=json.dumps(
                {
                    "role": "user",
                    "parts": [{"function_response": {"result": dedup_message}}],
                }
            ),
        ),
    ]
    monkeypatch.setattr(cache, "get_agent_trail", lambda seed, fs, pid: trail)
    monkeypatch.setattr(cache, "get_processor_assessments", lambda seed, fs, pid: None)

    steps = cache.get_reasoning_steps(SEED, FACTS_SOURCE, "PWP-07")

    assert steps[0]["dedup_hit"] is True
    assert steps[0]["result"] == dedup_message


def test_compute_reasoning_steps_appends_score_step_with_deducted_shipments(monkeypatch):
    trail = [
        _trail_row(0, "hypothesis", output_json="{}"),
        _trail_row(1, "revision", output_json=json.dumps({"revisions": []})),
    ]
    monkeypatch.setattr(cache, "get_agent_trail", lambda seed, fs, pid: trail)
    monkeypatch.setattr(
        cache,
        "get_processor_assessments",
        lambda seed, fs, pid: {
            "checks_only": {"verifiable_t": 100.0, "risk_band": "Low"},
            "full": {"verifiable_t": 90.0, "risk_band": "Medium"},
        },
    )
    monkeypatch.setattr(
        cache,
        "build_reconstruction_context",
        lambda seed, fs, pid: {
            "shipments": [{"shipment_id": "PWP-09-SHP-001", "weighbridge_net_t": 10.0}]
        },
    )
    monkeypatch.setattr(
        cache,
        "reconstruct_agent_findings",
        lambda trail, ctx: {"excluded_shipment_ids": frozenset({"PWP-09-SHP-001"})},
    )

    steps = cache.get_reasoning_steps(SEED, FACTS_SOURCE, "PWP-09")

    assert [s["step_type"] for s in steps] == ["hypothesis", "revision", "score"]
    score = steps[-1]["output"]
    assert score == {
        "checks_only_verifiable_t": 100.0,
        "full_verifiable_t": 90.0,
        "deducted_shipments": [{"shipment_id": "PWP-09-SHP-001", "weighbridge_net_t": 10.0}],
        "risk_band_before": "Low",
        "risk_band_after": "Medium",
    }


def test_compute_reasoning_steps_no_score_step_without_an_agent_run(monkeypatch):
    """A processor with no "full" assessment at all (agent loop never ran)
    gets no score step — nothing to report."""
    monkeypatch.setattr(cache, "get_agent_trail", lambda seed, fs, pid: [])
    monkeypatch.setattr(cache, "get_processor_assessments", lambda seed, fs, pid: None)

    steps = cache.get_reasoning_steps(SEED, FACTS_SOURCE, "PWP-01")

    assert steps == []
