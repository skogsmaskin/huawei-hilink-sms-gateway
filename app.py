import os
import signal
import time
import threading
import secrets
import logging
from collections import deque
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, Callable
from urllib.parse import urlparse

import requests
from fastapi import FastAPI, HTTPException, Depends, Header, Query, Response, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

# SMS operations (using huaweisms for all operations)
import huaweisms.api.user
import huaweisms.api.sms


# -----------------------------
# Constants
# -----------------------------
# Modem API constants
SMS_BOX_TYPE_INBOX = 1
SMS_PAGE_DEFAULT = 1
SMS_QUANTITY_DEFAULT = 20
SMS_STATUS_UNREAD = "0"

# Webhook constants
WEBHOOK_TIMEOUT_SECONDS = 10
WEBHOOK_MAX_RETRIES = 3
WEBHOOK_RETRY_BASE_DELAY = 1.0

# Login retry delays (seconds)
LOGIN_RETRY_DELAYS = (0.5, 1, 2, 4)

# Memory management
SEEN_IDS_MAX_SIZE = 10000  # Maximum number of message IDs to track

# Graceful shutdown
_shutdown_event = threading.Event()


# -----------------------------
# Settings (Pydantic-based configuration)
# -----------------------------
class Settings(BaseSettings):
    """Application settings with validation."""
    modem_url: str = "http://192.168.8.1"
    modem_username: str = "admin"
    modem_password: str = ""
    poll_seconds: int = 30
    webhook_url: str = ""
    webhook_token: str = ""
    api_token: str = ""
    debug_raw_default: bool = False
    process_read_messages: bool = False
    allowed_senders: str = ""  # Comma-separated
    log_level: str = "INFO"
    # Alertmanager integration (optional)
    alertmanager_phone: str = ""  # Default phone for all alerts
    alertmanager_phone_critical: str = ""  # Phone for critical alerts (overrides default)
    alertmanager_phone_warning: str = ""  # Phone for warning alerts (overrides default)

    @field_validator("api_token")
    @classmethod
    def validate_api_token(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("API_TOKEN is required (refusing to start without auth)")
        return v.strip()

    @field_validator("poll_seconds")
    @classmethod
    def validate_poll_seconds(cls, v: int) -> int:
        if v < 0:
            raise ValueError("POLL_SECONDS must be >= 0")
        return v

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            return v
        try:
            parsed = urlparse(v)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                raise ValueError(f"Invalid WEBHOOK_URL format: {v}")
        except Exception as e:
            raise ValueError(f"Invalid WEBHOOK_URL format: {v}") from e
        return v

    @property
    def allowed_senders_list(self) -> list[str]:
        """Get allowed senders as a list."""
        return [s.strip() for s in self.allowed_senders.split(",") if s.strip()]

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
    }


settings = Settings()

