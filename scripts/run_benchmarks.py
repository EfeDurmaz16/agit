#!/usr/bin/env python3
"""Run all agit benchmarks and produce consolidated report."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS = [
    ("Retry Success Rate", "tests/benchmarks/bench_retry_success.py"),
    ("Rollback Time", "tests/benchmarks/bench_rollback_time.py"),
    ("Token Usage Reduction", "tests/benchmarks/bench_token_usage.py"),
    ("Rust vs Python", "tests/benchmarks/bench_rust_vs_python.py"),
]


def run_benchmark(name: str, path: str) -> tuple[bool, str, float]:
    """Run a single benchmark, return (success, output, elapsed)."""
    full_path = ROOT / path
    if not full_path.exists():
        return False, f"File not found: {path}", 0.0

    start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, str(full_path)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=300,
    )
    elapsed = time.perf_counter() - start
    output = result.stdout + result.stderr
    return result.returncode == 0, output, elapsed


def main() -> None:
    print("=" * 70)
    print("AgentGit Benchmark Suite")
    print("=" * 70)
    print()

    all_passed = True
    summaries: list[tuple[str, bool, float]] = []

    for name, path in BENCHMARKS:
        print(f"\n{'─' * 70}")
        print(f"Running: {name} ({path})")
        print(f"{'─' * 70}")

        success, output, elapsed = run_benchmark(name, path)
        summaries.append((name, success, elapsed))

        if output.strip():
            # Indent output
            for line in output.strip().split("\n"):
                print(f"  {line}")

        status = "PASS" if success else "FAIL"
        print(f"\n  [{status}] {name} completed in {elapsed:.1f}s")

        if not success:
            all_passed = False

    # Consolidated report
    print(f"\n{'=' * 70}")
    print("Consolidated Report")
    print(f"{'=' * 70}")
    print(f"\n{'Benchmark':<30} {'Status':>8} {'Time (s)':>10}")
    print("-" * 50)
    for name, success, elapsed in summaries:
        status = "PASS" if success else "FAIL"
        print(f"{name:<30} {status:>8} {elapsed:>10.1f}")

    passed = sum(1 for _, s, _ in summaries if s)
    total = len(summaries)
    print(f"\nResults: {passed}/{total} benchmarks passed")

    # Target metrics
    print(f"\n{'=' * 70}")
    print("Target Metrics")
    print(f"{'=' * 70}")
    print("  Retry success rate:    target >= 96%")
    print("  Rollback time:         target < 5s")
    print("  Token reduction:       target >= 40%")
    print("  Native vs stubs:       informational comparison")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
