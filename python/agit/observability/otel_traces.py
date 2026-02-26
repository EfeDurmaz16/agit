"""OpenTelemetry tracing for agit – span per action with rich attributes."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Generator, Optional

try:
    from opentelemetry import trace  # type: ignore[import]
    from opentelemetry.trace import Span, Tracer, StatusCode  # type: ignore[import]
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator  # type: ignore[import]

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False

    # Stubs so the module is importable without opentelemetry
    StatusCode = type("StatusCode", (), {"OK": "OK", "ERROR": "ERROR"})  # type: ignore[assignment,misc]

    class Span:  # type: ignore[no-redef]
        def set_attribute(self, key: str, value: Any) -> None: ...
        def set_status(self, status: Any, description: str = "") -> None: ...
        def record_exception(self, exc: Exception) -> None: ...
        def __enter__(self) -> "Span": return self
        def __exit__(self, *a: Any) -> None: ...

    class Tracer:  # type: ignore[no-redef]
        def start_as_current_span(self, name: str, **kw: Any) -> Any:
            return Span()

        def start_span(self, name: str, **kw: Any) -> Span:
            return Span()

    class _FakeTrace:
        def get_tracer(self, name: str, **kw: Any) -> Tracer:
            return Tracer()

        def get_current_span(self) -> Span:
            return Span()

    trace = _FakeTrace()  # type: ignore[assignment]

    class TraceContextTextMapPropagator:  # type: ignore[no-redef]
        def inject(self, carrier: dict[str, Any]) -> None: ...
        def extract(self, carrier: dict[str, Any]) -> Any: ...


class AgitTracer:
    """OpenTelemetry tracer that wraps agit operations in spans.

    Usage::

        tracer = AgitTracer(service_name="my-agent")

        with tracer.trace_action("tool_call", agent_id="agent1") as span:
            span.set_attribute("agit.tool.name", "web_search")
            result = do_tool_call()

        # Or instrument an ExecutionEngine
        tracer.instrument_engine(engine)
    """

    AGIT_SPAN_PREFIX = "agit"

    def __init__(
        self,
        service_name: str = "agit",
        tracer_name: str = "agit.python",
        version: str = "0.1.0",
    ) -> None:
        self._service_name = service_name
        self._tracer: Tracer = trace.get_tracer(tracer_name, schema_url=None)  # type: ignore[call-arg]

    # ------------------------------------------------------------------
    # Core span factories
    # ------------------------------------------------------------------

    @contextmanager
    def trace_action(
        self,
        action_type: str,
        agent_id: str = "default",
        commit_hash: Optional[str] = None,
        message: str = "",
        extra_attrs: Optional[dict[str, Any]] = None,
    ) -> Generator[Any, None, None]:
        """Context manager that wraps a block in an agit action span."""
        span_name = f"{self.AGIT_SPAN_PREFIX}.{action_type}"

        with self._tracer.start_as_current_span(span_name) as span:
            span.set_attribute("agit.action_type", action_type)
            span.set_attribute("agit.agent_id", agent_id)
            span.set_attribute("agit.service_name", self._service_name)
            if message:
                span.set_attribute("agit.message", message)
            if commit_hash:
                span.set_attribute("agit.commit_hash", commit_hash)
            if extra_attrs:
                for k, v in extra_attrs.items():
                    span.set_attribute(k, str(v) if not isinstance(v, (str, int, float, bool)) else v)

            start_ts = time.monotonic()
            try:
                yield span
                elapsed = time.monotonic() - start_ts
                span.set_attribute("agit.duration_ms", int(elapsed * 1000))
                span.set_status(StatusCode.OK)  # type: ignore[arg-type]
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(StatusCode.ERROR, str(exc))  # type: ignore[arg-type]
                raise

    @contextmanager
    def trace_commit(
        self,
        agent_id: str,
        message: str,
        action_type: str = "checkpoint",
    ) -> Generator[Any, None, None]:
        """Convenience wrapper for commit spans."""
        with self.trace_action(
            action_type=action_type,
            agent_id=agent_id,
            message=message,
            extra_attrs={"agit.operation": "commit"},
        ) as span:
            yield span

    @contextmanager
    def trace_retry(
        self,
        agent_id: str,
        attempt: int,
        max_attempts: int,
    ) -> Generator[Any, None, None]:
        """Span for a single retry attempt."""
        with self.trace_action(
            action_type="retry",
            agent_id=agent_id,
            extra_attrs={
                "agit.retry.attempt": attempt,
                "agit.retry.max_attempts": max_attempts,
            },
        ) as span:
            yield span

    @contextmanager
    def trace_merge(
        self,
        agent_id: str,
        branch: str,
        strategy: str,
    ) -> Generator[Any, None, None]:
        """Span for a merge operation."""
        with self.trace_action(
            action_type="merge",
            agent_id=agent_id,
            extra_attrs={
                "agit.merge.branch": branch,
                "agit.merge.strategy": strategy,
            },
        ) as span:
            yield span

    # ------------------------------------------------------------------
    # Engine instrumentation
    # ------------------------------------------------------------------

    def instrument_engine(self, engine: Any) -> None:
        """Monkey-patch an :class:`ExecutionEngine` to add tracing.

        After calling this, every ``execute`` and ``commit_state`` call on
        *engine* will be wrapped in an OTel span.
        """
        tracer = self
        original_execute = engine.execute
        original_commit = engine.commit_state

        def traced_execute(
            action_fn: Any,
            state: Any,
            message: str,
            action_type: str = "tool_call",
        ) -> Any:
            with tracer.trace_action(action_type, agent_id=engine._agent_id, message=message):
                return original_execute(action_fn, state, message, action_type)

        def traced_commit(
            state: Any,
            message: str,
            action_type: str = "checkpoint",
        ) -> Any:
            with tracer.trace_commit(engine._agent_id, message, action_type):
                return original_commit(state, message, action_type)

        engine.execute = traced_execute
        engine.commit_state = traced_commit

    # ------------------------------------------------------------------
    # Context propagation helpers
    # ------------------------------------------------------------------

    def inject_context(self, carrier: dict[str, str]) -> None:
        """Inject current trace context into a carrier dict (e.g. HTTP headers)."""
        if _OTEL_AVAILABLE:
            TraceContextTextMapPropagator().inject(carrier)

    def extract_context(self, carrier: dict[str, str]) -> Any:
        """Extract trace context from a carrier dict."""
        if _OTEL_AVAILABLE:
            return TraceContextTextMapPropagator().extract(carrier)
        return None

    def current_span(self) -> Any:
        """Return the currently active span."""
        return trace.get_current_span()
