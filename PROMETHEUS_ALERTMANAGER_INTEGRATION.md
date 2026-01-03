# Prometheus Alertmanager Integration Guide

This guide explains how to integrate the Huawei HiLink SMS Gateway with Prometheus Alertmanager to send SMS notifications for alerts.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Configuration](#configuration)
4. [Advanced Configuration](#advanced-configuration)
5. [Complete Example](#complete-example)
6. [Troubleshooting](#troubleshooting)
7. [Best Practices](#best-practices)

---

## Overview

The SMS Gateway includes **built-in support for Prometheus Alertmanager** via the `/webhook/alertmanager` endpoint. This endpoint:

- Accepts Alertmanager's standard webhook format
- Automatically formats alerts into concise SMS messages
- Supports severity-based phone number routing
- Handles both firing and resolved alerts
- Requires no additional services or proxies

### Benefits

- **Reliable Delivery:** SMS messages work even when email/chat services are down
- **Critical Alerts:** SMS is ideal for urgent, on-call notifications
- **Simple Integration:** Direct webhook integration, no middleware needed
- **Cost-Effective:** Uses existing LTE modem infrastructure

### Architecture

```
Prometheus → Alertmanager → SMS Gateway (/webhook/alertmanager) → LTE Modem → SMS
```

---

## Quick Start

### Step 1: Configure SMS Gateway

Configure phone numbers for alerts in `docker-compose.yml`:

```yaml
services:
  sms-gateway:
    environment:
      API_TOKEN: "${API_TOKEN}"
      # At least one phone number required
      ALERTMANAGER_PHONE: "+4711223344"  # Default for all alerts
      ALERTMANAGER_PHONE_CRITICAL: "+4711223344"  # Override for critical
      ALERTMANAGER_PHONE_WARNING: "+4722334455"  # Override for warning
```

**Note:** `ALERTMANAGER_PHONE` is required. Severity-specific phones override the default when set.

### Step 2: Configure Alertmanager

Add a webhook receiver in `alertmanager.yml`:

```yaml
receivers:
  - name: 'sms-critical'
    webhook_configs:
      - url: 'http://sms-gateway:8080/webhook/alertmanager'
        http_config:
          bearer_token: 'YOUR_API_TOKEN'
        send_resolved: true
```

### Step 3: Configure Alert Routing

Route alerts to the SMS receiver:

```yaml
route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: 'sms-critical'
      continue: true
```

---

## Configuration

### Phone Number Routing

The SMS Gateway routes alerts to phone numbers based on severity:

- **Critical alerts** → `ALERTMANAGER_PHONE_CRITICAL` (if set) or `ALERTMANAGER_PHONE`
- **Warning alerts** → `ALERTMANAGER_PHONE_WARNING` (if set) or `ALERTMANAGER_PHONE`
- **Other severities** → `ALERTMANAGER_PHONE`

### Alertmanager Receiver Configuration

```yaml
receivers:
  - name: 'sms-critical'
    webhook_configs:
      - url: 'http://sms-gateway:8080/webhook/alertmanager'
        http_config:
          bearer_token: 'YOUR_API_TOKEN'
        send_resolved: true  # Send SMS when alerts resolve
```

**Important:** Always use `/webhook/alertmanager`, not `/sms/send`. The Alertmanager endpoint handles format conversion automatically.

### Alert Routing Examples

**Route only critical alerts to SMS:**
```yaml
route:
  routes:
    - match:
        severity: critical
      receiver: 'sms-critical'
    - match:
        severity: warning
      receiver: 'email-warning'
```

**Route all alerts to SMS:**
```yaml
route:
  receiver: 'sms-critical'
```

---

## Advanced Configuration

### Alert Grouping

Group related alerts to reduce SMS spam:

```yaml
route:
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 1h
```

### Time-Based Routing

Send SMS only during specific hours:

```yaml
route:
  routes:
    - match:
        severity: critical
      receiver: 'sms-critical'
      active_time_intervals:
        - business_hours
      continue: true
    - match:
        severity: critical
      receiver: 'sms-critical-offhours'
      active_time_intervals:
        - off_hours

time_intervals:
  - name: business_hours
    time_intervals:
      - times:
          - start_time: '09:00'
            end_time: '17:00'
        weekdays: ['monday:friday']
  - name: off_hours
    time_intervals:
      - times:
          - start_time: '00:00'
            end_time: '23:59'
        weekdays: ['saturday', 'sunday']
      - times:
          - start_time: '00:00'
            end_time: '09:00'
        weekdays: ['monday:friday']
      - times:
          - start_time: '17:00'
            end_time: '23:59'
        weekdays: ['monday:friday']
```

### Alert Inhibition

Suppress lower-severity alerts when critical ones are firing:

```yaml
inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'cluster']
```

---

## Complete Example

### Full alertmanager.yml

```yaml
global:
  resolve_timeout: 5m

route:
  receiver: 'default'
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  
  routes:
    # Critical alerts → SMS immediately
    - match:
        severity: critical
      receiver: 'sms-critical'
      group_wait: 5s
      group_interval: 5m
      repeat_interval: 1h
      continue: true
    
    # Warning alerts → Email
    - match:
        severity: warning
      receiver: 'email-warning'
      group_wait: 30s
      group_interval: 5m
      repeat_interval: 6h

receivers:
  - name: 'default'
    webhook_configs:
      - url: 'http://sms-gateway:8080/webhook/alertmanager'
        http_config:
          bearer_token: 'YOUR_API_TOKEN'
        send_resolved: true
  
  - name: 'sms-critical'
    webhook_configs:
      - url: 'http://sms-gateway:8080/webhook/alertmanager'
        http_config:
          bearer_token: 'YOUR_API_TOKEN'
        send_resolved: true
  
  - name: 'email-warning'
    email_configs:
      - to: 'alerts@example.com'
        from: 'alertmanager@example.com'
        smarthost: 'smtp.example.com:587'
        auth_username: 'alertmanager'
        auth_password: 'password'

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'cluster', 'service']
```

### Prometheus Alert Rules Example

**alerts.yml:**
```yaml
groups:
  - name: infrastructure
    interval: 30s
    rules:
      - alert: HighCPUUsage
        expr: 100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High CPU usage on {{ $labels.instance }}"
      
      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.job }} is down"
```

### prometheus.yml

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093

rule_files:
  - "/etc/prometheus/alerts.yml"

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
  
  - job_name: 'sms-gateway'
    static_configs:
      - targets: ['sms-gateway:8080']
```

### Docker Compose

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./alerts.yml:/etc/prometheus/alerts.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
    ports:
      - "9090:9090"
    networks:
      - monitoring

  alertmanager:
    image: prom/alertmanager:latest
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
    ports:
      - "9093:9093"
    networks:
      - monitoring

  sms-gateway:
    image: sms-gateway
    environment:
      API_TOKEN: "${API_TOKEN}"
      MODEM_URL: "http://192.168.8.1"
      MODEM_USERNAME: "admin"
      MODEM_PASSWORD: "${MODEM_PASSWORD}"
      ALERTMANAGER_PHONE: "+4711223344"
      ALERTMANAGER_PHONE_CRITICAL: "+4711223344"
      ALERTMANAGER_PHONE_WARNING: "+4722334455"
    networks:
      - monitoring

networks:
  monitoring:
    driver: bridge
```

---

## Prometheus Metrics Integration

The SMS Gateway includes a **built-in Prometheus metrics endpoint** at `/metrics` that exposes operational metrics in standard Prometheus format.

### Available Metrics

- `sms_sent_total` - Total number of SMS messages sent
- `sms_received_total{from_number="..."}` - Total SMS messages received, labeled by sender phone number
- `webhook_success_total` - Total number of successful webhook deliveries
- `webhook_failure_total` - Total number of failed webhook deliveries
- `modem_errors_total` - Total number of modem communication errors
- `poller_iterations_total` - Total number of poller loop iterations
- `alertmanager_alerts_total{severity="...", status="..."}` - Total Alertmanager alerts processed, labeled by severity and status

### Configuration

Add the SMS Gateway to your Prometheus scrape configuration:

**prometheus.yml:**
```yaml
scrape_configs:
  - job_name: 'sms-gateway'
    static_configs:
      - targets: ['sms-gateway:8080']
```

The metrics endpoint is available at:
```
http://sms-gateway:8080/metrics
```

### Example Queries

**SMS messages sent per minute:**
```promql
rate(sms_sent_total[5m])
```

**SMS messages received by sender:**
```promql
sms_received_total
```

**Webhook success rate:**
```promql
rate(webhook_success_total[5m]) / (rate(webhook_success_total[5m]) + rate(webhook_failure_total[5m]))
```

**Alertmanager alerts by severity:**
```promql
sum by(severity) (alertmanager_alerts_total)
```

---

## Troubleshooting

### SMS Not Being Sent

1. **Check logs:**
   ```bash
   docker logs alertmanager
   docker logs sms-gateway
   ```

2. **Test webhook manually:**
   ```bash
   curl -X POST http://sms-gateway:8080/webhook/alertmanager \
     -H "Authorization: Bearer YOUR_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "version": "4",
       "status": "firing",
       "alerts": [{
         "labels": {"alertname": "TestAlert", "severity": "critical"},
         "annotations": {"summary": "Test alert"}
       }]
     }'
   ```

3. **Verify configuration:**
   - Check `ALERTMANAGER_PHONE` is set
   - Verify phone number format (must include country code with +)
   - Verify API token matches in both services

### Alerts Not Reaching Alertmanager

1. **Check Prometheus configuration:**
   - Verify `alerting.alertmanagers` is configured
   - Check Prometheus logs for connection errors

2. **Verify alert rules:**
   - Check rules are loaded: `http://prometheus:9090/rules`
   - Test alert expressions in Prometheus UI

### Network Connectivity

```bash
# Test DNS resolution
docker exec alertmanager nslookup sms-gateway

# Test connectivity
docker exec alertmanager curl -v http://sms-gateway:8080/health
```

---

## Best Practices

### Alert Severity Levels

- **Critical:** Send SMS immediately (system down, data loss risk)
- **Warning:** Use email or delay SMS (high resource usage, degraded service)
- **Info:** Log only (informational alerts)

### Rate Limiting

Configure repeat intervals to prevent SMS flooding:
```yaml
route:
  repeat_interval: 1h  # Don't repeat same alert more than once per hour
```

### Alert Grouping

Group related alerts to avoid SMS spam:
```yaml
route:
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 5m
```

### Phone Number Management

- Use different phone numbers for different teams/severities
- Rotate on-call phone numbers
- Consider SMS gateway limits (rate limiting, cost)

### Monitoring the SMS Gateway

Monitor the SMS Gateway itself:
```yaml
- alert: SMSGatewayDown
  expr: up{job="sms-gateway"} == 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "SMS Gateway is down"
```

### Message Length

Keep SMS messages concise (160 characters for single SMS):
- Use short alert names
- Include only essential information
- Use abbreviations where appropriate

---

## Additional Resources

- [Prometheus Alerting Documentation](https://prometheus.io/docs/alerting/latest/overview/)
- [Alertmanager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)
- [Prometheus Alert Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [SMS Gateway API Documentation](../README.md#api-documentation)

---

**Last Updated:** 2026-01-03
