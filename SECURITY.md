# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security seriously. If you discover a vulnerability, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### Reporting Process

1. **GitHub Security Advisories** (preferred): Use [GitHub Security Advisories](../../security/advisories/new) to report vulnerabilities privately.
2. **Email**: Send details to security@agit.dev

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Fix timeline**: Depends on severity (Critical: 72h, High: 1 week, Medium: 2 weeks)

## Security Architecture

### Encryption

- **At-rest encryption**: AES-256-GCM with Argon2id key derivation
- **Key scoping**: Per-agent encryption keys for tenant isolation
- **S3 backend**: Server-side AES-256 encryption enforced on all objects

### Authentication

- **API key-based**: No hardcoded defaults, explicit configuration required
- **Role-based access control**: admin, write, read roles with permission mapping
- **Rate limiting**: Per-key sliding window (in-memory) or Redis-backed (distributed)

### Data Integrity

- **Content addressing**: SHA-256 hashing of all objects
- **Audit log chaining**: Hash-chained integrity verification
- **Deterministic serialization**: Canonical JSON for reproducible hashes

### Network Security

- **CORS**: Configurable origin allowlist
- **CSRF protection**: X-Requested-With header validation on mutations
- **Security headers**: nosniff, DENY frames, strict referrer policy, XSS protection
- **Request correlation**: UUID-based request tracing

### Known Limitations

- Pure-Python fallback encryption (stubs) uses Fernet; production deployments should use native Rust bindings with AES-256-GCM
- SQLite backend does not support row-level encryption
- No built-in TLS termination (use a reverse proxy)
