"""MCP Server – exposes agit tools via FastMCP."""
from __future__ import annotations

from typing import Any, Optional

from agit.engine.executor import ExecutionEngine

try:
    from fastmcp import FastMCP  # type: ignore[import]

    _FASTMCP_AVAILABLE = True
except ImportError:
    _FASTMCP_AVAILABLE = False

    class FastMCP:  # type: ignore[no-redef]
        """Minimal FastMCP stub."""

        def __init__(self, name: str) -> None:
            self.name = name
            self._tools: dict[str, Any] = {}

        def tool(self, fn: Any = None, **kwargs: Any) -> Any:
            if fn is not None:
                self._tools[fn.__name__] = fn
                return fn

            def decorator(f: Any) -> Any:
                self._tools[f.__name__] = f
                return f

            return decorator

        def run(self, transport: str = "stdio") -> None:
            pass


def create_mcp_server(
    engine: ExecutionEngine,
    server_name: str = "agit",
) -> FastMCP:
    """Build and return a FastMCP server with all agit tools registered.

    Parameters
    ----------
    engine:
        An initialised :class:`ExecutionEngine`.
    server_name:
        Name reported to MCP clients.

    Returns
    -------
    FastMCP:
        Ready-to-run MCP server. Call ``.run()`` to start serving.

    Example::

        engine = ExecutionEngine("./repo", agent_id="mcp-agent")
        server = create_mcp_server(engine)
        server.run()   # starts stdio MCP server
    """
    mcp = FastMCP(server_name)

    # ------------------------------------------------------------------
    # Tool: agit_init
    # ------------------------------------------------------------------
    @mcp.tool()
    def agit_init(repo_path: str = ".", agent_id: str = "mcp") -> dict[str, Any]:
        """Initialize an agit repository at the given path."""
        try:
            ExecutionEngine(repo_path=repo_path, agent_id=agent_id)
            return {"ok": True, "repo_path": repo_path}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Tool: agit_commit
    # ------------------------------------------------------------------
    @mcp.tool()
    def agit_commit(
        message: str,
        state: Optional[dict[str, Any]] = None,
        action_type: str = "checkpoint",
    ) -> dict[str, Any]:
        """Commit the given state (or current state) with a message."""
        try:
            s = state or engine.get_current_state() or {}
            h = engine.commit_state(s, message, action_type)
            return {"ok": True, "hash": h, "message": message}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Tool: agit_log
    # ------------------------------------------------------------------
    @mcp.tool()
    def agit_log(limit: int = 10) -> dict[str, Any]:
        """Return the commit history."""
        try:
            commits = engine.get_history(limit)
            return {"ok": True, "commits": commits}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Tool: agit_diff
    # ------------------------------------------------------------------
    @mcp.tool()
    def agit_diff(hash1: str, hash2: str) -> dict[str, Any]:
        """Compute the diff between two commit hashes."""
        try:
            d = engine.diff(hash1, hash2)
            return {"ok": True, "diff": d}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Tool: agit_branch
    # ------------------------------------------------------------------
    @mcp.tool()
    def agit_branch(
        name: Optional[str] = None,
        from_ref: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a branch (if name given) or list all branches."""
        try:
            if name:
                engine.branch(name, from_ref=from_ref)
                return {"ok": True, "created": name}
            return {"ok": True, "branches": engine.list_branches()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Tool: agit_checkout
    # ------------------------------------------------------------------
    @mcp.tool()
    def agit_checkout(target: str) -> dict[str, Any]:
        """Checkout a branch or commit hash."""
        try:
            state = engine.checkout(target)
            return {"ok": True, "target": target, "state": state}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Tool: agit_merge
    # ------------------------------------------------------------------
    @mcp.tool()
    def agit_merge(branch: str, strategy: str = "three_way") -> dict[str, Any]:
        """Merge a branch into HEAD."""
        try:
            h = engine.merge(branch, strategy=strategy)
            return {"ok": True, "merge_commit": h}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Tool: agit_revert
    # ------------------------------------------------------------------
    @mcp.tool()
    def agit_revert(commit_hash: str) -> dict[str, Any]:
        """Revert to the state at a previous commit hash."""
        try:
            state = engine.revert(commit_hash)
            return {"ok": True, "reverted_to": commit_hash, "state": state}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Tool: agit_status
    # ------------------------------------------------------------------
    @mcp.tool()
    def agit_status() -> dict[str, Any]:
        """Return current repository status."""
        try:
            history = engine.get_history(1)
            return {
                "ok": True,
                "branch": engine.current_branch(),
                "branches": engine.list_branches(),
                "last_commit": history[0] if history else None,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Tool: agit_audit
    # ------------------------------------------------------------------
    @mcp.tool()
    def agit_audit(limit: int = 20) -> dict[str, Any]:
        """Return the audit log."""
        try:
            logs = engine.audit_log(limit)
            return {"ok": True, "entries": logs}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Tool: agit_state_replay
    # ------------------------------------------------------------------
    @mcp.tool()
    def agit_state_replay(commit_hash: str) -> dict[str, Any]:
        """Get the agent state at a specific commit without changing HEAD."""
        try:
            # Get state at commit via checkout and restore
            current = engine.current_branch() or "main"
            state = engine.checkout(commit_hash)
            engine.checkout(current)  # restore position
            return {"ok": True, "hash": commit_hash, "state": state}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Tool: agit_search
    # ------------------------------------------------------------------
    @mcp.tool()
    def agit_search(
        query: str,
        action_type: Optional[str] = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search commits by message content or action type."""
        try:
            commits = engine.get_history(limit * 5)  # over-fetch for filtering
            results = []
            query_lower = query.lower()
            for c in commits:
                msg = c.get("message", "").lower()
                at = c.get("action_type", "")
                if query_lower in msg or query_lower in at:
                    if action_type and at != action_type:
                        continue
                    results.append(c)
                    if len(results) >= limit:
                        break
            return {"ok": True, "results": results, "count": len(results)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    return mcp


def main() -> None:
    """CLI entry-point: start the MCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="agit MCP server")
    parser.add_argument("--repo", default=".", help="Repository path")
    parser.add_argument("--agent", default="mcp", help="Agent ID")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse"])
    parser.add_argument("--host", default="0.0.0.0", help="SSE host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="SSE port (default: 8000)")
    args = parser.parse_args()

    engine = ExecutionEngine(repo_path=args.repo, agent_id=args.agent)
    server = create_mcp_server(engine)

    if args.transport == "sse":
        server.run(transport="sse", host=args.host, port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
