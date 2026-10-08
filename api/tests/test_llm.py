"""Tests for app/llm.py's retry logic. genai.Client is mocked throughout —
no real network calls.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from google.genai import errors, types
from pydantic import BaseModel

from app.llm import GeminiClient


class _DummySchema(BaseModel):
    value: str


def _make_response(json_text: str, usage: MagicMock | None = None) -> MagicMock:
    response = MagicMock()
    response.text = json_text
    response.usage_metadata = usage
    return response


def _usage(prompt=0, candidates=0, thoughts=0, total=0) -> MagicMock:
    usage = MagicMock()
    usage.prompt_token_count = prompt
    usage.candidates_token_count = candidates
    usage.thoughts_token_count = thoughts
    usage.total_token_count = total
    return usage


def _api_error(code: int) -> errors.APIError:
    return errors.APIError(code=code, response_json={"error": {"message": "boom", "status": "X"}})


@patch("app.llm.genai.Client")
def test_extract_succeeds_on_first_try(mock_client_cls):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_response('{"value": "ok"}')
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    result = client.extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")

    assert result.value == "ok"
    assert mock_client.models.generate_content.call_count == 1
    log = client.flush_call_log()
    assert len(log) == 1
    assert log[0]["success"] is True
    assert log[0]["purpose"] == "test"


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_extract_retries_on_429_then_succeeds(mock_client_cls, _mock_sleep):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _api_error(429),
        _make_response('{"value": "ok"}'),
    ]
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    result = client.extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")

    assert result.value == "ok"
    assert mock_client.models.generate_content.call_count == 2
    log = client.flush_call_log()
    assert [r["success"] for r in log] == [False, True]


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_extract_does_not_retry_on_non_retryable_4xx(mock_client_cls, _mock_sleep):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = _api_error(400)
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    with pytest.raises(errors.APIError):
        client.extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")

    assert mock_client.models.generate_content.call_count == 1


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_extract_gives_up_after_max_attempts(mock_client_cls, _mock_sleep):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = _api_error(503)
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    with pytest.raises(errors.APIError):
        client.extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")

    assert mock_client.models.generate_content.call_count == 5


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_extract_retries_on_read_timeout_then_succeeds(mock_client_cls, _mock_sleep):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        httpx.ReadTimeout("timed out"),
        _make_response('{"value": "ok"}'),
    ]
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    result = client.extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")

    assert result.value == "ok"
    assert mock_client.models.generate_content.call_count == 2
    log = client.flush_call_log()
    assert [r["success"] for r in log] == [False, True]


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_extract_retries_on_connect_timeout_too(mock_client_cls, _mock_sleep):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        httpx.ConnectTimeout("timed out"),
        _make_response('{"value": "ok"}'),
    ]
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    result = client.extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")

    assert result.value == "ok"
    assert mock_client.models.generate_content.call_count == 2


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_extract_gives_up_after_max_timeout_retries(mock_client_cls, _mock_sleep):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = httpx.ReadTimeout("timed out")
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    with pytest.raises(httpx.ReadTimeout):
        client.extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")

    # extract() shares the same max_attempts budget for timeouts as for
    # APIError (both default to _MAX_ATTEMPTS=5) — see
    # test_extract_gives_up_after_max_attempts for the APIError version.
    assert mock_client.models.generate_content.call_count == 5


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_generate_structured_gives_up_after_agent_max_attempts(mock_client_cls, _mock_sleep):
    """Agent calls (docs/PROGRESS.md: fail fast and retry) use a much
    smaller max_attempts budget than extract() for the same kind of
    timeout — 3, not 5."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = httpx.ReadTimeout("timed out")
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    with pytest.raises(httpx.ReadTimeout):
        client.generate_structured(["hello"], _DummySchema, purpose="test")

    assert mock_client.models.generate_content.call_count == 3


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_generate_structured_gives_up_after_agent_max_attempts_on_504(mock_client_cls, _mock_sleep):
    """The agent max-attempts budget is shared by BOTH retryable failure
    kinds (a 504 APIError here, a raw timeout above) — one combined cap,
    not two separate ones."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = _api_error(504)
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    with pytest.raises(errors.APIError):
        client.generate_structured(["hello"], _DummySchema, purpose="test")

    assert mock_client.models.generate_content.call_count == 3


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_generate_structured_critic_phase_purpose_gets_a_fourth_attempt(
    mock_client_cls, _mock_sleep
):
    """Critic-phase purposes (agent_critic_tools/agent_critic_final/
    agent_revision) get 4 attempts, not 3 — raised 2026-10-08 after the
    acceptance pair's PWP-05 loss to exactly three consecutive 504s."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _api_error(504),
        _api_error(504),
        _api_error(504),
        _make_response('{"value": "ok"}'),
    ]
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    result = client.generate_structured(["hello"], _DummySchema, purpose="agent_critic_final")

    assert result.value == "ok"
    assert mock_client.models.generate_content.call_count == 4


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_generate_structured_critic_phase_purpose_gives_up_after_four_attempts(
    mock_client_cls, _mock_sleep
):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = _api_error(504)
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    with pytest.raises(errors.APIError):
        client.generate_structured(["hello"], _DummySchema, purpose="agent_revision")

    assert mock_client.models.generate_content.call_count == 4


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_generate_structured_hypothesis_purpose_still_gives_up_after_three_attempts(
    mock_client_cls, _mock_sleep
):
    """agent_hypothesis deliberately keeps the original 3-attempt budget —
    only the critic-phase purposes (tools/final/revision) were raised to
    4, since the first step failing fast surfaces the processor-level
    retry (run_agent_loop_with_retry) sooner rather than later."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = _api_error(504)
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    with pytest.raises(errors.APIError):
        client.generate_structured(["hello"], _DummySchema, purpose="agent_hypothesis")

    assert mock_client.models.generate_content.call_count == 3


@patch("app.llm.genai.Client")
def test_extract_records_token_usage_from_response(mock_client_cls):
    mock_client = MagicMock()
    usage = _usage(prompt=120, candidates=45, thoughts=10, total=175)
    mock_client.models.generate_content.return_value = _make_response(
        '{"value": "ok"}', usage=usage
    )
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    client.extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")

    log = client.flush_call_log()
    assert log[0]["input_tokens"] == 120
    assert log[0]["output_tokens"] == 45
    assert log[0]["thinking_tokens"] == 10
    assert log[0]["total_tokens"] == 175


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_failed_call_records_no_token_usage(mock_client_cls, _mock_sleep):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = _api_error(400)
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    with pytest.raises(errors.APIError):
        client.extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")

    log = client.flush_call_log()
    assert log[0]["input_tokens"] is None
    assert log[0]["total_tokens"] is None


@patch("app.llm.genai.Client")
def test_flush_call_log_clears_buffer(mock_client_cls):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_response('{"value": "ok"}')
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    client.extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")
    assert len(client.flush_call_log()) == 1
    assert client.flush_call_log() == []


@patch("app.llm.genai.Client")
def test_thinking_level_is_passed_through_when_set(mock_client_cls):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_response('{"value": "ok"}')
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    client.extract(
        b"data", "application/pdf", "prompt", _DummySchema, purpose="test", thinking_level="low"
    )

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert isinstance(config.thinking_config, types.ThinkingConfig)
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW


@patch("app.llm.genai.Client")
def test_thinking_config_omitted_when_not_set(mock_client_cls):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_response('{"value": "ok"}')
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    client.extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.thinking_config is None


@patch("app.llm.genai.Client")
def test_thinking_level_minimal_is_rejected_before_any_call(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    for forbidden in ("minimal", "MINIMAL", " Minimal "):
        with pytest.raises(ValueError, match="minimal"):
            client.extract(
                b"data",
                "application/pdf",
                "prompt",
                _DummySchema,
                purpose="test",
                thinking_level=forbidden,
            )
    mock_client.models.generate_content.assert_not_called()


def _function_call_part(name: str, args: dict):
    fc = MagicMock()
    fc.name = name
    fc.args = args
    part = MagicMock()
    part.function_call = fc
    return part


def _text_part():
    part = MagicMock()
    part.function_call = None
    return part


def _tool_call_response(name: str, args: dict) -> MagicMock:
    response = MagicMock()
    response.candidates = [MagicMock(content=MagicMock(parts=[_function_call_part(name, args)]))]
    response.usage_metadata = None
    return response


def _text_response() -> MagicMock:
    response = MagicMock()
    response.candidates = [MagicMock(content=MagicMock(parts=[_text_part()]))]
    response.usage_metadata = None
    return response


def _dummy_tool(x: int):
    """A trivial tool for testing."""
    return f"got {x}", None


@patch("app.llm.genai.Client")
def test_generate_structured_uses_temperature_0_2(mock_client_cls):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_response('{"value": "ok"}')
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    result = client.generate_structured(["hello"], _DummySchema, purpose="test")

    assert result.value == "ok"
    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.temperature == 0.2


@patch("app.llm.genai.Client")
def test_generate_structured_disables_automatic_function_calling(mock_client_cls):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_response('{"value": "ok"}')
    mock_client_cls.return_value = mock_client

    GeminiClient().generate_structured(["hello"], _DummySchema, purpose="test")

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.automatic_function_calling.disable is True


@patch("app.llm.genai.Client")
def test_extract_disables_automatic_function_calling(mock_client_cls):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_response('{"value": "ok"}')
    mock_client_cls.return_value = mock_client

    GeminiClient().extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.automatic_function_calling.disable is True


@patch("app.llm.genai.Client")
def test_run_tool_loop_calls_tool_and_stops_when_model_returns_text(mock_client_cls):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _tool_call_response("_dummy_tool", {"x": 5}),
        _text_response(),
    ]
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    conversation, tool_cap_reached = client.run_tool_loop(
        contents=["question"], tools=[_dummy_tool], max_tool_calls=8, purpose="test"
    )

    assert tool_cap_reached is False
    assert mock_client.models.generate_content.call_count == 2
    # initial content + model turn 1 (tool call) + function response + model turn 2 (text)
    assert len(conversation) == 4

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.tool_config.function_calling_config.mode == types.FunctionCallingConfigMode.AUTO


@patch("app.llm.genai.Client")
def test_run_tool_loop_never_passes_a_raw_callable_in_tools(mock_client_cls):
    """Removes the harmless-but-noisy AFC warning without changing
    behavior: tools are pre-converted to real types.Tool/FunctionDeclaration
    objects ourselves (same schema the SDK would have derived internally
    from the same callables — google.genai._transformers.t_tool does the
    exact same FunctionDeclaration.from_callable(..., use_json_schema=True)
    call), never a bare Python callable, and automatic_function_calling is
    explicitly disabled on every call."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _tool_call_response("_dummy_tool", {"x": 5}),
        _text_response(),
    ]
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    client.run_tool_loop(
        contents=["question"], tools=[_dummy_tool], max_tool_calls=8, purpose="test"
    )

    config = mock_client.models.generate_content.call_args_list[0].kwargs["config"]
    assert config.automatic_function_calling.disable is True
    assert all(not callable(tool) for tool in config.tools)
    assert all(isinstance(tool, types.Tool) for tool in config.tools)
    declared_names = {fd.name for tool in config.tools for fd in (tool.function_declarations or [])}
    assert declared_names == {"_dummy_tool"}


