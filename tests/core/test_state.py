"""Tests for AgentState creation, serialization, diff, and merge."""
from __future__ import annotations

from typing import Any

import pytest

from agit import PyAgentState, PyStateDiff, PyDiffEntry


class TestAgentStateCreation:
    """Test creating PyAgentState objects."""

    def test_create_with_memory_and_world_state(self) -> None:
        memory = {"key": "value", "count": 42}
        world_state = {"env": "test"}
        state = PyAgentState(memory, world_state)
        assert state.memory == memory
        assert state.world_state == world_state

    def test_create_with_empty_dicts(self) -> None:
        state = PyAgentState({}, {})
        assert state.memory == {}
        assert state.world_state == {}

    def test_create_with_nested_memory(self) -> None:
        memory = {
            "agent_name": "test",
            "nested": {"level1": {"level2": "deep_value"}},
            "list_val": [1, 2, 3],
        }
        state = PyAgentState(memory, {})
        assert state.memory["nested"]["level1"]["level2"] == "deep_value"
        assert state.memory["list_val"] == [1, 2, 3]

    def test_create_with_numeric_values(self) -> None:
        memory = {"cost": 1.23, "tokens": 500, "score": 0.99}
        state = PyAgentState(memory, {})
        assert state.memory["cost"] == pytest.approx(1.23)
        assert state.memory["tokens"] == 500


class TestAgentStateSerialization:
    """Test state serialization and deserialization."""

    def test_to_dict_round_trip(self) -> None:
        memory = {"agent": "tester", "step": 3}
        world_state = {"status": "active"}
        state = PyAgentState(memory, world_state)
        d = state.to_dict()
        assert d["memory"] == memory
        assert d["world_state"] == world_state

    def test_from_dict_round_trip(self) -> None:
        original = {"memory": {"x": 1}, "world_state": {"y": 2}}
        state = PyAgentState.from_dict(original)
        recovered = state.to_dict()
        assert recovered == original

    def test_from_dict_missing_keys(self) -> None:
        state = PyAgentState.from_dict({})
        assert state.memory == {}
        assert state.world_state == {}

    def test_from_dict_only_memory(self) -> None:
        state = PyAgentState.from_dict({"memory": {"k": "v"}})
        assert state.memory == {"k": "v"}
        assert state.world_state == {}

    def test_serialization_preserves_types(self) -> None:
        memory = {
            "string": "hello",
            "integer": 42,
            "float": 3.14,
            "bool_true": True,
            "bool_false": False,
            "none_val": None,
            "list": [1, "two", 3.0],
        }
        state = PyAgentState(memory, {})
        d = state.to_dict()
        assert d["memory"]["string"] == "hello"
        assert d["memory"]["integer"] == 42
        assert d["memory"]["float"] == pytest.approx(3.14)
        assert d["memory"]["bool_true"] is True
        assert d["memory"]["bool_false"] is False
        assert d["memory"]["none_val"] is None
        assert d["memory"]["list"] == [1, "two", 3.0]


class TestStateDiff:
    """Test PyStateDiff and diff computation via PyRepository."""

    def test_diff_entry_added(self) -> None:
        entry = PyDiffEntry(path="memory.new_key", change_type="added", new_value="hello")
        assert entry.path == "memory.new_key"
        assert entry.change_type == "added"
        assert entry.new_value == "hello"
        assert entry.old_value is None

    def test_diff_entry_removed(self) -> None:
        entry = PyDiffEntry(path="memory.old_key", change_type="removed", old_value="bye")
        assert entry.change_type == "removed"
        assert entry.old_value == "bye"
        assert entry.new_value is None

    def test_diff_entry_changed(self) -> None:
        entry = PyDiffEntry(
            path="memory.counter",
            change_type="changed",
            old_value=1,
            new_value=2,
        )
        assert entry.change_type == "changed"
        assert entry.old_value == 1
        assert entry.new_value == 2

    def test_state_diff_empty_when_identical(self) -> None:
        from agit import PyRepository

        repo = PyRepository(":memory:", "test-agent")
        state = PyAgentState({"k": "v"}, {"env": "test"})
        h1 = repo.commit(state, "commit 1", "checkpoint")
        h2 = repo.commit(state, "commit 2", "checkpoint")
        diff = repo.diff(h1, h2)
        # Identical states → no meaningful changed entries
        assert diff.base_hash == h1
        assert diff.target_hash == h2

    def test_state_diff_detects_added_key(self) -> None:
        from agit import PyRepository

        repo = PyRepository(":memory:", "test-agent")
        s1 = PyAgentState({"k": "v"}, {})
        h1 = repo.commit(s1, "initial", "checkpoint")
        s2 = PyAgentState({"k": "v", "new": "value"}, {})
        h2 = repo.commit(s2, "added key", "tool_call")
        diff = repo.diff(h1, h2)
        paths = [e.path for e in diff.entries]
        assert any("new" in p for p in paths)

    def test_state_diff_detects_removed_key(self) -> None:
        from agit import PyRepository

        repo = PyRepository(":memory:", "test-agent")
        s1 = PyAgentState({"k": "v", "to_remove": "x"}, {})
        h1 = repo.commit(s1, "initial", "checkpoint")
        s2 = PyAgentState({"k": "v"}, {})
        h2 = repo.commit(s2, "removed key", "tool_call")
        diff = repo.diff(h1, h2)
        paths = [e.path for e in diff.entries]
        assert any("to_remove" in p for p in paths)

    def test_state_diff_detects_changed_value(self) -> None:
        from agit import PyRepository

        repo = PyRepository(":memory:", "test-agent")
        s1 = PyAgentState({"counter": 0}, {})
        h1 = repo.commit(s1, "initial", "checkpoint")
        s2 = PyAgentState({"counter": 99}, {})
        h2 = repo.commit(s2, "incremented", "tool_call")
        diff = repo.diff(h1, h2)
        changed = [e for e in diff.entries if e.change_type == "changed"]
        assert any("counter" in e.path for e in changed)


@pytest.mark.parametrize(
    "base_memory,other_memory",
    [
        ({"a": 1}, {"b": 2}),
        ({"shared": "old"}, {"shared": "new"}),
        ({}, {"new_key": "new_val"}),
    ],
)
class TestThreeWayMerge:
    """Test three-way merge via repository merge operation."""

    def test_merge_produces_commit(
        self, base_memory: dict, other_memory: dict
    ) -> None:
        from agit import PyRepository

        repo = PyRepository(":memory:", "merger")
        base_state = PyAgentState(base_memory, {})
        repo.commit(base_state, "base", "checkpoint")

        repo.branch("feature", from_ref=None)
        repo.checkout("feature")

        other_state = PyAgentState(other_memory, {})
        repo.commit(other_state, "feature commit", "tool_call")

        repo.checkout("main")
        merge_hash = repo.merge("feature", strategy="three_way")
        assert isinstance(merge_hash, str)
        assert len(merge_hash) == 64  # SHA-256 hex

    def test_merge_theirs_strategy(
        self, base_memory: dict, other_memory: dict
    ) -> None:
        from agit import PyRepository

        repo = PyRepository(":memory:", "merger")
        base_state = PyAgentState(base_memory, {})
        repo.commit(base_state, "base", "checkpoint")

        repo.branch("theirs-branch", from_ref=None)
        repo.checkout("theirs-branch")
        other_state = PyAgentState(other_memory, {})
        repo.commit(other_state, "theirs commit", "tool_call")

        repo.checkout("main")
        merge_hash = repo.merge("theirs-branch", strategy="theirs")
        merged_state = repo.get_state(merge_hash)
        assert merged_state is not None
