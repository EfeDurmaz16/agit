"""FastAPI application for agit REST API."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .middleware import RateLimitMiddleware
from .routes import router

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

# Rate limiting
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
