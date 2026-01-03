# Home Assistant Integration Guide

This guide explains how to integrate the Huawei HiLink SMS Gateway with Home Assistant for both receiving SMS messages (via webhooks) and sending SMS messages (via Home Assistant's Notifier API).

## Table of Contents

1. [Receiving SMS via Webhooks](#receiving-sms-via-webhooks)
2. [Sending SMS via Home Assistant Notifier](#sending-sms-via-home-assistant-notifier)
3. [Complete Example: Bidirectional SMS Integration](#complete-example-bidirectional-sms-integration)

---

## Receiving SMS via Webhooks

This section explains how to configure Home Assistant to receive SMS messages from the SMS Gateway via webhooks.

### Step 1: Create a Webhook in Home Assistant

1. Open Home Assistant
2. Go to **Settings → Automations & Scenes → Webhooks**
3. Click **Create Webhook** (or **+ CREATE WEBHOOK**)
4. Give it a name (e.g., `sms_gateway`)
5. Copy the webhook URL (e.g., `http://homeassistant.local:8123/api/webhook/sms_gateway`)
6. Note the webhook ID (e.g., `sms_gateway`)

### Step 2: Configure the SMS Gateway

Add the webhook URL to your SMS Gateway configuration:

**docker-compose.yml:**
```yaml
services:
  sms-gateway:
    environment:
      WEBHOOK_URL: "http://homeassistant.local:8123/api/webhook/sms_gateway"
      # Optional: Add authentication token if your webhook requires it
      WEBHOOK_TOKEN: "${HA_WEBHOOK_TOKEN}"
```

Or in your `.env` file:
```bash
WEBHOOK_URL=http://homeassistant.local:8123/api/webhook/sms_gateway
WEBHOOK_TOKEN=your-webhook-token-here  # Optional
```

**Note:** Replace `homeassistant.local` with your Home Assistant IP address or hostname. If Home Assistant is on a different network, use the full IP address (e.g., `http://192.168.1.100:8123`).

### Step 3: Create an Automation

Create an automation in Home Assistant to handle incoming SMS messages:

**Configuration → Automations & Scenes → Create Automation**

```yaml
alias: "SMS Received Handler"
description: "Handle incoming SMS messages from gateway"
trigger:
  - platform: webhook
    webhook_id: sms_gateway
condition: []
action:
  - service: system_log.write
    data:
      message: "SMS received from {{ trigger.json.from }}: {{ trigger.json.message }}"
      level: info
  # Add your custom actions here
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.json.from == '+4711223344' }}"
        sequence:
          - service: notify.mobile_app_your_phone
            data:
              message: "SMS from trusted sender: {{ trigger.json.message }}"
              title: "SMS Alert"
```

### Step 4: Advanced Automation Examples

#### Example 1: Light Control via SMS

```yaml
alias: "SMS Light Control"
description: "Control lights via SMS commands"
trigger:
  - platform: webhook
    webhook_id: sms_gateway
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
          - service: notify.mobile_app_your_phone
            data:
              message: "Living room light turned ON"
      - conditions:
          - condition: template
            value_template: "{{ 'LIGHT OFF' in trigger.json.message.upper() }}"
        sequence:
          - service: light.turn_off
            target:
              entity_id: light.living_room
          - service: notify.mobile_app_your_phone
            data:
              message: "Living room light turned OFF"
      - conditions:
          - condition: template
            value_template: "{{ 'LIGHT STATUS' in trigger.json.message.upper() }}"
        sequence:
          - service: notify.mobile_app_your_phone
            data:
              message: "Living room light is {{ states('light.living_room') }}"
```

#### Example 2: Temperature Alert via SMS

```yaml
alias: "SMS Temperature Alert"
description: "Send temperature alerts via SMS"
trigger:
  - platform: webhook
    webhook_id: sms_gateway
condition:
  - condition: template
    value_template: "{{ trigger.json.from == '+4711223344' }}"
  - condition: template
    value_template: "{{ 'TEMP' in trigger.json.message.upper() }}"
action:
  - service: notify.mobile_app_your_phone
    data:
      message: "Current temperature: {{ states('sensor.temperature') }}°C"
```

#### Example 3: Security Alert Forwarding

```yaml
alias: "SMS Security Alert"
description: "Forward security alerts via SMS"
trigger:
  - platform: state
    entity_id: binary_sensor.door_sensor
    to: "on"
action:
  - service: rest_command.send_sms
    data:
      to: "+4711223344"
      message: "ALERT: Door opened at {{ now().strftime('%H:%M:%S') }}"
```

---

## Sending SMS via Home Assistant Notifier

This section explains how to configure Home Assistant to send SMS messages using the SMS Gateway's REST API.

### Step 1: Create a REST Command

Add a REST command to your Home Assistant `configuration.yaml`:

**Configuration → File Editor → configuration.yaml**

```yaml
rest_command:
  send_sms:
    url: "http://sms-gateway:8080/sms/send"
    method: POST
    headers:
      Authorization: "Bearer YOUR_API_TOKEN"
      Content-Type: "application/json"
    payload: |
      {
        "to": "{{ to }}",
        "message": "{{ message }}"
      }
```

**Important:** 
- Replace `YOUR_API_TOKEN` with your actual API token from the SMS Gateway
- Replace `sms-gateway` with the hostname/IP of your SMS Gateway container
- If using Docker Compose on the same host, you can use the service name `sms-gateway`
- If Home Assistant is on a different host, use the IP address (e.g., `http://192.168.1.50:8080`)

### Step 2: Create a Notifier (Recommended)

For a cleaner integration, create a notifier in `configuration.yaml`:

```yaml
notify:
  - name: sms_gateway
    platform: rest
    resource: "http://sms-gateway:8080/sms/send"
    method: POST_JSON
    headers:
      Authorization: "Bearer YOUR_API_TOKEN"
    data:
      to: "{{ phone_number }}"
      message: "{{ message }}"
```

### Step 3: Using the Notifier

Once configured, you can use the notifier in automations, scripts, or the UI:

#### Using in Automation

```yaml
alias: "Send SMS Alert"
description: "Send SMS when door opens"
trigger:
  - platform: state
    entity_id: binary_sensor.door_sensor
    to: "on"
action:
  - service: notify.sms_gateway
    data:
      phone_number: "+4711223344"
      message: "Alert: Door opened at {{ now().strftime('%H:%M:%S') }}"
```

#### Using in Script

**Configuration → Automations & Scenes → Scripts → Create Script**

```yaml
send_sms_alert:
  alias: "Send SMS Alert"
  sequence:
    - service: notify.sms_gateway
      data:
        phone_number: "+4711223344"
        message: "This is a test message from Home Assistant"
```

#### Using REST Command Directly

```yaml
action:
  - service: rest_command.send_sms
    data:
      to: "+4711223344"
      message: "Hello from Home Assistant!"
```

### Step 4: Advanced Examples

#### Example 1: Daily Status Report

```yaml
alias: "Daily SMS Status Report"
description: "Send daily status report via SMS"
trigger:
  - platform: time
    at: "08:00:00"
action:
  - service: notify.sms_gateway
    data:
      phone_number: "+4711223344"
      message: |
        Daily Status Report:
        Temperature: {{ states('sensor.temperature') }}°C
        Humidity: {{ states('sensor.humidity') }}%
        Door: {{ states('binary_sensor.door_sensor') }}
        Lights ON: {{ states.light | selectattr('state', 'eq', 'on') | list | count }}
```

#### Example 2: Alert on High Temperature

```yaml
alias: "High Temperature SMS Alert"
description: "Send SMS when temperature is too high"
trigger:
  - platform: numeric_state
    entity_id: sensor.temperature
    above: 25
action:
  - service: notify.sms_gateway
    data:
      phone_number: "+4711223344"
      message: "WARNING: Temperature is {{ states('sensor.temperature') }}°C (above 25°C threshold)"
```

#### Example 3: Two-Factor Authentication Code

```yaml
alias: "Send 2FA Code via SMS"
description: "Send 2FA code when requested"
trigger:
  - platform: webhook
    webhook_id: request_2fa
action:
  - service: python_script.generate_2fa_code
  - service: notify.sms_gateway
    data:
      phone_number: "+4711223344"
      message: "Your 2FA code is: {{ states('input_text.2fa_code') }}"
```

---

## Complete Example: Bidirectional SMS Integration

Here's a complete example that demonstrates both receiving and sending SMS messages.

### Configuration Files

#### `configuration.yaml`

```yaml
# REST command for sending SMS
rest_command:
  send_sms:
    url: "http://sms-gateway:8080/sms/send"
    method: POST
    headers:
      Authorization: "Bearer YOUR_API_TOKEN"
      Content-Type: "application/json"
    payload: |
      {
        "to": "{{ to }}",
        "message": "{{ message }}"
      }

# Notifier for SMS
notify:
  - name: sms_gateway
    platform: rest
    resource: "http://sms-gateway:8080/sms/send"
    method: POST_JSON
    headers:
      Authorization: "Bearer YOUR_API_TOKEN"
    data:
      to: "{{ phone_number }}"
      message: "{{ message }}"

# Input helpers for trusted phone numbers
input_text:
  trusted_phone:
    name: "Trusted Phone Number"
    initial: "+4711223344"
```

#### Automation: Receive and Process SMS

```yaml
alias: "SMS Command Handler"
description: "Handle incoming SMS commands and respond"
trigger:
  - platform: webhook
    webhook_id: sms_gateway
condition:
  - condition: template
    value_template: "{{ trigger.json.from == states('input_text.trusted_phone') }}"
action:
  - choose:
      # Status command
      - conditions:
          - condition: template
            value_template: "{{ 'STATUS' in trigger.json.message.upper() }}"
        sequence:
          - service: notify.sms_gateway
            data:
              phone_number: "{{ trigger.json.from }}"
              message: |
                Home Status:
                Temp: {{ states('sensor.temperature') }}°C
                Lights: {{ states.light | selectattr('state', 'eq', 'on') | list | count }} ON
                Door: {{ states('binary_sensor.door_sensor') }}
      
      # Light control
      - conditions:
          - condition: template
            value_template: "{{ 'LIGHT ON' in trigger.json.message.upper() }}"
        sequence:
          - service: light.turn_on
            target:
              entity_id: light.living_room
          - service: notify.sms_gateway
            data:
              phone_number: "{{ trigger.json.from }}"
              message: "Living room light turned ON"
      
      - conditions:
          - condition: template
            value_template: "{{ 'LIGHT OFF' in trigger.json.message.upper() }}"
        sequence:
          - service: light.turn_off
            target:
              entity_id: light.living_room
          - service: notify.sms_gateway
            data:
              phone_number: "{{ trigger.json.from }}"
              message: "Living room light turned OFF"
      
      # Temperature query
      - conditions:
          - condition: template
            value_template: "{{ 'TEMP' in trigger.json.message.upper() }}"
        sequence:
          - service: notify.sms_gateway
            data:
              phone_number: "{{ trigger.json.from }}"
              message: "Current temperature: {{ states('sensor.temperature') }}°C"
      
      # Default: Echo the message
      - conditions: []
        sequence:
          - service: notify.sms_gateway
            data:
              phone_number: "{{ trigger.json.from }}"
              message: "Received: {{ trigger.json.message }}"
```

#### Automation: Send SMS on Events

```yaml
alias: "Send SMS on Door Open"
description: "Send SMS alert when door opens"
trigger:
  - platform: state
    entity_id: binary_sensor.door_sensor
    to: "on"
action:
  - service: notify.sms_gateway
    data:
      phone_number: "+4711223344"
      message: "🚨 ALERT: Door opened at {{ now().strftime('%Y-%m-%d %H:%M:%S') }}"
```

---

## Troubleshooting

### Webhook Not Receiving Messages

1. **Check SMS Gateway logs:**
   ```bash
   docker logs sms-gateway
   ```
   Look for webhook POST attempts and any error messages.

2. **Verify webhook URL:**
   - Ensure the URL in `WEBHOOK_URL` matches your Home Assistant webhook URL exactly
   - Check if Home Assistant is accessible from the SMS Gateway container
   - Test connectivity: `docker exec sms-gateway curl http://homeassistant.local:8123`

3. **Check Home Assistant logs:**
   - Go to **Settings → System → Logs**
   - Look for webhook-related errors

4. **Verify webhook ID:**
   - Ensure the `webhook_id` in your automation matches the webhook ID in Home Assistant

### SMS Sending Not Working

1. **Check API token:**
   - Verify `YOUR_API_TOKEN` in `configuration.yaml` matches the `API_TOKEN` in your SMS Gateway
   - Check SMS Gateway logs for authentication errors

2. **Check network connectivity:**
   - Ensure Home Assistant can reach the SMS Gateway
   - Test: `curl -H "Authorization: Bearer YOUR_TOKEN" http://sms-gateway:8080/health`

3. **Verify phone number format:**
   - Use international format with `+` prefix (e.g., `+4711223344`)
   - Check SMS Gateway logs for validation errors

4. **Check REST command syntax:**
   - Ensure the REST command URL and payload are correct
   - Test manually using the Developer Tools → REST Command

### Common Issues

**Issue:** "Connection refused" when sending SMS
- **Solution:** Check if SMS Gateway container is running and accessible
- Verify the URL uses the correct hostname/IP and port

**Issue:** "401 Unauthorized" when sending SMS
- **Solution:** Verify the API token in `configuration.yaml` matches the SMS Gateway `API_TOKEN`

**Issue:** Webhook receives messages but automation doesn't trigger
- **Solution:** Check the webhook ID matches exactly
- Verify the automation is enabled
- Check Home Assistant logs for automation errors

---

## Security Considerations

1. **API Token Security:**
   - Never commit API tokens to version control
   - Use Home Assistant secrets or environment variables
   - Rotate tokens regularly

2. **Network Security:**
   - Use HTTPS if possible (requires reverse proxy setup)
   - Restrict network access to SMS Gateway
   - Use firewall rules to limit access

3. **Phone Number Validation:**
   - Always validate sender phone numbers in automations
   - Use `ALLOWED_SENDERS` in SMS Gateway configuration
   - Don't trust SMS messages from unknown numbers

4. **Webhook Security:**
   - Use unique webhook IDs
   - Consider adding authentication tokens
   - Monitor webhook access logs

---

## Additional Resources

- [Home Assistant REST API Documentation](https://www.home-assistant.io/integrations/rest/)
- [Home Assistant Webhooks Documentation](https://www.home-assistant.io/integrations/webhook/)
- [Home Assistant Notify Platform](https://www.home-assistant.io/integrations/notify/)
- [SMS Gateway API Documentation](../README.md#api-documentation)

---

## Example Use Cases

1. **Home Security:** Receive SMS alerts when doors/windows open
2. **Remote Control:** Control lights, thermostats, and other devices via SMS
3. **Status Reports:** Receive daily/weekly status reports via SMS
4. **Two-Factor Authentication:** Send 2FA codes via SMS
5. **Emergency Alerts:** Send critical alerts when sensors detect issues
6. **Remote Monitoring:** Query sensor values remotely via SMS commands

---

**Last Updated:** 2026-01-03
