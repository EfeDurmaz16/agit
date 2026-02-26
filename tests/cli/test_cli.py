"""Tests for the agit CLI commands using typer.testing.CliRunner."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from agit.cli.app import app

runner = CliRunner()


@pytest.fixture()
def repo_dir(tmp_path: Path) -> str:
    """Return a temp directory path to use as an agit repo."""
    d = tmp_path / "cli_test_repo"
    d.mkdir()
    return str(d)


@pytest.fixture()
def committed_repo(repo_dir: str) -> tuple[str, str]:
    """Initialize a repo and commit a state; returns (repo_dir, commit_hash)."""
    state = json.dumps({"memory": {"step": 0, "cumulative_cost": 0.0}, "world_state": {}})
    result = runner.invoke(
        app,
        ["commit", "--message", "initial commit", "--state", state, "--repo", repo_dir],
    )
    assert result.exit_code == 0, result.output
    # Extract hash from output "ok: Committed <12char> – ..."
    for word in result.output.split():
        if len(word) == 12 and all(c in "0123456789abcdef" for c in word.lower()):
            return repo_dir, word
    return repo_dir, ""


class TestInitCommand:
    """Test `agit init`."""

    def test_init_succeeds(self, repo_dir: str) -> None:
        result = runner.invoke(app, ["init", repo_dir])
        assert result.exit_code == 0
        assert "Initialised" in result.output or "ok:" in result.output

    def test_init_current_directory(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0

    def test_init_with_agent_flag(self, repo_dir: str) -> None:
        result = runner.invoke(app, ["init", repo_dir, "--agent", "my-agent"])
        assert result.exit_code == 0


class TestCommitCommand:
    """Test `agit commit`."""

    def test_commit_with_message(self, repo_dir: str) -> None:
        state = json.dumps({"memory": {"k": "v"}, "world_state": {}})
        result = runner.invoke(
            app,
            ["commit", "--message", "test commit", "--state", state, "--repo", repo_dir],
        )
        assert result.exit_code == 0
        assert "Committed" in result.output or "ok:" in result.output

    def test_commit_without_state(self, repo_dir: str) -> None:
        result = runner.invoke(
            app,
            ["commit", "--message", "empty state commit", "--repo", repo_dir],
        )
        assert result.exit_code == 0

    def test_commit_with_action_type(self, repo_dir: str) -> None:
        state = json.dumps({"memory": {}, "world_state": {}})
        result = runner.invoke(
            app,
            [
                "commit",
                "--message",
                "tool call",
                "--state",
                state,
                "--type",
                "tool_call",
                "--repo",
                repo_dir,
            ],
        )
        assert result.exit_code == 0

    def test_commit_with_invalid_json_fails(self, repo_dir: str) -> None:
        result = runner.invoke(
            app,
            ["commit", "--message", "bad json", "--state", "{not valid json}", "--repo", repo_dir],
        )
        assert result.exit_code != 0 or "error" in result.output.lower() or "Invalid" in result.output

    def test_commit_state_from_file(self, repo_dir: str, tmp_path: Path) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"memory": {"from": "file"}, "world_state": {}}))
        result = runner.invoke(
            app,
            ["commit", "--message", "from file", "--state", str(state_file), "--repo", repo_dir],
        )
        assert result.exit_code == 0


class TestLogCommand:
    """Test `agit log`."""

    def test_log_empty_repo(self, repo_dir: str) -> None:
        result = runner.invoke(app, ["log", "--repo", repo_dir])
        assert result.exit_code == 0
        assert "No commits" in result.output

    def test_log_shows_commits(self, committed_repo: tuple[str, str]) -> None:
        repo_dir, _ = committed_repo
        result = runner.invoke(app, ["log", "--repo", repo_dir])
        assert result.exit_code == 0
        assert "initial commit" in result.output

    def test_log_limit(self, committed_repo: tuple[str, str]) -> None:
        repo_dir, _ = committed_repo
        # Add more commits
        for i in range(5):
            state = json.dumps({"memory": {"step": i}, "world_state": {}})
            runner.invoke(
                app,
                ["commit", "--message", f"commit {i}", "--state", state, "--repo", repo_dir],
            )
        result = runner.invoke(app, ["log", "--limit", "2", "--repo", repo_dir])
        assert result.exit_code == 0


class TestBranchCommand:
    """Test `agit branch`."""

    def test_branch_list_empty_repo(self, repo_dir: str) -> None:
        result = runner.invoke(app, ["branch", "--repo", repo_dir])
        assert result.exit_code == 0

    def test_branch_create(self, committed_repo: tuple[str, str]) -> None:
        repo_dir, _ = committed_repo
        result = runner.invoke(app, ["branch", "feature-x", "--repo", repo_dir])
        assert result.exit_code == 0
        assert "feature-x" in result.output or "Created" in result.output

    def test_branch_list_shows_created(self, committed_repo: tuple[str, str]) -> None:
        repo_dir, _ = committed_repo
        runner.invoke(app, ["branch", "show-me", "--repo", repo_dir])
        result = runner.invoke(app, ["branch", "--repo", repo_dir])
        assert result.exit_code == 0
        assert "show-me" in result.output or "main" in result.output


class TestCheckoutCommand:
    """Test `agit checkout`."""

    def test_checkout_branch(self, committed_repo: tuple[str, str]) -> None:
        repo_dir, _ = committed_repo
        runner.invoke(app, ["branch", "checkout-target", "--repo", repo_dir])
        result = runner.invoke(app, ["checkout", "checkout-target", "--repo", repo_dir])
        assert result.exit_code == 0
        assert "checkout-target" in result.output or "Checked out" in result.output

    def test_checkout_commit_hash(self, committed_repo: tuple[str, str]) -> None:
        repo_dir, _ = committed_repo
        # Get full hash from log
        from agit import ExecutionEngine
        eng = ExecutionEngine(repo_dir)
        history = eng.get_history(1)
        assert history
        full_hash = history[0]["hash"]
        result = runner.invoke(app, ["checkout", full_hash, "--repo", repo_dir])
        assert result.exit_code == 0


class TestDiffCommand:
    """Test `agit diff`."""

    def test_diff_between_two_commits(self, committed_repo: tuple[str, str]) -> None:
        repo_dir, _ = committed_repo
        state2 = json.dumps({"memory": {"step": 1, "cumulative_cost": 0.1}, "world_state": {}})
        runner.invoke(
            app,
            ["commit", "--message", "second commit", "--state", state2, "--repo", repo_dir],
        )
        from agit import ExecutionEngine
        eng = ExecutionEngine(repo_dir)
        history = eng.get_history(2)
        assert len(history) >= 2
        h1 = history[1]["hash"]
        h2 = history[0]["hash"]
        result = runner.invoke(app, ["diff", h1, h2, "--repo", repo_dir])
        assert result.exit_code == 0

    def test_diff_identical_commits_shows_no_differences(
        self, committed_repo: tuple[str, str]
    ) -> None:
        repo_dir, _ = committed_repo
        from agit import ExecutionEngine
        eng = ExecutionEngine(repo_dir)
        history = eng.get_history(1)
        h = history[0]["hash"]
        result = runner.invoke(app, ["diff", h, h, "--repo", repo_dir])
        assert result.exit_code == 0
        assert "No differences" in result.output


class TestStatusCommand:
    """Test `agit status`."""

    def test_status_empty_repo(self, repo_dir: str) -> None:
        result = runner.invoke(app, ["status", "--repo", repo_dir])
        assert result.exit_code == 0

    def test_status_shows_branch(self, committed_repo: tuple[str, str]) -> None:
        repo_dir, _ = committed_repo
        result = runner.invoke(app, ["status", "--repo", repo_dir])
        assert result.exit_code == 0
        assert "main" in result.output or "Repository Status" in result.output

    def test_status_shows_last_commit(self, committed_repo: tuple[str, str]) -> None:
        repo_dir, _ = committed_repo
        result = runner.invoke(app, ["status", "--repo", repo_dir])
        assert result.exit_code == 0
        assert "initial commit" in result.output or "Last commit" in result.output
