"""MCP server demo: Shows how to start and use the agit MCP server.

Demonstrates:
- Starting the agit MCP server
- Performing tool calls (commit, log, diff, branch, checkout, revert)
- Using agit through the MCP protocol

Run:
    python examples/mcp_demo.py
"""
from __future__ import annotations

import json
from typing import Any

from agit.engine.executor import ExecutionEngine


# ---------------------------------------------------------------------------
# In-process MCP tool dispatcher (mirrors real MCP server semantics)
# ---------------------------------------------------------------------------


class AgitMCPDemo:
    """Demonstrates agit MCP tool invocations without an external server."""

    TOOLS = [
        {
            "name": "agit_commit",
            "description": "Commit agent state to the agit repository",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "state":       {"type": "object", "description": "Agent state dict"},
                    "message":     {"type": "string", "description": "Commit message"},
                    "action_type": {"type": "string", "description": "Action type tag"},
                },
                "required": ["message"],
            },
        },
        {
            "name": "agit_log",
            "description": "Retrieve commit history",
            "inputSchema": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "Max commits"}},
            },
        },
        {
            "name": "agit_diff",
            "description": "Diff two commit hashes",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "hash1": {"type": "string"},
                    "hash2": {"type": "string"},
                },
                "required": ["hash1", "hash2"],
            },
        },
        {
            "name": "agit_branch",
            "description": "Create or list branches",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name":     {"type": "string", "description": "Branch name to create"},
                    "from_ref": {"type": "string", "description": "Source ref"},
                },
            },
        },
        {
            "name": "agit_checkout",
            "description": "Switch to a branch or commit",
            "inputSchema": {
                "type": "object",
                "properties": {"target": {"type": "string"}},
                "required": ["target"],
            },
        },
        {
            "name": "agit_status",
            "description": "Show current repository status",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "agit_revert",
            "description": "Revert to a previous commit state",
            "inputSchema": {
                "type": "object",
                "properties": {"hash": {"type": "string"}},
                "required": ["hash"],
            },
        },
    ]

    def __init__(self, repo_path: str = ":memory:", agent_id: str = "mcp-demo") -> None:
        self._engine = ExecutionEngine(repo_path=repo_path, agent_id=agent_id)

    def list_tools(self) -> list[dict[str, Any]]:
        return self.TOOLS

    def call_tool(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        dispatch = {
            "agit_commit":   self._commit,
            "agit_log":      self._log,
            "agit_diff":     self._diff,
            "agit_branch":   self._branch,
            "agit_checkout": self._checkout,
            "agit_status":   self._status,
            "agit_revert":   self._revert,
        }
        fn = dispatch.get(name)
        if not fn:
            return {"error": f"Unknown tool: {name}"}
        try:
            return fn(params)
        except Exception as exc:
            return {"error": str(exc)}

    def _commit(self, p: dict[str, Any]) -> dict[str, Any]:
        h = self._engine.commit_state(
            p.get("state", {}),
            p.get("message", "mcp commit"),
            p.get("action_type", "tool_call"),
        )
        return {"commit_hash": h, "message": p.get("message")}

    def _log(self, p: dict[str, Any]) -> dict[str, Any]:
        commits = self._engine.get_history(limit=p.get("limit", 10))
        return {"commits": commits, "count": len(commits)}

    def _diff(self, p: dict[str, Any]) -> dict[str, Any]:
        return {"diff": self._engine.diff(p["hash1"], p["hash2"])}

    def _branch(self, p: dict[str, Any]) -> dict[str, Any]:
        name = p.get("name")
        if name:
            self._engine.branch(name, from_ref=p.get("from_ref"))
            return {"created": name}
        return {
            "branches": self._engine.list_branches(),
            "current": self._engine.current_branch(),
        }

    def _checkout(self, p: dict[str, Any]) -> dict[str, Any]:
        state = self._engine.checkout(p["target"])
        return {"state": state, "target": p["target"]}

    def _status(self, p: dict[str, Any]) -> dict[str, Any]:
        history = self._engine.get_history(1)
        return {
            "current_branch": self._engine.current_branch(),
            "branches": list(self._engine.list_branches().keys()),
            "last_commit": history[0] if history else None,
        }

    def _revert(self, p: dict[str, Any]) -> dict[str, Any]:
        state = self._engine.revert(p["hash"])
        return {"state": state, "reverted_to": p["hash"]}


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run_demo() -> None:
    print(f"\n{'='*60}")
    print("  agit MCP Server Demo")
    print(f"{'='*60}\n")

    server = AgitMCPDemo(repo_path=":memory:", agent_id="mcp-demo-agent")

    # List tools
    print("Available MCP tools:")
    for tool in server.list_tools():
        print(f"  - {tool['name']}: {tool['description']}")

    print(f"\n{'─'*60}")
    print("Example tool invocations:\n")

    # 1. Commit initial state
    print("[Tool] agit_commit (initial state)")
    r = server.call_tool("agit_commit", {
        "state": {"memory": {"task": "analyze data", "step": 0}, "world_state": {"status": "started"}},
        "message": "initial agent state",
        "action_type": "checkpoint",
    })
    print(f"  Result: {json.dumps(r, indent=4)}")
    h1 = r["commit_hash"]

    # 2. Commit updated state
    print("\n[Tool] agit_commit (after analysis)")
    r = server.call_tool("agit_commit", {
        "state": {"memory": {"task": "analyze data", "step": 1, "result": "positive"}, "world_state": {"status": "running"}},
        "message": "analysis complete",
        "action_type": "llm_response",
    })
    print(f"  Result: {json.dumps(r, indent=4)}")
    h2 = r["commit_hash"]

    # 3. View log
    print("\n[Tool] agit_log")
    r = server.call_tool("agit_log", {"limit": 5})
    print(f"  Commits: {r['count']}")
    for c in r["commits"]:
        print(f"    {c['hash'][:12]}  {c['action_type']:16}  {c['message']}")

    # 4. Diff
    print("\n[Tool] agit_diff")
    r = server.call_tool("agit_diff", {"hash1": h1, "hash2": h2})
    diff = r["diff"]
    print(f"  {len(diff['entries'])} changed fields between {h1[:8]}..{h2[:8]}")
    for e in diff["entries"]:
        print(f"    {e['change_type']:8}  {e['path']}")

    # 5. Create branch
    print("\n[Tool] agit_branch (create)")
    r = server.call_tool("agit_branch", {"name": "feature/mcp-test", "from_ref": h1})
    print(f"  Result: {json.dumps(r)}")

    # 6. List branches
    print("\n[Tool] agit_branch (list)")
    r = server.call_tool("agit_branch", {})
    print(f"  Branches: {list(r['branches'].keys())}  current={r['current']}")

    # 7. Status
    print("\n[Tool] agit_status")
    r = server.call_tool("agit_status", {})
    print(f"  Branch: {r['current_branch']}, branches: {r['branches']}")
    if r["last_commit"]:
        print(f"  Last commit: {r['last_commit']['hash'][:12]} – {r['last_commit']['message']}")

    # 8. Checkout
    print("\n[Tool] agit_checkout")
    r = server.call_tool("agit_checkout", {"target": "feature/mcp-test"})
    print(f"  Checked out: {r['target']}")

    # 9. Revert
    print("\n[Tool] agit_revert")
    r = server.call_tool("agit_revert", {"hash": h1})
    print(f"  Reverted to: {r['reverted_to'][:12]}")
    print(f"  Restored state keys: {list(r['state'].get('memory', {}).keys())}")

    # 10. Starting real MCP server
    print(f"\n{'─'*60}")
    print("To start the real agit MCP server:")
    print("  pip install agit[mcp]")
    print("  python -m agit.integrations.mcp_server")
    print("  # Or via Docker:")
    print("  docker compose -f docker/docker-compose.yml up agit-api")

    print(f"\n{'='*60}\n  Demo complete.\n{'='*60}\n")


def main() -> None:
    run_demo()

    # Attempt to start real MCP server if dependencies available
    try:
        from agit.integrations.mcp_server import main as run_server  # type: ignore[import]
        print("\nMCP server dependencies found. Starting server ...")
        run_server()
    except ImportError:
        print("\nNote: Install agit[mcp] to start the real MCP server.")


if __name__ == "__main__":
    main()
