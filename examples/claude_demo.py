"""Claude API + agit versioning demo.

Run with --mock for offline testing, or provide ANTHROPIC_API_KEY for real API calls.

Usage:
    python examples/claude_demo.py --mock
    ANTHROPIC_API_KEY=sk-... python examples/claude_demo.py
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agit.engine.executor import ExecutionEngine
from agit.engine.retry import RetryEngine


# ---------------------------------------------------------------------------
# Mock responses
# ---------------------------------------------------------------------------

MOCK_RESPONSES = [
    {
        "role": "assistant",
        "content": "Quantum computing uses quantum mechanical phenomena like "
        "superposition and entanglement to process information. Unlike "
        "classical bits (0 or 1), quantum bits (qubits) can exist in "
        "multiple states simultaneously, enabling parallel computation.",
        "model": "claude-sonnet-4-20250514-mock",
        "usage": {"input_tokens": 18, "output_tokens": 45},
    },
    {
        "role": "assistant",
        "content": "Here are three key benefits of version control for AI agents:\n\n"
        "1. **Auditability**: Every decision is tracked with full context\n"
        "2. **Rollback**: Bad decisions can be reverted instantly\n"
        "3. **Branching**: Multiple strategies can be explored in parallel",
        "model": "claude-sonnet-4-20250514-mock",
        "usage": {"input_tokens": 22, "output_tokens": 55},
    },
    {
        "role": "assistant",
        "content": "To implement a binary search tree in Python:\n\n"
        "class Node:\n"
        "    def __init__(self, val):\n"
        "        self.val = val\n"
        "        self.left = self.right = None\n\n"
        "class BST:\n"
        "    def __init__(self):\n"
        "        self.root = None\n\n"
        "    def insert(self, val):\n"
        "        self.root = self._insert(self.root, val)\n\n"
        "    def _insert(self, node, val):\n"
        "        if not node: return Node(val)\n"
        "        if val < node.val: node.left = self._insert(node.left, val)\n"
        "        else: node.right = self._insert(node.right, val)\n"
        "        return node",
        "model": "claude-sonnet-4-20250514-mock",
        "usage": {"input_tokens": 15, "output_tokens": 92},
    },
]

PROMPTS = [
    "Explain quantum computing in 2-3 sentences.",
    "What are the benefits of version control for AI agents?",
    "Implement a binary search tree in Python.",
]


def call_claude(prompt: str, mock: bool = True, _idx: int = 0) -> dict:
    """Call Claude API or return mock response."""
    if mock:
        time.sleep(0.1)
        return MOCK_RESPONSES[_idx % len(MOCK_RESPONSES)]

    try:
        import anthropic

        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return {
            "role": "assistant",
            "content": message.content[0].text,
            "model": message.model,
            "usage": {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            },
        }
    except Exception as e:
        print(f"Claude API error: {e}")
        print("Falling back to mock response.")
        return MOCK_RESPONSES[_idx % len(MOCK_RESPONSES)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Claude + agit versioning demo")
    parser.add_argument("--mock", action="store_true", default=False, help="Use mock responses")
    args = parser.parse_args()

    use_mock = args.mock
    if not use_mock:
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("No ANTHROPIC_API_KEY found. Using --mock mode.")
            use_mock = True

    with tempfile.TemporaryDirectory() as tmp:
        engine = ExecutionEngine(repo_path=tmp, agent_id="claude-agent")
        retry_engine = RetryEngine(engine, max_retries=2, base_delay=0.5)

        print("=" * 60)
        print("Claude + AgentGit Versioning Demo")
        print("=" * 60)
        print(f"Mode: {'MOCK' if use_mock else 'LIVE API'}")
        print(f"Repo: {tmp}\n")

        all_hashes = []
        for i, prompt in enumerate(PROMPTS):
            print(f"\n--- Prompt {i + 1}: {prompt[:50]}... ---")

            input_state = {
                "memory": {"conversation": [], "step": i + 1},
                "world_state": {"prompt": prompt, "model": "claude-sonnet-4-20250514"},
            }
            h1 = engine.commit_state(input_state, f"user_input: {prompt[:40]}", "user_input")
            all_hashes.append(h1)
            print(f"  Committed input: {h1[:12]}")

            def _call(state: dict, idx: int = i, mock: bool = use_mock) -> dict:
                resp = call_claude(state["world_state"]["prompt"], mock=mock, _idx=idx)
                state["memory"]["conversation"].append({"role": "user", "content": state["world_state"]["prompt"]})
                state["memory"]["conversation"].append(resp)
                state["world_state"]["last_response"] = resp["content"]
                state["world_state"]["tokens"] = resp["usage"]
                return state

            result, h2 = engine.execute(_call, input_state, f"llm_response: {prompt[:40]}", "llm_response")
            all_hashes.append(h2)
            print(f"  Committed response: {h2[:12]}")
            tokens = result["world_state"].get("tokens", {})
            print(f"  Tokens: input={tokens.get('input_tokens', 0)}, output={tokens.get('output_tokens', 0)}")
            print(f"  Response: {result['world_state']['last_response'][:80]}...")

            diff = engine.diff(h1, h2)
            print(f"  Diff entries: {len(diff.get('entries', []))}")

            if i == len(PROMPTS) - 1:
                print("\n--- Branching for alternative strategy ---")
                engine.branch("alternative")
                engine.checkout("alternative")
                result2, h3 = engine.execute(_call, input_state, "alternative: different approach", "retry")
                print(f"  Alternative committed: {h3[:12]}")

                engine.checkout("main")
                merge_hash = engine.merge("alternative")
                print(f"  Merged alternative: {merge_hash[:12]}")

        print("\n" + "=" * 60)
        print("Commit History")
        print("=" * 60)
        for entry in engine.get_history(20):
            print(f"  {entry['hash'][:12]}  [{entry['action_type']:>12}]  {entry['message'][:50]}")

        print(f"\nBranches: {list(engine.list_branches().keys())}")
        print(f"Current branch: {engine.current_branch()}")
        print("\nDemo complete!")


if __name__ == "__main__":
    main()
