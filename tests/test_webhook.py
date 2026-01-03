import pytest
from unittest.mock import patch, MagicMock
from app import _post_webhook, settings


@patch('app._http_session')
def test_webhook_success(mock_session):
    """Test successful webhook delivery."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_session.post.return_value = mock_response
    
    _post_webhook({"event": "test", "data": "test"})
    
    mock_session.post.assert_called_once()
    assert mock_session.post.call_args[1]["json"]["event"] == "test"


@patch('app._http_session')
def test_webhook_4xx_no_retry(mock_session):
    """Test that 4xx errors don't retry."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"
    mock_session.post.return_value = mock_response
    
    _post_webhook({"event": "test"})
    
    # Should only be called once (no retries for 4xx)
    assert mock_session.post.call_count == 1


@patch('app._http_session')
def test_webhook_5xx_retries(mock_session):
    """Test that 5xx errors retry."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_session.post.return_value = mock_response
    
    _post_webhook({"event": "test"})
    
    # Should retry up to WEBHOOK_MAX_RETRIES times
    assert mock_session.post.call_count == 3  # WEBHOOK_MAX_RETRIES
