# Development Guide

This guide covers development setup, testing, and contribution guidelines for the SMS Gateway project.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Setup](#local-setup)
3. [Testing](#testing)
4. [Code Structure](#code-structure)
5. [Development Workflow](#development-workflow)
6. [Debugging](#debugging)
7. [Testing Without a Modem](#testing-without-a-modem)
8. [API Testing](#api-testing)
9. [Environment Variables](#environment-variables)
10. [Building Docker Image](#building-docker-image)
11. [Code Style](#code-style)
12. [Contributing](#contributing)
13. [Troubleshooting Development Issues](#troubleshooting-development-issues)

---

## Prerequisites

- Python 3.12 or higher
- pip (Python package manager)
- Access to a Huawei modem with HiLink firmware (for full testing) or mock for unit tests

---

## Local Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/skogsmaskin/huawei-hilink-sms-gateway
   cd sms-gateway
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   
   This installs all required packages including:
   - Runtime dependencies (FastAPI, uvicorn, etc.)
   - `httpx` - Required for FastAPI's TestClient used in tests
   - `pytest` and `pytest-cov` - For running and testing with coverage

5. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

6. **Run the application:**
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8080 --reload
   ```

   The `--reload` flag enables auto-reload on code changes during development.

---

## Testing

The project includes comprehensive test suites using pytest.

### Running Tests

**Run all tests:**
```bash
pytest
```

**Run with verbose output:**
```bash
pytest -v
```

**Run specific test file:**
```bash
pytest tests/test_api.py
pytest tests/test_metrics.py
pytest tests/test_webhook.py
```

**Run specific test:**
```bash
pytest tests/test_api.py::test_health_basic
```

**Run with coverage report:**
```bash
pytest --cov=app --cov-report=html
# Open htmlcov/index.html in your browser to view coverage
```

### Test Structure

- `tests/test_api.py` - API endpoint tests (authentication, validation, endpoints)
- `tests/test_webhook.py` - Webhook functionality tests (retry logic, error handling)
- `tests/test_metrics.py` - Prometheus metrics tests (endpoints, metric tracking)

### Writing Tests

When adding new features, write corresponding tests:

```python
# Example test structure
def test_new_feature():
    """Test description."""
    # Arrange
    # Act
    # Assert
```

**Best practices:**
- Test both success and failure cases
- Use mocking for external dependencies (modem, webhooks)
- Test edge cases and error conditions
- Keep tests isolated and independent

### Mocking the Modem

For testing without a physical modem, mock the modem API calls:

```python
from unittest.mock import patch, MagicMock

@patch('app._transaction')
def test_send_sms(mock_transaction):
    mock_transaction.return_value = {"result": "OK"}
    # Your test code here
```

---

## Code Structure

```
sms-gateway/
├── app.py                 # Main application file
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker build configuration
├── docker-compose.yml    # Docker Compose configuration
├── tests/               # Test suite
│   ├── __init__.py
│   ├── test_api.py      # API endpoint tests
│   ├── test_webhook.py  # Webhook tests
│   └── test_metrics.py  # Metrics tests
├── .env.example         # Example environment variables
├── pytest.ini          # Pytest configuration
└── README.md           # Main documentation
```

**Key components in `app.py`:**
- **Settings** - Pydantic-based configuration management
- **Metrics** - Prometheus metrics definitions
- **Auth** - Bearer token authentication
- **Models** - Pydantic request/response models
- **Modem Operations** - SMS send/receive operations
- **Webhook** - Webhook delivery with retry logic
- **API Endpoints** - FastAPI route handlers
- **Poller** - Background SMS polling loop

---

## Development Workflow

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes:**
   - Write code following existing patterns
   - Add tests for new functionality
   - Update documentation if needed

3. **Run tests:**
   ```bash
   pytest
   ```

4. **Check code quality:**
   ```bash
   # Install linting tools (optional)
   pip install flake8 black mypy
   
   # Format code
   black app.py tests/
   
   # Check linting
   flake8 app.py tests/
   ```

5. **Test locally:**
   ```bash
   # Run the application
   uvicorn app:app --reload
   
   # Test endpoints
   curl http://localhost:8080/health
   curl http://localhost:8080/metrics
   ```

6. **Commit and push:**
   ```bash
   git add .
   git commit -m "Add feature: description"
   git push origin feature/your-feature-name
   ```

---

## Debugging

### Enable Debug Logging

Set `LOG_LEVEL=DEBUG` in your `.env` file or environment:
```bash
export LOG_LEVEL=DEBUG
uvicorn app:app --reload
```

### View Logs

**Local development:**
```bash
# Logs appear in terminal when running uvicorn
```

**Docker:**
```bash
docker logs sms-gateway
docker logs -f sms-gateway  # Follow logs
```

### Common Debugging Scenarios

**Modem not responding:**
- Check `MODEM_URL` is accessible: `curl http://192.168.8.1`
- Verify credentials in logs (be careful with sensitive data)
- Test modem connectivity: `curl http://localhost:8080/health?check_modem=true`

**Webhook not working:**
- Check webhook URL is correct
- Test webhook endpoint directly: `curl -X POST http://webhook-url`
- Review webhook retry logs
- Enable debug logging to see detailed webhook attempts

**Metrics not updating:**
- Check `/metrics` endpoint: `curl http://localhost:8080/metrics`
- Verify metrics are being incremented in code
- Check Prometheus can scrape: `curl http://localhost:8080/metrics`

---

## Testing Without a Modem

For development and testing without physical hardware:

1. **Mock modem operations:**
   ```python
   from unittest.mock import patch
   
   @patch('app._transaction')
   def test_without_modem(mock_transaction):
       mock_transaction.return_value = {"result": "OK"}
       # Your test code
   ```

2. **Use test configuration:**
   - Set `POLL_SECONDS=0` to disable polling
   - Mock webhook endpoints for testing
   - Use test phone numbers

---

## API Testing

**Using curl:**
```bash
# Health check
curl http://localhost:8080/health

# Metrics
curl http://localhost:8080/metrics

# Send SMS (requires auth)
curl -X POST http://localhost:8080/sms/send \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to": "+1234567890", "message": "Test"}'

# Get inbox (requires auth)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8080/sms/inbox
```

**Using the interactive API docs:**
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

---

## Environment Variables

See `.env.example` for all available configuration options. Key variables for development:

```bash
# Required
API_TOKEN=dev-token-123  # Use a test token for development

# Modem (use test values or mock)
MODEM_URL=http://192.168.8.1
MODEM_USERNAME=admin
MODEM_PASSWORD=test-password

# Development settings
LOG_LEVEL=DEBUG  # Enable debug logging
POLL_SECONDS=0   # Disable polling during development
DEBUG_RAW_DEFAULT=1  # Include raw responses in API
```

---

## Building Docker Image

**Build locally:**
```bash
docker build -t sms-gateway .
```

**Test Docker image:**
```bash
docker run -p 8080:8080 \
  -e API_TOKEN=test-token \
  -e MODEM_URL=http://192.168.8.1 \
  sms-gateway
```

**Build and test with docker-compose:**
```bash
docker-compose build
docker-compose up
```

---

## Code Style

The project follows Python best practices:
- Use type hints where possible
- Follow PEP 8 style guide
- Use descriptive variable and function names
- Add docstrings to functions and classes
- Keep functions focused and small

**Recommended tools:**
- `black` - Code formatter
- `flake8` - Linting
- `mypy` - Type checking (optional)

---

## Contributing

When contributing:
1. Write tests for new features
2. Ensure all tests pass: `pytest`
3. Update documentation if needed
4. Follow existing code patterns
5. Add clear commit messages

---

## Troubleshooting Development Issues

**Import errors:**
- Ensure virtual environment is activated
- Reinstall dependencies: `pip install -r requirements.txt`

**Tests failing:**
- Check test output for specific errors
- Verify environment variables are set correctly
- Ensure mocks are configured properly

**Application won't start:**
- Check required environment variables are set
- Verify Python version: `python --version` (should be 3.12+)
- Check for port conflicts: `lsof -i :8080`

---

**See also:**
- [README.md](README.md) - Main project documentation
- [HOME_ASSISTANT_INTEGRATION.md](HOME_ASSISTANT_INTEGRATION.md) - Home Assistant integration guide
- [PROMETHEUS_ALERTMANAGER_INTEGRATION.md](PROMETHEUS_ALERTMANAGER_INTEGRATION.md) - Prometheus Alertmanager integration guide
