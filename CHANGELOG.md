# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security

## [1.0] - 2026-01-04

### Added
- **Core SMS Operations**
  - Send SMS messages via REST API with validation
  - Receive SMS with automatic polling and webhook delivery (push-based model)
  - Inbox management: view, mark as read, and delete SMS messages
  - Bulk operations: delete multiple messages with flexible filtering (all, read-only, unread-only, or by limit)
  
- **Integration & Automation**
  - Webhook delivery for push-based SMS notifications to external systems
  - Prometheus Alertmanager integration with built-in webhook endpoint
  - Prometheus metrics endpoint (`/metrics`) for monitoring SMS counts, webhook success/failure, and errors
  - SMS command parsing support for automation workflows
  
- **Security & Reliability**
  - Bearer token authentication for secure API access
  - Sender allow-list to restrict SMS processing to trusted phone numbers
  - Message deduplication via tracking and mark-as-read to prevent duplicate processing
  - Robust message handling that works even when messages arrive pre-marked as "read"
  - Webhook retry logic with exponential backoff for failed deliveries
  - Comprehensive error handling with differentiated retry logic (4xx vs 5xx errors)
  
- **Technical Features**
  - Thread-safe modem operations to avoid Huawei login conflicts
  - Interactive API documentation (Swagger UI and ReDoc)
  - Docker and Docker Compose support
  - Health check endpoint with optional modem/webhook connectivity checks
  - Configurable polling interval (can be disabled for pull-mode usage)
  
- **Development & Testing**
  - Comprehensive test suite with pytest
  - GitHub Actions workflows for automated testing
  - Automated Docker image builds and releases
  - CHANGELOG and release documentation

### Changed
- Migrated from deprecated `@app.on_event` to modern `lifespan` context manager
- Updated FastAPI event handlers to use async context manager pattern

### Fixed
- Fixed deprecation warnings in FastAPI startup/shutdown handlers

[Unreleased]: https://github.com/skogsmaskin/huawei-hilink-sms-gateway/compare/v1.0...HEAD
[1.0]: https://github.com/skogsmaskin/huawei-hilink-sms-gateway/releases/tag/v1.0
