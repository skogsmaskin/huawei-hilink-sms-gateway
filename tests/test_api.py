import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app import app, settings

client = TestClient(app)


def test_health_basic():
    """Test basic health check."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "metrics" in data


def test_health_with_metrics():
    """Test health check includes metrics."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "metrics" in data
    assert isinstance(data["metrics"], dict)
    assert "sms_sent" in data["metrics"]
    assert "sms_received" in data["metrics"]


def test_send_sms_requires_auth():
    """Test that sending SMS requires authentication."""
    response = client.post(
        "/sms/send",
        json={"to": "+1234567890", "message": "test"}
    )
    assert response.status_code == 401


def test_send_sms_invalid_token():
    """Test that invalid token is rejected."""
    response = client.post(
        "/sms/send",
        json={"to": "+1234567890", "message": "test"},
        headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 403


def test_send_sms_invalid_phone():
    """Test phone number validation."""
    response = client.post(
        "/sms/send",
        json={"to": "", "message": "test"},
        headers={"Authorization": f"Bearer {settings.api_token}"}
    )
    assert response.status_code == 422  # Validation error


def test_send_sms_invalid_message():
    """Test message validation."""
    response = client.post(
        "/sms/send",
        json={"to": "+1234567890", "message": ""},
        headers={"Authorization": f"Bearer {settings.api_token}"}
    )
    assert response.status_code == 422  # Validation error


def test_inbox_requires_auth():
    """Test that inbox requires authentication."""
    response = client.get("/sms/inbox")
    assert response.status_code == 401


def test_mark_read_requires_auth():
    """Test that mark read requires authentication."""
    response = client.post("/sms/123/read")
    assert response.status_code == 401


def test_consume_unread_requires_auth():
    """Test that consume unread requires authentication."""
    response = client.post("/sms/inbox/consume")
    assert response.status_code == 401
