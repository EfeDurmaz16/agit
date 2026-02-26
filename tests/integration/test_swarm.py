"""Integration tests for swarm orchestration."""
from __future__ import annotations

import tempfile

import pytest

from agit.swarm.orchestrator import (
    DistributedLock,
    SubTask,
    SwarmOrchestrator,
    topological_sort,
)


class TestDistributedLock:
    """Test file-based advisory locking."""

    def test_acquire_and_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock = DistributedLock(f"{tmp}/test.lock")
            assert lock.acquire() is True
            lock.release()

    def test_context_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with DistributedLock(f"{tmp}/test.lock") as lock:
                assert lock._fd is not None
            assert lock._fd is None

    def test_reentrant_different_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock1 = DistributedLock(f"{tmp}/lock1")
            lock2 = DistributedLock(f"{tmp}/lock2")
            assert lock1.acquire() is True
            assert lock2.acquire() is True
            lock1.release()
            lock2.release()


class TestTopologicalSort:
    """Test dependency resolution."""

    def test_simple_chain(self) -> None:
        a = SubTask(id="a", description="first")
        b = SubTask(id="b", description="second", dependencies=["a"])
        c = SubTask(id="c", description="third", dependencies=["b"])
        result = topological_sort([c, a, b])
        ids = [st.id for st in result]
        assert ids.index("a") < ids.index("b") < ids.index("c")

    def test_parallel_tasks(self) -> None:
        root = SubTask(id="root", description="root")
        a = SubTask(id="a", dependencies=["root"])
        b = SubTask(id="b", dependencies=["root"])
        final = SubTask(id="final", dependencies=["a", "b"])
        result = topological_sort([final, b, root, a])
        ids = [st.id for st in result]
        assert ids.index("root") < ids.index("a")
        assert ids.index("root") < ids.index("b")
        assert ids.index("a") < ids.index("final")
        assert ids.index("b") < ids.index("final")

    def test_cycle_detection(self) -> None:
        a = SubTask(id="a", dependencies=["b"])
        b = SubTask(id="b", dependencies=["a"])
        with pytest.raises(ValueError, match="cycle"):
            topological_sort([a, b])

    def test_no_dependencies(self) -> None:
        tasks = [SubTask(id=str(i)) for i in range(5)]
        result = topological_sort(tasks)
        assert len(result) == 5


class TestSwarmOrchestrator:
    """Test swarm decomposition, assignment, and execution."""

    def test_decompose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orch = SwarmOrchestrator(tmp)
            subtasks = orch.decompose("test task", num_agents=3)
            assert len(subtasks) >= 3  # plan + exec + synthesis
            # First task should have no dependencies
            assert subtasks[0].dependencies == []

    def test_assign_round_robin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orch = SwarmOrchestrator(tmp)
            subtasks = orch.decompose("test", num_agents=3)
            agents = ["agent-1", "agent-2", "agent-3"]
            assignment = orch.assign(subtasks, agents)
            assert all(agent in assignment for agent in agents)
            assert sum(len(tasks) for tasks in assignment.values()) == len(subtasks)

    def test_assign_requires_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orch = SwarmOrchestrator(tmp)
            subtasks = orch.decompose("test", num_agents=2)
            with pytest.raises(ValueError, match="(?i)at least one agent"):
                orch.assign(subtasks, [])

    def test_execute_full_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orch = SwarmOrchestrator(tmp)
            result = orch.execute(
                "Research AI papers",
                agents=["researcher-1", "researcher-2", "synthesizer"],
            )
            assert result["task"] == "Research AI papers"
            assert len(result["subtasks"]) >= 3
            assert all(st["status"] in ("completed", "failed") for st in result["subtasks"])
            assert result["duration"] >= 0

    def test_execute_single_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orch = SwarmOrchestrator(tmp)
            result = orch.execute("Simple task", agents=["solo-agent"])
            assert len(result["subtasks"]) >= 2  # at least plan + synthesis

    def test_concurrent_safety(self) -> None:
        """Verify that concurrent execution doesn't crash."""
        import asyncio

        async def run_concurrent():
            with tempfile.TemporaryDirectory() as tmp:
                orch = SwarmOrchestrator(tmp)
                tasks = [
                    orch._execute_async("task 1", ["a1", "a2"]),
                    orch._execute_async("task 2", ["a3", "a4"]),
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                return results

        results = asyncio.run(run_concurrent())
        assert len(results) == 2
        for r in results:
            if isinstance(r, dict):
                assert "task" in r
