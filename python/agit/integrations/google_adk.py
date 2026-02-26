"""Google ADK integration – auto-commit on every tool call."""
from __future__ import annotations

from typing import Any

from agit.engine.executor import ExecutionEngine

try:
    from google.adk.agents import Agent  # type: ignore[import]
    from google.adk.tools import BaseTool  # type: ignore[import]

    _ADK_AVAILABLE = True
except ImportError:
    _ADK_AVAILABLE = False
    Agent = object  # type: ignore[assignment,misc]
    BaseTool = object  # type: ignore[assignment,misc]


class AgitPlugin:
    """Google ADK plugin that wraps tool calls with agit commits.

    Attach to an ADK agent by passing it in the agent's plugin list::

        engine = ExecutionEngine("./my_repo", agent_id="my_agent")
        plugin = AgitPlugin(engine)
        agent = Agent(..., plugins=[plugin])

    The plugin records a pre-tool checkpoint commit and a post-tool commit for
    every tool invocation, providing full auditability.
    """

    def __init__(self, engine: ExecutionEngine) -> None:
        self._engine = engine
        self._pre_hashes: dict[str, str] = {}  # call_id -> pre-commit hash

    # ------------------------------------------------------------------
    # ADK plugin protocol hooks
    # ------------------------------------------------------------------

    def before_tool(
        self,
        tool: Any,
        args: dict[str, Any],
        tool_context: Any = None,
    ) -> dict[str, Any] | None:
        """Called by ADK before executing a tool.

        Commits the current agent state as a pre-tool checkpoint.
        Returns *None* to signal that the original args should be used unchanged.
        """
        tool_name = getattr(tool, "name", str(tool))
        state = self._extract_state(tool_context)
        call_id = self._make_call_id(tool_name, args)

        try:
            h = self._engine.commit_state(
                state,
                message=f"pre-tool: {tool_name}",
                action_type="checkpoint",
            )
            self._pre_hashes[call_id] = h
        except Exception:
            pass  # Never block tool execution

        return None  # Don't modify args

    def after_tool(
        self,
        tool: Any,
        args: dict[str, Any],
        tool_context: Any = None,
        tool_response: Any = None,
    ) -> Any:
        """Called by ADK after a tool returns.

        Commits the updated agent state as a tool_call commit.
        Returns *tool_response* unchanged.
        """
        tool_name = getattr(tool, "name", str(tool))
        state = self._extract_state(tool_context)

        # Fold tool response into state if possible
        if isinstance(tool_response, dict):
            memory = state.get("memory", {})
            memory = {**memory, f"_last_{tool_name}_result": tool_response}
            state = {**state, "memory": memory}

        try:
            self._engine.commit_state(
                state,
                message=f"tool: {tool_name}",
                action_type="tool_call",
            )
        except Exception:
            pass

        return tool_response

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_state(self, tool_context: Any) -> dict[str, Any]:
        """Pull state dict from ADK tool context or return empty state."""
        if tool_context is None:
            return self._engine.get_current_state() or {}
        # ADK contexts expose `.state` as a dict-like object
        ctx_state = getattr(tool_context, "state", None)
        if isinstance(ctx_state, dict):
            return {"memory": ctx_state, "world_state": {}}
        return self._engine.get_current_state() or {}

    @staticmethod
    def _make_call_id(tool_name: str, args: dict[str, Any]) -> str:
        import hashlib
        import json

        raw = f"{tool_name}:{json.dumps(args, sort_keys=True, default=str)}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]  # noqa: S324
