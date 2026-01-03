FROM python:3.12-slim as builder

WORKDIR /app

RUN pip install --no-cache-dir \
  fastapi uvicorn[standard] pydantic pydantic-settings requests prometheus-client \
  huawei-modem-api-client

FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder (installed globally, so copy from site-packages)
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create non-root user
RUN useradd -m -u 1000 smsgateway && \
    chown -R smsgateway:smsgateway /app

COPY app.py /app/app.py

USER smsgateway

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=5)" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
