"""Tests for GET /processors and GET /processors/{id} — app/store/cache.py
is monkeypatched directly, so these exercise only app/main.py's routing,
404 handling, and response shaping."""

from app.store import cache

_CHECKS_ONLY = {
    "certified_t": 100.0,
    "verified_inbound_t": 100.0,
    "capacity_limit_t": 1200.0,
    "verifiable_t": 100.0,
    "unverifiable_t": 0.0,
    "risk_band": "Low",
}
_FULL = {**_CHECKS_ONLY, "verifiable_t": 95.0, "unverifiable_t": 5.0}
_PROFILE = {
    "processor_id": "PWP-01",
    "name": "Alpha Recyclers",
    "type": "Recycler",
    "capacity_t_per_year": 1200.0,
    "permitted_categories": ["I"],
    "consent_no": "CTO-01",
    "consent_valid_from": "01/04/2022",
    "consent_valid_to": "31/03/2028",
    "registration_no": "REG-01",
    "gstin": "27AAAAA0000A1Z5",
    "address": "Plot 12, Industrial Area, Maharashtra",
    "lat": 19.08,
    "lon": 72.88,
}


def test_list_processors_happy_path(api_client, monkeypatch):
    monkeypatch.setattr(
        cache,
        "list_processors",
        lambda seed, facts_source: [
            {
                "processor_id": "PWP-01",
                "name": "Alpha Recyclers",
                "type": "Recycler",
                "checks_only": _CHECKS_ONLY,
                "full": _FULL,
                "agent_status": "ok",
            }
        ],
    )

    response = api_client.get("/processors")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {"seed": 42, "facts_source": "truth"}
    assert body["processors"][0]["processor_id"] == "PWP-01"
    assert body["processors"][0]["full"]["verifiable_t"] == 95.0


def test_get_processor_happy_path(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: _PROFILE)
    monkeypatch.setattr(
        cache,
        "get_processor_assessments",
        lambda seed, fs, pid: {"checks_only": _CHECKS_ONLY, "full": _FULL, "agent_status": "ok"},
    )
    monkeypatch.setattr(
        cache,
        "get_monthly_flow",
        lambda seed, fs, pid: [
            {"month": "2026-01", "certified_t": 100.0, "verified_inbound_t": 100.0}
        ],
    )
    monkeypatch.setattr(
        cache,
        "get_check_results",
        lambda seed, fs, pid: [
            {
                "check_id": "C1",
                "status": "pass",
                "severity": "hard",
                "measured": 100.0,
                "threshold": 1200.0,
                "affected_tonnes": 0.0,
                "evidence_ids": [],
                "explanation": "within capacity",
                "source": "Consented capacity (processor-specific fact, not a tunable threshold)",
            }
        ],
    )
    monkeypatch.setattr(
        cache,
        "get_findings",
        lambda seed, fs, pid: [
            {
                "finding_type": "virgin material wording",
                "classification": "deductible",
                "effect": "raises_concern",
                "cited_shipment_ids": ["PWP-01-SHP-001"],
                "evidence_ids": ["DOC-INV-1"],
                "explanation": "HSN 3915 but description reads as virgin granules",
                "origin": "hypothesis",
                "proposed_by": "hypothesis",
                "verdict": {"by": "critic", "verdict": "upheld", "reason": "confirmed"},
                "disputed_by": None,
            }
        ],
    )

    response = api_client.get("/processors/PWP-01")

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["processor_id"] == "PWP-01"
    assert body["checks_only"]["risk_band"] == "Low"
    assert body["full"]["verifiable_t"] == 95.0
    assert body["agent_status"] == "ok"
    assert body["findings"][0]["classification"] == "deductible"
    assert body["monthly_flow"][0]["month"] == "2026-01"
    assert body["check_results"][0]["check_id"] == "C1"


def test_get_processor_404_unknown_processor(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: None)

    response = api_client.get("/processors/PWP-99")

    assert response.status_code == 404


def test_get_processor_404_when_not_scored(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: _PROFILE)
    monkeypatch.setattr(cache, "get_processor_assessments", lambda seed, fs, pid: None)

    response = api_client.get("/processors/PWP-01")

    assert response.status_code == 404


def test_get_processor_404_when_checks_only_missing(api_client, monkeypatch):
    """checks_only is the response model's one non-optional stage — a
    processor record with no checks_only row (e.g. only "full" somehow
    exists) must 404 cleanly, not fail response-model validation."""
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: _PROFILE)
    monkeypatch.setattr(
        cache,
        "get_processor_assessments",
        lambda seed, fs, pid: {"checks_only": None, "full": _FULL, "agent_status": "ok"},
    )

    response = api_client.get("/processors/PWP-01")

    assert response.status_code == 404
