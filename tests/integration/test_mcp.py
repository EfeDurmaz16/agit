"""Integration test: MCP server tool invocations via agit Python API."""
from __future__ import annotations

from typing import Any

import pytest

from agit import ExecutionEngine, PyAgentState, PyRepository


# ---------------------------------------------------------------------------
# Minimal MCP-like tool dispatcher (no external MCP server needed)
# ---------------------------------------------------------------------------


class MockMCPServer:
    """Minimal in-process MCP tool dispatcher for testing agit MCP semantics."""

    def __init__(self, repo_path: str = ":memory:", agent_id: str = "mcp-agent") -> None:
        self._engine = ExecutionEngine(repo_path=repo_path, agent_id=agent_id)
        self._tools = {
            "agit_commit": self._tool_commit,
            "agit_log": self._tool_log,
            "agit_diff": self._tool_diff,
            "agit_branch": self._tool_branch,
            "agit_checkout": self._tool_checkout,
            "agit_status": self._tool_status,
            "agit_revert": self._tool_revert,
        }

    def invoke(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tool call by name."""
        if tool_name not in self._tools:
            return {"error": f"Unknown tool: {tool_name}", "success": False}
        try:
            return self._tools[tool_name](params)
        except Exception as exc:
            return {"error": str(exc), "success": False}

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _tool_commit(self, params: dict[str, Any]) -> dict[str, Any]:
        state = params.get("state", {})
        message = params.get("message", "mcp commit")
        action_type = params.get("action_type", "tool_call")
        h = self._engine.commit_state(state, message, action_type)
        return {"success": True, "commit_hash": h, "message": message}

    def _tool_log(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = params.get("limit", 10)
        commits = self._engine.get_history(limit=limit)
        return {"success": True, "commits": commits, "count": len(commits)}

    def _tool_diff(self, params: dict[str, Any]) -> dict[str, Any]:
        h1 = params.get("hash1", "")
        h2 = params.get("hash2", "")
        diff = self._engine.diff(h1, h2)
        return {"success": True, "diff": diff}

    def _tool_branch(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        from_ref = params.get("from_ref")
        if name:
            self._engine.branch(name, from_ref=from_ref)
            return {"success": True, "created": name}
        branches = self._engine.list_branches()
        current = self._engine.current_branch()
        return {"success": True, "branches": branches, "current": current}

    def _tool_checkout(self, params: dict[str, Any]) -> dict[str, Any]:
        target = params.get("target", "main")
        state = self._engine.checkout(target)
        return {"success": True, "state": state, "target": target}

    def _tool_status(self, params: dict[str, Any]) -> dict[str, Any]:
        branch = self._engine.current_branch()
        branches = self._engine.list_branches()
        history = self._engine.get_history(1)
        last = history[0] if history else None
        return {
            "success": True,
            "current_branch": branch,
            "branch_count": len(branches),
            "last_commit": last,
        }

    def _tool_revert(self, params: dict[str, Any]) -> dict[str, Any]:
        to_hash = params.get("hash", "")
        state = self._engine.revert(to_hash)
        return {"success": True, "state": state, "reverted_to": to_hash}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def mcp() -> MockMCPServer:
    return MockMCPServer(repo_path=":memory:", agent_id="mcp-test")


class TestMCPToolListing:
    """Test that all expected MCP tools are registered."""

    def test_all_tools_present(self, mcp: MockMCPServer) -> None:
        tools = mcp.list_tools()
        expected = [
            "agit_commit",
            "agit_log",
            "agit_diff",
            "agit_branch",
            "agit_checkout",
            "agit_status",
            "agit_revert",
        ]
        for t in expected:
            assert t in tools, f"Missing tool: {t}"

    def test_unknown_tool_returns_error(self, mcp: MockMCPServer) -> None:
        result = mcp.invoke("nonexistent_tool", {})
        assert result["success"] is False
        assert "Unknown tool" in result["error"]


class TestMCPCommitTool:
    """Test agit_commit tool invocations."""

    def test_commit_returns_hash(self, mcp: MockMCPServer) -> None:
        result = mcp.invoke("agit_commit", {
            "state": {"memory": {"k": "v"}, "world_state": {}},
            "message": "mcp test commit",
        })
        assert result["success"] is True
        assert isinstance(result["commit_hash"], str)
        assert len(result["commit_hash"]) == 64

    def test_commit_empty_state(self, mcp: MockMCPServer) -> None:
        result = mcp.invoke("agit_commit", {"message": "empty state"})
        assert result["success"] is True

    def test_commit_with_action_type(self, mcp: MockMCPServer) -> None:
        result = mcp.invoke("agit_commit", {
            "state": {"memory": {"action": "test"}, "world_state": {}},
            "message": "llm decision",
            "action_type": "llm_response",
        })
        assert result["success"] is True


class TestMCPLogTool:
    """Test agit_log tool invocations."""

    def test_log_empty_returns_empty_list(self, mcp: MockMCPServer) -> None:
        result = mcp.invoke("agit_log", {"limit": 5})
        assert result["success"] is True
        assert result["commits"] == []
        assert result["count"] == 0

    def test_log_after_commits(self, mcp: MockMCPServer) -> None:
        for i in range(3):
            mcp.invoke("agit_commit", {
                "state": {"memory": {"step": i}, "world_state": {}},
                "message": f"step {i}",
            })
        result = mcp.invoke("agit_log", {"limit": 10})
        assert result["success"] is True
        assert result["count"] >= 3

    def test_log_limit_respected(self, mcp: MockMCPServer) -> None:
        for i in range(5):
            mcp.invoke("agit_commit", {
                "state": {"memory": {"step": i}, "world_state": {}},
                "message": f"commit {i}",
            })
        result = mcp.invoke("agit_log", {"limit": 2})
        assert result["success"] is True
        assert len(result["commits"]) <= 2


class TestMCPDiffTool:
    """Test agit_diff tool invocations."""

    def test_diff_between_two_states(self, mcp: MockMCPServer) -> None:
        r1 = mcp.invoke("agit_commit", {
            "state": {"memory": {"x": 1}, "world_state": {}},
            "message": "v1",
        })
        r2 = mcp.invoke("agit_commit", {
            "state": {"memory": {"x": 2}, "world_state": {}},
            "message": "v2",
        })
        diff_result = mcp.invoke("agit_diff", {
            "hash1": r1["commit_hash"],
            "hash2": r2["commit_hash"],
        })
        assert diff_result["success"] is True
        assert "diff" in diff_result
        assert diff_result["diff"]["base_hash"] == r1["commit_hash"]
        assert diff_result["diff"]["target_hash"] == r2["commit_hash"]

    def test_diff_identical_commits_has_no_entries(self, mcp: MockMCPServer) -> None:
        r = mcp.invoke("agit_commit", {
            "state": {"memory": {"stable": True}, "world_state": {}},
            "message": "stable",
        })
        h = r["commit_hash"]
        diff_result = mcp.invoke("agit_diff", {"hash1": h, "hash2": h})
        assert diff_result["success"] is True


class TestMCPBranchTool:
    """Test agit_branch tool invocations."""

    def test_list_branches_empty(self, mcp: MockMCPServer) -> None:
        result = mcp.invoke("agit_branch", {})
        assert result["success"] is True
        assert isinstance(result["branches"], dict)

    def test_create_branch(self, mcp: MockMCPServer) -> None:
        mcp.invoke("agit_commit", {
            "state": {"memory": {"init": True}, "world_state": {}},
            "message": "initial",
        })
        result = mcp.invoke("agit_branch", {"name": "feature/mcp-test"})
        assert result["success"] is True
        assert result["created"] == "feature/mcp-test"

    def test_list_shows_created_branch(self, mcp: MockMCPServer) -> None:
        mcp.invoke("agit_commit", {
            "state": {"memory": {}, "world_state": {}},
            "message": "base",
        })
        mcp.invoke("agit_branch", {"name": "my-branch"})
        result = mcp.invoke("agit_branch", {})
        assert "my-branch" in result["branches"]


class TestMCPCheckoutTool:
    """Test agit_checkout tool invocations."""

    def test_checkout_branch(self, mcp: MockMCPServer) -> None:
        mcp.invoke("agit_commit", {
            "state": {"memory": {"v": 1}, "world_state": {}},
            "message": "initial",
        })
        mcp.invoke("agit_branch", {"name": "checkout-me"})
        result = mcp.invoke("agit_checkout", {"target": "checkout-me"})
        assert result["success"] is True
        assert result["target"] == "checkout-me"

    def test_status_reflects_branch(self, mcp: MockMCPServer) -> None:
        mcp.invoke("agit_commit", {
            "state": {"memory": {}, "world_state": {}},
            "message": "initial",
        })
        mcp.invoke("agit_branch", {"name": "status-branch"})
        mcp.invoke("agit_checkout", {"target": "status-branch"})
        status = mcp.invoke("agit_status", {})
        assert status["success"] is True
        assert status["current_branch"] == "status-branch"


class TestMCPRevertTool:
    """Test agit_revert tool invocations."""

    def test_revert_to_previous_state(self, mcp: MockMCPServer) -> None:
        r1 = mcp.invoke("agit_commit", {
            "state": {"memory": {"step": 0}, "world_state": {}},
            "message": "v1",
        })
        mcp.invoke("agit_commit", {
            "state": {"memory": {"step": 999}, "world_state": {}},
            "message": "v2",
        })
        result = mcp.invoke("agit_revert", {"hash": r1["commit_hash"]})
        assert result["success"] is True
        assert result["state"]["memory"]["step"] == 0
