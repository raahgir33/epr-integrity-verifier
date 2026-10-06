"""Tests for app/llm.py's retry logic. genai.Client is mocked throughout —
no real network calls.
"""

from unittest.mock import MagicMock, patch

import pytest
from google.genai import errors
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
