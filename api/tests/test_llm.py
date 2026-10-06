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


def _make_response(json_text: str) -> MagicMock:
    response = MagicMock()
    response.text = json_text
    return response


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
def test_flush_call_log_clears_buffer(mock_client_cls):
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_response('{"value": "ok"}')
    mock_client_cls.return_value = mock_client

    client = GeminiClient()
    client.extract(b"data", "application/pdf", "prompt", _DummySchema, purpose="test")
    assert len(client.flush_call_log()) == 1
    assert client.flush_call_log() == []
