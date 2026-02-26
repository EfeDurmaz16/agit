"""OpenAI API + agit versioning demo.

Run with --mock for offline testing, or provide OPENAI_API_KEY for real API calls.

Usage:
    python examples/openai_demo.py --mock
    OPENAI_API_KEY=sk-... python examples/openai_demo.py
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

# Add parent to path for development
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agit.engine.executor import ExecutionEngine
from agit.engine.retry import RetryEngine


# ---------------------------------------------------------------------------
# Mock responses for offline testing
# ---------------------------------------------------------------------------

MOCK_RESPONSES = [
    {
        "role": "assistant",
        "content": "The capital of France is Paris. It has been the capital since "
        "the late 10th century and is the country's largest city with a "
        "population of over 2 million in the city proper.",
        "model": "gpt-4o-mock",
        "usage": {"prompt_tokens": 15, "completion_tokens": 42, "total_tokens": 57},
    },
    {
        "role": "assistant",
        "content": "Here's a Python quicksort implementation:\n\n"
        "def quicksort(arr):\n"
        "    if len(arr) <= 1:\n"
        "        return arr\n"
        "    pivot = arr[len(arr) // 2]\n"
        "    left = [x for x in arr if x < pivot]\n"
        "    middle = [x for x in arr if x == pivot]\n"
        "    right = [x for x in arr if x > pivot]\n"
        "    return quicksort(left) + middle + quicksort(right)",
        "model": "gpt-4o-mock",
        "usage": {"prompt_tokens": 12, "completion_tokens": 85, "total_tokens": 97},
    },
    {
        "role": "assistant",
        "content": "Machine learning is a subset of artificial intelligence that "
        "enables systems to learn and improve from experience without "
        "being explicitly programmed. Key types include supervised learning, "
        "unsupervised learning, and reinforcement learning.",
        "model": "gpt-4o-mock",
        "usage": {"prompt_tokens": 10, "completion_tokens": 38, "total_tokens": 48},
    },
]

PROMPTS = [
    "What is the capital of France? Give a brief answer.",
    "Write a Python quicksort implementation.",
    "Explain machine learning in 2-3 sentences.",
]


def call_openai(prompt: str, mock: bool = True, _idx: int = 0) -> dict:
    """Call OpenAI API or return mock response."""
    if mock:
        resp = MOCK_RESPONSES[_idx % len(MOCK_RESPONSES)]
        time.sleep(0.1)  # Simulate latency
        return resp

    try:
        from openai import OpenAI

        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
        )
        choice = response.choices[0]
        return {
            "role": "assistant",
            "content": choice.message.content,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        }
    except Exception as e:
        print(f"OpenAI API error: {e}")
        print("Falling back to mock response.")
        return MOCK_RESPONSES[_idx % len(MOCK_RESPONSES)]


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAI + agit versioning demo")
    parser.add_argument("--mock", action="store_true", default=False, help="Use mock responses")
    args = parser.parse_args()

    use_mock = args.mock
    if not use_mock:
        import os
        if not os.environ.get("OPENAI_API_KEY"):
            print("No OPENAI_API_KEY found. Using --mock mode.")
            use_mock = True

    with tempfile.TemporaryDirectory() as tmp:
        engine = ExecutionEngine(repo_path=tmp, agent_id="openai-agent")
        retry_engine = RetryEngine(engine, max_retries=2, base_delay=0.5)

        print("=" * 60)
        print("OpenAI + AgentGit Versioning Demo")
        print("=" * 60)
        print(f"Mode: {'MOCK' if use_mock else 'LIVE API'}")
        print(f"Repo: {tmp}\n")

        for i, prompt in enumerate(PROMPTS):
            print(f"\n--- Prompt {i + 1}: {prompt[:50]}... ---")

            # Commit user input
            input_state = {
                "memory": {"conversation": [], "step": i + 1},
                "world_state": {"prompt": prompt, "model": "gpt-4o"},
            }
            h1 = engine.commit_state(input_state, f"user_input: {prompt[:40]}", "user_input")
            print(f"  Committed input: {h1[:12]}")

            # Call LLM (with retry)
            def _call(state: dict, idx: int = i, mock: bool = use_mock) -> dict:
                resp = call_openai(state["world_state"]["prompt"], mock=mock, _idx=idx)
                state["memory"]["conversation"].append({"role": "user", "content": state["world_state"]["prompt"]})
                state["memory"]["conversation"].append(resp)
                state["world_state"]["last_response"] = resp["content"]
                state["world_state"]["tokens"] = resp["usage"]
                return state

            result, h2 = engine.execute(_call, input_state, f"llm_response: {prompt[:40]}", "llm_response")
            print(f"  Committed response: {h2[:12]}")
            print(f"  Tokens: {result['world_state'].get('tokens', {})}")
            print(f"  Response: {result['world_state']['last_response'][:80]}...")

            # Show diff
            diff = engine.diff(h1, h2)
            changes = diff.get("entries", [])
            print(f"  Diff entries: {len(changes)}")

            # Branch for retry demonstration on last prompt
            if i == len(PROMPTS) - 1:
                print("\n--- Retry demonstration ---")
                engine.branch("retry-1")
                engine.checkout("retry-1")
                result2, h3 = engine.execute(_call, input_state, "retry: alternative response", "retry")
                print(f"  Retry committed: {h3[:12]}")

                # Switch back to main
                engine.checkout("main")

        # Show full history
        print("\n" + "=" * 60)
        print("Commit History")
        print("=" * 60)
        for entry in engine.get_history(20):
            print(f"  {entry['hash'][:12]}  [{entry['action_type']:>12}]  {entry['message'][:50]}")

        # Show branches
        print(f"\nBranches: {list(engine.list_branches().keys())}")
        print(f"Current branch: {engine.current_branch()}")
        print("\nDemo complete!")


if __name__ == "__main__":
    main()
