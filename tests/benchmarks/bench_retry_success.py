"""Benchmark: retry success rate across various failure rates.

Target: >96% success rate with max_retries=3.

Run directly:
    python tests/benchmarks/bench_retry_success.py

Or via pytest:
    pytest tests/benchmarks/bench_retry_success.py -v -s
"""
from __future__ import annotations

import random
import statistics
import time
from typing import Any

from agit import ExecutionEngine, RetryEngine


def make_flaky_action(failure_rate: float) -> Any:
    """Return an action that fails with probability *failure_rate* on each call."""

    def action(state: dict[str, Any]) -> dict[str, Any]:
        if random.random() < failure_rate:
            raise RuntimeError(f"transient failure (rate={failure_rate:.2f})")
        return {**state, "memory": {**state.get("memory", {}), "done": True}}

    return action


def run_benchmark(
    failure_rate: float,
    n_trials: int = 200,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Run *n_trials* retry attempts at *failure_rate* and collect statistics."""
    successes = 0
    elapsed_times: list[float] = []
    attempt_counts: list[int] = []

    base_state: dict[str, Any] = {
        "memory": {"cumulative_cost": 0.0},
        "world_state": {},
    }

    for _ in range(n_trials):
        executor = ExecutionEngine(":memory:", agent_id="bench")
        retry_eng = RetryEngine(executor, max_retries=max_retries, base_delay=0.0)
        action = make_flaky_action(failure_rate)

        t0 = time.monotonic()
        try:
            _, history = retry_eng.execute_with_retry(action, base_state, "bench action")
            successes += 1
            attempt_counts.append(history.total_attempts)
        except RuntimeError:
            attempt_counts.append(max_retries + 1)
        elapsed_times.append(time.monotonic() - t0)

    success_rate = successes / n_trials
    return {
        "failure_rate": failure_rate,
        "n_trials": n_trials,
        "max_retries": max_retries,
        "successes": successes,
        "success_rate": success_rate,
        "avg_attempts": statistics.mean(attempt_counts),
        "avg_elapsed_ms": statistics.mean(elapsed_times) * 1000,
        "p95_elapsed_ms": sorted(elapsed_times)[int(0.95 * len(elapsed_times))] * 1000,
    }


def print_report(results: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 72)
    print(f"{'Bench: Retry Success Rate':^72}")
    print("=" * 72)
    header = f"{'failure_rate':>14} {'trials':>7} {'success%':>10} {'avg_attempts':>13} {'avg_ms':>9}"
    print(header)
    print("-" * 72)
    all_pass = True
    for r in results:
        status = "OK" if r["success_rate"] >= 0.96 else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(
            f"{r['failure_rate']:>14.0%} "
            f"{r['n_trials']:>7} "
            f"{r['success_rate']:>9.1%}  "
            f"{r['avg_attempts']:>12.2f} "
            f"{r['avg_elapsed_ms']:>8.2f}ms "
            f" [{status}]"
        )
    print("=" * 72)
    print(f"Overall: {'PASS' if all_pass else 'FAIL'} (target: >96% success rate)\n")


def main() -> None:
    random.seed(42)
    failure_rates = [0.10, 0.20, 0.30, 0.40, 0.50]
    results = []
    for rate in failure_rates:
        print(f"  Running failure_rate={rate:.0%} ...")
        r = run_benchmark(failure_rate=rate, n_trials=200, max_retries=3)
        results.append(r)
    print_report(results)


# ---------------------------------------------------------------------------
# pytest-compatible test
# ---------------------------------------------------------------------------


def test_bench_retry_success_rate() -> None:
    """Benchmark guard: >96% success rate at <=50% per-attempt failure rate."""
    random.seed(0)
    result = run_benchmark(failure_rate=0.50, n_trials=100, max_retries=3)
    assert result["success_rate"] >= 0.96, (
        f"Success rate {result['success_rate']:.1%} below 96% target"
    )


def test_bench_retry_success_rate_low_failure() -> None:
    random.seed(1)
    result = run_benchmark(failure_rate=0.20, n_trials=100, max_retries=3)
    assert result["success_rate"] >= 0.99


if __name__ == "__main__":
    main()
