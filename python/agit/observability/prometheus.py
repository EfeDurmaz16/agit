"""Prometheus metrics for agit – counters, histograms, and gauges."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Generator

try:
    from prometheus_client import (  # type: ignore[import]
        Counter,
        Histogram,
        Gauge,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

    # Minimal stubs so the module is importable without prometheus_client
    class _Stub:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def inc(self, amount: float = 1) -> None:
            pass

        def observe(self, value: float) -> None:
            pass

        def set(self, value: float) -> None:
            pass

        def labels(self, **kw: Any) -> "_Stub":
            return self

    Counter = _Stub  # type: ignore[assignment,misc]
    Histogram = _Stub  # type: ignore[assignment,misc]
    Gauge = _Stub  # type: ignore[assignment,misc]

    class CollectorRegistry:  # type: ignore[no-redef]
        pass

    def generate_latest(registry: Any = None) -> bytes:  # type: ignore[misc]
        return b""

    CONTENT_TYPE_LATEST = "text/plain"


class AgitMetrics:
    """Prometheus metrics collector for agit operations.

    Usage::

        metrics = AgitMetrics()

        # Instrument a commit
        metrics.commits_total.labels(action_type="tool_call", agent_id="agent1").inc()

        # Time an action
        with metrics.action_duration_seconds.labels(action_type="tool_call").time():
            do_work()

        # Expose via HTTP
        from prometheus_client import start_http_server
        start_http_server(8000)
    """

    def __init__(self, registry: Any = None) -> None:
        kw: dict[str, Any] = {"registry": registry} if registry is not None else {}

        # ------------------------------------------------------------------
        # Counters
        # ------------------------------------------------------------------
        self.commits_total = Counter(
            "agit_commits_total",
            "Total number of agit commits",
            ["action_type", "agent_id"],
            **kw,
        )

        self.retries_total = Counter(
            "agit_retries_total",
            "Total number of retry attempts",
            ["agent_id", "success"],
            **kw,
        )

        self.rollbacks_total = Counter(
            "agit_rollbacks_total",
            "Total number of rollback operations",
            ["agent_id"],
            **kw,
        )

        self.merges_total = Counter(
            "agit_merges_total",
            "Total number of merge operations",
            ["strategy", "agent_id"],
            **kw,
        )

        self.validation_failures_total = Counter(
            "agit_validation_failures_total",
            "Total number of pre/post validation failures",
            ["stage", "validator_name"],
            **kw,
        )

        # ------------------------------------------------------------------
        # Histograms
        # ------------------------------------------------------------------
        self.action_duration_seconds = Histogram(
            "agit_action_duration_seconds",
            "Duration of agent actions in seconds",
            ["action_type"],
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0),
            **kw,
        )

        self.state_size_bytes = Histogram(
            "agit_state_size_bytes",
            "Size of serialised agent state in bytes",
            ["agent_id"],
            buckets=(256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304),
            **kw,
        )

        self.retry_delay_seconds = Histogram(
            "agit_retry_delay_seconds",
            "Backoff delay before each retry attempt",
            ["agent_id"],
            buckets=(0.1, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0),
            **kw,
        )

        # ------------------------------------------------------------------
        # Gauges
        # ------------------------------------------------------------------
        self.active_branches = Gauge(
            "agit_active_branches",
            "Number of currently active branches",
            ["agent_id"],
            **kw,
        )

        self.head_commit_timestamp = Gauge(
            "agit_head_commit_timestamp_seconds",
            "Unix timestamp of the HEAD commit",
            ["agent_id"],
            **kw,
        )

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def record_commit(
        self,
        action_type: str,
        agent_id: str,
        state_bytes: int = 0,
        duration_seconds: float = 0.0,
    ) -> None:
        """Record metrics for a single commit."""
        self.commits_total.labels(action_type=action_type, agent_id=agent_id).inc()
        if duration_seconds > 0:
            self.action_duration_seconds.labels(action_type=action_type).observe(duration_seconds)
        if state_bytes > 0:
            self.state_size_bytes.labels(agent_id=agent_id).observe(state_bytes)
        self.head_commit_timestamp.labels(agent_id=agent_id).set(time.time())

    def record_retry(
        self,
        agent_id: str,
        success: bool,
        delay_seconds: float = 0.0,
    ) -> None:
        """Record metrics for a retry attempt."""
        self.retries_total.labels(agent_id=agent_id, success=str(success).lower()).inc()
        if delay_seconds > 0:
            self.retry_delay_seconds.labels(agent_id=agent_id).observe(delay_seconds)

    def record_rollback(self, agent_id: str) -> None:
        """Record a rollback event."""
        self.rollbacks_total.labels(agent_id=agent_id).inc()

    def record_merge(self, strategy: str, agent_id: str) -> None:
        """Record a merge operation."""
        self.merges_total.labels(strategy=strategy, agent_id=agent_id).inc()

    def record_validation_failure(self, stage: str, validator_name: str) -> None:
        """Record a validator failure."""
        self.validation_failures_total.labels(stage=stage, validator_name=validator_name).inc()

    def update_branch_count(self, agent_id: str, count: int) -> None:
        """Update the active branch gauge."""
        self.active_branches.labels(agent_id=agent_id).set(count)

    @contextmanager
    def time_action(self, action_type: str) -> Generator[None, None, None]:
        """Context manager that times a block and records it."""
        start = time.monotonic()
        try:
            yield
        finally:
            elapsed = time.monotonic() - start
            self.action_duration_seconds.labels(action_type=action_type).observe(elapsed)


# Module-level default instance (lazy; only instantiated on first use)
_default_metrics: AgitMetrics | None = None


def get_default_metrics() -> AgitMetrics:
    """Return the module-level default :class:`AgitMetrics` instance."""
    global _default_metrics
    if _default_metrics is None:
        _default_metrics = AgitMetrics()
    return _default_metrics
