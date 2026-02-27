#!/usr/bin/env python3
"""LangGraph + agit integration demo.

Demonstrates using AgitCheckpointSaver with LangGraph workflows
for persistent, version-controlled agent state management.

Usage:
    pip install agit[langgraph]
    python examples/langgraph_demo.py
"""
from __future__ import annotations

import json


def main():
    """Run the LangGraph + agit demo."""
    try:
        from agit.integrations.langgraph import AgitCheckpointSaver
    except ImportError:
        print("LangGraph integration not available.")
        print("Install with: pip install agit[langgraph]")
        return

    # Create an agit-backed checkpoint saver
    saver = AgitCheckpointSaver(repo_path="/tmp/agit-langgraph-demo")

    # Simulate a LangGraph workflow with checkpointing
    print("=== LangGraph + agit Demo ===\n")

    # Simulate thread-aware checkpointing
    thread_id = "thread-001"
    config = {"configurable": {"thread_id": thread_id}}

    # Step 1: Initial state
    state_v1 = {
        "messages": [{"role": "user", "content": "What is the weather?"}],
        "step": 1,
    }
    print(f"Step 1: Saving initial state for thread {thread_id}")
    checkpoint_1 = {
        "v": 1,
        "id": "cp-001",
        "ts": "2024-01-01T00:00:00Z",
        "channel_values": state_v1,
    }
    saver.put(config, checkpoint_1, {"source": "input", "step": 1})
    print(f"  Checkpoint saved: {json.dumps(state_v1, indent=2)[:80]}...")

    # Step 2: After tool call
    state_v2 = {
        "messages": [
            {"role": "user", "content": "What is the weather?"},
            {"role": "assistant", "content": "Let me check the weather API."},
        ],
        "step": 2,
        "tool_calls": [{"name": "get_weather", "args": {"city": "NYC"}}],
    }
    print(f"\nStep 2: Saving state after tool call")
    checkpoint_2 = {
        "v": 1,
        "id": "cp-002",
        "ts": "2024-01-01T00:00:01Z",
        "channel_values": state_v2,
    }
    saver.put(config, checkpoint_2, {"source": "loop", "step": 2})
    print(f"  Checkpoint saved with {len(state_v2['messages'])} messages")

    # Retrieve latest checkpoint
    print(f"\nRetrieving latest checkpoint for thread {thread_id}...")
    latest = saver.get(config)
    if latest:
        print(f"  Latest checkpoint step: {latest.get('channel_values', {}).get('step')}")
    else:
        print("  No checkpoint found (expected with stub implementation)")

    # List checkpoints
    print(f"\nListing checkpoint history for thread {thread_id}...")
    checkpoints = list(saver.list(config, limit=10))
    print(f"  Found {len(checkpoints)} checkpoints")

    print("\n=== Demo Complete ===")
    print("agit provides persistent, version-controlled checkpointing for LangGraph workflows.")


if __name__ == "__main__":
    main()
