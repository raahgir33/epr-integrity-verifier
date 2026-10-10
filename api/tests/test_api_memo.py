"""Tests for GET /processors/{id}/memo."""

import datetime

from app.store import cache

_MEMO_ROW_EN = {
    "processor_id": "PWP-08",
    "doc_type": "clarification_memo",
    "lang": "en",
    "memo_json": (
        '{"subject": "Request for clarification", "salutation": "Dear Sir/Madam,", '
        '"opening_paragraph": "...", "items": [], "response_deadline_days": 15, '
        '"closing_paragraph": "..."}'
    ),
    "guard_status": "ok",
    "generated_at": datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC),
}

_MEMO_ROW_HI = {**_MEMO_ROW_EN, "lang": "hi"}

_STATEMENT_ROW_EN = {
    "processor_id": "PWP-01",
    "doc_type": "verification_statement",
    "lang": "en",
    "memo_json": (
        '{"subject": "Verification statement", "salutation": "Dear Sir/Madam,", '
        '"part_a_paragraph": "...", "observations": [], "no_items_note": '
        '"No improvement items identified from the documents examined.", '
        '"closing_paragraph": "..."}'
    ),
    "guard_status": "ok",
    "generated_at": datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC),
}


def _get_memo(rows_by_key):
    def _fake(seed, facts_source, processor_id, lang):
        return rows_by_key.get((processor_id, lang))

    return _fake


def test_memo_happy_path_clarification_memo(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: {"processor_id": pid})
    monkeypatch.setattr(
        cache,
        "get_memo",
        _get_memo({("PWP-08", "en"): _MEMO_ROW_EN, ("PWP-08", "hi"): _MEMO_ROW_HI}),
    )

    response = api_client.get("/processors/PWP-08/memo")

    assert response.status_code == 200
    body = response.json()
    assert body["doc_type"] == "clarification_memo"
    assert body["lang"] == "en"
    assert body["guard_status"] == "ok"
    assert body["has_hindi"] is True
    assert body["drafted_by"] == "Gemini — review before sending"
    assert body["sender_line"] == "Compliance team, [Brand]"
    assert body["memo"]["response_deadline_days"] == 15


def test_memo_happy_path_verification_statement(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: {"processor_id": pid})
    monkeypatch.setattr(cache, "get_memo", _get_memo({("PWP-01", "en"): _STATEMENT_ROW_EN}))

    response = api_client.get("/processors/PWP-01/memo")

    assert response.status_code == 200
    body = response.json()
    assert body["doc_type"] == "verification_statement"
    assert body["has_hindi"] is False
    assert body["memo"]["observations"] == []


def test_memo_hindi_lang_query_param(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: {"processor_id": pid})
    monkeypatch.setattr(
        cache,
        "get_memo",
        _get_memo({("PWP-08", "en"): _MEMO_ROW_EN, ("PWP-08", "hi"): _MEMO_ROW_HI}),
    )

    response = api_client.get("/processors/PWP-08/memo?lang=hi")

    assert response.status_code == 200
    assert response.json()["lang"] == "hi"


def test_memo_404_unknown_processor(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: None)

    response = api_client.get("/processors/PWP-99/memo")

    assert response.status_code == 404


def test_memo_422_bad_lang(api_client, monkeypatch):
    """T13.8: lang is now a FastAPI Literal["en", "hi"] — an invalid value
    is rejected by request validation (422) before the route body runs."""
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: {"processor_id": pid})

    response = api_client.get("/processors/PWP-08/memo?lang=fr")

    assert response.status_code == 422


def test_memo_404_not_generated_yet(api_client, monkeypatch):
    monkeypatch.setattr(cache, "get_processor_profile", lambda seed, pid: {"processor_id": pid})
    monkeypatch.setattr(cache, "get_memo", _get_memo({}))

    response = api_client.get("/processors/PWP-08/memo")

    assert response.status_code == 404
