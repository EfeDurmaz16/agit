"""OpenAI Agents SDK integration – AgentHooks subclass."""
from __future__ import annotations

import logging
import time
from typing import Any

from agit.engine.executor import ExecutionEngine

logger = logging.getLogger("agit.integrations.openai_agents")

try:
    from agents import AgentHooks, RunContextWrapper, Tool  # type: ignore[import]

    _OPENAI_AGENTS_AVAILABLE = True
except ImportError:
    _OPENAI_AGENTS_AVAILABLE = False

    # Minimal stubs so the module is importable without the SDK installed
    class RunContextWrapper:  # type: ignore[no-redef]
        context: Any = None

    class Tool:  # type: ignore[no-redef]
        name: str = ""

    class AgentHooks:  # type: ignore[no-redef]
        """Stub base class."""

        async def on_tool_start(
            self,
            context: RunContextWrapper,  # type: ignore[override]
            agent: Any,
            tool: Tool,  # type: ignore[override]
        ) -> None: ...

        async def on_tool_end(
            self,
            context: RunContextWrapper,  # type: ignore[override]
            agent: Any,
            tool: Tool,  # type: ignore[override]
            result: str,
        ) -> None: ...


class AgitAgentHooks(AgentHooks):  # type: ignore[misc]
    """OpenAI Agents SDK hooks that auto-commit state around every tool call.

    Usage::

        engine = ExecutionEngine("./repo", agent_id="my-agent")
        hooks = AgitAgentHooks(engine)
        agent = Agent(..., hooks=hooks)
    """

    def __init__(self, engine: ExecutionEngine) -> None:
        self._engine = engine
        self._tool_start_times: dict[str, float] = {}

    async def on_tool_start(
        self,
        context: Any,
        agent: Any,
        tool: Any,
    ) -> None:
        """Commit state before tool execution."""
        tool_name = getattr(tool, "name", str(tool))
        state = self._context_to_state(context)
        self._tool_start_times[tool_name] = time.monotonic()
        try:
            self._engine.commit_state(
                state,
                message=f"pre-tool: {tool_name}",
                action_type="checkpoint",
            )
        except Exception:
            logger.warning("Failed to commit pre-tool state for %s", tool_name, exc_info=True)

    async def on_tool_end(
        self,
        context: Any,
        agent: Any,
        tool: Any,
        result: str,
    ) -> None:
        """Commit state after tool execution."""
        tool_name = getattr(tool, "name", str(tool))
        elapsed = time.monotonic() - self._tool_start_times.pop(tool_name, time.monotonic())
        state = self._context_to_state(context)

        # Record result in state memory
        memory = state.get("memory", {})
        memory = {**memory, f"_tool_{tool_name}_result": result}
        state = {**state, "memory": memory}

        try:
            self._engine.commit_state(
                state,
                message=f"tool: {tool_name} (elapsed={elapsed:.3f}s)",
                action_type="tool_call",
            )
        except Exception:
            logger.warning("Failed to commit post-tool state for %s", tool_name, exc_info=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _context_to_state(self, context: Any) -> dict[str, Any]:
        if context is None:
            return self._engine.get_current_state() or {}
        ctx = getattr(context, "context", context)
        if isinstance(ctx, dict):
            return {"memory": ctx, "world_state": {}}
        return self._engine.get_current_state() or {}
