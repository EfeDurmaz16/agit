"""Multi-SDK demo: Same workflow across Google ADK, OpenAI Agents, and Claude SDK.

Demonstrates how agit integration adapters work identically across all
major AI agent frameworks. Each framework wraps the same agit core.

Run:
    python examples/multi_sdk_demo.py
"""
from __future__ import annotations

import json
import tempfile
from typing import Any

from agit.engine.executor import ExecutionEngine
from agit.engine.retry import RetryEngine


# ---------------------------------------------------------------------------
# Shared agent workflow (framework-agnostic)
# ---------------------------------------------------------------------------


def analysis_step(state: dict[str, Any]) -> dict[str, Any]:
    """Simulate an LLM analysis step."""
    state["memory"]["step"] = 1
    state["memory"]["analysis"] = {
        "summary": "Data contains 3 anomalies requiring review.",
        "confidence": 0.91,
        "tokens_used": 412,
    }
    return state


def decision_step(state: dict[str, Any]) -> dict[str, Any]:
    """Simulate an LLM decision step."""
    anomalies = state["memory"]["analysis"]["anomalies_count"] if "anomalies_count" in state["memory"]["analysis"] else 3
    state["memory"]["step"] = 2
    state["memory"]["decision"] = {
        "action": "escalate" if anomalies > 2 else "monitor",
        "rationale": "Anomaly count exceeds threshold",
        "tokens_used": 289,
    }
    return state


def action_step(state: dict[str, Any]) -> dict[str, Any]:
    """Simulate executing the decided action."""
    decision = state["memory"]["decision"]
    state["memory"]["step"] = 3
    state["memory"]["action_result"] = {
        "executed": decision["action"],
        "timestamp": "2026-02-26T12:00:00Z",
        "status": "completed",
    }
    return state


# ---------------------------------------------------------------------------
# Standalone agit (no framework)
# ---------------------------------------------------------------------------


def demo_standalone(tmp: str) -> None:
    print("\n--- Standalone AgentGit ---")
    engine = ExecutionEngine(repo_path=tmp, agent_id="standalone-agent")
    retry = RetryEngine(engine, max_retries=2, base_delay=0.0)

    initial: dict[str, Any] = {
        "memory": {"task": "anomaly_detection", "cumulative_cost": 0.0},
        "world_state": {"dataset": "sensor_feed_v2"},
    }

    r1, h1 = engine.execute(analysis_step, initial, "analysis", "llm_response")
    r2, h2 = engine.execute(decision_step, r1, "decision", "llm_response")
    r3, h3 = engine.execute(action_step, r2, "action", "tool_call")

    print(f"  Final step: {r3['memory']['step']}")
    print(f"  Action: {r3['memory']['action_result']['executed']}")
    print(f"  Commits: {len(engine.get_history())}")
    diff = engine.diff(h1, h3)
    print(f"  Diff (step 1→3): {len(diff['entries'])} changed fields")
    print("  OK")


# ---------------------------------------------------------------------------
# Google ADK integration
# ---------------------------------------------------------------------------


def demo_google_adk(tmp: str) -> None:
    print("\n--- Google ADK Integration ---")
    try:
        from agit.integrations.google_adk import AgitPlugin  # type: ignore[import]

        engine = ExecutionEngine(repo_path=tmp, agent_id="adk-agent")
        plugin = AgitPlugin(engine)

        # Simulate ADK hook calls
        class MockTool:
            name = "analysis_tool"

        class MockContext:
            state = {"task": "adk_demo", "cumulative_cost": 0.0}

        tool = MockTool()
        ctx = MockContext()

        plugin.before_tool(tool, {"input": "data"}, tool_context=ctx)
        response = {"result": "3 anomalies detected"}
        plugin.after_tool(tool, {"input": "data"}, tool_context=ctx, tool_response=response)

        print(f"  Plugin commits: {len(engine.get_history())}")
        print("  OK (native ADK)")
    except ImportError:
        print("  google-adk not installed – showing interface only")
        print("  AgitPlugin wraps every ADK tool call with before/after commits")
        print("  Usage:")
        print("    engine = ExecutionEngine('./repo', agent_id='my_agent')")
        print("    plugin = AgitPlugin(engine)")
        print("    agent = Agent(..., plugins=[plugin])")
        print("  Install: pip install agit[google-adk]")


