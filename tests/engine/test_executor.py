"""Tests for ExecutionEngine: auto-commit, history, and error handling."""
from __future__ import annotations

from typing import Any

import pytest

from agit import ExecutionEngine


@pytest.fixture()
def engine() -> ExecutionEngine:
    return ExecutionEngine(":memory:", agent_id="test-executor")


@pytest.fixture()
def base_state() -> dict[str, Any]:
    return {
        "memory": {"step": 0, "data": "initial", "cumulative_cost": 0.0},
        "world_state": {"status": "idle"},
    }


class TestAutoCommit:
    """Test that ExecutionEngine auto-commits before and after actions."""

    def test_execute_returns_result_and_hash(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            return {**state, "memory": {**state["memory"], "step": 1}}

        result, commit_hash = engine.execute(action, base_state, "step forward")
        assert isinstance(result, dict)
        assert isinstance(commit_hash, str)
        assert len(commit_hash) == 64

    def test_execute_commits_pre_and_post_state(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            return {**state, "memory": {**state["memory"], "processed": True}}

        engine.execute(action, base_state, "process data")
        history = engine.get_history(limit=10)
        # At least 2 commits: pre-checkpoint + post-action
        assert len(history) >= 2

    def test_execute_updates_current_state(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            new_mem = {**state["memory"], "step": 99}
            return {**state, "memory": new_mem}

        engine.execute(action, base_state, "update step")
        current = engine.get_current_state()
        assert current is not None
        assert current["memory"]["step"] == 99

    def test_execute_action_returning_non_dict(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        def action(state: dict[str, Any]) -> str:
            return "plain_result"

        result, commit_hash = engine.execute(action, base_state, "plain action")
        assert result == "plain_result"
        assert isinstance(commit_hash, str)

    def test_commit_state_directly(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        h = engine.commit_state(base_state, "direct commit", "checkpoint")
        assert isinstance(h, str)
        assert len(h) == 64

    def test_multiple_executions_produce_ordered_history(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        state = base_state
        for i in range(3):
            def action(s: dict[str, Any], i: int = i) -> dict[str, Any]:
                return {**s, "memory": {**s["memory"], "step": i + 1}}

            result, _ = engine.execute(action, state, f"step {i + 1}")
            state = result if isinstance(result, dict) else state

        history = engine.get_history(limit=20)
        assert len(history) >= 3
        messages = [c["message"] for c in history]
        assert any("step 1" in m or "pre:" in m for m in messages)


class TestHistoryRetrieval:
    """Test get_history and get_current_state."""

    def test_history_empty_on_fresh_engine(self) -> None:
        engine = ExecutionEngine(":memory:", agent_id="fresh")
        history = engine.get_history()
        assert history == []

    def test_history_limit_respected(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        state = base_state
        for i in range(5):
            def action(s: dict[str, Any], i: int = i) -> dict[str, Any]:
                return {**s, "memory": {**s["memory"], "step": i}}

            engine.execute(action, state, f"action {i}")

        history = engine.get_history(limit=3)
        assert len(history) <= 3

    def test_history_entries_have_required_fields(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            return state

        engine.execute(action, base_state, "test action")
        history = engine.get_history()
        assert len(history) > 0
        entry = history[0]
        assert "hash" in entry
        assert "message" in entry
        assert "author" in entry
        assert "timestamp" in entry
        assert "action_type" in entry

    def test_current_state_none_before_any_commit(self) -> None:
        engine = ExecutionEngine(":memory:", agent_id="fresh")
        assert engine.get_current_state() is None

    def test_current_state_after_commit(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        engine.commit_state(base_state, "initial", "checkpoint")
        current = engine.get_current_state()
        assert current is not None
        assert current["memory"]["step"] == 0

    def test_get_state_at_returns_historical_state_without_head_mutation(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        h1 = engine.commit_state(base_state, "v1", "checkpoint")
        engine.branch("feature")
        engine.checkout("feature")
        h2 = engine.commit_state(
            {
                **base_state,
                "memory": {**base_state["memory"], "step": 2},
            },
            "v2",
            "checkpoint",
        )
        assert h1 != h2

        state = engine.get_state_at(h1)
        assert state["memory"]["step"] == 0
        assert engine.current_branch() == "feature"


class TestErrorHandling:
    """Test error handling during execution."""

    def test_execute_raises_on_action_failure(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        def failing_action(state: dict[str, Any]) -> dict[str, Any]:
            raise ValueError("deliberate failure")

        with pytest.raises(ValueError, match="deliberate failure"):
            engine.execute(failing_action, base_state, "failing step")

    def test_execute_records_error_commit_on_failure(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        def failing_action(state: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            engine.execute(failing_action, base_state, "boom step")

        history = engine.get_history(limit=20)
        messages = [c["message"] for c in history]
        assert any("error:" in m or "boom" in m for m in messages)

    def test_diff_between_two_commits(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        h1 = engine.commit_state(base_state, "v1", "checkpoint")
        modified = {**base_state, "memory": {**base_state["memory"], "step": 10}}
        h2 = engine.commit_state(modified, "v2", "checkpoint")
        diff = engine.diff(h1, h2)
        assert diff["base_hash"] == h1
        assert diff["target_hash"] == h2
        assert isinstance(diff["entries"], list)

    def test_branch_and_checkout(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        engine.commit_state(base_state, "initial", "checkpoint")
        engine.branch("feature-branch")
        state = engine.checkout("feature-branch")
        assert state is not None
        assert engine.current_branch() == "feature-branch"

    def test_list_branches_after_creation(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        engine.commit_state(base_state, "initial", "checkpoint")
        engine.branch("branch-a")
        engine.branch("branch-b")
        branches = engine.list_branches()
        assert "branch-a" in branches
        assert "branch-b" in branches

    def test_revert_restores_previous_state(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        h1 = engine.commit_state(base_state, "original", "checkpoint")
        modified = {**base_state, "memory": {**base_state["memory"], "step": 999}}
        engine.commit_state(modified, "modified", "tool_call")
        reverted = engine.revert(h1)
        assert reverted["memory"]["step"] == 0

    def test_audit_log_records_actions(
        self, engine: ExecutionEngine, base_state: dict[str, Any]
    ) -> None:
        engine.commit_state(base_state, "audit test", "checkpoint")
        log = engine.audit_log(limit=10)
        assert isinstance(log, list)
        assert len(log) >= 1
