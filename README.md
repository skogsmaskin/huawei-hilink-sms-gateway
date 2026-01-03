# Huawei HiLink SMS Gateway

A reliable SMS gateway using **Huawei modems with HiLink firmware** (tested with E3372-325), exposing a REST API and push-based webhook system for automation and monitoring integrations.

## Features

### Core SMS Operations
- 📤 **Send SMS** - Send SMS messages via REST API with validation
- 📥 **Receive SMS** - Automatic polling and webhook delivery (push-based model)
- 📋 **Inbox Management** - View, mark as read, and delete SMS messages
- 🗑️ **Bulk Operations** - Delete multiple messages with flexible filtering (all, read-only, unread-only, or by limit)

### Integration & Automation
- 🔗 **Webhook Delivery** - Push SMS notifications to external systems (Home Assistant, custom endpoints)
- 🚨 **Prometheus Alertmanager Integration** - Built-in webhook endpoint for receiving and forwarding alerts as SMS
- 📊 **Prometheus Metrics** - Built-in `/metrics` endpoint for monitoring (SMS counts, webhook success/failure, errors)
- 📝 **SMS Command Parsing** - Process SMS commands for automation (e.g. `LIGHT ON`, `LIGHT OFF`)

### Security & Reliability
- 🔐 **Bearer Token Authentication** - Secure API access with token-based authentication
- 🔒 **Sender Allow-list** - Restrict SMS processing to trusted phone numbers
- ✅ **No-repeat Guarantees** - Deduplication via message tracking and mark-as-read
- 🔧 **Robust Message Handling** - Works even when messages arrive pre-marked as "read"
- 🔄 **Webhook Retry Logic** - Automatic retry with exponential backoff for failed deliveries
- 🛡️ **Error Handling** - Comprehensive error handling with differentiated retry logic (4xx vs 5xx errors)

### Technical Features
- 🔐 **Single-session Modem Access** - Thread-safe modem operations to avoid Huawei login conflicts
- 📚 **Interactive API Documentation** - Swagger UI and ReDoc for easy API exploration
- 🐳 **Docker Ready** - Pre-configured Docker and Docker Compose setup
- 📈 **Health Monitoring** - Health check endpoint with optional modem/webhook connectivity checks
- ⚙️ **Configurable Polling** - Adjustable polling interval or disable for pull-mode usage

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Huawei modem with HiLink firmware (tested with E3372-325)
- Webhook endpoint (optional, for push-based integrations)

### Compatible Modems

This gateway works with **Huawei modems that have HiLink firmware installed**. The key requirement is HiLink firmware, not a specific model number.

**Tested with:**
- Huawei E3372-325 (HiLink firmware)

**Should work with other HiLink-compatible modems including:**
- E3372 series (E3372, E3372h, E3372h-153, etc.)
- E3531, E3131
- E3272 series
- E8372 series
- E5186 series
- Other Huawei modems with HiLink firmware

**Note:** The modem must have HiLink firmware (provides web interface at 192.168.8.1). Some modems may come with Stick firmware instead, which is not compatible.

### Configuration

1. Copy environment variables to `.env` or set them in `docker-compose.yml`:

```bash
# Required
API_TOKEN=your-secure-random-token-here

# Modem Configuration
MODEM_URL=http://192.168.8.1
MODEM_USERNAME=admin
MODEM_PASSWORD=your-modem-password

# Polling Configuration
POLL_SECONDS=30  # Set to 0 to disable polling

# Webhook Configuration (optional)
WEBHOOK_URL=http://your-endpoint.local:8080/webhook/sms
WEBHOOK_TOKEN=  # Optional, for webhook authentication

# Security (optional)
ALLOWED_SENDERS=+4711223344,+4722334455  # Comma-separated phone numbers

# Advanced Options
PROCESS_READ_MESSAGES=1  # Recommended: process messages even if marked read
LOG_LEVEL=INFO  # INFO or DEBUG
DEBUG_RAW_DEFAULT=0  # Include raw modem responses in API by default

# Alertmanager Integration (optional)
ALERTMANAGER_PHONE=+4711223344  # Default phone for all alerts
ALERTMANAGER_PHONE_CRITICAL=+4711223344  # Override for critical alerts
ALERTMANAGER_PHONE_WARNING=+4722334455  # Override for warning alerts
```

