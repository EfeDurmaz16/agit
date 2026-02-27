#!/usr/bin/env python3
"""OpenClaw + agit integration demo.

Demonstrates using AgitOpenClawSkill for action dispatching
and webhook handling with agit version control.

Usage:
    python examples/openclaw_demo.py
"""
from __future__ import annotations


def main():
    """Run the OpenClaw + agit demo."""
    try:
        from agit.integrations.openclaw import AgitOpenClawSkill
    except ImportError:
        print("OpenClaw integration not available.")
        print("This integration is included in the base agit package.")
        return

    print("=== OpenClaw + agit Demo ===\n")

    skill = AgitOpenClawSkill(repo_path="/tmp/agit-openclaw-demo")
    print("Created AgitOpenClawSkill\n")

    # Action dispatcher demo
    actions = [
        ("commit", {"state": {"step": 1}, "message": "initial state"}),
        ("log", {"limit": 5}),
        ("branch", {"name": "experiment-1"}),
        ("checkout", {"target": "experiment-1"}),
        ("commit", {"state": {"step": 2, "result": "success"}, "message": "experiment result"}),
    ]

    for action_name, params in actions:
        print(f"  Action: {action_name}({params})")
        try:
            result = skill.dispatch(action_name, params)
            print(f"    Result: {result}")
        except Exception as e:
            print(f"    (noted: {e})")

    # Webhook handler demo
    print("\n--- Webhook Handler ---")
    webhook_payload = {
        "event": "agent.complete",
        "agent_id": "demo-agent",
        "data": {"status": "success", "output": "Task completed"},
    }
    print(f"  Webhook: {webhook_payload['event']}")
    try:
        skill.handle_webhook(webhook_payload)
        print("  Webhook processed and committed to agit")
    except Exception as e:
        print(f"    (noted: {e})")

    print("\n=== Demo Complete ===")
    print("agit integrates with OpenClaw for skill-based agent version control.")


if __name__ == "__main__":
    main()
