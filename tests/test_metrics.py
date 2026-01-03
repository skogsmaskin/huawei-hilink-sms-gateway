import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app import (
    app,
    settings,
    sms_sent_total,
    sms_received_total,
    webhook_success_total,
    webhook_failure_total,
    modem_errors_total,
    poller_iterations_total,
    alertmanager_alerts_total,
    _increment_metric,
    _get_metrics_summary,
)

client = TestClient(app)


def test_metrics_endpoint_exists():
    """Test that /metrics endpoint exists and returns Prometheus format."""
    response = client.get("/metrics")
    assert response.status_code == 200
    # Check content-type contains the expected parts (version may vary)
    assert "text/plain" in response.headers["content-type"]
    assert "charset=utf-8" in response.headers["content-type"]
    
    content = response.text
    assert "sms_sent_total" in content
    assert "sms_received_total" in content
    assert "webhook_success_total" in content
    assert "webhook_failure_total" in content
    assert "modem_errors_total" in content
    assert "poller_iterations_total" in content
    assert "alertmanager_alerts_total" in content


def test_metrics_endpoint_format():
    """Test that /metrics returns valid Prometheus format."""
    response = client.get("/metrics")
    assert response.status_code == 200
    
    lines = response.text.split('\n')
    # Check for Prometheus format (metric_name value or metric_name{labels} value)
    metric_lines = [line for line in lines if line and not line.startswith('#')]
    
    for line in metric_lines:
        if line.strip():
            parts = line.split()
            assert len(parts) >= 2, f"Invalid metric line: {line}"
            # Value should be a number
            try:
                float(parts[-1])
            except ValueError:
                pytest.fail(f"Invalid metric value in line: {line}")


def test_health_includes_metrics():
    """Test that /health endpoint includes metrics summary."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    
    assert "metrics" in data
    assert isinstance(data["metrics"], dict)
    assert "sms_sent" in data["metrics"]
    assert "sms_received" in data["metrics"]
    assert "webhook_success" in data["metrics"]
    assert "webhook_failure" in data["metrics"]
    assert "modem_errors" in data["metrics"]
    assert "poller_iterations" in data["metrics"]
    
    # All metrics should be integers
    for key, value in data["metrics"].items():
        assert isinstance(value, int), f"Metric {key} should be int, got {type(value)}"


def test_metrics_increment_sms_sent():
    """Test that sms_sent metric increments correctly."""
    initial_value = int(sms_sent_total._value.get())
    
    _increment_metric("sms_sent")
    
    new_value = int(sms_sent_total._value.get())
    assert new_value == initial_value + 1


def test_metrics_increment_sms_received():
    """Test that sms_received metric increments with labels."""
    # Get initial count
    initial_count = sum(
        int(child._value.get()) 
        for child in sms_received_total._metrics.values()
    )
    
    _increment_metric("sms_received", from_number="+1234567890")
    
    # Check that a new labeled metric was created or incremented
    new_count = sum(
        int(child._value.get()) 
        for child in sms_received_total._metrics.values()
    )
    assert new_count == initial_count + 1
    
    # Verify the specific label exists
    labeled_metric = sms_received_total.labels(from_number="+1234567890")
    assert int(labeled_metric._value.get()) >= 1


def test_metrics_increment_webhook_success():
    """Test that webhook_success metric increments."""
    initial_value = int(webhook_success_total._value.get())
    
    _increment_metric("webhook_success")
    
    new_value = int(webhook_success_total._value.get())
    assert new_value == initial_value + 1


def test_metrics_increment_webhook_failure():
    """Test that webhook_failure metric increments."""
    initial_value = int(webhook_failure_total._value.get())
    
    _increment_metric("webhook_failure")
    
    new_value = int(webhook_failure_total._value.get())
    assert new_value == initial_value + 1


def test_metrics_increment_modem_errors():
    """Test that modem_errors metric increments."""
    initial_value = int(modem_errors_total._value.get())
    
    _increment_metric("modem_errors")
    
    new_value = int(modem_errors_total._value.get())
    assert new_value == initial_value + 1


def test_metrics_increment_poller_iterations():
    """Test that poller_iterations metric increments."""
    initial_value = int(poller_iterations_total._value.get())
    
    _increment_metric("poller_iterations")
    
    new_value = int(poller_iterations_total._value.get())
    assert new_value == initial_value + 1


def test_metrics_increment_alertmanager_alert():
    """Test that alertmanager_alerts metric increments with labels."""
    initial_count = sum(
        int(child._value.get())
        for child in alertmanager_alerts_total._metrics.values()
    )
    
    _increment_metric("alertmanager_alert", severity="critical", status="firing")
    
    new_count = sum(
        int(child._value.get())
        for child in alertmanager_alerts_total._metrics.values()
    )
    assert new_count == initial_count + 1
    
    # Verify the specific labeled metric
    labeled_metric = alertmanager_alerts_total.labels(severity="critical", status="firing")
    assert int(labeled_metric._value.get()) >= 1


def test_metrics_summary_parsing():
    """Test that _get_metrics_summary correctly parses Prometheus metrics."""
    # Increment some metrics
    _increment_metric("sms_sent")
    _increment_metric("sms_received", from_number="+1111111111")
    _increment_metric("webhook_success")
    
    summary = _get_metrics_summary()
    
    assert isinstance(summary, dict)
    assert "sms_sent" in summary
    assert "sms_received" in summary
    assert "webhook_success" in summary
    assert "webhook_failure" in summary
    assert "modem_errors" in summary
    assert "poller_iterations" in summary
    
    # Values should be non-negative integers
    for key, value in summary.items():
        assert isinstance(value, int)
        assert value >= 0


def test_metrics_endpoint_no_auth_required():
    """Test that /metrics endpoint doesn't require authentication."""
    response = client.get("/metrics")
    assert response.status_code == 200
    # Should not be 401 or 403
    assert response.status_code not in [401, 403]


