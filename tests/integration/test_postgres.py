"""Postgres integration tests (Python side).

These tests verify that the Rust Postgres backend works correctly
via cargo test. Requires Docker postgres running on port 5433.
"""
from __future__ import annotations

import subprocess
import pytest


@pytest.mark.skipif(
    subprocess.run(
        ["docker", "ps", "--filter", "publish=5433", "--format", "{{.ID}}"],
        capture_output=True, text=True,
    ).stdout.strip() == "",
    reason="Postgres test container not running on port 5433",
)
class TestPostgresIntegration:
    """Run Rust postgres integration tests via cargo."""

    def test_cargo_postgres_tests(self) -> None:
        """Verify all Rust postgres tests pass."""
        result = subprocess.run(
            ["cargo", "test", "--features", "postgres", "--", "postgres"],
            capture_output=True,
            text=True,
            cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent),
            timeout=120,
        )
        # Print output for debugging
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        assert result.returncode == 0, f"Postgres tests failed:\n{result.stderr}"
