"""Benchmark: Rust native vs Python stubs performance comparison.

Measures commit, log, diff, and revert operations for both backends.
"""
from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass

import agit


@dataclass
class BenchResult:
    operation: str
    backend: str
    iterations: int
    total_seconds: float
    ops_per_second: float

    @property
    def avg_ms(self) -> float:
        return (self.total_seconds / self.iterations) * 1000


def bench_commits(engine: agit.ExecutionEngine, n: int = 100) -> float:
    """Benchmark N sequential commits."""
    start = time.perf_counter()
    for i in range(n):
        engine.commit_state(
            {"memory": {"step": i, "data": f"payload-{i}" * 10}, "world_state": {"tick": i}},
            f"commit {i}",
            "checkpoint",
        )
    return time.perf_counter() - start


def bench_log(engine: agit.ExecutionEngine, limit: int = 50) -> float:
    """Benchmark log retrieval."""
    start = time.perf_counter()
    for _ in range(20):
        engine.get_history(limit)
    return time.perf_counter() - start


def bench_diff(engine: agit.ExecutionEngine, h1: str, h2: str) -> float:
    """Benchmark diff computation."""
    start = time.perf_counter()
    for _ in range(50):
        engine.diff(h1, h2)
    return time.perf_counter() - start


def bench_revert(engine: agit.ExecutionEngine, target_hash: str) -> float:
    """Benchmark revert operations."""
    start = time.perf_counter()
    for _ in range(20):
        engine.revert(target_hash)
    return time.perf_counter() - start


def run_backend_benchmark(backend_name: str) -> list[BenchResult]:
    """Run full benchmark suite for one backend."""
    results = []

    with tempfile.TemporaryDirectory() as tmp:
        engine = agit.ExecutionEngine(repo_path=tmp, agent_id="bench-agent")

        # Bench commits (100 ops)
        elapsed = bench_commits(engine, 100)
        results.append(BenchResult("commit", backend_name, 100, elapsed, 100 / elapsed))

        # Get two hashes for diff
        history = engine.get_history(100)
        h_first = history[-1]["hash"]
        h_last = history[0]["hash"]

        # Bench log (20 ops)
        elapsed = bench_log(engine, 50)
        results.append(BenchResult("log", backend_name, 20, elapsed, 20 / elapsed))

        # Bench diff (50 ops)
        elapsed = bench_diff(engine, h_first, h_last)
        results.append(BenchResult("diff", backend_name, 50, elapsed, 50 / elapsed))

        # Bench revert (20 ops)
        elapsed = bench_revert(engine, h_first)
        results.append(BenchResult("revert", backend_name, 20, elapsed, 20 / elapsed))

    return results


def main() -> None:
    print("=" * 70)
    print("Benchmark: Rust Native vs Python Stubs")
    print("=" * 70)
    print(f"Native available: {agit.NATIVE_AVAILABLE}")
    print()

    backend = "native" if agit.NATIVE_AVAILABLE else "stubs"
    results = run_backend_benchmark(backend)

    # Print results table
    print(f"{'Operation':<12} {'Backend':<10} {'Iters':>6} {'Total (s)':>10} {'Avg (ms)':>10} {'Ops/s':>10}")
    print("-" * 70)
    for r in results:
        print(f"{r.operation:<12} {r.backend:<10} {r.iterations:>6} {r.total_seconds:>10.3f} {r.avg_ms:>10.2f} {r.ops_per_second:>10.1f}")

    print()
    print("Summary:")
    for r in results:
        status = "PASS" if r.avg_ms < 100 else "SLOW"
        print(f"  [{status}] {r.operation}: {r.avg_ms:.2f}ms avg ({r.ops_per_second:.0f} ops/s)")


if __name__ == "__main__":
    main()
