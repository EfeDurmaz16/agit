"""Multi-SDK demo: Same workflow across different AI agent frameworks.

Shows how agit integrates with Google ADK, OpenAI Agents, and Claude SDK.
"""

from __future__ import annotations

import json
import tempfile


def demo_google_adk() -> None:
    """Demonstrate Google ADK integration."""
    print("\n--- Google ADK Integration ---")
    try:
        from agit.integrations.google_adk import AgitPlugin
        print("  AgitPlugin available")
        print("  Usage: plugin = AgitPlugin(repo_path='/tmp/adk-agent')")
        print("  Then add to your ADK agent's plugins list")
    except ImportError:
        print("  google-adk not installed. pip install agit[google-adk]")


def demo_openai_agents() -> None:
    """Demonstrate OpenAI Agents SDK integration."""
    print("\n--- OpenAI Agents SDK Integration ---")
    try:
        from agit.integrations.openai_agents import AgitAgentHooks
        print("  AgitAgentHooks available")
        print("  Usage: hooks = AgitAgentHooks(repo_path='/tmp/openai-agent')")
        print("  Then pass as hooks parameter to your Agent")
    except ImportError:
        print("  openai-agents not installed. pip install agit[openai]")


def demo_claude_sdk() -> None:
    """Demonstrate Claude Agent SDK integration."""
    print("\n--- Claude Agent SDK Integration ---")
    try:
        from agit.integrations.claude_sdk import AgitClaudeHooks
        print("  AgitClaudeHooks available")
        print("  Usage: hooks = AgitClaudeHooks(repo_path='/tmp/claude-agent')")
        print("  Register with Claude Agent SDK hook system")
    except ImportError:
        print("  claude-agent-sdk not installed. pip install agit[claude]")


def demo_standalone() -> None:
    """Demonstrate standalone agit usage."""
    print("\n--- Standalone AgentGit ---")
    from agit.engine.executor import ExecutionEngine

    with tempfile.TemporaryDirectory() as tmp:
        engine = ExecutionEngine(repo_path=tmp, agent_id="demo-agent")

        def step_one(state: dict) -> dict:
            state["memory"]["step"] = 1
            state["memory"]["data"] = "analyzed"
            return state

        def step_two(state: dict) -> dict:
            state["memory"]["step"] = 2
            state["memory"]["result"] = "completed"
            return state

        initial = {"memory": {}, "world_state": {}}
        state = engine.execute(step_one, initial, "analysis step")
        state = engine.execute(step_two, state, "completion step")

        print(f"  Final state: {json.dumps(state['memory'])}")
        print(f"  Commits: {len(engine.get_history())}")


def main() -> None:
    print("=== AgentGit Multi-SDK Demo ===")
    print("Showing integration across different AI agent frameworks")

    demo_standalone()
    demo_google_adk()
    demo_openai_agents()
    demo_claude_sdk()

    print("\n\nAll integrations share the same agit core:")
    print("  - Content-addressed state storage")
    print("  - Branch-per-retry for safe exploration")
    print("  - Full audit trail for compliance")
    print("  - Instant rollback to any point")

    print("\nDone!")


if __name__ == "__main__":
    main()
