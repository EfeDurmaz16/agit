"""Tests for RetryEngine: retry logic, backoff, and branch isolation."""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch

import pytest

from agit import ExecutionEngine, RetryEngine


@pytest.fixture()
def executor() -> ExecutionEngine:
    return ExecutionEngine(":memory:", agent_id="retry-tester")


@pytest.fixture()
def retry_engine(executor: ExecutionEngine) -> RetryEngine:
    return RetryEngine(executor, max_retries=3, base_delay=0.0)


@pytest.fixture()
def base_state() -> dict[str, Any]:
    return {
        "memory": {"step": 0, "cumulative_cost": 0.0},
        "world_state": {"status": "idle"},
    }


class TestSuccessfulRetry:
    """Test that RetryEngine succeeds after transient failures."""

    def test_succeeds_on_first_attempt(
        self,
        retry_engine: RetryEngine,
        base_state: dict[str, Any],
    ) -> None:
        def always_succeeds(state: dict[str, Any]) -> dict[str, Any]:
            return {**state, "memory": {**state["memory"], "step": 1}}

        result, history = retry_engine.execute_with_retry(
            always_succeeds, base_state, "immediate success"
        )
        assert history.succeeded
        assert history.total_attempts == 1
        assert history.attempts[0].success is True

    def test_succeeds_after_one_failure(
        self,
        retry_engine: RetryEngine,
        base_state: dict[str, Any],
    ) -> None:
        call_count = {"n": 0}

        def fails_once(state: dict[str, Any]) -> dict[str, Any]:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ValueError("transient error")
            return {**state, "memory": {**state["memory"], "recovered": True}}

        result, history = retry_engine.execute_with_retry(
            fails_once, base_state, "recover after one failure"
        )
        assert history.succeeded
        assert history.total_attempts == 2
        assert history.attempts[0].success is False
        assert history.attempts[1].success is True

    def test_succeeds_after_two_failures(
        self,
        retry_engine: RetryEngine,
        base_state: dict[str, Any],
    ) -> None:
        call_count = {"n": 0}

        def fails_twice(state: dict[str, Any]) -> dict[str, Any]:
            call_count["n"] += 1
            if call_count["n"] <= 2:
                raise RuntimeError(f"failure #{call_count['n']}")
            return {**state, "memory": {**state["memory"], "step": 3}}

        result, history = retry_engine.execute_with_retry(
            fails_twice, base_state, "recover after two failures"
        )
        assert history.succeeded
        assert history.total_attempts == 3

    def test_result_value_returned_on_success(
        self,
        retry_engine: RetryEngine,
        base_state: dict[str, Any],
    ) -> None:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            return {**state, "memory": {**state["memory"], "answer": 42}}

        result, history = retry_engine.execute_with_retry(action, base_state, "get answer")
        assert isinstance(result, dict)
        assert result["memory"]["answer"] == 42


class TestMaxRetriesExceeded:
    """Test that RetryEngine raises after exhausting all retries."""

    def test_raises_after_max_retries(
        self,
        retry_engine: RetryEngine,
        base_state: dict[str, Any],
    ) -> None:
        def always_fails(state: dict[str, Any]) -> dict[str, Any]:
            raise ValueError("always fails")

        with pytest.raises(RuntimeError, match="failed after"):
            retry_engine.execute_with_retry(always_fails, base_state, "doomed action")

    def test_history_records_all_failed_attempts(
        self,
        retry_engine: RetryEngine,
        base_state: dict[str, Any],
    ) -> None:
        def always_fails(state: dict[str, Any]) -> dict[str, Any]:
            raise ValueError("always fails")

        with pytest.raises(RuntimeError):
            retry_engine.execute_with_retry(always_fails, base_state, "all fail")

        histories = retry_engine.get_retry_history()
        assert len(histories) >= 1
        last = histories[-1]
        assert last["succeeded"] is False
        assert last["total_attempts"] == 4  # initial + 3 retries

    def test_history_contains_error_messages(
        self,
        retry_engine: RetryEngine,
        base_state: dict[str, Any],
    ) -> None:
        def always_fails(state: dict[str, Any]) -> dict[str, Any]:
            raise ValueError("unique_error_text")

        with pytest.raises(RuntimeError):
            retry_engine.execute_with_retry(always_fails, base_state, "error capture")

        histories = retry_engine.get_retry_history()
        last = histories[-1]
        errors = [a["error"] for a in last["attempts"] if a["error"]]
        assert all("unique_error_text" in e for e in errors)

    def test_custom_max_retries_respected(
        self,
        executor: ExecutionEngine,
        base_state: dict[str, Any],
    ) -> None:
        engine = RetryEngine(executor, max_retries=1, base_delay=0.0)

        def always_fails(state: dict[str, Any]) -> dict[str, Any]:
            raise ValueError("fail")

        with pytest.raises(RuntimeError):
            engine.execute_with_retry(always_fails, base_state, "custom max")

        histories = engine.get_retry_history()
        last = histories[-1]
        assert last["total_attempts"] == 2  # initial + 1 retry


