"""Single Gemini client wrapper: retries, logging, timeouts.

Exposes the LLMClient protocol so callers (extraction, and the agent
orchestrator) can be tested with a fake client instead of hitting Vertex AI.

Two distinct retry layers, matching two distinct rules:
- Network-level retry (429/5xx including 504, and a client-side
  httpx.ReadTimeout/ConnectTimeout if the server never responds at all —
  one shared attempt budget, exponential backoff) lives here, inside
  GeminiClient's _call_generate_content, shared by every public method.
  extract() gets _MAX_ATTEMPTS (5); agent calls (generate_structured,
  run_tool_loop) get the smaller _agent_max_attempts(purpose) — fail fast
  and retry, rather than wait longer, for the intermittent backend stalls
  docs/PROGRESS.md diagnosed on agent_critic_tools (normal calls <25s;
  a stalled one took ~118s before the server's own 504 — confirmed via
  google-genai's _api_client.py source: it forwards our configured
  timeout to the server as the X-Server-Timeout header, so a 504 here is
  the server enforcing the deadline we set, not a raw client read
  timeout; the very next retry succeeded in 4.2s). That budget is itself
  split in two (2026-10-08, after the acceptance pair): agent_hypothesis
  keeps the original 3; agent_critic_tools/agent_critic_final/
  agent_revision get 4 — PWP-05's run-1 loss in the acceptance pair was
  exactly three consecutive retryable 504s on a critic-phase call,
  exhausting the old shared budget of 3. Paired with the processor-level
  retry in app/agents/orchestrator.py's run_agent_loop_with_retry, which
  re-runs the whole loop once more if either budget is still exhausted.
- Schema-validation retry (one retry, then record failure) is the caller's
  job (app/ingest/extract.py) — a ValidationError from here propagates
  immediately, uncaught.
"""

import json
import logging
import random
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol, TypeVar

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_RETRYABLE_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 5
# Agent calls (generate_structured, run_tool_loop) fail fast and retry
# rather than wait longer (docs/PROGRESS.md) — a much smaller total-attempt
# budget than extract()'s _MAX_ATTEMPTS, shared by both the 504/5xx path
# and the raw-timeout path above (one combined cap, not two separate ones).
# agent_hypothesis keeps the original budget; the critic-phase purposes
# (which is where the acceptance pair's own PWP-05 loss happened — three
# consecutive 504s on one agent_critic_tools call) get one more attempt,
# 2026-10-08. Not raised for agent_hypothesis: it's the first step, so a
# fast failure there surfaces app/agents/orchestrator.py's
# run_agent_loop_with_retry sooner rather than later.
_AGENT_MAX_ATTEMPTS = 3
_CRITIC_PHASE_MAX_ATTEMPTS = 4
_CRITIC_PHASE_PURPOSES = {"agent_critic_tools", "agent_critic_final", "agent_revision"}


def _agent_max_attempts(purpose: str) -> int:
    return _CRITIC_PHASE_MAX_ATTEMPTS if purpose in _CRITIC_PHASE_PURPOSES else _AGENT_MAX_ATTEMPTS


# Never send thinking_budget to Gemini 3.x models — live-verified rejected
# (and inconsistently) for gemini-3.5-flash/asia-south1 on 2026-10-07; see
# docs/PROGRESS.md. thinking_level is the only supported knob, and
# "minimal" is also forbidden (developer instruction) — enforced below,
# not just documented here.
_FORBIDDEN_THINKING_LEVELS = {"minimal"}

# Per-request HTTP timeouts now live in app/config.py's Settings
# (agent_hypothesis_timeout_ms/agent_critic_tools_timeout_ms/
# agent_critic_final_timeout_ms/agent_revision_timeout_ms,
# extract_request_timeout_ms) — see there for how each value was derived
# and env-override them if needed.

# Fallback for any purpose string outside the four named agent purposes
# above — currently only app/agents/scorer.py's generate_narrative(),
# purpose="narrative" by default, which is defined but not yet called from
# the pipeline. Same floor as the critic_final/revision purposes, not a
# guess at a different number for an untested call shape.
_DEFAULT_AGENT_TIMEOUT_MS = 30_000


