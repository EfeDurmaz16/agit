"""Shared pytest fixtures for the agit test suite."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture()
def tmp_repo_path(tmp_path: Path) -> str:
    """Return a temporary filesystem path suitable for an agit repository."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    return str(repo_dir)


@pytest.fixture()
def sample_state() -> dict[str, Any]:
    """Return a minimal agent state dict with memory and world_state."""
    return {
        "memory": {
            "agent_name": "test-agent",
            "step": 0,
            "cumulative_cost": 0.0,
            "context": "initial context",
        },
        "world_state": {
            "environment": "test",
            "status": "idle",
            "pending_tasks": [],
        },
    }


@pytest.fixture()
def sample_states() -> list[dict[str, Any]]:
    """Return a sequence of evolving agent states for multi-step tests."""
    return [
        {
            "memory": {
                "agent_name": "test-agent",
                "step": i,
                "cumulative_cost": i * 0.05,
                "context": f"context at step {i}",
                "observations": [f"obs_{j}" for j in range(i)],
            },
            "world_state": {
                "environment": "test",
                "status": "running" if i > 0 else "idle",
                "step_count": i,
                "last_action": f"action_{i}" if i > 0 else None,
            },
        }
        for i in range(5)
    ]