def test_metrics_reflect_activity():
    """Test that metrics reflect actual activity."""
    # Get initial metrics
    initial_response = client.get("/metrics")
    initial_sms_sent = None
    for line in initial_response.text.split('\n'):
        if line.startswith('sms_sent_total ') and not line.startswith('#'):
            initial_sms_sent = int(float(line.split()[1]))
            break
    
    # Increment metric
    _increment_metric("sms_sent")
    _increment_metric("sms_sent")
    
    # Check metrics endpoint reflects the change
    new_response = client.get("/metrics")
    new_sms_sent = None
    for line in new_response.text.split('\n'):
        if line.startswith('sms_sent_total ') and not line.startswith('#'):
            new_sms_sent = int(float(line.split()[1]))
            break
    
    if initial_sms_sent is not None and new_sms_sent is not None:
        assert new_sms_sent == initial_sms_sent + 2


def test_health_metrics_match_prometheus():
    """Test that /health metrics match what's in /metrics."""
    # Get metrics from both endpoints
    health_response = client.get("/health")
    metrics_response = client.get("/metrics")
    
    health_metrics = health_response.json()["metrics"]
    metrics_text = metrics_response.text
    
    # Parse Prometheus format and compare
    prometheus_metrics = {}
    for line in metrics_text.split('\n'):
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        
        metric_name = parts[0]
        try:
            value = int(float(parts[1]))
        except (ValueError, IndexError):
            continue
        
        if metric_name == 'sms_sent_total':
            prometheus_metrics['sms_sent'] = value
        elif metric_name.startswith('sms_received_total'):
            prometheus_metrics['sms_received'] = prometheus_metrics.get('sms_received', 0) + value
        elif metric_name == 'webhook_success_total':
            prometheus_metrics['webhook_success'] = value
        elif metric_name == 'webhook_failure_total':
            prometheus_metrics['webhook_failure'] = value
        elif metric_name == 'modem_errors_total':
            prometheus_metrics['modem_errors'] = value
        elif metric_name == 'poller_iterations_total':
            prometheus_metrics['poller_iterations'] = value
    
    # Compare (allowing for small timing differences)
    for key in ['sms_sent', 'webhook_success', 'webhook_failure', 'modem_errors', 'poller_iterations']:
        if key in prometheus_metrics:
            assert health_metrics[key] == prometheus_metrics[key], \
                f"Metric {key} mismatch: health={health_metrics[key]}, prometheus={prometheus_metrics[key]}"
    
    # SMS received might have multiple labeled instances, so just check it's consistent
    if 'sms_received' in prometheus_metrics:
        assert health_metrics['sms_received'] == prometheus_metrics['sms_received'], \
            f"SMS received mismatch: health={health_metrics['sms_received']}, prometheus={prometheus_metrics['sms_received']}"


@patch('app._transaction')
@patch('app.settings')
def test_alertmanager_webhook_tracks_metrics(mock_settings, mock_transaction):
    """Test that Alertmanager webhook tracks metrics correctly."""
    # Mock settings to have alertmanager phone configured
    mock_settings.alertmanager_phone = "+1234567890"
    mock_settings.alertmanager_phone_critical = ""
    mock_settings.alertmanager_phone_warning = ""
    
    # Mock successful SMS send
    mock_transaction.return_value = {"result": "OK"}
    
    # Get initial metric values
    initial_sms_sent = int(sms_sent_total._value.get())
    initial_webhook_success = int(webhook_success_total._value.get())
    initial_alerts = sum(
        int(child._value.get())
        for child in alertmanager_alerts_total._metrics.values()
    )
    
    # Send Alertmanager webhook
    payload = {
        "version": "4",
        "status": "firing",
        "alerts": [{
            "labels": {"alertname": "TestAlert", "severity": "critical"},
            "annotations": {"summary": "Test alert"}
        }]
    }
    
    response = client.post(
        "/webhook/alertmanager",
        json=payload
    )
    
    # Check response
    assert response.status_code == 200
    
    # Check metrics were incremented
    new_sms_sent = int(sms_sent_total._value.get())
    new_webhook_success = int(webhook_success_total._value.get())
    new_alerts = sum(
        int(child._value.get())
        for child in alertmanager_alerts_total._metrics.values()
    )
    
    assert new_sms_sent == initial_sms_sent + 1
    assert new_webhook_success == initial_webhook_success + 1
    assert new_alerts == initial_alerts + 1
    
    # Verify the alert was tracked with correct labels
    alert_metric = alertmanager_alerts_total.labels(severity="critical", status="firing")
    assert int(alert_metric._value.get()) >= 1
