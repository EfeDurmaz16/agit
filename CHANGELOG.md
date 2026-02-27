# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- SQLite WAL mode and performance pragmas for improved concurrent access
- PostgreSQL connection pooling via deadpool-postgres (max 16 connections)
- GC `keep_last_n` parameter for preserving recent commits per branch
- Merge base depth limit (10,000) to prevent unbounded traversal
- S3 SQS integration for real-time log streaming
- Shared Tokio runtime for Python bindings (reduced overhead)
- Three-way merge implementation in TypeScript fallback
- Fernet encryption replacing XOR in Python stubs
- CSRF protection middleware for mutation endpoints
- Request correlation ID middleware (X-Request-ID)
- Secrets scanning (TruffleHog) in CI pipeline
- Container image scanning (Trivy) in CI pipeline
- Cosign signing and SBOM generation in release pipeline
- Role-based access control (admin/write/read)
- Tracing instrumentation for Rust core (optional `observability` feature)
- Structured JSON logging for Python server
- Health check indicator in web dashboard
- Storage backend migration tooling
- Retention policy support for automatic cleanup
- Circuit breaker pattern for storage resilience
- LangGraph, CrewAI, Vercel AI, OpenClaw, Google ADK integration examples
- TypeScript integrations: Claude SDK, OpenAI Agents, LangGraph
- SECURITY.md, ARCHITECTURE.md, DEPLOYMENT.md, CONTRIBUTING.md
- Content Security Policy headers for web dashboard

### Changed
- Python dependencies now have version upper bounds
- Docker Compose uses environment variable interpolation for secrets

### Security
- Replaced XOR encryption with Fernet (PBKDF2 + AES-128-CBC + HMAC-SHA256)
- Added CSRF validation on POST/PUT/DELETE endpoints
- Hardcoded Docker passwords moved to .env files
- Dependency version pinning to prevent supply chain attacks

## [0.1.0] - 2024-12-01

### Added
- Initial release
- Rust core VCS engine with content-addressed storage
- SQLite, PostgreSQL, and S3 storage backends
- Python SDK with PyO3 native bindings and pure-Python fallback
- TypeScript SDK with NAPI native bindings and pure-TS fallback
- REST API server with FastAPI
- Web dashboard with Next.js
- Field-level encryption (AES-256-GCM + Argon2id)
- Merkle tree-based O(log N) state diffing
- Three-way merge with conflict detection
- Garbage collection and commit squashing
- Hash-chained audit logging
- Multi-tenant isolation
- Rate limiting (in-memory and Redis-backed)
- VS Code extension
- Docker Compose deployment
- CI/CD pipelines
