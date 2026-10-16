"""PubSub publish + push-handler helpers for the live event path (T13,
docs/ARCHITECTURE.md §3.2). The actual verification work (extraction,
checks, agents, memo) lives in app/events/run_processor.py — this module
is only the PubSub plumbing: publishing the "a new certificate batch
arrived" message, and decoding/authenticating a push delivery of it.

Same PublisherClient/topic_path construction as
scripts/smoke/smoke_pubsub.py — the only prior real call this project has
made to this topic.
"""

import base64
import hmac
import json

from google.cloud import pubsub_v1

from app.config import settings


def publish_certificate_batch(run_id: str, batch_id: str) -> str:
    """Publishes {"run_id", "batch_id"} to settings.pubsub_topic. Returns
    the PubSub message_id (logged for audit — not used for idempotency;
    run_id, generated fresh per POST /demo/certificate-batch, is the
    idempotency key the push handler checks)."""
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(settings.gcp_project, settings.pubsub_topic)
    payload = json.dumps({"run_id": run_id, "batch_id": batch_id}).encode("utf-8")
    future = publisher.publish(topic_path, payload)
    return future.result(timeout=30)


def verify_push_token(token: str | None) -> bool:
    """A missing or empty configured push_token must never silently
    accept every request — settings.push_token is Optional only because
    nothing checks it before T13 exists (app/config.py's comment).
    T13.8: constant-time compare (hmac.compare_digest) so a wrong token's
    length/prefix can't be inferred from response timing."""
    if not settings.push_token or token is None:
        return False
    return hmac.compare_digest(token, settings.push_token)


def decode_push_envelope(body: dict) -> dict:
    """body is the standard PubSub push JSON shape:
    {"message": {"data": "<base64>", "messageId": "...", "publishTime": "..."},
     "subscription": "..."}. Returns the decoded {"run_id", "batch_id"}
    payload published by publish_certificate_batch above. Raises (KeyError/
    ValueError/json.JSONDecodeError) on a malformed envelope — the caller
    (app/main.py's push route) turns that into a 400, never a silent
    no-op."""
    message = body["message"]
    data = base64.b64decode(message["data"]).decode("utf-8")
    return json.loads(data)
