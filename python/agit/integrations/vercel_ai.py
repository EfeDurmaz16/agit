"""Vercel AI SDK Python-side middleware wrapper."""
from __future__ import annotations

import logging
import time
from typing import Any, AsyncGenerator, Callable, Generator

logger = logging.getLogger("agit.integrations.vercel_ai")

from agit.engine.executor import ExecutionEngine


class AgitVercelMiddleware:
    """Middleware adapter for Vercel AI SDK usage from Python.

    The Vercel AI SDK is primarily JavaScript/TypeScript, but Python services
    can call it via HTTP or use the Python ``ai`` package when available.
    This middleware wraps streaming generation calls with agit commits.

    Usage::

        engine = ExecutionEngine("./repo", agent_id="vercel-agent")
        mw = AgitVercelMiddleware(engine)

        # Wrap any callable that returns text/stream
        result = mw.wrap_generate(my_generate_fn, prompt="Hello", state={"memory": {}})
    """

    def __init__(self, engine: ExecutionEngine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # Synchronous wrapping
    # ------------------------------------------------------------------

    def wrap_generate(
        self,
        generate_fn: Callable[..., Any],
        *args: Any,
        state: dict[str, Any] | None = None,
        message: str = "vercel-ai generate",
        **kwargs: Any,
    ) -> Any:
        """Wrap a synchronous generate call with pre/post commits."""
        current_state = state or self._engine.get_current_state() or {}
        self._engine.commit_state(current_state, f"pre: {message}", "checkpoint")

        start = time.monotonic()
        try:
            result = generate_fn(*args, **kwargs)
        except Exception as exc:
            self._engine.commit_state(current_state, f"error: {message}: {exc}", "rollback")
            raise
        elapsed = time.monotonic() - start

        # Try to serialise result into state
        new_state = self._result_to_state(current_state, result, message)
        self._engine.commit_state(
            new_state,
            f"{message} (elapsed={elapsed:.3f}s)",
            "llm_response",
        )
        return result

    def wrap_stream(
        self,
        stream_fn: Callable[..., Generator[str, None, None]],
        *args: Any,
        state: dict[str, Any] | None = None,
        message: str = "vercel-ai stream",
        **kwargs: Any,
    ) -> Generator[str, None, None]:
        """Wrap a synchronous streaming call, committing the full accumulated text."""
        current_state = state or self._engine.get_current_state() or {}
        self._engine.commit_state(current_state, f"pre: {message}", "checkpoint")

        start = time.monotonic()
        chunks: list[str] = []
        try:
            for chunk in stream_fn(*args, **kwargs):
                chunks.append(str(chunk))
                yield chunk
        except Exception as exc:
            self._engine.commit_state(current_state, f"error: {message}: {exc}", "rollback")
            raise
        elapsed = time.monotonic() - start

        full_text = "".join(chunks)
        memory = dict(current_state.get("memory", current_state))
        memory["_last_stream_output"] = full_text
        new_state = {**current_state, "memory": memory}
        self._engine.commit_state(
            new_state,
            f"{message} streamed {len(full_text)} chars (elapsed={elapsed:.3f}s)",
            "llm_response",
        )

    async def wrap_generate_async(
        self,
        generate_fn: Callable[..., Any],
        *args: Any,
        state: dict[str, Any] | None = None,
        message: str = "vercel-ai generate",
        **kwargs: Any,
    ) -> Any:
        """Async variant of :meth:`wrap_generate`."""
        import asyncio

        current_state = state or self._engine.get_current_state() or {}
        self._engine.commit_state(current_state, f"pre: {message}", "checkpoint")

        start = time.monotonic()
        try:
            if asyncio.iscoroutinefunction(generate_fn):
                result = await generate_fn(*args, **kwargs)
            else:
                result = generate_fn(*args, **kwargs)
        except Exception as exc:
            self._engine.commit_state(current_state, f"error: {message}: {exc}", "rollback")
            raise
        elapsed = time.monotonic() - start

        new_state = self._result_to_state(current_state, result, message)
        self._engine.commit_state(
            new_state,
            f"{message} (elapsed={elapsed:.3f}s)",
            "llm_response",
        )
        return result

    async def wrap_stream_async(
        self,
        stream_fn: Callable[..., AsyncGenerator[str, None]],
        *args: Any,
        state: dict[str, Any] | None = None,
        message: str = "vercel-ai stream",
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """Async streaming variant."""
        current_state = state or self._engine.get_current_state() or {}
        self._engine.commit_state(current_state, f"pre: {message}", "checkpoint")

        start = time.monotonic()
        chunks: list[str] = []
        try:
            async for chunk in stream_fn(*args, **kwargs):
                chunks.append(str(chunk))
                yield chunk
        except Exception as exc:
            self._engine.commit_state(current_state, f"error: {message}: {exc}", "rollback")
            raise
        elapsed = time.monotonic() - start

        full_text = "".join(chunks)
        memory = dict(current_state.get("memory", current_state))
        memory["_last_stream_output"] = full_text
        new_state = {**current_state, "memory": memory}
        self._engine.commit_state(
            new_state,
            f"{message} streamed {len(full_text)} chars (elapsed={elapsed:.3f}s)",
            "llm_response",
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _result_to_state(base_state: dict[str, Any], result: Any, label: str) -> dict[str, Any]:
        memory = dict(base_state.get("memory", base_state))
        if isinstance(result, dict):
            memory.update(result)
        elif isinstance(result, str):
            memory[f"_last_{label.replace(' ', '_')}_output"] = result
        else:
            try:
                import json
                memory["_last_output"] = json.dumps(result, default=str)
            except Exception:
                memory["_last_output"] = str(result)
        return {**base_state, "memory": memory}
