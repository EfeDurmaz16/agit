#!/usr/bin/env python3
"""Google ADK + agit integration demo.

Demonstrates using AgitPlugin with Google ADK for
automatic tool execution versioning.

Usage:
    pip install agit[google-adk]
    python examples/google_adk_demo.py
"""
from __future__ import annotations


def main():
    """Run the Google ADK + agit demo."""
    try:
        from agit.integrations.google_adk import AgitPlugin
    except ImportError:
        print("Google ADK integration not available.")
        print("Install with: pip install agit[google-adk]")
        return

    print("=== Google ADK + agit Demo ===\n")

    plugin = AgitPlugin(repo_path="/tmp/agit-google-adk-demo")
    print("Created AgitPlugin\n")

    # Simulate before/after tool hooks
    print("--- Tool Execution with Versioning ---")

    class MockToolContext:
        def __init__(self, name: str, args: dict):
            self.tool_name = name
            self.arguments = args
            self.result = None

    tools = [
        MockToolContext("search", {"query": "AI trends 2024"}),
        MockToolContext("calculator", {"expression": "42 * 3.14"}),
        MockToolContext("write_file", {"path": "output.txt", "content": "results"}),
    ]

    for tool_ctx in tools:
        print(f"\n  Tool: {tool_ctx.tool_name}({tool_ctx.arguments})")

        # Before hook
        try:
            plugin.before_tool(tool_ctx)
            print("    [before_tool] State checkpointed")
        except Exception as e:
            print(f"    [before_tool] (noted: {e})")

        # Simulate tool execution
        tool_ctx.result = f"Result of {tool_ctx.tool_name}"

        # After hook
        try:
            plugin.after_tool(tool_ctx)
            print(f"    [after_tool] Result committed: {tool_ctx.result}")
        except Exception as e:
            print(f"    [after_tool] (noted: {e})")

    print("\n=== Demo Complete ===")
    print("agit plugin automatically versions Google ADK tool executions.")


if __name__ == "__main__":
    main()
