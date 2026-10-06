"""Smoke test: Pub/Sub — publish one trivial message.

Does not require a subscription (that is created in T13).
Run: uv run python scripts/smoke/smoke_pubsub.py
"""

import json
import sys

from google.cloud import pubsub_v1

from app.config import settings


def main() -> int:
    print("--- smoke_pubsub: publish one message ---")
    try:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(settings.gcp_project, settings.pubsub_topic)
        payload = json.dumps({"smoke_test": True}).encode("utf-8")

        future = publisher.publish(topic_path, payload)
        message_id = future.result(timeout=30)
        print(f"published to {topic_path}, message_id={message_id}")

        print("smoke_pubsub: PASS")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"smoke_pubsub: FAIL — {exc!r}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
