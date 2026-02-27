# Deployment Guide

## Quick Start (Docker Compose)

```bash
# Copy environment template
cp docker/.env.example docker/.env
# Edit docker/.env with your values

# Start all services
docker compose -f docker/docker-compose.yml up -d
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGIT_API_KEYS` | (none) | JSON map of API keys to metadata |
| `AGIT_CORS_ORIGINS` | `http://localhost:3000,http://localhost:8000` | Comma-separated CORS origins |
| `AGIT_REDIS_URL` | (none) | Redis URL for distributed rate limiting |
| `AGIT_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `AGIT_ENGINE_CACHE` | (none) | Enable engine caching |
| `AGIT_ALLOW_STUBS` | (none) | Allow pure-Python/TS fallback (dev only) |
| `POSTGRES_PASSWORD` | (none) | PostgreSQL password |
| `POSTGRES_USER` | `agit` | PostgreSQL user |
| `POSTGRES_DB` | `agit` | PostgreSQL database |

## Production Deployment Checklist

- [ ] Set strong `AGIT_API_KEYS` with role assignments
- [ ] Configure `AGIT_CORS_ORIGINS` to your domain
- [ ] Set up PostgreSQL with connection pooling
- [ ] Configure TLS termination (nginx/caddy reverse proxy)
- [ ] Set `AGIT_LOG_LEVEL=WARNING` for production
- [ ] Enable Redis rate limiting for multi-replica deployments
- [ ] Set up monitoring (Prometheus + Grafana)
- [ ] Configure backup schedules

## SSL/TLS Configuration

agit does not terminate TLS directly. Use a reverse proxy:

```nginx
server {
    listen 443 ssl;
    server_name agit.example.com;
    ssl_certificate /etc/ssl/certs/agit.pem;
    ssl_certificate_key /etc/ssl/private/agit.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## PostgreSQL Production Setup

```sql
CREATE USER agit WITH PASSWORD 'your-secure-password';
CREATE DATABASE agit OWNER agit;
GRANT ALL PRIVILEGES ON DATABASE agit TO agit;
```

Connection string: `host=localhost user=agit password=... dbname=agit`

## S3 Backend Configuration

```bash
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
```

Enable cross-region replication for disaster recovery.

## Backup & Disaster Recovery

### SQLite

```bash
# Scheduled backup (safe with WAL mode — no downtime required)
sqlite3 /path/to/agit.db ".backup /backups/agit-$(date +%Y%m%d).db"

# Cron job example: daily backup at 2 AM
# 0 2 * * * sqlite3 /data/agit.db ".backup /backups/agit-$(date +\%Y\%m\%d).db"

# Verify backup integrity
sqlite3 /backups/agit-*.db "PRAGMA integrity_check;"

# Retention: keep 30 days of backups
find /backups -name "agit-*.db" -mtime +30 -delete
```

### PostgreSQL

```bash
# Daily backup with compression
pg_dump -U agit -Fc agit > /backups/agit-$(date +%Y%m%d).dump

# Cron job: daily at 2 AM with 30-day retention
# 0 2 * * * pg_dump -U agit -Fc agit > /backups/agit-$(date +\%Y\%m\%d).dump
# 0 3 * * * find /backups -name "agit-*.dump" -mtime +30 -delete

# Point-in-time recovery: enable WAL archiving in postgresql.conf
# wal_level = replica
# archive_mode = on
# archive_command = 'cp %p /wal_archive/%f'

# Restore from backup
pg_restore -U agit -d agit /backups/agit-20240101.dump
```

### S3

- **Versioning**: Enable bucket versioning for object-level point-in-time recovery
- **Cross-region replication**: Configure CRR for disaster recovery
  ```bash
  aws s3api put-bucket-versioning --bucket agit-prod --versioning-configuration Status=Enabled
  ```
- **Lifecycle policies**: Move old objects to Glacier after 90 days
- **Backup verification**: Periodically list and spot-check objects

### Recovery Objectives

| Scenario | RTO | RPO | Strategy |
|----------|-----|-----|----------|
| SQLite corruption | < 30 min | < 24 hours | Restore from daily backup |
| PostgreSQL failure | < 1 hour | < 5 minutes | WAL archiving + streaming replica |
| S3 bucket deletion | < 2 hours | < 1 minute | Cross-region replication |
| Full datacenter loss | < 4 hours | < 1 hour | Cross-region S3 + PG replica |

### Migration Between Backends

Use the built-in migration tool to move data between storage backends:

```bash
# SQLite to PostgreSQL
agit migrate --from sqlite --to postgres

# Migration is idempotent — safe to re-run
```

## Monitoring Setup

### Prometheus Metrics
The observability feature exposes tracing spans compatible with OpenTelemetry collectors.

### Grafana Dashboard
Import the provided dashboard template for:
- Commit throughput (commits/second)
- Storage backend latency (p50/p95/p99)
- API request rate and error rate
- Active connections and pool utilization

## Scaling Guidelines

| Backend | Throughput | Latency (p99) | Notes |
|---------|-----------|---------------|-------|
| SQLite | ~1,000 RPS | < 5ms | Single-writer, concurrent readers |
| PostgreSQL | ~5,000 QPS | < 10ms | With connection pool (16 conns) |
| S3 | ~500 RPS | < 100ms | Network-bound, use with caching |
