"""Tests for app/llm.py's retry logic. genai.Client is mocked throughout —
no real network calls.
"""

from unittest.mock import MagicMock, patch

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
