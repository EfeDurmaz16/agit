"""Multi-agent swarm demo: 3 agents collaborate on a research task.

Usage:
    python examples/swarm_demo.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agit.engine.executor import ExecutionEngine
from agit.swarm.orchestrator import SwarmOrchestrator


def main() -> None:
    print("=" * 60)
    print("Multi-Agent Swarm Demo")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        orch = SwarmOrchestrator(tmp)

        agents = ["searcher", "summarizer", "synthesizer"]
        task = "Research recent advances in AI agent memory systems"

        print(f"\nTask: {task}")
        print(f"Agents: {agents}")

        # Decompose
        subtasks = orch.decompose(task, num_agents=len(agents))
        print(f"\nDecomposed into {len(subtasks)} sub-tasks:")
        for st in subtasks:
            deps = f" (depends on: {st.dependencies})" if st.dependencies else ""
            print(f"  [{st.id[:6]}] {st.description[:60]}{deps}")

        # Assign
        assignment = orch.assign(subtasks, agents)
        print("\nAssignment:")
        for agent_id, tasks in assignment.items():
            print(f"  {agent_id}: {len(tasks)} task(s)")

        # Execute
        print("\nExecuting...")
        result = orch.execute(task, agents)

        print(f"\nCompleted in {result['duration']:.2f}s")
        print(f"Sub-tasks: {len(result['subtasks'])}")
        for st in result["subtasks"]:
            print(f"  [{st['id'][:6]}] {st['status']:>10}  {st['assigned_agent']:<15} {st['description'][:40]}")

        # Show audit trail
        engine = ExecutionEngine(repo_path=tmp, agent_id="demo")
        history = engine.get_history(20)
        print(f"\nAudit trail ({len(history)} commits):")
        for entry in history:
            print(f"  {entry['hash'][:12]}  {entry['message'][:50]}")

        print("\nDemo complete!")


if __name__ == "__main__":
    main()
