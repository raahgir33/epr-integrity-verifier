"""Tests for GET /processors/{id}/reasoning."""

from app.store import cache

_FINDING = {
    "finding_type": "virgin material wording",
    "classification": "deductible",
    "effect": "raises_concern",
    "cited_shipment_ids": ["PWP-05-SHP-001"],
    "evidence_ids": ["DOC-INV-1"],
    "explanation": "HSN 3915 but description reads as virgin granules",
    "origin": "hypothesis",
    "proposed_by": "hypothesis",
    "verdict": {"by": "critic", "verdict": "upheld", "reason": "confirmed"},
    "disputed_by": None,
}

_STEPS = [
    {
        "step_index": 0,
        "step_type": "hypothesis",
        "tool_name": None,
        "tool_args": None,
        "output": {"conclusions": []},
        "result": None,
        "result_summary": None,
        "latency_ms": 25000.0,
        "tokens": {"input": 1000, "output": 200, "thinking": None},
        "dedup_hit": False,
    },
    {
        "step_index": 1,
        "step_type": "critic_tool",
        "tool_name": "get_shipments",
        "tool_args": {"month": "2026-01"},
        "output": None,
        "result": [{"shipment_id": "PWP-05-SHP-001", "match_status": "matched"}],
        "result_summary": '[{"shipment_id": "PWP-05-SHP-001", "match_status": "matched"}]',
        "latency_ms": None,
        "tokens": {"input": None, "output": None, "thinking": None},
        "dedup_hit": False,
    },
]


def test_reasoning_happy_path(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: {"processor_id": pid})
    monkeypatch.setattr(
        cache, "get_processor_assessments", lambda seed, fs, pid: {"agent_status": "ok"}
    )
    monkeypatch.setattr(cache, "get_reasoning_steps", lambda seed, fs, pid: _STEPS)
    monkeypatch.setattr(cache, "get_findings", lambda seed, fs, pid: [_FINDING])

    response = api_client.get("/processors/PWP-05/reasoning")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_status"] == "ok"
    assert body["tool_cap_reached"] is False
    assert [s["step_type"] for s in body["steps"]] == ["hypothesis", "critic_tool"]
    assert body["steps"][1]["result"][0]["shipment_id"] == "PWP-05-SHP-001"
    assert body["findings"][0]["classification"] == "deductible"


def test_reasoning_detects_tool_cap_reached(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: {"processor_id": pid})
    monkeypatch.setattr(
        cache, "get_processor_assessments", lambda seed, fs, pid: {"agent_status": "ok"}
    )
    monkeypatch.setattr(
        cache,
        "get_reasoning_steps",
        lambda seed, fs, pid: [
            *_STEPS,
            {
                "step_index": 2,
                "step_type": "tool_cap_reached",
                "tool_name": None,
                "tool_args": None,
                "output": {"tool_cap_reached": True},
                "result": None,
                "result_summary": None,
                "latency_ms": None,
                "tokens": {"input": None, "output": None, "thinking": None},
                "dedup_hit": False,
            },
        ],
    )
    monkeypatch.setattr(cache, "get_findings", lambda seed, fs, pid: [])

    response = api_client.get("/processors/PWP-05/reasoning")

    assert response.json()["tool_cap_reached"] is True


def test_reasoning_no_agent_run_yet_returns_empty_not_error(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: {"processor_id": pid})
    monkeypatch.setattr(cache, "get_processor_assessments", lambda seed, fs, pid: None)
    monkeypatch.setattr(cache, "get_reasoning_steps", lambda seed, fs, pid: [])
    monkeypatch.setattr(cache, "get_findings", lambda seed, fs, pid: [])

    response = api_client.get("/processors/PWP-02/reasoning")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_status"] is None
    assert body["steps"] == []
    assert body["findings"] == []


def test_reasoning_404_unknown_processor(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: None)

    response = api_client.get("/processors/PWP-99/reasoning")

    assert response.status_code == 404
