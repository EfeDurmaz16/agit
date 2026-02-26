"""ExecutionEngine – wraps agent actions with auto-commit via agit_core."""
from __future__ import annotations

import time
from typing import Any, Callable

try:
    import agit_core  # type: ignore[import]

    _PyRepository = agit_core.PyRepository
    _PyAgentState = agit_core.PyAgentState
    _PyCommit = agit_core.PyCommit
    _NATIVE = True
except ImportError:
    from agit._stubs import PyRepository as _PyRepository  # type: ignore[assignment]
    from agit._stubs import PyAgentState as _PyAgentState  # type: ignore[assignment]
    from agit._stubs import PyCommit as _PyCommit  # type: ignore[assignment]

    _NATIVE = False


class ExecutionEngine:
    """High-level engine that wraps every agent action with before/after commits.

    Parameters
    ----------
    repo_path:
        Filesystem path for the agit repository (or ``":memory:"`` for tests).
    agent_id:
        Logical identifier for the agent using this engine (used in commit authorship).
    """

    def __init__(self, repo_path: str, agent_id: str = "default") -> None:
        self._repo_path = repo_path
        self._agent_id = agent_id
        self._current_state: dict[str, Any] | None = None

        # Instantiate the correct repository backend
        self._repo = _PyRepository(repo_path, agent_id)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def execute(
        self,
        action_fn: Callable[..., Any],
        state: dict[str, Any],
        message: str,
        action_type: str = "tool_call",
    ) -> tuple[Any, str]:
        """Execute *action_fn* and auto-commit state before and after.

        Parameters
        ----------
        action_fn:
            Callable that receives *state* and returns a new state dict.
        state:
            The current agent state dict (``{"memory": {...}, "world_state": {...}}``).
        message:
            Human-readable description of the action.
        action_type:
            One of the agit ActionType string values (``"tool_call"``, ``"llm_response"``, …).

        Returns
        -------
        (result, commit_hash):
            The action result and the hash of the post-action commit.
        """
        pre_state_obj = self._dict_to_state(state)

        # Pre-action checkpoint
        pre_hash = self._repo.commit(pre_state_obj, f"pre: {message}", "checkpoint")

        start_ts = time.monotonic()
        try:
            result = action_fn(state)
        except Exception as exc:
            # On failure, record the error as a rollback checkpoint
            self._repo.commit(pre_state_obj, f"error: {message} – {exc}", "rollback")
            raise

        elapsed = time.monotonic() - start_ts

        # Determine new state
        if isinstance(result, dict):
            new_state = result
        else:
            # The action may return a raw value; wrap it in memory
            new_state = {**state, "last_result": result}

        post_state_obj = self._dict_to_state(new_state)
        post_hash = self._repo.commit(
            post_state_obj,
            f"{message} (elapsed={elapsed:.3f}s)",
            action_type,
        )
        self._current_state = new_state
        return result, post_hash

    def get_history(self, limit: int = 10) -> list[Any]:
        """Return the *limit* most-recent commits as plain dicts."""
        commits = self._repo.log(limit)
        return [self._commit_to_dict(c) for c in commits]

    def get_current_state(self) -> dict[str, Any] | None:
        """Return the last committed state as a dict, or ``None`` if empty."""
        if self._current_state is not None:
            return self._current_state
        try:
            commits = self._repo.log(1)
            if commits:
                state_obj = self._repo.get_state(commits[0].hash)
                return self._state_to_dict(state_obj)
        except Exception:
            pass
        return None

    def commit_state(
        self,
        state: dict[str, Any],
        message: str,
        action_type: str = "checkpoint",
    ) -> str:
        """Directly commit *state* without running an action function."""
        state_obj = self._dict_to_state(state)
        h = self._repo.commit(state_obj, message, action_type)
        self._current_state = state
        return h

    # ------------------------------------------------------------------
    # Branch helpers (thin pass-through)
    # ------------------------------------------------------------------

    def branch(self, name: str, from_ref: str | None = None) -> None:
        """Create a branch named *name*."""
        self._repo.branch(name, from_ref)

    def checkout(self, target: str) -> dict[str, Any]:
        """Checkout *target* branch or commit hash; returns the recovered state."""
        state_obj = self._repo.checkout(target)
        state = self._state_to_dict(state_obj)
        self._current_state = state
        return state

    def merge(self, branch: str, strategy: str = "three_way") -> str:
        """Merge *branch* into HEAD; returns the merge commit hash."""
        return self._repo.merge(branch, strategy)

    def revert(self, to_hash: str) -> dict[str, Any]:
        """Revert to the state at *to_hash*; returns the restored state."""
        state_obj = self._repo.revert(to_hash)
        state = self._state_to_dict(state_obj)
        self._current_state = state
        return state

    def diff(self, hash1: str, hash2: str) -> dict[str, Any]:
        """Return diff between two commit hashes."""
        diff_obj = self._repo.diff(hash1, hash2)
        return self._diff_to_dict(diff_obj)

    def list_branches(self) -> dict[str, str]:
        return self._repo.list_branches()

    def current_branch(self) -> str | None:
        return self._repo.current_branch()

    def audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._repo.audit_log(limit)

    # ------------------------------------------------------------------
    # Internal conversion helpers
    # ------------------------------------------------------------------

    def _dict_to_state(self, d: dict[str, Any]) -> Any:
        memory = d.get("memory", d)
        world_state = d.get("world_state", {})
        return _PyAgentState(memory, world_state)

    def _state_to_dict(self, state_obj: Any) -> dict[str, Any]:
        if hasattr(state_obj, "to_dict"):
            return state_obj.to_dict()
        return {"memory": getattr(state_obj, "memory", {}), "world_state": getattr(state_obj, "world_state", {})}

    def _commit_to_dict(self, c: Any) -> dict[str, Any]:
        return {
            "hash": getattr(c, "hash", ""),
            "message": getattr(c, "message", ""),
            "author": getattr(c, "author", ""),
            "timestamp": getattr(c, "timestamp", ""),
            "action_type": getattr(c, "action_type", ""),
            "parent_hashes": getattr(c, "parent_hashes", []),
        }

    def _diff_to_dict(self, diff_obj: Any) -> dict[str, Any]:
        entries = []
        for e in getattr(diff_obj, "entries", []):
            entries.append({
                "path": getattr(e, "path", ""),
                "change_type": getattr(e, "change_type", ""),
                "old_value": getattr(e, "old_value", None),
                "new_value": getattr(e, "new_value", None),
            })
        return {
            "base_hash": getattr(diff_obj, "base_hash", ""),
            "target_hash": getattr(diff_obj, "target_hash", ""),
            "entries": entries,
        }