2. Build and run:

```bash
docker-compose up -d
```

### Using Pre-built Docker Images

Pre-built Docker images are available on [GitHub Container Registry](https://github.com/skogsmaskin/huawei-hilink-sms-gateway/pkgs/container/sms-gateway):

```bash
# Pull the latest release
docker pull ghcr.io/skogsmaskin/sms-gateway:latest

# Or use a specific version
docker pull ghcr.io/skogsmaskin/sms-gateway:v1.0
```

### Docker Compose Example

**Using pre-built image:**
```yaml
services:
  sms-gateway:
    image: ghcr.io/skogsmaskin/sms-gateway:latest
    container_name: sms-gateway
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      MODEM_URL: "http://192.168.8.1"
      MODEM_USERNAME: "admin"
      MODEM_PASSWORD: "${E3372_ADMIN_PASSWORD}"
      API_TOKEN: "${API_TOKEN}"
      POLL_SECONDS: "30"
      WEBHOOK_URL: "http://your-endpoint.local:8080/webhook/sms"
      PROCESS_READ_MESSAGES: "1"
      ALLOWED_SENDERS: "${ALLOWED_SENDERS}"
      LOG_LEVEL: "INFO"
```

**Or build from source:**
```yaml
services:
  sms-gateway:
    build: .
    container_name: sms-gateway
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      MODEM_URL: "http://192.168.8.1"
      MODEM_USERNAME: "admin"
      MODEM_PASSWORD: "${E3372_ADMIN_PASSWORD}"
      API_TOKEN: "${API_TOKEN}"
      POLL_SECONDS: "30"
      WEBHOOK_URL: "http://your-endpoint.local:8080/webhook/sms"
      PROCESS_READ_MESSAGES: "1"
      ALLOWED_SENDERS: "${ALLOWED_SENDERS}"
      LOG_LEVEL: "INFO"
```

## API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc

### Authentication

All endpoints (except `/health`) require Bearer token authentication:

```bash
curl -H "Authorization: Bearer YOUR_API_TOKEN" http://localhost:8080/sms/inbox
```

### Endpoints

#### `GET /health`

Health check endpoint. Returns `{"ok": true}` and optionally checks modem connectivity.

#### `POST /sms/send`

Send an SMS message.

**Request:**
```json
{
  "to": "+4711223344",
  "message": "Hello from SMS Gateway"
}
```

**Response:**
```json
{
  "ok": true,
  "modem_response": {
    "result": "OK"
  }
}
```

#### `GET /sms/inbox`

Retrieve SMS messages from inbox.

**Query Parameters:**
- `unread_only` (bool): Filter to unread messages only
- `limit` (int): Maximum number of messages to return (default: 20)
- `debug` (bool): Include raw modem response

**Response:**
```json
{
  "count": 5,
  "messages": [
    {
      "Index": "40000",
      "Phone": "+4711223344",
      "Content": "LIGHT ON",
      "Date": "26/01/03,10:30:00+08",
      "Smstat": "0"
    }
  ]
}
```

#### `POST /sms/{index}/read`

Mark a specific SMS message as read.

#### `DELETE /sms/{index}`

Delete a specific SMS message by its index.

**Response:**
```json
{
  "ok": true,
  "index": "40000",
  "raw": {...}
}
```

#### `DELETE /sms/inbox`

Truncate inbox by deleting multiple messages.

**Query Parameters:**
- `all` (bool): Delete all messages (overrides other filters)
- `read_only` (bool): Delete only read messages
- `unread_only` (bool): Delete only unread messages
- `limit` (int): Maximum number of messages to delete, oldest first (default: 100, max: 500)

**Examples:**
- Delete all messages: `DELETE /sms/inbox?all=true`
- Delete all read messages: `DELETE /sms/inbox?read_only=true`
- Delete oldest 50 messages: `DELETE /sms/inbox?limit=50`

**Response:**
```json
{
  "ok": true,
  "deleted_count": 25,
  "failed_count": 0,
  "deleted_indices": ["40000", "40001", ...],
  "failed": []
}
```

#### `POST /sms/inbox/consume`

Pull-mode helper: returns unread messages and marks them as read.

#### `GET /metrics`

**Prometheus metrics endpoint.** Exposes operational metrics in standard Prometheus format for scraping by Prometheus server.

**Response:** Prometheus metrics format (text/plain)

**Available metrics:**
- `sms_sent_total` - Total SMS messages sent
- `sms_received_total{from_number="..."}` - Total SMS messages received (labeled by sender)
- `webhook_success_total` - Successful webhook deliveries
- `webhook_failure_total` - Failed webhook deliveries
- `modem_errors_total` - Modem communication errors
- `poller_iterations_total` - Poller loop iterations
- `alertmanager_alerts_total{severity="...", status="..."}` - Alertmanager alerts processed

#### `POST /webhook/alertmanager`

**Prometheus Alertmanager webhook endpoint.** Receives alerts from Alertmanager and sends them as SMS messages. See [Prometheus Alertmanager Integration Guide](PROMETHEUS_ALERTMANAGER_INTEGRATION.md) for complete setup instructions.

**Request:** Alertmanager webhook payload (standard format)

**Response:**
```json
{
  "ok": true,
  "phone": "+4711223344",
  "message": "[CRITICAL] HighCPUUsage: CPU usage is above 80%",
  "modem_response": {
    "result": "OK"
  }
}
```

## Integration Examples

The gateway can integrate with any system that accepts HTTP POST requests. Configure `WEBHOOK_URL` to point to your endpoint, and the gateway will automatically forward received SMS messages.

### Integration Guides

- **[Home Assistant Integration](HOME_ASSISTANT_INTEGRATION.md)** - Complete guide for bidirectional SMS integration with Home Assistant
- **[Prometheus Alertmanager Integration](PROMETHEUS_ALERTMANAGER_INTEGRATION.md)** - Setup guide for sending alert notifications via SMS

### Webhook Payload

The webhook sends the following JSON payload via HTTP POST:

```json
{
  "event": "sms.received",
  "id": "40000",
  "from": "+4711223344",
  "message": "LIGHT ON",
  "timestamp": "26/01/03,10:30:00+08",
  "raw": {
    "Index": "40000",
    "Phone": "+4711223344",
    "Content": "LIGHT ON",
    "Date": "26/01/03,10:30:00+08",
    "Smstat": "0"
  }
}
```

### Home Assistant Integration

The SMS Gateway integrates seamlessly with Home Assistant for both receiving SMS (via webhooks) and sending SMS (via REST API).

**📖 For complete setup instructions, examples, and automation templates, see the [Home Assistant Integration Guide](HOME_ASSISTANT_INTEGRATION.md).**

**Quick Example:**

1. Create a webhook in Home Assistant:
   - Go to **Settings → Automations & Scenes → Webhooks**
   - Click **Create Webhook**
   - Copy the webhook URL (e.g., `http://homeassistant.local:8123/api/webhook/lte_sms`)

2. Configure the gateway:
   ```bash
   WEBHOOK_URL=http://homeassistant.local:8123/api/webhook/lte_sms
   ```

3. Create an automation in Home Assistant:

```yaml
automation:
  - alias: "SMS Light Control"
    trigger:
      - platform: webhook
        webhook_id: lte_sms
    condition:
      - condition: template
        value_template: "{{ trigger.json.from == '+4711223344' }}"
    action:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ 'LIGHT ON' in trigger.json.message.upper() }}"
            sequence:
              - service: light.turn_on
                target:
                  entity_id: light.living_room
          - conditions:
              - condition: template
                value_template: "{{ 'LIGHT OFF' in trigger.json.message.upper() }}"
            sequence:
              - service: light.turn_off
                target:
                  entity_id: light.living_room
```

### Prometheus Alertmanager Integration

The SMS Gateway includes **built-in support for Prometheus Alertmanager**. No proxy or middleware needed!

**Quick Setup:**

1. Configure phone numbers in `docker-compose.yml`:
   ```yaml
   environment:
     ALERTMANAGER_PHONE: "+4711223344"
     ALERTMANAGER_PHONE_CRITICAL: "+4711223344"
     ALERTMANAGER_PHONE_WARNING: "+4722334455"
   ```

2. Configure Alertmanager to send webhooks:
   ```yaml
   receivers:
     - name: 'sms-critical'
       webhook_configs:
         - url: 'http://sms-gateway:8080/webhook/alertmanager'
           http_config:
             bearer_token: 'YOUR_API_TOKEN'
           send_resolved: true
   ```

**📖 For complete setup instructions, examples, and best practices, see the [Prometheus Alertmanager Integration Guide](PROMETHEUS_ALERTMANAGER_INTEGRATION.md).**

### Custom Endpoint Example

Any HTTP endpoint that accepts POST requests with JSON payloads can be used:

```bash
WEBHOOK_URL=http://your-server.local:8080/api/sms/webhook
WEBHOOK_TOKEN=your-secret-token  # Optional, sent as Bearer token
```

## Operating Mode

This project uses **Push/Webhook Mode**:

- Background poller fetches SMS every `POLL_SECONDS`
- Messages are processed once and sent to configured webhook endpoint
- Messages are marked as read after successful processing
- Deduplication is enforced via modem message index and in-memory tracking

This mode is preferred because:
- External systems do not need to poll
- Near-real-time response
- Works even if the webhook endpoint is temporarily unavailable (messages are retried)

## Security

- `API_TOKEN` required for all REST endpoints
- Sender allow-list (`ALLOWED_SENDERS`) for SMS commands
- Optional `WEBHOOK_TOKEN` for webhook authentication
- Webhook endpoints should be secured appropriately (HTTPS, authentication, network isolation)

## Troubleshooting

### Modem Not Responding

- Check `MODEM_URL` is correct and modem is accessible
- Verify `MODEM_USERNAME` and `MODEM_PASSWORD` are correct
- Check logs: `docker logs sms-gateway`

### Messages Not Being Processed

- Enable `PROCESS_READ_MESSAGES=1` (recommended)
- Check `ALLOWED_SENDERS` if configured
- Verify `WEBHOOK_URL` is correct
- Check poller logs for errors

### Webhook Failures

- Verify the webhook endpoint is accessible from the container
- Check webhook URL is correct
- Verify `WEBHOOK_TOKEN` if authentication is required
- Review webhook endpoint logs for errors
- Check network connectivity between container and endpoint

## Releases

This project uses [Semantic Versioning](https://semver.org/). See the [CHANGELOG.md](CHANGELOG.md) for a detailed list of changes in each release.

**Latest releases:** Check the [Releases page](https://github.com/skogsmaskin/huawei-hilink-sms-gateway/releases) for the latest version and release notes.

**Docker images** are automatically built and published to [GitHub Container Registry](https://github.com/skogsmaskin/huawei-hilink-sms-gateway/pkgs/container/sms-gateway) for each release and on every push to the main branch.

## Development

For detailed development instructions, testing guidelines, and contribution information, see the [Development Guide](DEVELOPMENT.md).

**Quick start:**
```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Run locally
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
