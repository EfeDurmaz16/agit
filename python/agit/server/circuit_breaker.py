"""Circuit breaker pattern for storage backend resilience."""
from __future__ import annotations

import functools
import logging
import time
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("agit.server.circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker that protects external calls from cascading failures.

    States: CLOSED → OPEN → HALF_OPEN → CLOSED
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    def record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            logger.info("Circuit breaker '%s' closed (recovered)", self.name)
        self._failure_count = 0

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker '%s' opened after %d failures",
                self.name,
                self._failure_count,
            )

    def allow_request(self) -> bool:
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
        return False


# Registry of named circuit breakers
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(name: str, **kwargs: Any) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name=name, **kwargs)
    return _breakers[name]


def circuit_breaker(name: str = "default", **kwargs: Any) -> Callable:
    """Decorator that wraps a function with circuit breaker protection."""

    def decorator(func: Callable) -> Callable:
        breaker = get_breaker(name, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kw: Any) -> Any:
            if not breaker.allow_request():
                raise RuntimeError(
                    f"Circuit breaker '{name}' is open; request rejected"
                )
            try:
                result = await func(*args, **kw)
                breaker.record_success()
                return result
            except Exception:
                breaker.record_failure()
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kw: Any) -> Any:
            if not breaker.allow_request():
                raise RuntimeError(
                    f"Circuit breaker '{name}' is open; request rejected"
                )
            try:
                result = func(*args, **kw)
                breaker.record_success()
                return result
            except Exception:
                breaker.record_failure()
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