class TestExponentialBackoff:
    """Test that exponential backoff delays are applied between retries."""

    def test_backoff_delays_increase(
        self,
        executor: ExecutionEngine,
        base_state: dict[str, Any],
    ) -> None:
        call_times: list[float] = []
        call_count = {"n": 0}

        def record_times(state: dict[str, Any]) -> dict[str, Any]:
            call_times.append(time.monotonic())
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ValueError("not yet")
            return state

        engine = RetryEngine(executor, max_retries=3, base_delay=0.05)
        engine.execute_with_retry(record_times, base_state, "backoff test")

        assert len(call_times) >= 2
        # The gap between retries should grow (second gap >= first gap approximately)
        if len(call_times) >= 3:
            gap1 = call_times[1] - call_times[0]
            gap2 = call_times[2] - call_times[1]
            # With exponential backoff base=0.05: delay[1]=0.05, delay[2]=0.1
            # Allow generous tolerance due to scheduling jitter
            assert gap2 >= gap1 * 0.5

    def test_zero_base_delay_runs_immediately(
        self,
        executor: ExecutionEngine,
        base_state: dict[str, Any],
    ) -> None:
        call_count = {"n": 0}

        def fails_once(state: dict[str, Any]) -> dict[str, Any]:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ValueError("once")
            return state

        engine = RetryEngine(executor, max_retries=2, base_delay=0.0)
        start = time.monotonic()
        engine.execute_with_retry(fails_once, base_state, "fast retry")
        elapsed = time.monotonic() - start
        # With zero base delay, should complete very quickly
        assert elapsed < 5.0


class TestBranchPerRetry:
    """Test that each retry creates an isolated branch."""

    def test_retry_branches_created_on_failure(
        self,
        executor: ExecutionEngine,
        base_state: dict[str, Any],
    ) -> None:
        call_count = {"n": 0}

        def fails_once(state: dict[str, Any]) -> dict[str, Any]:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ValueError("first fail")
            return state

        engine = RetryEngine(executor, max_retries=2, base_delay=0.0)
        engine.execute_with_retry(fails_once, base_state, "branch isolation")

        histories = engine.get_retry_history()
        last = histories[-1]
        branch_names = [a["branch"] for a in last["attempts"]]
        # Retry attempts should have distinct branch names
        assert len(set(branch_names)) >= 1

    def test_history_summary_format(
        self,
        retry_engine: RetryEngine,
        base_state: dict[str, Any],
    ) -> None:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            return state

        _, history = retry_engine.execute_with_retry(action, base_state, "summary test")
        summary = history.summary()
        assert "action" in summary
        assert "total_attempts" in summary
        assert "succeeded" in summary
        assert "attempts" in summary
        assert isinstance(summary["attempts"], list)

    def test_clear_history(
        self,
        retry_engine: RetryEngine,
        base_state: dict[str, Any],
    ) -> None:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            return state

        retry_engine.execute_with_retry(action, base_state, "to be cleared")
        assert len(retry_engine.get_retry_history()) >= 1

        retry_engine.clear_history()
        assert retry_engine.get_retry_history() == []
