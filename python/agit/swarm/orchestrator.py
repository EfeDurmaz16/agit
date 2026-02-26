"""Multi-agent task decomposition and orchestration."""
from __future__ import annotations

import asyncio
import fcntl
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("agit.swarm.orchestrator")

from agit.engine.executor import ExecutionEngine


class DistributedLock:
    """File-based advisory lock for safe concurrent commits.

    Uses fcntl.flock for POSIX advisory locking on a lock file,
    ensuring only one agent writes to the repository at a time.

    Parameters
    ----------
    lock_path:
        Path to the lock file. Created if it doesn't exist.
    timeout:
        Maximum seconds to wait for lock (0 = non-blocking).
    """

    def __init__(self, lock_path: str, timeout: float = 30.0) -> None:
        self._lock_path = Path(lock_path)
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._timeout = timeout
        self._fd: Any = None

    def acquire(self) -> bool:
        """Acquire the advisory lock. Returns True on success."""
        self._fd = open(self._lock_path, "w")
        try:
            if self._timeout == 0:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                # Blocking lock (fcntl doesn't support timeout natively,
                # so we use blocking mode)
                fcntl.flock(self._fd, fcntl.LOCK_EX)
            return True
        except (IOError, OSError):
            self._fd.close()
            self._fd = None
            return False

    def release(self) -> None:
        """Release the advisory lock."""
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                self._fd.close()
            except (IOError, OSError):
                pass
            self._fd = None

    def __enter__(self) -> DistributedLock:
        self.acquire()
        return self

    def __exit__(self, *args: Any) -> None:
        self.release()


