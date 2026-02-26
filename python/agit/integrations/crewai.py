"""CrewAI integration – step_callback and task_callback wrappers."""
from __future__ import annotations

import time
from typing import Any, Callable

from agit.engine.executor import ExecutionEngine

try:
    from crewai import Task  # type: ignore[import]

    _CREWAI_AVAILABLE = True
except ImportError:
    _CREWAI_AVAILABLE = False

    class Task:  # type: ignore[no-redef]
        output: Any = None
        description: str = ""


def agit_step_callback(engine: ExecutionEngine) -> Callable[[Any], None]:
    """Return a CrewAI ``step_callback`` that commits state after each agent step.

    Usage::

        engine = ExecutionEngine("./repo", agent_id="crew-agent")
        crew = Crew(
            agents=[...],
            tasks=[...],
            step_callback=agit_step_callback(engine),
        )
    """
    _step_counter: list[int] = [0]

    def _callback(step_output: Any) -> None:
        _step_counter[0] += 1
        step_num = _step_counter[0]

        # Extract whatever information CrewAI provides in the step output
        if hasattr(step_output, "__dict__"):
            step_data = vars(step_output)
        elif isinstance(step_output, dict):
            step_data = step_output
        else:
            step_data = {"raw_output": str(step_output)}

        state = {
            "memory": {
                "step_number": step_num,
                "step_output": step_data,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            "world_state": {},
        }

        try:
            engine.commit_state(
                state,
                message=f"crew step {step_num}",
                action_type="tool_call",
            )
        except Exception:
            pass

    return _callback


def agit_task_callback(engine: ExecutionEngine) -> Callable[[Any], None]:
    """Return a CrewAI ``task_callback`` that commits state after each task completes.

    Usage::

        engine = ExecutionEngine("./repo", agent_id="crew-agent")
        crew = Crew(
            agents=[...],
            tasks=[...],
            task_callback=agit_task_callback(engine),
        )
    """
    _task_counter: list[int] = [0]

    def _callback(task_output: Any) -> None:
        _task_counter[0] += 1
        task_num = _task_counter[0]

        description = ""
        output_raw = ""

        if isinstance(task_output, Task):
            description = getattr(task_output, "description", "")
            raw = getattr(task_output, "output", None)
            output_raw = str(raw) if raw is not None else ""
        elif isinstance(task_output, dict):
            description = task_output.get("description", "")
            output_raw = str(task_output.get("output", ""))
        else:
            output_raw = str(task_output)

        state = {
            "memory": {
                "task_number": task_num,
                "task_description": description,
                "task_output": output_raw,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            "world_state": {},
        }

        try:
            engine.commit_state(
                state,
                message=f"crew task {task_num}: {description[:60]}",
                action_type="checkpoint",
            )
        except Exception:
            pass

    return _callback


class AgitCrewCallbacks:
    """Convenience wrapper that bundles both callbacks.

    Usage::

        engine = ExecutionEngine("./repo", agent_id="crew")
        cbs = AgitCrewCallbacks(engine)
        crew = Crew(..., step_callback=cbs.step, task_callback=cbs.task)
    """

    def __init__(self, engine: ExecutionEngine) -> None:
        self._engine = engine
        self.step = agit_step_callback(engine)
        self.task = agit_task_callback(engine)