@patch("app.llm.genai.Client")
def test_run_tool_loop_appends_attachment_as_separate_part(mock_client_cls):
    def _tool_with_attachment(path: str):
        """A tool that hands back raw bytes alongside its summary."""
        return f"read {path}", (b"%PDF-1.4 fake", "application/pdf")

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _tool_call_response("_tool_with_attachment", {"path": "gs://bucket/doc.pdf"}),
        _text_response(),
    ]
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    conversation, _ = client.run_tool_loop(
        contents=["question"], tools=[_tool_with_attachment], max_tool_calls=8, purpose="test"
    )

    # initial + model turn (tool call) + function response + attachment Part + model turn (text)
    assert len(conversation) == 5
    attachment_content = conversation[3]
    assert attachment_content.parts[0].inline_data.data == b"%PDF-1.4 fake"
    assert attachment_content.parts[0].inline_data.mime_type == "application/pdf"


@patch("app.llm.genai.Client")
def test_run_tool_loop_stops_at_cap_without_raising(mock_client_cls):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _tool_call_response("_dummy_tool", {"x": 1}),
        _tool_call_response("_dummy_tool", {"x": 2}),
    ]
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    conversation, tool_cap_reached = client.run_tool_loop(
        contents=["question"], tools=[_dummy_tool], max_tool_calls=2, purpose="test"
    )

    assert tool_cap_reached is True
    assert mock_client.models.generate_content.call_count == 2


