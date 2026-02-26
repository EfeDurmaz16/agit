"""Middleware for rate limiting."""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("agit.server.middleware")

# Maximum number of distinct API keys tracked (LRU eviction after this)
_MAX_TRACKED_KEYS = 10_000


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory sliding-window rate limiter with LRU eviction.

    Limits requests per API key to max_requests per window_seconds.
    Evicts least-recently-used keys when tracking more than _MAX_TRACKED_KEYS.
    """

    def __init__(self, app: Any, max_requests: int = 100, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: OrderedDict[str, list[float]] = OrderedDict()

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Skip rate limiting for health checks
        if request.url.path == "/api/v1/health":
            return await call_next(request)

        api_key = request.headers.get("x-api-key", "anonymous")
        now = time.monotonic()

        # LRU eviction: remove oldest keys if we're tracking too many
        while len(self._requests) >= _MAX_TRACKED_KEYS:
            self._requests.popitem(last=False)

        # Clean old entries and move key to end (most recently used)
        cutoff = now - self.window_seconds
        if api_key in self._requests:
            self._requests[api_key] = [
                t for t in self._requests[api_key] if t > cutoff
            ]
            self._requests.move_to_end(api_key)
        else:
            self._requests[api_key] = []

        if len(self._requests[api_key]) >= self.max_requests:
            logger.warning("Rate limit exceeded for key prefix: %s...", api_key[:8] if len(api_key) > 8 else "***")
            return Response(
                content='{"ok": false, "error": "Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(self.window_seconds)},
            )

        self._requests[api_key].append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(
            self.max_requests - len(self._requests[api_key])
        )
        return response


class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed fixed-window rate limiter for multi-replica deployments."""

    def __init__(
        self,
        app: Any,
        redis_url: str,
        max_requests: int = 100,
        window_seconds: int = 60,
        key_prefix: str = "agit:rate",
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix
        self._redis = self._build_client(redis_url)

    def _build_client(self, redis_url: str) -> Any:
        try:
            import redis.asyncio as redis_async  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "Redis middleware requires 'redis' package. Install with: pip install redis"
            ) from exc
        return redis_async.from_url(redis_url, decode_responses=True)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.url.path == "/api/v1/health":
            return await call_next(request)

        api_key = request.headers.get("x-api-key", "anonymous")
        now = int(time.time())
        bucket = now // self.window_seconds
        key = f"{self.key_prefix}:{api_key}:{bucket}"
        retry_after = self.window_seconds - (now % self.window_seconds)

        try:
            count = int(await self._redis.incr(key))
            if count == 1:
                await self._redis.expire(key, self.window_seconds + 1)
        except Exception:
            logger.warning("Redis rate limiter unavailable; allowing request", exc_info=True)
            return await call_next(request)

        if count > self.max_requests:
            logger.warning(
                "Redis rate limit exceeded for key prefix: %s...",
                api_key[:8] if len(api_key) > 8 else "***",
            )
            return Response(
                content='{"ok": false, "error": "Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.max_requests - count))
        return response
