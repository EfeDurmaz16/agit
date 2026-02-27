#!/usr/bin/env python3
"""CrewAI + agit integration demo.

Demonstrates using agit callbacks with CrewAI for
step-by-step version control of multi-agent tasks.

Usage:
    pip install agit[crewai]
    python examples/crewai_demo.py
"""
from __future__ import annotations


def main():
    """Run the CrewAI + agit demo."""
    try:
        from agit.integrations.crewai import agit_step_callback, agit_task_callback
    except ImportError:
        print("CrewAI integration not available.")
        print("Install with: pip install agit[crewai]")
        return

    print("=== CrewAI + agit Demo ===\n")

    # Simulate CrewAI step and task callbacks
    print("Simulating CrewAI agent workflow with agit versioning...\n")

    # Mock step output
    class MockStepOutput:
        def __init__(self, text: str, tool: str = ""):
            self.text = text
            self.tool = tool

    # Simulate step callbacks
    steps = [
        MockStepOutput("Searching for information...", tool="search"),
        MockStepOutput("Found 3 relevant documents", tool="search"),
        MockStepOutput("Analyzing document content...", tool="analyze"),
        MockStepOutput("Generated summary report", tool="summarize"),
    ]

    for i, step in enumerate(steps, 1):
        print(f"  Step {i}: {step.text}")
        try:
            agit_step_callback(step)
        except Exception as e:
            print(f"    (callback noted: {e})")

    # Mock task output
    class MockTaskOutput:
        def __init__(self, description: str, result: str):
            self.description = description
            self.raw = result

    task = MockTaskOutput(
        description="Research and summarize AI trends",
        result="AI trends summary: LLMs, agents, multimodal models...",
    )
    print(f"\n  Task complete: {task.description}")
    try:
        agit_task_callback(task)
    except Exception as e:
        print(f"    (callback noted: {e})")

    print("\n=== Demo Complete ===")
    print("agit records each CrewAI step and task as versioned commits.")


if __name__ == "__main__":
    main()