def topological_sort(subtasks: list[SubTask]) -> list[SubTask]:
    """Sort sub-tasks in dependency order using Kahn's algorithm.

    Parameters
    ----------
    subtasks:
        List of sub-tasks with dependency references.

    Returns
    -------
    list[SubTask]:
        Topologically sorted list.

    Raises
    ------
    ValueError:
        If a dependency cycle is detected.
    """
    id_to_task = {st.id: st for st in subtasks}
    in_degree: dict[str, int] = {st.id: 0 for st in subtasks}
    adjacency: dict[str, list[str]] = {st.id: [] for st in subtasks}

    for st in subtasks:
        for dep in st.dependencies:
            if dep in adjacency:
                adjacency[dep].append(st.id)
                in_degree[st.id] += 1

    queue: deque[str] = deque()
    for sid, degree in in_degree.items():
        if degree == 0:
            queue.append(sid)

    result: list[SubTask] = []
    while queue:
        current = queue.popleft()
        result.append(id_to_task[current])
        for neighbor in adjacency[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(subtasks):
        raise ValueError("Dependency cycle detected in sub-tasks")

    return result


@dataclass
class SubTask:
    """A single unit of work within a decomposed multi-agent task.

    Attributes
    ----------
    id:
        Unique identifier for this sub-task.
    description:
        Human-readable description of what this sub-task does.
    dependencies:
        IDs of sub-tasks that must complete before this one can start.
    assigned_agent:
        The agent ID assigned to execute this sub-task (empty until assigned).
    status:
        Current status: ``"pending"``, ``"in_progress"``, ``"completed"``, ``"failed"``.
    result:
        The output produced by executing this sub-task (populated on completion).
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    dependencies: list[str] = field(default_factory=list)
    assigned_agent: str = ""
    status: str = "pending"
    result: dict[str, Any] = field(default_factory=dict)


class SwarmOrchestrator:
    """Orchestrate a swarm of AI agents to collaboratively complete a task.

    The orchestrator decomposes a high-level task into :class:`SubTask` units,
    assigns them to available agents, and executes them respecting dependency
    ordering.  Each sub-task result is committed to the agit repository so the
    full execution trace is auditable.

    Parameters
    ----------
    repo_path:
        Path to the agit repository used for state persistence.

    Example::

        orch = SwarmOrchestrator("./repo")
        result = asyncio.run(orch.execute(
            "Research and summarise recent AI papers",
            agents=["agent-1", "agent-2", "agent-3"],
        ))
    """

    def __init__(self, repo_path: str) -> None:
        self._repo_path = repo_path
        self._engine = ExecutionEngine(repo_path=repo_path, agent_id="orchestrator")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decompose(self, task: str, num_agents: int = 3) -> list[SubTask]:
        """Decompose *task* into a list of parallelisable :class:`SubTask` objects.

        The decomposition heuristic creates a simple DAG:

        * One *planning* sub-task (no dependencies).
        * ``num_agents - 1`` *execution* sub-tasks that each depend on the
          planning step.
        * One *synthesis* sub-task that depends on all execution steps.

        Parameters
        ----------
        task:
            High-level task description.
        num_agents:
            Target number of parallel agents (determines graph width).

        Returns
        -------
        list[SubTask]:
            Ordered list of sub-tasks (topological order).
        """
        subtasks: list[SubTask] = []

        # Planning phase
        plan_task = SubTask(
            description=f"[PLAN] Analyse and plan: {task}",
            dependencies=[],
        )
        subtasks.append(plan_task)

        # Parallel execution phase
        exec_tasks: list[SubTask] = []
        num_exec = max(1, num_agents - 1)
        for i in range(num_exec):
            exec_task = SubTask(
                description=f"[EXECUTE-{i + 1}] Execute sub-task {i + 1} of {num_exec}: {task}",
                dependencies=[plan_task.id],
            )
            subtasks.append(exec_task)
            exec_tasks.append(exec_task)

        # Synthesis phase
        synth_task = SubTask(
            description=f"[SYNTHESISE] Merge results and produce final output: {task}",
            dependencies=[t.id for t in exec_tasks],
        )
        subtasks.append(synth_task)

        return topological_sort(subtasks)

    def assign(
        self, subtasks: list[SubTask], agents: list[str]
    ) -> dict[str, list[SubTask]]:
        """Assign sub-tasks to agents using round-robin scheduling.

        Parameters
        ----------
        subtasks:
            Sub-tasks to assign.
        agents:
            Available agent IDs.

        Returns
        -------
        dict[str, list[SubTask]]:
            Mapping of ``agent_id`` → list of assigned sub-tasks.
        """
        if not agents:
            raise ValueError("At least one agent must be provided")

        assignment: dict[str, list[SubTask]] = {a: [] for a in agents}

        for i, subtask in enumerate(subtasks):
            agent_id = agents[i % len(agents)]
            subtask.assigned_agent = agent_id
            assignment[agent_id].append(subtask)

        return assignment

    def execute(self, task: str, agents: list[str]) -> dict[str, Any]:
        """Orchestrate the full decompose → assign → execute workflow.

        Runs sub-tasks asynchronously respecting dependency order.

        Parameters
        ----------
        task:
            High-level task description.
        agents:
            Available agent IDs.

        Returns
        -------
        dict:
            Summary containing ``task``, ``subtasks`` results, ``duration``,
            and the final ``synthesis`` result.
        """
        return asyncio.run(self._execute_async(task, agents))

    async def _execute_async(self, task: str, agents: list[str]) -> dict[str, Any]:
        subtasks = self.decompose(task, num_agents=len(agents))
        self.assign(subtasks, agents)

        start_ts = time.monotonic()

        # Commit the decomposition plan
        plan_state = {
            "memory": {
                "task": task,
                "subtasks": [
                    {
                        "id": st.id,
                        "description": st.description,
                        "dependencies": st.dependencies,
                        "assigned_agent": st.assigned_agent,
                    }
                    for st in subtasks
                ],
            },
            "world_state": {},
        }
        self._engine.commit_state(plan_state, f"swarm plan: {task[:60]}", "checkpoint")

        # Execute respecting dependencies
        completed: dict[str, SubTask] = {}
        id_to_task: dict[str, SubTask] = {st.id: st for st in subtasks}

        pending = list(subtasks)
        max_iterations = len(subtasks) * 2  # safety valve

        iteration = 0
        while pending and iteration < max_iterations:
            iteration += 1
            ready = [
                st for st in pending
                if all(dep in completed for dep in st.dependencies)
            ]
            if not ready:
                # No progress possible – dependency cycle or bug
                break

            results = await asyncio.gather(
                *[self._execute_subtask(st, st.assigned_agent) for st in ready],
                return_exceptions=True,
            )

            for st, result in zip(ready, results):
                if isinstance(result, BaseException):
                    st.status = "failed"
                    st.result = {"error": str(result)}
                else:
                    st.status = "completed"
                    st.result = result  # type: ignore[assignment]
                completed[st.id] = st
                pending.remove(st)

        elapsed = time.monotonic() - start_ts

        synthesis = completed.get(subtasks[-1].id, SubTask()).result

        final_state = {
            "memory": {
                "task": task,
                "completed_subtasks": len(completed),
                "total_subtasks": len(subtasks),
                "synthesis": synthesis,
                "duration": elapsed,
            },
            "world_state": {},
        }
        self._engine.commit_state(final_state, f"swarm complete: {task[:60]}", "checkpoint")

        return {
            "task": task,
            "subtasks": [
                {
                    "id": st.id,
                    "description": st.description,
                    "assigned_agent": st.assigned_agent,
                    "status": st.status,
                    "result": st.result,
                }
                for st in subtasks
            ],
            "synthesis": synthesis,
            "duration": elapsed,
            "agents": agents,
        }

    async def _execute_subtask(self, subtask: SubTask, agent_id: str) -> dict[str, Any]:
        """Execute a single sub-task and commit its result.

        In production, replace the body with actual agent invocation.
        The current implementation records the sub-task as a stub result so
        the orchestration logic and audit trail work end-to-end without
        requiring live agents.

        Parameters
        ----------
        subtask:
            The sub-task to execute.
        agent_id:
            The agent executing this sub-task.

        Returns
        -------
        dict:
            Result dict with at least ``"output"`` and ``"agent_id"`` keys.
        """
        subtask.status = "in_progress"

        # Simulate async work (replace with actual agent call)
        await asyncio.sleep(0)

        result: dict[str, Any] = {
            "output": f"Completed: {subtask.description}",
            "agent_id": agent_id,
            "subtask_id": subtask.id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # Persist result as an agit commit
        state = {
            "memory": {
                "subtask_id": subtask.id,
                "description": subtask.description,
                "result": result,
                "agent_id": agent_id,
            },
            "world_state": {},
        }

        lock = DistributedLock(f"{self._repo_path}/.agit/swarm.lock")
        engine = ExecutionEngine(repo_path=self._repo_path, agent_id=agent_id)
        try:
            with lock:
                engine.commit_state(
                    state,
                    message=f"swarm subtask {subtask.id[:6]}: {subtask.description[:50]}",
                    action_type="tool_call",
                )
        except Exception:
            logger.warning("Failed to commit swarm subtask %s state", subtask.id[:6], exc_info=True)

        return result
