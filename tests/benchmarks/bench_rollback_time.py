"""Benchmark: rollback speed across N commits.

Target: <5 seconds to rollback to any historical state.

Run directly:
    python tests/benchmarks/bench_rollback_time.py

Or via pytest:
    pytest tests/benchmarks/bench_rollback_time.py -v -s
"""
from __future__ import annotations

import statistics
import time
from typing import Any

from agit import ExecutionEngine


def build_commit_chain(n_commits: int) -> tuple[ExecutionEngine, list[str]]:
    """Create an engine with *n_commits* commits; return (engine, list_of_hashes)."""
    engine = ExecutionEngine(":memory:", agent_id="rollback-bench")
    hashes: list[str] = []
    for i in range(n_commits):
        state: dict[str, Any] = {
            "memory": {
                "step": i,
                "data": f"payload_at_step_{i}",
                "cumulative_cost": i * 0.01,
                "observations": list(range(i)),
            },
            "world_state": {"iteration": i, "active": True},
        }
        h = engine.commit_state(state, f"step {i}", "tool_call")
        hashes.append(h)
    return engine, hashes


def measure_rollback_times(
    engine: ExecutionEngine,
    hashes: list[str],
    sample_indices: list[int] | None = None,
) -> list[float]:
    """Measure rollback latency (seconds) for each sampled hash."""
    indices = sample_indices if sample_indices is not None else list(range(len(hashes)))
    times: list[float] = []
    for idx in indices:
        t0 = time.monotonic()
        engine.revert(hashes[idx])
        elapsed = time.monotonic() - t0
        times.append(elapsed)
    return times


def print_report(
    n_commits: int,
    build_time: float,
    rollback_times: list[float],
    target_s: float = 5.0,
) -> None:
    print("\n" + "=" * 60)
    print(f"{'Bench: Rollback Time':^60}")
    print("=" * 60)
    print(f"  Commits built : {n_commits}")
    print(f"  Build time    : {build_time:.3f}s")
    print(f"  Rollback samples: {len(rollback_times)}")
    print(f"  Min rollback  : {min(rollback_times)*1000:.2f}ms")
    print(f"  Max rollback  : {max(rollback_times)*1000:.2f}ms")
    print(f"  Mean rollback : {statistics.mean(rollback_times)*1000:.2f}ms")
    print(f"  P95 rollback  : {sorted(rollback_times)[int(0.95*len(rollback_times))]*1000:.2f}ms")
    all_under = all(t < target_s for t in rollback_times)
    print(f"  All <{target_s}s    : {'YES (OK)' if all_under else 'NO (FAIL)'}")
    print("=" * 60 + "\n")


def main() -> None:
    for n in [50, 100, 200]:
        print(f"Building chain of {n} commits ...")
        t0 = time.monotonic()
        engine, hashes = build_commit_chain(n)
        build_time = time.monotonic() - t0

        # Sample up to 20 rollback targets spread across the chain
        step = max(1, len(hashes) // 20)
        sample_indices = list(range(0, len(hashes), step))
        times = measure_rollback_times(engine, hashes, sample_indices)
        print_report(n, build_time, times)


# ---------------------------------------------------------------------------
# pytest-compatible tests
# ---------------------------------------------------------------------------


def test_bench_rollback_50_commits() -> None:
    """Rollback to any of 50 commits must complete in <5 seconds each."""
    engine, hashes = build_commit_chain(50)
    times = measure_rollback_times(engine, hashes)
    assert all(t < 5.0 for t in times), (
        f"Some rollbacks exceeded 5s: max={max(times):.3f}s"
    )


def test_bench_rollback_100_commits() -> None:
    """Rollback to any of 100 commits must complete in <5 seconds each."""
    engine, hashes = build_commit_chain(100)
    # Sample every 5th to keep test fast
    sample = hashes[::5]
    times = measure_rollback_times(engine, sample)
    assert all(t < 5.0 for t in times), (
        f"Some rollbacks exceeded 5s: max={max(times):.3f}s"
    )


def test_bench_rollback_mean_under_one_second() -> None:
    """Mean rollback time for 50 commits must be under 1 second."""
    engine, hashes = build_commit_chain(50)
    times = measure_rollback_times(engine, hashes)
    mean = statistics.mean(times)
    assert mean < 1.0, f"Mean rollback time {mean:.3f}s exceeds 1s"


if __name__ == "__main__":
    main()
