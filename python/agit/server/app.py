"""FastAPI application for agit REST API."""
from __future__ import annotations

import logging
import os
import json as _json

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .middleware import RateLimitMiddleware, RedisRateLimitMiddleware, CSRFMiddleware, CorrelationIdMiddleware
from .routes import router

# Structured JSON logging
_log_level = os.environ.get("AGIT_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, _log_level, logging.INFO))

class _JsonFormatter(logging.Formatter):
    """Simple JSON log formatter for structured logging."""
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "correlation_id"):
            log_obj["correlation_id"] = record.correlation_id
        if record.exc_info and record.exc_info[0]:
            log_obj["exception"] = self.formatException(record.exc_info)
        return _json.dumps(log_obj)

# Apply JSON formatter to root logger
for _handler in logging.root.handlers:
    _handler.setFormatter(_JsonFormatter())

logger = logging.getLogger("agit.server")

app = FastAPI(
    title="agit API",
    description="REST API for AgentGit - Git-like version control for AI agents",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS -- configurable via AGIT_CORS_ORIGINS env var (comma-separated).
# Defaults to localhost origins for development.
_cors_origins = os.environ.get(
    "AGIT_CORS_ORIGINS",
    "http://localhost:3000,http://localhost:8000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# CSRF protection for mutation endpoints
app.add_middleware(CSRFMiddleware)

# Request correlation ID for tracing
app.add_middleware(CorrelationIdMiddleware)

# Rate limiting (distributed if Redis is configured)
_redis_url = os.environ.get("AGIT_REDIS_URL", "").strip()
if _redis_url:
    try:
        app.add_middleware(
            RedisRateLimitMiddleware,
            redis_url=_redis_url,
            max_requests=100,
            window_seconds=60,
        )
        logger.info("Enabled Redis rate limiting via AGIT_REDIS_URL")
    except RuntimeError:
        logger.warning("Redis rate limiting unavailable; falling back to in-memory limiter", exc_info=True)
        app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)
else:
    app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)


# Security headers middleware
@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Routes
app.include_router(router)


@app.get("/")
async def root():
    return {
        "name": "agit API",
        "version": "0.1.0",
        "docs": "/docs",
    }
