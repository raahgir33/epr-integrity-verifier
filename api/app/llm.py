"""Single Gemini client wrapper: retries, logging, timeouts.

Exposes the LLMClient protocol so callers (extraction, and the agent
orchestrator) can be tested with a fake client instead of hitting Vertex AI.

Two distinct retry layers, matching two distinct rules:
- Network-level retry (429/5xx, exponential backoff, max 5 attempts) lives
  here, inside GeminiClient's _call_generate_content, shared by every
  public method.
- Schema-validation retry (one retry, then record failure) is the caller's
  job (app/ingest/extract.py) — a ValidationError from here propagates
  immediately, uncaught.
"""

import logging
import random
import threading
import time
from collections.abc import Callable
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

# Never send thinking_budget to Gemini 3.x models — live-verified rejected
# (and inconsistently) for gemini-3.5-flash/asia-south1 on 2026-10-07; see
# docs/PROGRESS.md. thinking_level is the only supported knob, and
# "minimal" is also forbidden (developer instruction) — enforced below,
# not just documented here.
_FORBIDDEN_THINKING_LEVELS = {"minimal"}

# Per-request HTTP timeout for agent calls (run_tool_loop, generate_structured)
# — milliseconds (google.genai's HttpOptions.timeout unit). Leaves room for
# several calls inside the 180s per-run agent-loop deadline (ARCHITECTURE.md
# §4); extract() is unaffected (T6's verified behaviour, unchanged).
_AGENT_REQUEST_TIMEOUT_MS = 60_000


class LLMClient(Protocol):
    def extract(
        self,
        data: bytes,
        mime_type: str,
        prompt: str,
        schema: type[T],
        purpose: str,
        thinking_level: str | None = None,
    ) -> T: ...

    def run_tool_loop(
        self,
        contents: list,
        tools: list[Callable],
        max_tool_calls: int,
        purpose: str,
        thinking_level: str | None = None,
    ) -> tuple[list, bool]:
        """tools: each callable returns (summary: str | dict, attachment:
        tuple[bytes, str] | None) — attachment is (data, mime_type) for a
        tool like read_document that needs to hand back raw document
        bytes, appended as a separate Part right after the function
        response; None for every other tool."""
        ...

    def generate_structured(
        self,
        contents: list,
        schema: type[T],
        purpose: str,
        thinking_level: str | None = None,
    ) -> T: ...


