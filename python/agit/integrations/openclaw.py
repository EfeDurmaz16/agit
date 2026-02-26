"""OpenClaw integration – webhook handlers and custom skill."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Callable

from agit.engine.executor import ExecutionEngine

try:
    from openclaw import Skill, SkillContext, SkillResponse  # type: ignore[import]

    _OPENCLAW_AVAILABLE = True
except ImportError:
    _OPENCLAW_AVAILABLE = False

    class SkillContext:  # type: ignore[no-redef]
        parameters: dict[str, Any] = {}
        agent_state: dict[str, Any] = {}

    class SkillResponse:  # type: ignore[no-redef]
        def __init__(self, success: bool, message: str = "", data: Any = None) -> None:
            self.success = success
            self.message = message
            self.data = data

    class Skill:  # type: ignore[no-redef]
        name: str = ""
        description: str = ""

        def execute(self, context: SkillContext) -> SkillResponse:
            raise NotImplementedError


class AgitOpenClawSkill(Skill):  # type: ignore[misc]
    """OpenClaw skill that exposes agit operations as a callable skill.

    The skill supports the following actions (passed as ``context.parameters["action"]``):
    - ``commit``   – commit current state
    - ``log``      – return commit history
    - ``branch``   – create or list branches
    - ``checkout`` – checkout a branch
    - ``revert``   – revert to a commit hash
    - ``status``   – return current status
    - ``diff``     – diff two commits

    Usage::

        engine = ExecutionEngine("./repo", agent_id="openclaw")
        skill = AgitOpenClawSkill(engine)
        # Register with your OpenClaw agent/router
        router.register_skill(skill)
    """

    name = "agit_vcs"
    description = "Git-like version control for AI agent state"

    def __init__(self, engine: ExecutionEngine) -> None:
        self._engine = engine

    def execute(self, context: SkillContext) -> SkillResponse:  # type: ignore[override]
        params: dict[str, Any] = getattr(context, "parameters", {}) or {}
        action: str = params.get("action", "status")

        try:
            result = self._dispatch(action, params, context)
            return SkillResponse(success=True, message=f"agit {action} ok", data=result)
        except Exception as exc:
            return SkillResponse(success=False, message=str(exc), data=None)

    def _dispatch(self, action: str, params: dict[str, Any], context: Any) -> Any:
        agent_state = getattr(context, "agent_state", {}) or {}

        if action == "commit":
            message = params.get("message", "openclaw commit")
            action_type = params.get("action_type", "tool_call")
            state = agent_state or self._engine.get_current_state() or {}
            return {"hash": self._engine.commit_state(state, message, action_type)}

        elif action == "log":
            limit = int(params.get("limit", 10))
            return self._engine.get_history(limit)

        elif action == "branch":
            name = params.get("name")
            if name:
                self._engine.branch(name, from_ref=params.get("from_ref"))
                return {"created": name}
            return self._engine.list_branches()

        elif action == "checkout":
            target = params.get("target", "main")
            state = self._engine.checkout(target)
            return {"state": state, "target": target}

        elif action == "revert":
            to_hash = params.get("hash", "")
            if not to_hash:
                raise ValueError("hash parameter required for revert")
            state = self._engine.revert(to_hash)
            return {"state": state, "reverted_to": to_hash}

        elif action == "diff":
            h1 = params.get("hash1", "")
            h2 = params.get("hash2", "")
            return self._engine.diff(h1, h2)

        elif action == "status":
            return {
                "branch": self._engine.current_branch(),
                "branches": self._engine.list_branches(),
                "last_commit": (self._engine.get_history(1) or [None])[0],
            }

        else:
            raise ValueError(f"Unknown agit action: {action!r}")


# ---------------------------------------------------------------------------
# Webhook handlers
# ---------------------------------------------------------------------------

def create_webhook_handler(
    engine: ExecutionEngine,
    webhook_secret: str | None = None,
) -> Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]:
    """Create an OpenClaw webhook handler function.

    Parameters
    ----------
    engine:
        The :class:`ExecutionEngine` to use for commits.
    webhook_secret:
        Optional HMAC-SHA256 secret for verifying webhook signatures.  When
        provided the handler expects a ``X-Openclaw-Signature`` header.

    Returns
    -------
    handler:
        ``(payload, headers) -> response_dict``
    """

    def _verify_signature(payload_bytes: bytes, headers: dict[str, Any]) -> bool:
        if webhook_secret is None:
            return True
        sig_header = headers.get("X-Openclaw-Signature", headers.get("x-openclaw-signature", ""))
        expected = "sha256=" + hmac.new(
            webhook_secret.encode(), payload_bytes, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, sig_header)

    def handler(payload: dict[str, Any], headers: dict[str, Any]) -> dict[str, Any]:
        payload_bytes = json.dumps(payload, sort_keys=True).encode()

        if not _verify_signature(payload_bytes, headers):
            return {"ok": False, "error": "invalid signature"}

        event_type = payload.get("event", "unknown")
        agent_state = payload.get("state", {})
        agent_id = payload.get("agent_id", "openclaw-webhook")

        try:
            h = engine.commit_state(
                agent_state,
                message=f"webhook: {event_type}",
                action_type="system_event",
            )
            return {
                "ok": True,
                "event": event_type,
                "commit_hash": h,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    return handler
