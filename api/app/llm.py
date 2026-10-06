"""Single Gemini client wrapper: retries, logging, timeouts.

Exposes the LLMClient protocol so callers (extraction, and later the agent
orchestrator) can be tested with a fake client instead of hitting Vertex AI.

Two distinct retry layers, matching two distinct rules:
- Network-level retry (429/5xx, exponential backoff, max 5 attempts) lives
  here, inside GeminiClient.extract.
- Schema-validation retry (one retry, then record failure) is the caller's
  job (app/ingest/extract.py) — a ValidationError from here propagates
  immediately, uncaught.
"""

import logging
import random
import threading
import time
from datetime import UTC, datetime
from typing import Protocol, TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_RETRYABLE_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 5


class LLMClient(Protocol):
    def extract(
        self, data: bytes, mime_type: str, prompt: str, schema: type[T], purpose: str
    ) -> T: ...


class GeminiClient:
    def __init__(self) -> None:
        self._client = genai.Client(
            vertexai=True, project=settings.gcp_project, location=settings.vertex_location
        )
        self._call_log: list[dict] = []
        self._lock = threading.Lock()

    def extract(
        self, data: bytes, mime_type: str, prompt: str, schema: type[T], purpose: str = "extract"
    ) -> T:
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            start = time.monotonic()
            try:
                response = self._client.models.generate_content(
                    model=settings.gemini_model,
                    contents=[types.Part.from_bytes(data=data, mime_type=mime_type), prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=0,
                    ),
                )
                self._record_call(purpose, (time.monotonic() - start) * 1000, success=True)
                return schema.model_validate_json(response.text)
            except errors.APIError as exc:
                self._record_call(purpose, (time.monotonic() - start) * 1000, success=False)
                last_exc = exc
                if exc.code not in _RETRYABLE_CODES or attempt == _MAX_ATTEMPTS - 1:
                    raise
                backoff = min(2**attempt + random.uniform(0, 1), 30)
                logger.warning(
                    "retryable Gemini error (code=%s) on attempt %d, backing off %.1fs",
                    exc.code,
                    attempt + 1,
                    backoff,
                )
                time.sleep(backoff)
        raise last_exc  # unreachable, satisfies type checkers

    def _record_call(self, purpose: str, latency_ms: float, success: bool) -> None:
        record = {
            "purpose": purpose,
            "model": settings.gemini_model,
            "latency_ms": latency_ms,
            "success": success,
            "called_at": datetime.now(UTC).isoformat(),
        }
        with self._lock:
            self._call_log.append(record)

    def flush_call_log(self) -> list[dict]:
        """Returns buffered call records and clears the buffer. Called once
        per pipeline stage, never per call."""
        with self._lock:
            records, self._call_log = self._call_log, []
        return records