def _agent_timeout_ms(purpose: str) -> int:
    return {
        "agent_hypothesis": settings.agent_hypothesis_timeout_ms,
        "agent_critic_tools": settings.agent_critic_tools_timeout_ms,
        "agent_critic_final": settings.agent_critic_final_timeout_ms,
        "agent_revision": settings.agent_revision_timeout_ms,
    }.get(purpose, _DEFAULT_AGENT_TIMEOUT_MS)


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

    def _call_generate_content(self, purpose: str, max_attempts: int = _MAX_ATTEMPTS, **kwargs):
        """Shared retry/record wrapper around client.models.generate_content.
        Every public method below goes through this — one retry/backoff/
        call-log implementation, not duplicated per method. max_attempts is
        one shared budget for BOTH retryable failure kinds below — extract()
        uses the default (_MAX_ATTEMPTS); agent calls pass the smaller
        _AGENT_MAX_ATTEMPTS (docs/PROGRESS.md: fail fast and retry rather
        than wait longer, for the intermittent ~120s-class backend stalls
        observed on agent_critic_tools)."""
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
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
                if exc.code not in _RETRYABLE_CODES or attempt == max_attempts - 1:
                    raise
                backoff = min(2**attempt + random.uniform(0, 1), 30)
                logger.warning(
                    "retryable Gemini error (code=%s) on attempt %d/%d, backing off %.1fs",
                    exc.code,
                    attempt + 1,
                    max_attempts,
                    backoff,
                )
                time.sleep(backoff)
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
                # The server never responded at all within the configured
                # timeout — no API response/status code exists to judge
                # retryability from, unlike errors.APIError above (which is
                # what a 504 Gateway Timeout actually is — see the module
                # docstring). Shares the same max_attempts budget as the
                # APIError path above, not a separate cap.
                self._record_call(purpose, (time.monotonic() - start) * 1000, success=False)
                last_exc = exc
                if attempt == max_attempts - 1:
                    raise
                backoff = min(2**attempt + random.uniform(0, 1), 30)
                logger.warning(
                    "retryable network timeout (%s) on attempt %d/%d, backing off %.1fs",
                    type(exc).__name__,
                    attempt + 1,
                    max_attempts,
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
            "http_options": types.HttpOptions(timeout=settings.extract_request_timeout_ms),
            # No tools on this call, but AFC defaults to ON when this isn't
            # set at all — that's what printed the harmless-but-noisy "AFC
            # in Models.generate_content is not recommended" warning on
            # every extraction call (T2's smoke test; confirmed via the
            # SDK's own should_disable_afc(), which otherwise defaults to
            # enabling the legacy AFC loop even with zero tools present).
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
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
        """Temperature 0.2 (project conventions: "0.2 for agents") — used for
        the Hypothesis calls, the Critic's final no-tools call, and the
        Hypothesis revision. Not for extraction (use extract(), temp 0)."""
        config_kwargs = {
            "response_mime_type": "application/json",
            "response_schema": schema,
            "temperature": 0.2,
            "http_options": types.HttpOptions(timeout=_agent_timeout_ms(purpose)),
            # Same as extract() above — no tools on this call either, but
            # AFC still defaults to ON (and prints its warning) unless
            # explicitly disabled.
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        if thinking_level is not None:
            config_kwargs["thinking_config"] = self._thinking_config(thinking_level)

        response = self._call_generate_content(
            purpose,
            max_attempts=_agent_max_attempts(purpose),
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        return schema.model_validate_json(response.text)

    def _tool_declarations(self, tools: list[Callable]) -> list[types.Tool]:
        """Converts our Python callables to FunctionDeclaration schemas
        ourselves, and passes real types.Tool objects in `tools=` instead
        — never a raw callable. Confirmed via the SDK's own source
        (google.genai._transformers.t_tool/t_tools) that this produces the
        EXACT same thing the SDK would build internally from the same
        callables: one types.FunctionDeclaration per callable (via
        FunctionDeclaration.from_callable(..., use_json_schema=True), the
        same call t_tool makes), all merged into a single types.Tool. No
        schema or behavior change — only who builds it."""
        declarations = [
            types.FunctionDeclaration.from_callable(
                client=self._client._api_client, callable=fn, use_json_schema=True
            )
            for fn in tools
        ]
        return [types.Tool(function_declarations=declarations)]

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

        Tool-call efficiency (docs/PROGRESS.md): a repeated tool call —
        identical name and arguments to one already made this loop — is
        not re-executed and does not count toward max_tool_calls; it gets
        a cheap "already returned in call N" response instead (the fourth
        canary's PWP-08 trail spent 5 of its 8 real calls on exactly this
        kind of redundant re-fetch). Each such iteration still costs one
        real Gemini call though, so a model that keeps repeating itself
        could otherwise loop indefinitely — max_total_iterations is the
        backstop against that, generous since real repeats should become
        rare once the model sees the "already returned" response.
        """
        config_kwargs = {
            "tools": self._tool_declarations(tools),
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
            "tool_config": types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            ),
            "temperature": 0.2,
            "http_options": types.HttpOptions(timeout=_agent_timeout_ms(purpose)),
        }
        if thinking_level is not None:
            config_kwargs["thinking_config"] = self._thinking_config(thinking_level)

        # Dispatch is by name against the ORIGINAL callables — unchanged;
        # only what's sent to the model (tools= above) is pre-converted.
        tools_by_name = {fn.__name__: fn for fn in tools}
        conversation = list(contents)
        seen_calls: dict[tuple[str, str], int] = {}
        call_number = 0
        max_total_iterations = max_tool_calls * 3

        for _ in range(max_total_iterations):
            response = self._call_generate_content(
                purpose,
                max_attempts=_agent_max_attempts(purpose),
                contents=conversation,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            model_turn = response.candidates[0].content
            conversation = [*conversation, model_turn]
            function_calls = [p.function_call for p in model_turn.parts if p.function_call]
            if not function_calls:
                return conversation, False

            # EVERY function_call part gets exactly one function_response
            # part back, in the same order, with the same name, in a
            # single user turn. The model can emit several calls in one
            # turn and this loop used to answer only the first, which
            # Gemini rejects outright: 400 INVALID_ARGUMENT, "Please
            # ensure that the number of function response parts is equal
            # to the number of function call parts of the function call
            # turn" (live, 2026-10-17). So no branch below may skip a
            # response — not a duplicate, not a call past the budget, not
            # a tool that raised. The orchestrator's final structured
            # call continues from this same conversation, so an
            # unbalanced turn would fail there too, after the loop had
            # apparently succeeded.
            response_parts = []
            attachments = []
            budget_exhausted = False
            for function_call in function_calls:
                args = dict(function_call.args or {})
                cache_key = (
                    function_call.name,
                    json.dumps(args, sort_keys=True, default=str),
                )
                if cache_key in seen_calls:
                    summary = (
                        f"Already returned in call {seen_calls[cache_key]} — "
                        "see that result, do not call this again."
                    )
                    attachment = None
                elif call_number >= max_tool_calls:
                    # Only reachable within a parallel-call turn that
                    # straddles the cap; the loop returns below as soon as
                    # the budget is gone.
                    budget_exhausted = True
                    summary = json.dumps(
                        {"error": "tool budget exhausted — no further tool calls will run"}
                    )
                    attachment = None
                else:
                    call_number += 1
                    seen_calls[cache_key] = call_number
                    summary, attachment = self._execute_tool(
                        tools_by_name, function_call.name, args
                    )
                response_parts.append(
                    types.Part.from_function_response(
                        name=function_call.name, response={"result": summary}
                    )
                )
                if attachment is not None:
                    attachments.append(attachment)

            conversation = [*conversation, types.Content(role="user", parts=response_parts)]
            # A tool (read_document) can hand back raw document bytes
            # alongside its text summary — attached as a separate user
            # Part right after the function response turn, the fallback
            # path from the read_document smoke test (docs/PROGRESS.md):
            # embedding binary data inside the function_response itself
            # is the untested alternative, not assumed to work. Kept
            # outside the function-response Content for the same reason
            # the responses are all inside one: that turn must contain
            # exactly as many parts as the call turn did.
            for data, mime_type in attachments:
                conversation = [
                    *conversation,
                    types.Content(
                        role="user", parts=[types.Part.from_bytes(data=data, mime_type=mime_type)]
                    ),
                ]
            if budget_exhausted or call_number >= max_tool_calls:
                return conversation, True

        return conversation, True

    @staticmethod
    def _execute_tool(tools_by_name: dict, name: str, args: dict) -> tuple[str, tuple | None]:
        """Runs one tool, converting any failure into an error response
        for the model instead of letting it escape. A ValueError out of
        read_document propagated through run_tool_loop and killed a whole
        live agent run (2026-10-17), which cost that run its findings and
        silently dropped the processor to rule-checks-only scoring — a
        wrong answer, not a visible failure. A tool that fails is
        information the Critic can work around; it is never a reason to
        lose the run."""
        fn = tools_by_name.get(name)
        if fn is None:
            return json.dumps({"error": f"unknown tool {name!r}"}), None
        try:
            return fn(**args)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tool %s failed: %s", name, exc, exc_info=True)
            return json.dumps({"error": f"tool {name} failed: {exc}"}), None

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

    @property
    def call_log(self) -> list[dict]:
        """Non-destructive snapshot of the call log so far — unlike
        flush_call_log(), never clears the buffer. Lets a caller (the
        agent orchestrator) correlate the specific calls it just made
        with their latency/token usage — e.g. snapshot len(call_log)
        before a call, then slice call_log[start:] after — while
        flush_call_log() remains the sole, once-per-pipeline-stage drain
        feeding the llm_calls BigQuery table, unaffected by reads here."""
        with self._lock:
            return list(self._call_log)