# -----------------------------
# Logging
# -----------------------------
LOG_LEVEL = getattr(logging, settings.log_level.upper(), logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("sms-gateway")

# -----------------------------
# FastAPI App
# -----------------------------
# Security scheme for Swagger UI
security_scheme = HTTPBearer(
    bearerFormat="Bearer",
    description="Enter your API token (without 'Bearer' prefix)",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    
    t = threading.Thread(target=poller_loop, daemon=True, name="poller")
    t.start()
    log.info("SMS Gateway started (version 1.0)")
    
    yield
    
    # Shutdown
    log.info("Shutting down SMS Gateway...")
    _shutdown_event.set()
    # Close HTTP session
    _http_session.close()


app = FastAPI(
    title="Huawei HiLink SMS Gateway",
    version="1.0",
    description="A reliable SMS gateway using Huawei modems with HiLink firmware (tested with E3372-325), exposing a REST API and push-based webhook system for automation and monitoring integrations.",
    tags_metadata=[
        {"name": "health", "description": "Health check endpoints"},
        {"name": "sms", "description": "SMS operations (send, receive, manage)"},
    ],
    lifespan=lifespan,
)

# -----------------------------
# HTTP Session (connection pooling)
# -----------------------------
_http_session = requests.Session()
_http_session.headers.update({
    'User-Agent': 'sms-gateway/1.0',
    'Content-Type': 'application/json'
})


# -----------------------------
# Prometheus Metrics
# -----------------------------
# Prometheus Counter metrics
sms_sent_total = Counter('sms_sent_total', 'Total number of SMS messages sent')
sms_received_total = Counter('sms_received_total', 'Total number of SMS messages received', ['from_number'])
webhook_success_total = Counter('webhook_success_total', 'Total number of successful webhook deliveries')
webhook_failure_total = Counter('webhook_failure_total', 'Total number of failed webhook deliveries')
modem_errors_total = Counter('modem_errors_total', 'Total number of modem errors')
poller_iterations_total = Counter('poller_iterations_total', 'Total number of poller iterations')
alertmanager_alerts_total = Counter('alertmanager_alerts_total', 'Total number of Alertmanager alerts processed', ['severity', 'status'])


def _increment_metric(name: str, **labels) -> None:
    """Increment Prometheus metric by name."""
    if name == "sms_sent":
        sms_sent_total.inc()
    elif name == "sms_received":
        from_number = labels.get('from_number', 'unknown')
        sms_received_total.labels(from_number=from_number).inc()
    elif name == "webhook_success":
        webhook_success_total.inc()
    elif name == "webhook_failure":
        webhook_failure_total.inc()
    elif name == "modem_errors":
        modem_errors_total.inc()
    elif name == "poller_iterations":
        poller_iterations_total.inc()
    elif name == "alertmanager_alert":
        severity = labels.get('severity', 'unknown')
        status = labels.get('status', 'firing')
        alertmanager_alerts_total.labels(severity=severity, status=status).inc()


def _get_metrics_summary() -> Dict[str, int]:
    """Get metrics summary from Prometheus counters for /health endpoint."""
    # Generate Prometheus format and parse it
    # generate_latest() returns a bytes string, decode to text
    metrics_text = generate_latest().decode('utf-8')
    
    # Parse metrics from Prometheus format
    result = {
        "sms_sent": 0,
        "sms_received": 0,
        "webhook_success": 0,
        "webhook_failure": 0,
        "modem_errors": 0,
        "poller_iterations": 0,
    }
    
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
            result["sms_sent"] = value
        elif metric_name.startswith('sms_received_total'):
            result["sms_received"] += value
        elif metric_name == 'webhook_success_total':
            result["webhook_success"] = value
        elif metric_name == 'webhook_failure_total':
            result["webhook_failure"] = value
        elif metric_name == 'modem_errors_total':
            result["modem_errors"] = value
        elif metric_name == 'poller_iterations_total':
            result["poller_iterations"] = value
    
    return result


# -----------------------------
# Auth
# -----------------------------
def verify_token(credentials: HTTPAuthorizationCredentials = Security(security_scheme)) -> None:
    """Verify Bearer token authentication."""
    token = credentials.credentials
    if not secrets.compare_digest(token, settings.api_token):
        raise HTTPException(status_code=403, detail="Invalid token")


# Keep require_auth for backward compatibility (used in dependencies)
require_auth = verify_token


# -----------------------------
# Models
# -----------------------------
class SendSMSRequest(BaseModel):
    """Request model for sending SMS."""
    to: str
    message: str

    @field_validator("to")
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        """Basic phone number validation - must be non-empty and reasonable length."""
        v = v.strip()
        if not v:
            raise ValueError("Phone number cannot be empty")
        if len(v) > 20:  # Reasonable max length for international numbers
            raise ValueError("Phone number too long")
        # Allow +, digits, spaces, dashes, parentheses
        if not all(c in "+0123456789 -()" for c in v):
            raise ValueError("Phone number contains invalid characters")
        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate SMS message length (max 1600 chars for multipart SMS)."""
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        if len(v) > 1600:  # Support multipart SMS (10 parts * 160 chars)
            raise ValueError(f"Message too long: {len(v)} chars (max 1600)")
        return v


class SendSMSResponse(BaseModel):
    ok: bool
    modem_response: Optional[Dict[str, Any]] = None


# -----------------------------
# Huawei error helpers
# -----------------------------
def _is_no_rights(e: Exception) -> bool:
    msg = str(e)
    return ("100003" in msg) or ("No rights" in msg) or ("needs login" in msg)


def _is_already_login(e: Exception) -> bool:
    msg = str(e)
    return ("108003" in msg) or ("Already login" in msg)


# -----------------------------
# Global modem serialization + backoff
# -----------------------------
_modem_lock = threading.Lock()
_backoff_until = 0.0
_backoff_seconds = 0.0


def _apply_backoff_locked() -> None:
    """Apply exponential backoff delay if needed."""
    global _backoff_until
    now = time.time()
    if now < _backoff_until:
        time.sleep(_backoff_until - now)


def _increase_backoff_locked() -> None:
    """Increase exponential backoff delay."""
    global _backoff_seconds, _backoff_until
    _backoff_seconds = 1.0 if _backoff_seconds == 0 else min(_backoff_seconds * 2, 30.0)
    _backoff_until = time.time() + _backoff_seconds
    log.warning("Backoff increased: %.1fs", _backoff_seconds)
    _increment_metric("modem_errors")


def _reset_backoff_locked() -> None:
    """Reset exponential backoff delay."""
    global _backoff_seconds, _backoff_until
    _backoff_seconds = 0.0
    _backoff_until = 0.0


# -------------------------
# Modem Operations (using huaweisms for all operations)
# -------------------------
def _modem_host_from_url(url: str) -> str:
    """Extract hostname from modem URL."""
    try:
        u = urlparse(url)
        if u.hostname:
            return u.hostname
    except Exception:
        pass
    # Fallback: simple string manipulation
    url = url.replace("http://", "").replace("https://", "").strip("/")
    return url.split("/")[0].split(":")[0]


def _transaction(op: Callable[[Any], Any]) -> Any:
    with _modem_lock:
        _apply_backoff_locked()

        modem_host = _modem_host_from_url(settings.modem_url)

        def attempt():
            ctx = huaweisms.api.user.quick_login(
                settings.modem_username,
                settings.modem_password,
                modem_host=modem_host,
            )
            try:
                return op(ctx)
            finally:
                try:
                    huaweisms.api.user.logout(ctx)
                except Exception as e:
                    log.warning("Failed to logout from modem context: %s", e)

        try:
            res = attempt()
            _reset_backoff_locked()
            return res
        except Exception as e:
            if _is_no_rights(e) or _is_already_login(e):
                _increase_backoff_locked()
                _apply_backoff_locked()
                res = attempt()
                _reset_backoff_locked()
                return res
            _increase_backoff_locked()
            raise


def _normalize_huaweisms_messages(data: Dict[str, Any]) -> list[dict]:
    """Normalize huaweisms API response to list of messages."""
    # Handle edge cases: empty response, string response, or error response
    if not isinstance(data, dict):
        log.warning("Unexpected response type: %s, value: %r", type(data).__name__, data)
        return []
    
    # Check for error responses
    if data.get("type") == "error" or "error" in data:
        # Error response - return empty list (caller should handle the error)
        return []
    
    resp = data.get("response", data)
    
    # Handle case where response might be a string or other non-dict type
    if not isinstance(resp, dict):
        log.debug("Response is not a dict: %s, value: %r", type(resp).__name__, resp)
        return []
    
    messages = resp.get("Messages", {})
    if not isinstance(messages, dict):
        log.debug("Messages is not a dict: %s, value: %r", type(messages).__name__, messages)
        return []
    
    items = messages.get("Message", [])
    if isinstance(items, dict):
        return [items]
    if isinstance(items, list):
        return items
    return []


# -----------------------------
# Webhook
# -----------------------------
def _post_webhook(payload: dict) -> None:
    """Post webhook with retry logic and exponential backoff.
    
    Distinguishes between retryable (5xx, network errors) and 
    non-retryable (4xx client errors) failures.
    """
    if not settings.webhook_url:
        log.debug("WEBHOOK_URL not set; skipping webhook")
        return

    headers: Dict[str, str] = {}
    if settings.webhook_token:
        headers["Authorization"] = f"Bearer {settings.webhook_token}"

    last_exception = None
    for attempt in range(WEBHOOK_MAX_RETRIES):
        try:
            r = _http_session.post(
                settings.webhook_url,
                json=payload,
                headers=headers,
                timeout=WEBHOOK_TIMEOUT_SECONDS
            )
            
            # Don't retry on 4xx errors (client errors)
            if 400 <= r.status_code < 500:
                log.warning(
                    "Webhook returned client error %d (not retrying): %s",
                    r.status_code,
                    r.text[:500]
                )
                _increment_metric("webhook_failure")
                return
            
            # Success (2xx)
            if 200 <= r.status_code < 300:
                log.info(
                    "Webhook POST -> %s (status=%d, attempt=%d/%d)",
                    settings.webhook_url,
                    r.status_code,
                    attempt + 1,
                    WEBHOOK_MAX_RETRIES
                )
                _increment_metric("webhook_success")
                return
            
            # 5xx errors are retryable
            if attempt < WEBHOOK_MAX_RETRIES - 1:
                delay = WEBHOOK_RETRY_BASE_DELAY * (2 ** attempt)
                log.warning(
                    "Webhook returned server error %d (attempt %d/%d), retrying in %.1fs",
                    r.status_code,
                    attempt + 1,
                    WEBHOOK_MAX_RETRIES,
                    delay
                )
                time.sleep(delay)
            else:
                log.error(
                    "Webhook POST failed after %d attempts with status %d",
                    WEBHOOK_MAX_RETRIES,
                    r.status_code
                )
                _increment_metric("webhook_failure")
                return
                
        except requests.exceptions.Timeout as e:
            last_exception = e
            if attempt < WEBHOOK_MAX_RETRIES - 1:
                delay = WEBHOOK_RETRY_BASE_DELAY * (2 ** attempt)
                log.warning(
                    "Webhook POST timeout (attempt %d/%d): %s, retrying in %.1fs",
                    attempt + 1,
                    WEBHOOK_MAX_RETRIES,
                    e,
                    delay
                )
                time.sleep(delay)
            else:
                log.exception("Webhook POST timeout after %d attempts: %s", WEBHOOK_MAX_RETRIES, e)
                _increment_metric("webhook_failure")
        except requests.exceptions.RequestException as e:
            last_exception = e
            if attempt < WEBHOOK_MAX_RETRIES - 1:
                delay = WEBHOOK_RETRY_BASE_DELAY * (2 ** attempt)
                log.warning(
                    "Webhook POST failed (attempt %d/%d): %s, retrying in %.1fs",
                    attempt + 1,
                    WEBHOOK_MAX_RETRIES,
                    e,
                    delay
                )
                time.sleep(delay)
            else:
                log.exception("Webhook POST failed after %d attempts: %s", WEBHOOK_MAX_RETRIES, e)
                _increment_metric("webhook_failure")

    if last_exception:
        log.error("Webhook POST permanently failed after %d attempts", WEBHOOK_MAX_RETRIES)


# Track seen message IDs with size limit to prevent unbounded memory growth
_seen_ids: set = set()
_seen_ids_order: deque = deque(maxlen=SEEN_IDS_MAX_SIZE)


def _message_id(m: dict) -> str:
    """Extract message ID from message dict, handling various field names."""
    for key in ("Index", "Id", "SmsIndex", "index", "id"):
        value = m.get(key)
        if value is not None:
            return str(value)
    return ""


# -----------------------------
# API Endpoints
# -----------------------------
@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    description="Check service health and optionally modem/webhook connectivity",
    response_description="Health status",
)
def health(
    check_modem: bool = Query(default=False, description="Check modem connectivity"),
    check_webhook: bool = Query(default=False, description="Check webhook endpoint connectivity"),
) -> Dict[str, Any]:
    """
    Health check endpoint.

    - Returns basic health status and metrics
    - Optionally checks modem connectivity if check_modem=true
    - Optionally checks webhook endpoint if check_webhook=true
    """
    result: Dict[str, Any] = {
        "ok": True,
        "metrics": _get_metrics_summary(),
    }

    if check_modem:
        try:
            # Quick connectivity check - try to get SMS count
            def op(ctx):
                # Lightweight operation to test connectivity
                return huaweisms.api.sms.sms_count(ctx)

            _transaction(op)
            result["modem"] = {"connected": True}
        except Exception as e:
            result["ok"] = False
            result["modem"] = {"connected": False, "error": str(e)}
            log.warning("Modem health check failed: %s", e)

    if check_webhook and settings.webhook_url:
        try:
            # Quick connectivity check
            r = _http_session.get(
                settings.webhook_url,
                timeout=5,
                allow_redirects=False
            )
            result["webhook"] = {
                "url": settings.webhook_url,
                "reachable": True,
                "status_code": r.status_code,
            }
        except requests.exceptions.RequestException as e:
            result["webhook"] = {
                "url": settings.webhook_url,
                "reachable": False,
                "error": str(e),
            }
            # Don't mark overall health as failed for webhook issues
            log.debug("Webhook health check failed: %s", e)
    elif check_webhook:
        result["webhook"] = {"configured": False}

    return result


@app.get(
    "/metrics",
    tags=["health"],
    summary="Prometheus metrics",
    description="Expose Prometheus metrics in standard format",
    response_description="Prometheus metrics",
)
def metrics() -> Response:
    """
    Prometheus metrics endpoint.
    
    Exposes metrics in Prometheus format for scraping by Prometheus server.
    Metrics include:
    - sms_sent_total: Total SMS messages sent
    - sms_received_total: Total SMS messages received (labeled by sender)
    - webhook_success_total: Successful webhook deliveries
    - webhook_failure_total: Failed webhook deliveries
    - modem_errors_total: Modem communication errors
    - poller_iterations_total: Poller loop iterations
    - alertmanager_alerts_total: Alertmanager alerts processed (labeled by severity and status)
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post(
    "/sms/send",
    tags=["sms"],
    response_model=SendSMSResponse,
    dependencies=[Depends(require_auth)],
    summary="Send SMS",
    description="Send an SMS message via the modem",
    response_description="SMS send result",
)
def send_sms(req: SendSMSRequest) -> SendSMSResponse:
    """
    Send an SMS message.

    - Validates phone number and message length
    - Sends via Huawei modem API
    - Returns modem response
    """
    try:
        def op(ctx):
            return huaweisms.api.sms.send_sms(ctx, req.to, req.message)

        resp = _transaction(op)
        _increment_metric("sms_sent")

        # Normalize response into a dict for response validation
        if isinstance(resp, str):
            resp = {"result": resp}
        elif not isinstance(resp, dict):
            resp = {"result": "OK" if resp else "FAILED"}

        return SendSMSResponse(ok=True, modem_response=resp)
    except Exception as e:
        error_msg = f"Failed to send SMS to {req.to}: {str(e)}"
        log.error(error_msg)
        _increment_metric("modem_errors")
        if _is_no_rights(e):
            raise HTTPException(status_code=502, detail=f"Modem authentication error: {str(e)}")
        raise HTTPException(status_code=500, detail=error_msg)


@app.get(
    "/sms/inbox",
    tags=["sms"],
    dependencies=[Depends(require_auth)],
    summary="Get SMS inbox",
    description="Retrieve SMS messages from the modem inbox",
    response_description="List of SMS messages",
)
def inbox(
    unread_only: bool = Query(default=False, description="Filter to unread messages only"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of messages to return"),
    debug: bool = Query(default=settings.debug_raw_default, description="Include raw modem response for debugging"),
) -> Dict[str, Any]:
    """
    Human-friendly inbox.

    - Returns SMS messages from modem inbox
    - Count always reflects the returned messages list
    - debug=true includes raw modem response
    """
    try:
        def op(ctx):
            return huaweisms.api.sms.get_sms(
                ctx,
                box_type=SMS_BOX_TYPE_INBOX,
                page=SMS_PAGE_DEFAULT,
                qty=limit,
                unread_preferred=unread_only,
            )

        data = _transaction(op)
        items = _normalize_huaweisms_messages(data)

        if unread_only:
            items = [m for m in items if str(m.get("Smstat", "")) == SMS_STATUS_UNREAD]

        result: Dict[str, Any] = {"count": len(items), "messages": items}
        if debug:
            result["raw"] = data
        return result
    except Exception as e:
        error_msg = f"Failed to retrieve inbox: {str(e)}"
        log.error(error_msg)
        _increment_metric("modem_errors")
        raise HTTPException(status_code=500, detail=error_msg)


@app.post(
    "/sms/{index}/read",
    tags=["sms"],
    dependencies=[Depends(require_auth)],
    summary="Mark SMS as read",
    description="Mark a specific SMS message as read by its index",
    response_description="Mark read result",
)
def mark_read(index: str) -> Dict[str, Any]:
    """
    Mark an SMS message as read.

    - Marks the message with the given index as read
    - Returns the raw modem response
    """
    try:
        def op(ctx):
            return huaweisms.api.sms.sms_set_read(ctx, index)

        res = _transaction(op)
        return {"ok": True, "index": index, "raw": res}
    except Exception as e:
        error_msg = f"Failed to mark SMS {index} as read: {str(e)}"
        log.error(error_msg)
        _increment_metric("modem_errors")
        raise HTTPException(status_code=500, detail=error_msg)


@app.post(
    "/sms/inbox/consume",
    tags=["sms"],
    dependencies=[Depends(require_auth)],
    summary="Consume unread SMS",
    description="Pull-mode helper: returns unread messages and marks them as read",
    response_description="List of consumed unread messages",
)
def consume_unread(
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of messages to consume")
) -> Dict[str, Any]:
    """
    Pull-mode helper (not needed for Option A, but handy):

    - Returns unread messages
    - Marks returned messages as read (best effort)
    - Useful for manual consumption or testing
    """
    try:
        def op(ctx):
            data = huaweisms.api.sms.get_sms(
                ctx,
                box_type=SMS_BOX_TYPE_INBOX,
                page=SMS_PAGE_DEFAULT,
                qty=limit,
                unread_preferred=True
            )
            items = _normalize_huaweisms_messages(data)
            unread = [m for m in items if str(m.get("Smstat", "")) == SMS_STATUS_UNREAD]

            for m in unread:
                mid = _message_id(m)
                if not mid:
                    continue
                try:
                    huaweisms.api.sms.sms_set_read(ctx, mid)
                except Exception as e:
                    log.warning("Failed to mark SMS %s as read: %s", mid, e)

            return unread

        unread = _transaction(op)
        return {"count": len(unread), "messages": unread}
    except Exception as e:
        error_msg = f"Failed to consume unread messages: {str(e)}"
        log.error(error_msg)
        _increment_metric("modem_errors")
        raise HTTPException(status_code=500, detail=error_msg)


@app.delete(
    "/sms/inbox",
    tags=["sms"],
    dependencies=[Depends(require_auth)],
    summary="Truncate inbox",
    description="Delete multiple SMS messages from inbox with various filters",
    response_description="Truncate result",
)
def truncate_inbox(
    all: bool = Query(default=False, description="Delete all messages (overrides other filters)"),
    read_only: bool = Query(default=False, description="Delete only read messages"),
    unread_only: bool = Query(default=False, description="Delete only unread messages"),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum number of messages to delete (oldest first)"),
) -> Dict[str, Any]:
    """
    Truncate inbox by deleting multiple messages.

    Options:
    - `all=true`: Delete all messages (ignores other filters)
    - `read_only=true`: Delete only read messages
    - `unread_only=true`: Delete only unread messages
    - `limit=N`: Delete up to N messages (oldest first, default: 100, max: 500)

    Examples:
    - Delete all messages: `DELETE /sms/inbox?all=true`
    - Delete all read messages: `DELETE /sms/inbox?read_only=true`
    - Delete oldest 50 messages: `DELETE /sms/inbox?limit=50`
    """
    try:
        def op(ctx):
            deleted = []
            failed = []
            total_processed = 0
            total_fetched = 0
            iterations = 0
            
            if all:
                # When deleting all, delete page by page to avoid pagination issues
                # Keep fetching page 1 until no more messages (deleting shifts remaining messages to page 1)
                max_iterations = 1000  # Safety limit
                
                while iterations < max_iterations:
                    iterations += 1
                    # Always fetch page 1, as deleting messages shifts remaining ones to page 1
                    log.info("Iteration %d: fetching page 1...", iterations)
                    # Use exact same pattern as inbox endpoint when unread_only=False
                    # Start with smaller qty to avoid API errors, then increase
                    qty_to_use = min(20 if iterations == 1 else 100, 100)  # Start with 20, then 100
                    data = huaweisms.api.sms.get_sms(
                        ctx,
                        box_type=SMS_BOX_TYPE_INBOX,
                        page=SMS_PAGE_DEFAULT,
                        qty=qty_to_use,
                        unread_preferred=False  # Same as inbox when unread_only=False
                    )
                    log.debug("Raw API response keys: %r", list(data.keys()) if isinstance(data, dict) else "not a dict")
                    
                    # Check for API errors
                    if isinstance(data, dict) and (data.get("type") == "error" or "error" in data):
                        error_info = data.get("error", {})
                        error_code = error_info.get("code", "unknown") if isinstance(error_info, dict) else str(error_info)
                        error_msg = error_info.get("message", "") if isinstance(error_info, dict) else ""
                        log.error("API returned error when fetching messages: code=%s, message=%s, full_response=%r", 
                                 error_code, error_msg, data)
                        # If it's the first iteration and we get an error, this might be a real problem
                        if iterations == 1:
                            raise HTTPException(
                                status_code=500, 
                                detail=f"Failed to fetch messages from modem: code={error_code}, message={error_msg}"
                            )
                        # Otherwise, maybe the inbox is empty or there's a transient error
                        break
                    
                    items = _normalize_huaweisms_messages(data)
                    total_fetched += len(items)
                    
                    log.info("Iteration %d: fetched %d messages from page 1 (raw response type: %s)", 
                             iterations, len(items), type(data).__name__)
                    
                    if not items:
                        log.info("No more messages to delete (iteration %d)", iterations)
                        break
                    
                    # Log first message structure for debugging
                    if items and iterations == 1:
                        log.info("First message sample: keys=%r, Index=%r, Id=%r", 
                                 list(items[0].keys()), 
                                 items[0].get("Index"), 
                                 items[0].get("Id"))
                    
                    # Delete all messages from this page
                    page_deleted = 0
                    page_failed = 0
                    for m in items:
                        total_processed += 1
                        mid = _message_id(m)
                        if not mid:
                            log.warning("Skipping message without valid ID: keys=%r, Index=%r, Id=%r", 
                                       list(m.keys()), m.get("Index"), m.get("Id"))
                            failed.append({"index": None, "error": "No valid message ID found", "message_keys": list(m.keys())})
                            page_failed += 1
                            continue
                        try:
                            log.debug("Deleting SMS id=%s", mid)
                            result = huaweisms.api.sms.delete_sms(ctx, mid)
                            log.debug("Delete result for %s: %r", mid, result)
                            
                            # Check if delete was successful
                            if isinstance(result, dict):
                                error = result.get("error") or result.get("type") == "error"
                                if error:
                                    error_msg = result.get("error", {}).get("message", "Unknown error") if isinstance(result.get("error"), dict) else str(result.get("error", "Delete failed"))
                                    log.warning("Delete SMS %s returned error: %s (full response: %r)", mid, error_msg, result)
                                    failed.append({"index": mid, "error": error_msg, "response": result})
                                    page_failed += 1
                                    continue
                            
                            deleted.append(mid)
                            page_deleted += 1
                        except Exception as e:
                            log.warning("Failed to delete SMS %s: %s (exception type: %s)", mid, e, type(e).__name__, exc_info=True)
                            failed.append({"index": mid, "error": str(e), "exception_type": type(e).__name__})
                            page_failed += 1
                    
                    log.info("Iteration %d: deleted %d, failed %d (total: deleted=%d, failed=%d)", 
                             iterations, page_deleted, page_failed, len(deleted), len(failed))
                    
                    # If we deleted fewer than we fetched, we might be done or hit an issue
                    if page_deleted == 0 and page_failed == 0:
                        log.warning("No messages were processed in iteration %d (fetched %d but none had valid IDs?), stopping", 
                                   iterations, len(items))
                        break
                    
                    # If we got fewer than 100 messages, we're on the last page
                    if len(items) < 100:
                        log.info("Last page reached (got %d messages)", len(items))
                        break
            else:
                # For filtered deletes, get a single page
                data = huaweisms.api.sms.get_sms(
                    ctx,
                    box_type=SMS_BOX_TYPE_INBOX,
                    page=SMS_PAGE_DEFAULT,
                    qty=limit if not (read_only or unread_only) else 100,  # Max 100 supported by API
                    unread_preferred=False
                )
                items = _normalize_huaweisms_messages(data)
                
                # Filter messages based on criteria
                if read_only:
                    candidates = [m for m in items if str(m.get("Smstat", "")) != SMS_STATUS_UNREAD]
                elif unread_only:
                    candidates = [m for m in items if str(m.get("Smstat", "")) == SMS_STATUS_UNREAD]
                else:
                    # Default: delete oldest messages up to limit
                    candidates = items[:limit]

                log.info("Truncate inbox: found %d messages to delete (read_only=%s, unread_only=%s, limit=%d)", 
                         len(candidates), read_only, unread_only, limit)
                
                # Delete each candidate message
                for idx, m in enumerate(candidates):
                    total_processed += 1
                    mid = _message_id(m)
                    if not mid:
                        log.warning("Skipping message without valid ID: keys=%r", list(m.keys()))
                        failed.append({"index": None, "error": "No valid message ID found", "message_keys": list(m.keys())})
                        continue
                    try:
                        result = huaweisms.api.sms.delete_sms(ctx, mid)
                        # Check if delete was successful
                        if isinstance(result, dict):
                            error = result.get("error") or result.get("type") == "error"
                            if error:
                                error_msg = result.get("error", {}).get("message", "Unknown error") if isinstance(result.get("error"), dict) else str(result.get("error", "Delete failed"))
                                log.warning("Delete SMS %s returned error: %s", mid, error_msg)
                                failed.append({"index": mid, "error": error_msg, "response": result})
                                continue
                        
                        deleted.append(mid)
                    except Exception as e:
                        log.warning("Failed to delete SMS %s: %s", mid, e)
                        failed.append({"index": mid, "error": str(e)})

            log.info("Truncate inbox: deleted %d messages, failed %d (total processed: %d, total fetched: %d, iterations: %d)", 
                     len(deleted), len(failed), total_processed, total_fetched, iterations)

            return {
                "deleted": deleted,
                "failed": failed,
                "count": len(deleted),
                "failed_count": len(failed),
                "total_processed": total_processed,
                "total_fetched": total_fetched,
                "iterations": iterations
            }

        result = _transaction(op)
        return {
            "ok": True,
            "deleted_count": result["count"],
            "failed_count": result["failed_count"],
            "deleted_indices": result["deleted"],
            "failed": result["failed"],
            "debug": {
                "total_processed": result.get("total_processed", 0),
                "iterations": result.get("iterations", 0),
                "messages_fetched": result.get("messages_fetched", 0)
            } if all else {}
        }
    except Exception as e:
        error_msg = f"Failed to truncate inbox: {str(e)}"
        log.error(error_msg)
        _increment_metric("modem_errors")
        raise HTTPException(status_code=500, detail=error_msg)


@app.delete(
    "/sms/{index}",
    tags=["sms"],
    dependencies=[Depends(require_auth)],
    summary="Delete SMS message",
    description="Delete a specific SMS message by its index",
    response_description="Delete result",
)
def delete_sms(index: str) -> Dict[str, Any]:
    """
    Delete an SMS message by index.

    - Permanently deletes the message with the given index
    - Returns the raw modem response
    """
    try:
        def op(ctx):
            return huaweisms.api.sms.delete_sms(ctx, index)

        res = _transaction(op)
        return {"ok": True, "index": index, "raw": res}
    except Exception as e:
        error_msg = f"Failed to delete SMS {index}: {str(e)}"
        log.error(error_msg)
        _increment_metric("modem_errors")
        raise HTTPException(status_code=500, detail=error_msg)


# -----------------------------
# Alertmanager Webhook Integration
# -----------------------------
class AlertmanagerWebhookRequest(BaseModel):
    """Alertmanager webhook payload model."""
    version: str = "4"
    groupKey: Optional[str] = None
    status: str = "firing"  # firing or resolved
    receiver: Optional[str] = None
    groupLabels: Optional[Dict[str, str]] = None
    commonLabels: Optional[Dict[str, str]] = None
    commonAnnotations: Optional[Dict[str, str]] = None
    externalURL: Optional[str] = None
    alerts: list[Dict[str, Any]] = []


def _format_alertmanager_message(alert_data: Dict[str, Any]) -> tuple[str, str]:
    """Format Alertmanager alert into SMS message and determine phone number.
    
    Returns:
        tuple: (phone_number, message)
    """
    alerts = alert_data.get("alerts", [])
    if not alerts:
        raise ValueError("No alerts in payload")
    
    alert = alerts[0]
    status = alert_data.get("status", "firing")
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    
    alertname = labels.get("alertname", "Unknown Alert")
    severity = labels.get("severity", "unknown").lower()
    summary = annotations.get("summary", "")
    description = annotations.get("description", "")
    
    # Build message
    if status == "resolved":
        message = f"[RESOLVED] {alertname}"
    else:
        message = f"[{severity.upper()}] {alertname}"
    
    # Add summary or description (truncate to fit SMS)
    if summary:
        # SMS max length is 160 chars for single message, but we support multipart
        # Keep it concise - around 140 chars to be safe
        msg_text = f"{message}: {summary}"
        if len(msg_text) > 140:
            msg_text = f"{message}: {summary[:140-len(message)-3]}..."
        message = msg_text
    elif description:
        msg_text = f"{message}: {description}"
        if len(msg_text) > 140:
            msg_text = f"{message}: {description[:140-len(message)-3]}..."
        message = msg_text
    
    # Determine phone number based on severity
    phone = ""
    if severity == "critical" and settings.alertmanager_phone_critical:
        phone = settings.alertmanager_phone_critical
    elif severity == "warning" and settings.alertmanager_phone_warning:
        phone = settings.alertmanager_phone_warning
    elif settings.alertmanager_phone:
        phone = settings.alertmanager_phone
    else:
        raise ValueError("No phone number configured for Alertmanager alerts")
    
    return (phone.strip(), message)


@app.post(
    "/webhook/alertmanager",
    tags=["webhook"],
    summary="Alertmanager webhook",
    description="Receive alerts from Prometheus Alertmanager and send as SMS",
    response_description="Webhook processing result",
)
def alertmanager_webhook(payload: AlertmanagerWebhookRequest) -> Dict[str, Any]:
    """
    Alertmanager webhook endpoint.
    
    Receives alerts from Prometheus Alertmanager in the standard webhook format
    and sends them as SMS messages. Phone numbers can be configured per severity
    level via environment variables.
    
    Configuration:
    - ALERTMANAGER_PHONE: Default phone number for all alerts
    - ALERTMANAGER_PHONE_CRITICAL: Phone number for critical alerts (overrides default)
    - ALERTMANAGER_PHONE_WARNING: Phone number for warning alerts (overrides default)
    
    Example Alertmanager configuration:
    ```yaml
    receivers:
      - name: 'sms-critical'
        webhook_configs:
          - url: 'http://sms-gateway:8080/webhook/alertmanager'
            http_config:
              bearer_token: 'YOUR_API_TOKEN'
    ```
    """
    try:
        # Convert Pydantic model to dict for processing
        alert_data = payload.model_dump()
        
        # Format alert and get phone number
        phone, message = _format_alertmanager_message(alert_data)
        
        # Send SMS using huaweisms
        def op(ctx):
            return huaweisms.api.sms.send_sms(ctx, phone, message)
        
        resp = _transaction(op)
        _increment_metric("sms_sent")
        _increment_metric("webhook_success")
        
        # Track Alertmanager alert
        alerts = alert_data.get("alerts", [])
        if alerts:
            severity = alerts[0].get("labels", {}).get("severity", "unknown")
            status = alert_data.get("status", "firing")
            _increment_metric("alertmanager_alert", severity=severity, status=status)
        
        # Normalize response
        if isinstance(resp, str):
            resp = {"result": resp}
        
        log.info(
            "Alertmanager webhook processed: status=%s severity=%s phone=%s",
            alert_data.get("status"),
            alerts[0].get("labels", {}).get("severity", "unknown") if alerts else "unknown",
            phone
        )
        
        return {
            "ok": True,
            "phone": phone,
            "message": message,
            "modem_response": resp,
        }
    except ValueError as e:
        error_msg = f"Invalid Alertmanager webhook payload: {str(e)}"
        log.error(error_msg)
        _increment_metric("webhook_failure")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Failed to process Alertmanager webhook: {str(e)}"
        log.error(error_msg)
        _increment_metric("webhook_failure")
        _increment_metric("modem_errors")
        if _is_no_rights(e):
            raise HTTPException(status_code=502, detail=f"Modem authentication error: {str(e)}")
        raise HTTPException(status_code=500, detail=error_msg)


# -----------------------------
# Poller (Option A: push/webhook)
# -----------------------------
def poller_loop():
    log.info(
        "Poller started (POLL_SECONDS=%s, webhook=%s, process_read=%s, allowed_senders=%s)",
        settings.poll_seconds,
        bool(settings.webhook_url),
        settings.process_read_messages,
        settings.allowed_senders_list or "any"
    )

    while not _shutdown_event.is_set():
        if settings.poll_seconds <= 0:
            _shutdown_event.wait(60)
            continue

        try:
            _increment_metric("poller_iterations")
            
            def op(ctx):
                data = huaweisms.api.sms.get_sms(
                    ctx,
                    box_type=SMS_BOX_TYPE_INBOX,
                    page=SMS_PAGE_DEFAULT,
                    qty=SMS_QUANTITY_DEFAULT,
                    unread_preferred=True
                )
                items = _normalize_huaweisms_messages(data)

                # Normal mode: process only unread
                if settings.process_read_messages:
                    candidates = items
                else:
                    candidates = [m for m in items if str(m.get("Smstat", "")) == SMS_STATUS_UNREAD]

                log.debug(
                    "Poll: fetched=%d candidates=%d process_read=%s",
                    len(items),
                    len(candidates),
                    settings.process_read_messages
                )

                for m in candidates:
                    mid = _message_id(m)
                    sender = str(m.get("Phone") or "")
                    text = str(m.get("Content") or "")
                    smstat = str(m.get("Smstat") or "")

                    allowed_senders = settings.allowed_senders_list
                    if allowed_senders and sender not in allowed_senders:
                        log.info("Skipping SMS id=%s from=%s (not in allowlist)", mid, sender)
                        continue

                    if not mid:
                        log.debug("Skipping SMS with no Index/Id: %r", m)
                        continue

                    if mid in _seen_ids:
                        log.debug("Skipping already-seen SMS id=%s", mid)
                        continue

                    # Add to tracking with size limit
                    if len(_seen_ids) >= SEEN_IDS_MAX_SIZE:
                        # Remove oldest entry
                        oldest = _seen_ids_order.popleft()
                        _seen_ids.discard(oldest)

                    _seen_ids.add(mid)
                    _seen_ids_order.append(mid)
                    log.info("Processing SMS id=%s from=%s smstat=%s content=%r", mid, sender, smstat, text)
                    _increment_metric("sms_received", from_number=sender)

                    _post_webhook({
                        "event": "sms.received",
                        "id": mid,
                        "from": sender,
                        "message": text,
                        "timestamp": m.get("Date"),
                        "raw": m,
                    })

                    # Mark as read so we don't re-notify (best effort)
                    try:
                        huaweisms.api.sms.sms_set_read(ctx, mid)
                        log.debug("Marked read id=%s", mid)
                    except Exception as e:
                        log.warning("Failed to mark read id=%s: %s", mid, e)

                return True

            _transaction(op)

        except Exception:
            log.exception("Poller iteration failed")
            _increment_metric("modem_errors")

        # Wait with shutdown awareness
        if _shutdown_event.wait(settings.poll_seconds):
            break  # Shutdown requested


def _signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    log.info("Received signal %d, initiating graceful shutdown...", signum)
    _shutdown_event.set()