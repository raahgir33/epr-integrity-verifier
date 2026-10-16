"""Tests for app/events/pubsub.py's pure logic (token check, push-
envelope decoding) — no real PubSub call (publish_certificate_batch
itself is a thin SDK wrapper, not unit-tested here, same convention as
every other direct-SDK-call function in this codebase, e.g.
app/store/gcs.py's upload_file)."""

import base64
import json

import pytest

from app.config import settings
from app.events import pubsub


@pytest.fixture(autouse=True)
def _push_token(monkeypatch):
    monkeypatch.setattr(settings, "push_token", "correct-token")


def test_verify_push_token_accepts_the_configured_token():
    assert pubsub.verify_push_token("correct-token") is True


def test_verify_push_token_rejects_wrong_or_missing_token():
    assert pubsub.verify_push_token("wrong-token") is False
    assert pubsub.verify_push_token(None) is False
    assert pubsub.verify_push_token("") is False


def test_verify_push_token_rejects_everything_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "push_token", None)
    assert pubsub.verify_push_token("anything") is False
    assert pubsub.verify_push_token(None) is False


def test_verify_push_token_rejects_everything_when_configured_empty(monkeypatch):
    monkeypatch.setattr(settings, "push_token", "")
    assert pubsub.verify_push_token("") is False


def _push_envelope(payload: dict) -> dict:
    data = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return {
        "message": {"data": data, "messageId": "123", "publishTime": "2026-04-01T00:00:00Z"},
        "subscription": "projects/p/subscriptions/certificate-batches-push",
    }


def test_decode_push_envelope_round_trips_the_published_payload():
    envelope = _push_envelope({"run_id": "RUN-1", "batch_id": "BATCH-PWP-01-001"})

    decoded = pubsub.decode_push_envelope(envelope)

    assert decoded == {"run_id": "RUN-1", "batch_id": "BATCH-PWP-01-001"}


def test_decode_push_envelope_raises_on_malformed_body():
    with pytest.raises(KeyError):
        pubsub.decode_push_envelope({"not_message": {}})