class GeminiClient:
    def __init__(self) -> None:
        self._client = genai.Client(
            vertexai=True, project=settings.gcp_project, location=settings.vertex_location
        )
        self._call_log: list[dict] = []
        self._lock = threading.Lock()

    def _thinking_config(self, thinking_level: str) -> types.ThinkingConfig:
        normalized = thinking_level.strip().lower()
        if normalized in _FORBIDDEN_THINKING_LEVELS:
            raise ValueError(
                f"thinking_level={thinking_level!r} is not allowed — never send "
                "'minimal' (or thinking_budget) to Gemini 3.x models."
            )
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel(normalized.upper()))

    def _call_generate_content(self, purpose: str, **kwargs):
        """Shared retry/record wrapper around client.models.generate_content.
        Every public method below goes through this — one retry/backoff/
        call-log implementation, not duplicated per method."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            start = time.monotonic()
            try:
                response = self._client.models.generate_content(
                    model=settings.gemini_model, **kwargs
                )
                self._record_call(
                    purpose,
                    (time.monotonic() - start) * 1000,
                    success=True,
                    usage=response.usage_metadata,
                )
                return response
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

    def extract(
        self,
        data: bytes,
        mime_type: str,
        prompt: str,
        schema: type[T],
        purpose: str = "extract",
        thinking_level: str | None = None,
    ) -> T:
        config_kwargs = {
            "response_mime_type": "application/json",
            "response_schema": schema,
            "temperature": 0,
        }
        if thinking_level is not None:
            config_kwargs["thinking_config"] = self._thinking_config(thinking_level)

        response = self._call_generate_content(
            purpose,
            contents=[types.Part.from_bytes(data=data, mime_type=mime_type), prompt],
            config=types.GenerateContentConfig(**config_kwargs),
        )
        return schema.model_validate_json(response.text)

    def generate_structured(
        self,
        contents: list,
        schema: type[T],
        purpose: str,
        thinking_level: str | None = None,
    ) -> T:
        """Temperature 0.2 (CLAUDE.md §6: "0.2 for agents") — used for the
        Hypothesis calls, the Critic's final no-tools call, and the
        Hypothesis revision. Not for extraction (use extract(), temp 0)."""
        config_kwargs = {
            "response_mime_type": "application/json",
            "response_schema": schema,
            "temperature": 0.2,
            "http_options": types.HttpOptions(timeout=_AGENT_REQUEST_TIMEOUT_MS),
        }
        if thinking_level is not None:
            config_kwargs["thinking_config"] = self._thinking_config(thinking_level)

        response = self._call_generate_content(
            purpose, contents=contents, config=types.GenerateContentConfig(**config_kwargs)
        )
        return schema.model_validate_json(response.text)

    def run_tool_loop(
        self,
        contents: list,
        tools: list[Callable],
        max_tool_calls: int,
        purpose: str,
        thinking_level: str | None = None,
    ) -> tuple[list, bool]:
        """Bounded multi-turn function-calling loop (the Critic's phase 1,
        ARCHITECTURE.md §4). mode="AUTO" so the model can stop on its own
        by returning text instead of another function call — "ANY" (T2's
        smoke-tested pattern) forces a call every turn and is only correct
        for a single guaranteed-tool-call, not a loop that must terminate
        itself. Returns (conversation, tool_cap_reached): hitting
        max_tool_calls is not an error, just a flag for the caller to
        record — the orchestrator proceeds to the final structured call
        with whatever conversation exists so far.
        """
        config_kwargs = {
            "tools": tools,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
            "tool_config": types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ),
            "temperature": 0.2,
            "http_options": types.HttpOptions(timeout=_AGENT_REQUEST_TIMEOUT_MS),
        }
        if thinking_level is not None:
            config_kwargs["thinking_config"] = self._thinking_config(thinking_level)

        tools_by_name = {fn.__name__: fn for fn in tools}
        conversation = list(contents)

        for _ in range(max_tool_calls):
            response = self._call_generate_content(
                purpose, contents=conversation, config=types.GenerateContentConfig(**config_kwargs)
            )
            model_turn = response.candidates[0].content
            conversation = [*conversation, model_turn]
            function_call = next(
                (p.function_call for p in model_turn.parts if p.function_call), None
            )
            if function_call is None:
                return conversation, False

            fn = tools_by_name[function_call.name]
            summary, attachment = fn(**function_call.args)
            conversation = [
                *conversation,
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=function_call.name, response={"result": summary}
                        )
                    ],
                ),
            ]
            # A tool (read_document) can hand back raw document bytes
            # alongside its text summary — attached as a separate user
            # Part right after the function response, the fallback path
            # from the read_document smoke test (docs/PROGRESS.md):
            # embedding binary data inside the function_response itself
            # is the untested alternative, not assumed to work.
            if attachment is not None:
                data, mime_type = attachment
                conversation = [
                    *conversation,
                    types.Content(
                        role="user", parts=[types.Part.from_bytes(data=data, mime_type=mime_type)]
                    ),
                ]

        return conversation, True

    def _record_call(self, purpose: str, latency_ms: float, success: bool, usage=None) -> None:
        record = {
            "purpose": purpose,
            "model": settings.gemini_model,
            "latency_ms": latency_ms,
            "success": success,
            "called_at": datetime.now(UTC).isoformat(),
            "input_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None),
            "thinking_tokens": getattr(usage, "thoughts_token_count", None),
            "total_tokens": getattr(usage, "total_token_count", None),
        }
        with self._lock:
            self._call_log.append(record)

    def flush_call_log(self) -> list[dict]:
        """Returns buffered call records and clears the buffer. Called once
        per pipeline stage, never per call."""
        with self._lock:
            records, self._call_log = self._call_log, []
        return records
