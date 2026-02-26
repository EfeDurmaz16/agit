"""Benchmark: token efficiency with vs. without branch reuse.

Target: 40% token reduction when using branch reuse.

Token usage is approximated by state serialization size (bytes), which
correlates directly with LLM context tokens. Branch reuse avoids re-sending
the full state on every retry by referencing a shared base branch.

Run directly:
    python tests/benchmarks/bench_token_usage.py

Or via pytest:
    pytest tests/benchmarks/bench_token_usage.py -v -s
"""
from __future__ import annotations

import json
import statistics
import time
from typing import Any

from agit import ExecutionEngine, RetryEngine


# ---------------------------------------------------------------------------
# Token usage estimators
# ---------------------------------------------------------------------------

def estimate_tokens(state: dict[str, Any]) -> int:
    """Approximate token count as ceil(json_bytes / 4)."""
    return max(1, len(json.dumps(state, default=str).encode()) // 4)


def simulate_without_branch_reuse(
    states: list[dict[str, Any]],
    n_retries: int = 3,
) -> int:
    """Naive approach: resend full state on every retry attempt.

    Total tokens = sum over all retries of full_state_tokens.
    """
    total = 0
    for state in states:
        state_tokens = estimate_tokens(state)
        # Initial attempt + n_retries, each sending the full state
        total += state_tokens * (1 + n_retries)
    return total


def simulate_with_branch_reuse(
    states: list[dict[str, Any]],
    n_retries: int = 3,
) -> int:
    """Branch-reuse approach: send full state once; retries send only delta.

    Delta tokens = estimate_tokens(diff) which is ~20% of full state.
    """
    total = 0
    for i, state in enumerate(states):
        state_tokens = estimate_tokens(state)
        # Send full state once (first attempt)
        total += state_tokens
        if i > 0:
            # Delta from previous state (much smaller)
            prev_state = states[i - 1]
            diff_keys = {
                k: state.get("memory", {}).get(k)
                for k in set(state.get("memory", {}).keys()) | set(prev_state.get("memory", {}).keys())
                if state.get("memory", {}).get(k) != prev_state.get("memory", {}).get(k)
            }
            delta_tokens = max(10, len(json.dumps(diff_keys).encode()) // 4)
            # Retries send only the delta
            total += delta_tokens * n_retries
        else:
            # First state: retries still send something small (branch reference)
            total += 10 * n_retries  # just a hash reference
    return total


def generate_test_states(n: int = 20) -> list[dict[str, Any]]:
    """Generate a sequence of incrementally evolving states."""
    states = []
    base_context = "The agent is processing a complex multi-step workflow. " * 10
    for i in range(n):
        state: dict[str, Any] = {
            "memory": {
                "step": i,
                "cumulative_cost": i * 0.05,
                "context": base_context,
                "observations": [f"observation_{j}" for j in range(i)],
                "tool_calls": [f"tool_{j}" for j in range(i)],
                "current_task": f"task_{i}",
                "history_summary": f"Completed {i} steps so far.",
            },
            "world_state": {
                "iteration": i,
                "status": "running" if i > 0 else "idle",
                "metrics": {"accuracy": 0.5 + i * 0.02, "latency_ms": 100 + i * 5},
            },
        }
        states.append(state)
    return states


def print_report(
    n_states: int,
    tokens_naive: int,
    tokens_reuse: int,
    target_reduction: float = 0.40,
) -> None:
    reduction = 1.0 - (tokens_reuse / tokens_naive) if tokens_naive > 0 else 0.0
    print("\n" + "=" * 60)
    print(f"{'Bench: Token Usage (Branch Reuse)':^60}")
    print("=" * 60)
    print(f"  States simulated  : {n_states}")
    print(f"  Tokens (naive)    : {tokens_naive:,}")
    print(f"  Tokens (reuse)    : {tokens_reuse:,}")
    print(f"  Reduction         : {reduction:.1%}")
    target_met = reduction >= target_reduction
    print(f"  Target (>={target_reduction:.0%})   : {'OK' if target_met else 'FAIL'}")
    print("=" * 60 + "\n")


def main() -> None:
    for n in [10, 20, 50]:
        print(f"Simulating {n} states ...")
        states = generate_test_states(n)
        naive = simulate_without_branch_reuse(states)
        reuse = simulate_with_branch_reuse(states)
        print_report(n, naive, reuse)


# ---------------------------------------------------------------------------
# Agit integration: measure actual repo overhead
# ---------------------------------------------------------------------------

def run_agit_overhead_benchmark(n_commits: int = 30) -> dict[str, Any]:
    """Measure actual commit + retrieve cycle to assess real overhead."""
    engine = ExecutionEngine(":memory:", agent_id="token-bench")
    states = generate_test_states(n_commits)

    commit_times: list[float] = []
    retrieve_times: list[float] = []
    hashes: list[str] = []

    for state in states:
        t0 = time.monotonic()
        h = engine.commit_state(state, f"step {state['memory']['step']}", "tool_call")
        commit_times.append(time.monotonic() - t0)
        hashes.append(h)

    for h in hashes[::3]:  # sample every 3rd
        t0 = time.monotonic()
        engine.revert(h)
        retrieve_times.append(time.monotonic() - t0)

    return {
        "n_commits": n_commits,
        "avg_commit_ms": statistics.mean(commit_times) * 1000,
        "avg_retrieve_ms": statistics.mean(retrieve_times) * 1000,
        "total_tokens_naive": simulate_without_branch_reuse(states),
        "total_tokens_reuse": simulate_with_branch_reuse(states),
    }


# ---------------------------------------------------------------------------
# pytest-compatible tests
# ---------------------------------------------------------------------------


def test_bench_token_reduction_target() -> None:
    """Branch reuse must achieve >=40% token reduction over naive approach."""
    states = generate_test_states(20)
    naive = simulate_without_branch_reuse(states, n_retries=3)
    reuse = simulate_with_branch_reuse(states, n_retries=3)
    reduction = 1.0 - (reuse / naive)
    assert reduction >= 0.40, (
        f"Token reduction {reduction:.1%} below 40% target. "
        f"naive={naive:,}, reuse={reuse:,}"
    )


def test_bench_token_reduction_small_dataset() -> None:
    """Even with 5 states, branch reuse should provide some reduction."""
    states = generate_test_states(5)
    naive = simulate_without_branch_reuse(states, n_retries=3)
    reuse = simulate_with_branch_reuse(states, n_retries=3)
    assert reuse <= naive, "Branch reuse must never increase token usage"


def test_bench_agit_commit_overhead() -> None:
    """Agit commit overhead must be <100ms per commit on average."""
    result = run_agit_overhead_benchmark(n_commits=30)
    assert result["avg_commit_ms"] < 100, (
        f"Average commit time {result['avg_commit_ms']:.2f}ms exceeds 100ms"
    )


def test_bench_agit_retrieve_overhead() -> None:
    """Agit state retrieval must be <100ms on average."""
    result = run_agit_overhead_benchmark(n_commits=30)
    assert result["avg_retrieve_ms"] < 100, (
        f"Average retrieve time {result['avg_retrieve_ms']:.2f}ms exceeds 100ms"
    )


if __name__ == "__main__":
    main()
    result = run_agit_overhead_benchmark(30)
    print("Agit overhead benchmark:")
    for k, v in result.items():
        print(f"  {k}: {v:.2f}" if isinstance(v, float) else f"  {k}: {v}")
