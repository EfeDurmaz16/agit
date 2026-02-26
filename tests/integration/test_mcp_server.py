"""Integration tests for the MCP server."""
from __future__ import annotations

import tempfile

import pytest

from agit.engine.executor import ExecutionEngine
from agit.integrations.mcp_server import create_mcp_server


@pytest.fixture()
def mcp_setup():
    """Create an engine with some commits and an MCP server."""
    with tempfile.TemporaryDirectory() as tmp:
        engine = ExecutionEngine(repo_path=tmp, agent_id="test-mcp")

        # Create some test commits
        engine.commit_state(
            {"memory": {"step": 1, "data": "hello"}, "world_state": {}},
            "first commit",
            "tool_call",
        )
        engine.commit_state(
            {"memory": {"step": 2, "data": "world"}, "world_state": {}},
            "second commit",
            "checkpoint",
        )
        engine.commit_state(
            {"memory": {"step": 3, "data": "search-me"}, "world_state": {}},
            "third commit with searchable content",
            "llm_response",
        )

        server = create_mcp_server(engine)
        yield engine, server


class TestMcpServerTools:
    """Test MCP server tool functions."""

    def test_agit_init(self, mcp_setup):
        _engine, server = mcp_setup
        tools = server._tools
        result = tools["agit_init"]()
        assert result["ok"] is True

    def test_agit_log(self, mcp_setup):
        _engine, server = mcp_setup
        result = server._tools["agit_log"](limit=10)
        assert result["ok"] is True
        assert len(result["commits"]) == 3

    def test_agit_commit(self, mcp_setup):
        _engine, server = mcp_setup
        result = server._tools["agit_commit"](
            message="test via mcp",
            state={"memory": {"via": "mcp"}, "world_state": {}},
        )
        assert result["ok"] is True
        assert "hash" in result

    def test_agit_status(self, mcp_setup):
        _engine, server = mcp_setup
        result = server._tools["agit_status"]()
        assert result["ok"] is True
        assert result["branch"] is not None

    def test_agit_branch(self, mcp_setup):
        _engine, server = mcp_setup
        # Create branch
        result = server._tools["agit_branch"](name="test-branch")
        assert result["ok"] is True
        # List branches
        result = server._tools["agit_branch"]()
        assert result["ok"] is True
        assert "test-branch" in result["branches"]

    def test_agit_diff(self, mcp_setup):
        engine, server = mcp_setup
        history = engine.get_history(3)
        h1 = history[-1]["hash"]
        h2 = history[0]["hash"]
        result = server._tools["agit_diff"](hash1=h1, hash2=h2)
        assert result["ok"] is True
        assert "diff" in result

    def test_agit_audit(self, mcp_setup):
        _engine, server = mcp_setup
        result = server._tools["agit_audit"](limit=10)
        assert result["ok"] is True
        assert len(result["entries"]) > 0

    def test_agit_state_replay(self, mcp_setup):
        engine, server = mcp_setup
        history = engine.get_history(3)
        first_hash = history[-1]["hash"]
        result = server._tools["agit_state_replay"](commit_hash=first_hash)
        assert result["ok"] is True
        assert result["state"]["memory"]["step"] == 1

    def test_agit_search_by_message(self, mcp_setup):
        _engine, server = mcp_setup
        result = server._tools["agit_search"](query="searchable")
        assert result["ok"] is True
        assert result["count"] >= 1
        assert any("searchable" in r["message"].lower() for r in result["results"])

    def test_agit_search_by_action_type(self, mcp_setup):
        _engine, server = mcp_setup
        result = server._tools["agit_search"](query="commit", action_type="tool_call")
        assert result["ok"] is True
        for r in result["results"]:
            assert r["action_type"] == "tool_call"

    def test_agit_search_no_results(self, mcp_setup):
        _engine, server = mcp_setup
        result = server._tools["agit_search"](query="nonexistent-query-xyz")
        assert result["ok"] is True
        assert result["count"] == 0

    def test_agit_revert(self, mcp_setup):
        engine, server = mcp_setup
        history = engine.get_history(3)
        first_hash = history[-1]["hash"]
        result = server._tools["agit_revert"](commit_hash=first_hash)
        assert result["ok"] is True

    def test_agit_checkout(self, mcp_setup):
        engine, server = mcp_setup
        server._tools["agit_branch"](name="checkout-test")
        result = server._tools["agit_checkout"](target="checkout-test")
        assert result["ok"] is True