# ---------------------------------------------------------------------------
# OpenAI Agents SDK integration
# ---------------------------------------------------------------------------


def demo_openai_agents(tmp: str) -> None:
    print("\n--- OpenAI Agents SDK Integration ---")
    try:
        from agit.integrations.openai_agents import AgitAgentHooks  # type: ignore[import]

        engine = ExecutionEngine(repo_path=tmp, agent_id="openai-agent")
        hooks = AgitAgentHooks(engine)
        print(f"  AgitAgentHooks loaded, engine ready")
        print("  OK (native OpenAI)")
    except ImportError:
        print("  openai-agents not installed – showing interface only")
        print("  AgitAgentHooks wraps OpenAI Agent lifecycle hooks")
        print("  Usage:")
        print("    engine = ExecutionEngine('./repo', agent_id='my_agent')")
        print("    hooks = AgitAgentHooks(engine)")
        print("    agent = Agent(..., hooks=hooks)")
        print("  Install: pip install agit[openai]")


# ---------------------------------------------------------------------------
# Claude Agent SDK integration
# ---------------------------------------------------------------------------


def demo_claude_sdk(tmp: str) -> None:
    print("\n--- Claude Agent SDK Integration ---")
    try:
        from agit.integrations.claude_sdk import AgitClaudeHooks  # type: ignore[import]

        engine = ExecutionEngine(repo_path=tmp, agent_id="claude-agent")
        hooks = AgitClaudeHooks(engine)
        print("  AgitClaudeHooks loaded, engine ready")
        print("  OK (native Claude)")
    except ImportError:
        print("  claude-agent-sdk not installed – showing interface only")
        print("  AgitClaudeHooks integrates with Claude Agent SDK lifecycle")
        print("  Usage:")
        print("    engine = ExecutionEngine('./repo', agent_id='claude_agent')")
        print("    hooks = AgitClaudeHooks(engine)")
        print("    # Register with Claude Agent SDK hook registry")
        print("  Install: pip install agit[claude]")


# ---------------------------------------------------------------------------
# Cross-SDK feature summary
# ---------------------------------------------------------------------------


def show_feature_summary() -> None:
    print(f"\n{'─'*60}")
    print("  All integrations share the same agit core features:")
    features = [
        ("Content-addressed storage", "Every state snapshot stored as SHA-256 hash"),
        ("Auto-commit on actions",    "Before/after commits wrap every tool call"),
        ("Branch-per-retry",          "Isolated branches for safe re-execution"),
        ("Full audit trail",          "Every commit recorded with author + timestamp"),
        ("Instant rollback",          "Revert to any previous state in <5s"),
        ("Cross-framework diff",      "Compare states across any two commits"),
        ("MCP server",                "Expose agit tools over Model Context Protocol"),
    ]
    for name, desc in features:
        print(f"  + {name:<28} {desc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print(f"\n{'='*60}")
    print("  agit Multi-SDK Demo")
    print("  Same workflow, multiple AI agent frameworks")
    print(f"{'='*60}")

    with tempfile.TemporaryDirectory() as tmp:
        import os
        demo_standalone(os.path.join(tmp, "standalone"))
        demo_google_adk(os.path.join(tmp, "adk"))
        demo_openai_agents(os.path.join(tmp, "openai"))
        demo_claude_sdk(os.path.join(tmp, "claude"))

    show_feature_summary()
    print(f"\n{'='*60}\n  Demo complete.\n{'='*60}\n")


if __name__ == "__main__":
    main()
