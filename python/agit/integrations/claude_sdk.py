"""Claude Agent SDK integration – PreToolUse / PostToolUse hooks."""
from __future__ import annotations

import time
from typing import Any

from agit.engine.executor import ExecutionEngine

try:
    from claude_agent_sdk import PreToolUse, PostToolUse  # type: ignore[import]

    _CLAUDE_SDK_AVAILABLE = True
except ImportError:
    _CLAUDE_SDK_AVAILABLE = False

    class PreToolUse:  # type: ignore[no-redef]
        """Stub for claude_agent_sdk.PreToolUse."""

        tool_name: str = ""
        tool_input: dict[str, Any] = {}

    class PostToolUse:  # type: ignore[no-redef]
        """Stub for claude_agent_sdk.PostToolUse."""

        tool_name: str = ""
        tool_input: dict[str, Any] = {}
        tool_output: Any = None


class AgitClaudeHooks:
    """Claude Agent SDK hook handler that commits state around each tool call.

    Usage::

        engine = ExecutionEngine("./repo", agent_id="claude-agent")
        hooks = AgitClaudeHooks(engine)

        # Register with your claude_agent_sdk session:
        session.add_hook("pre_tool_use", hooks.on_pre_tool_use)
        session.add_hook("post_tool_use", hooks.on_post_tool_use)
    """

    def __init__(self, engine: ExecutionEngine) -> None:
        self._engine = engine
        self._start_times: dict[str, float] = {}

    def on_pre_tool_use(self, event: PreToolUse) -> None:  # type: ignore[override]
        """Handle PreToolUse event – commit checkpoint before the tool runs."""
        tool_name = getattr(event, "tool_name", "unknown")
        tool_input = getattr(event, "tool_input", {})
        state = self._engine.get_current_state() or {}

        # Annotate state with incoming tool call metadata
        memory = state.get("memory", {})
        memory = {**memory, "_pending_tool": tool_name, "_pending_input": tool_input}
        state = {**state, "memory": memory}

        self._start_times[tool_name] = time.monotonic()
        try:
            self._engine.commit_state(
                state,
                message=f"pre-tool: {tool_name}",
                action_type="checkpoint",
            )
        except Exception:
            pass

    def on_post_tool_use(self, event: PostToolUse) -> None:  # type: ignore[override]
        """Handle PostToolUse event – commit state after the tool returns."""
        tool_name = getattr(event, "tool_name", "unknown")
        tool_output = getattr(event, "tool_output", None)
        elapsed = time.monotonic() - self._start_times.pop(tool_name, time.monotonic())

        state = self._engine.get_current_state() or {}
        memory = state.get("memory", {})
        # Clear pending marker, record result
        memory = {k: v for k, v in memory.items() if k not in ("_pending_tool", "_pending_input")}
        memory[f"_tool_{tool_name}_output"] = tool_output
        state = {**state, "memory": memory}

        try:
            self._engine.commit_state(
                state,
                message=f"tool: {tool_name} (elapsed={elapsed:.3f}s)",
                action_type="tool_call",
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Convenience – return hook pairs as a dict for easy registration
    # ------------------------------------------------------------------

    def as_hook_dict(self) -> dict[str, Any]:
        """Return ``{"pre_tool_use": ..., "post_tool_use": ...}`` mapping."""
        return {
            "pre_tool_use": self.on_pre_tool_use,
            "post_tool_use": self.on_post_tool_use,
        }