@patch("app.llm.genai.Client")
def test_run_tool_loop_duplicate_call_does_not_count_toward_cap_or_reexecute(mock_client_cls):
    call_count = {"n": 0}

    def _counting_tool(x: int):
        call_count["n"] += 1
        return f"got {x}", None

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _tool_call_response("_counting_tool", {"x": 1}),
        _tool_call_response("_counting_tool", {"x": 1}),  # exact duplicate of the call above
        _tool_call_response("_counting_tool", {"x": 2}),
    ]
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    conversation, tool_cap_reached = client.run_tool_loop(
        contents=["question"], tools=[_counting_tool], max_tool_calls=2, purpose="test"
    )

    assert tool_cap_reached is True
    # 3 Gemini calls happened, but only 2 real tool executions — the
    # duplicate (2nd call) counted toward neither the tool's own call
    # count nor max_tool_calls.
    assert mock_client.models.generate_content.call_count == 3
    assert call_count["n"] == 2
    duplicate_response = conversation[4].parts[0].function_response.response["result"]
    assert "already returned in call 1" in duplicate_response.lower()


@patch("app.llm.genai.Client")
def test_run_tool_loop_stops_at_safety_backstop_if_model_repeats_forever(mock_client_cls):
    mock_client = MagicMock()
    # The model requests the exact same call every turn — call_number never
    # advances past 1, so only the total-iteration backstop can stop this.
    mock_client.models.generate_content.side_effect = [
        _tool_call_response("_dummy_tool", {"x": 1}) for _ in range(10)
    ]
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    conversation, tool_cap_reached = client.run_tool_loop(
        contents=["question"], tools=[_dummy_tool], max_tool_calls=2, purpose="test"
    )

    assert tool_cap_reached is True
    # max_total_iterations = max_tool_calls * 3 = 6 — the backstop, since
    # call_number (real, unique calls) never reaches max_tool_calls here.
    assert mock_client.models.generate_content.call_count == 6


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_run_tool_loop_retries_up_to_agent_max_attempts_then_succeeds(mock_client_cls, _mock_sleep):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _api_error(504),
        _api_error(504),
        _text_response(),
    ]
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    conversation, tool_cap_reached = client.run_tool_loop(
        contents=["question"], tools=[_dummy_tool], max_tool_calls=8, purpose="test"
    )

    assert tool_cap_reached is False
    assert mock_client.models.generate_content.call_count == 3


