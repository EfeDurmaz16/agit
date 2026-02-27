#!/usr/bin/env python3
"""Google A2A (Agent-to-Agent) protocol + agit integration demo.

Demonstrates using AgitA2AExecutor to automatically version
all A2A message exchanges with agit audit trail.

Usage:
    pip install agit[a2a]
    python examples/a2a_demo.py
"""
from __future__ import annotations


def main():
    """Run the A2A + agit demo."""
    try:
        from agit.integrations.a2a import AgitA2AExecutor, AgitA2AClient, create_agent_card
    except ImportError:
        print("A2A integration not available.")
        print("Install with: pip install agit[a2a]")
        return

    print("=== Google A2A + agit Demo ===\n")

    # --- Server-side: AgitA2AExecutor ---
    print("--- Server-Side: A2A Executor with agit Versioning ---\n")

    from agit.engine.executor import ExecutionEngine

    engine = ExecutionEngine("/tmp/agit-a2a-demo", agent_id="a2a-agent")
    executor = AgitA2AExecutor(engine, branch_per_context=True)
    print("Created AgitA2AExecutor with branch-per-context enabled\n")

    # Create an Agent Card
    card = create_agent_card(
        name="Agit Demo Agent",
        description="An A2A agent with full state versioning via agit",
        url="http://localhost:9999/",
        skills=[
            {
                "id": "state_versioning",
                "name": "State Versioning",
                "description": "Git-like version control for agent state",
                "tags": ["versioning", "audit"],
                "examples": ["Track my state", "Show history"],
            },
            {
                "id": "rollback",
                "name": "State Rollback",
                "description": "Revert agent state to any previous checkpoint",
                "tags": ["rollback", "recovery"],
                "examples": ["Revert to last checkpoint"],
            },
        ],
    )
    print(f"Agent Card: {card.get('name', getattr(card, 'name', 'unknown'))}")
    print(f"  Skills: {len(card.get('skills', getattr(card, 'skills', [])))} registered\n")

    # Simulate A2A message processing
    print("--- Simulating A2A Message Exchange ---\n")

    class MockPart:
        def __init__(self, text: str):
            self.kind = "text"
            self.text = text

    class MockMessage:
        def __init__(self, role: str, text: str, context_id: str = None, task_id: str = None):
            self.role = role
            self.parts = [MockPart(text)]
            self.messageId = f"msg-{id(self)}"
            self.contextId = context_id
            self.taskId = task_id

    class MockParams:
        def __init__(self, message):
            self.message = message

    class MockContext:
        def __init__(self, message):
            self.params = MockParams(message)

    messages = [
        MockMessage("user", "What tools do you have available?", context_id="ctx-001"),
        MockMessage("user", "Search for recent AI papers", context_id="ctx-001", task_id="task-001"),
        MockMessage("user", "Summarize the top 3 results", context_id="ctx-001", task_id="task-002"),
    ]

    import asyncio

    class MockEventQueue:
        async def enqueue_event(self, event):
            print(f"    [event] Agent response queued")

    async def run_messages():
        event_queue = MockEventQueue()
        for msg in messages:
            text = msg.parts[0].text
            print(f"  [{msg.role}] {text}")
            print(f"    context={msg.contextId}, task={msg.taskId}")

            ctx = MockContext(msg)
            try:
                await executor.execute(ctx, event_queue)
                print("    [agit] State committed\n")
            except Exception as e:
                print(f"    [agit] (noted: {e})\n")

    asyncio.run(run_messages())

    # Show version history
    print("--- agit Version History ---\n")
    try:
        history = engine.get_history(limit=10)
        for i, commit in enumerate(history):
            msg = commit.get("message", "")
            print(f"  {i + 1}. {msg}")
    except Exception as e:
        print(f"  (history: {e})")

    # --- Client-side demo ---
    print("\n--- Client-Side: A2A Discovery + Messaging ---\n")

    client = AgitA2AClient(engine, base_url="http://localhost:9999")
    print(f"Created AgitA2AClient targeting {client._base_url}")
    print("  (In production, client.discover() fetches the remote Agent Card)")
    print("  (Then client.send_message() exchanges messages with full agit audit trail)")

    print("\n=== Demo Complete ===")
    print("A2A + agit provides:")
    print("  - Automatic versioning of all A2A message exchanges")
    print("  - Branch-per-context isolation for parallel conversations")
    print("  - Full audit trail with rollback capability")
    print("  - Agent Card discovery tracking")


if __name__ == "__main__":
    main()