@patch("app.llm.time.sleep", return_value=None)
@patch("app.llm.genai.Client")
def test_run_tool_loop_critic_tools_purpose_gets_a_fourth_attempt(mock_client_cls, _mock_sleep):
    """agent_critic_tools is one of the critic-phase purposes raised to 4
    attempts, 2026-10-08 — 3 consecutive 504s no longer exhausts the
    budget before a 4th attempt can succeed."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _api_error(504),
        _api_error(504),
        _api_error(504),
        _text_response(),
    ]
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    conversation, tool_cap_reached = client.run_tool_loop(
        contents=["question"], tools=[_dummy_tool], max_tool_calls=8, purpose="agent_critic_tools"
    )

    assert tool_cap_reached is False
    assert mock_client.models.generate_content.call_count == 4


@patch("app.llm.genai.Client")
def test_thinking_budget_parameter_no_longer_exists(mock_client_cls):
    """Never send thinking_budget to Gemini 3.x models — confirmed rejected
    (and inconsistently) for this model/region on 2026-10-07. The parameter
    is removed from GeminiClient.extract entirely, not just unused."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_response('{"value": "ok"}')
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    with pytest.raises(TypeError):
        client.extract(
            b"data", "application/pdf", "prompt", _DummySchema, purpose="test", thinking_budget=0
        )
