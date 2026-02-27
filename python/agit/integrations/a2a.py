"""Google A2A (Agent-to-Agent) protocol integration for agit.

Provides an A2A-compatible AgentExecutor that automatically versions
agent state on every message exchange, plus a discovery-aware client
wrapper that commits remote agent interactions.

Usage (server)::

    from agit.integrations.a2a import AgitA2AExecutor
    engine = ExecutionEngine("./my_repo", agent_id="a2a-agent")
    executor = AgitA2AExecutor(engine, inner_executor=my_executor)

Usage (client)::

    from agit.integrations.a2a import AgitA2AClient
    engine = ExecutionEngine("./my_repo", agent_id="a2a-client")
    client = AgitA2AClient(engine, base_url="http://remote-agent:9999")
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from agit.engine.executor import ExecutionEngine

logger = logging.getLogger("agit.integrations.a2a")

try:
    from a2a.server.agent_execution import AgentExecutor, RequestContext  # type: ignore[import]
    from a2a.server.events import EventQueue  # type: ignore[import]
    from a2a.types import AgentCard, AgentSkill, AgentCapabilities  # type: ignore[import]

    _A2A_AVAILABLE = True
except ImportError:
    _A2A_AVAILABLE = False
    AgentExecutor = object  # type: ignore[assignment,misc]
    RequestContext = object  # type: ignore[assignment,misc]
    EventQueue = object  # type: ignore[assignment,misc]
    AgentCard = object  # type: ignore[assignment,misc]
    AgentSkill = object  # type: ignore[assignment,misc]
    AgentCapabilities = object  # type: ignore[assignment,misc]


class AgitA2AExecutor(AgentExecutor):  # type: ignore[misc]
    """A2A AgentExecutor that wraps another executor with agit versioning.

    Every incoming message is committed as a pre-execution checkpoint,
    and every outgoing response is committed as a post-execution commit.
    This provides full audit trail of all A2A interactions.
    """

    def __init__(
        self,
        engine: ExecutionEngine,
        inner_executor: Any = None,
        *,
        branch_per_context: bool = True,
    ) -> None:
        self._engine = engine
        self._inner = inner_executor
        self._branch_per_context = branch_per_context

    async def execute(
        self,
        context: Any,
        event_queue: Any,
    ) -> None:
        """Execute an A2A request with agit versioning.

        1. Commits incoming message as checkpoint
        2. Delegates to inner executor
        3. Commits outgoing events as tool_call
        """
        # Extract message info from A2A context
        params = getattr(context, "params", None)
        message = getattr(params, "message", None) if params else None

        context_id = self._get_context_id(context)
        task_id = self._get_task_id(context)

        # Branch per conversation context if enabled
        if self._branch_per_context and context_id:
            branch_name = f"a2a/{context_id}"
            try:
                self._engine.branch(branch_name)
            except Exception:
                pass  # Branch may already exist
            try:
                self._engine.checkout(branch_name)
            except Exception:
                logger.debug("Could not checkout branch %s", branch_name)

        # Commit incoming message as pre-execution checkpoint
        incoming_state = self._message_to_state(message, context_id, task_id)
        try:
            self._engine.commit_state(
                incoming_state,
                message=f"a2a-recv: {self._extract_text(message)[:80]}",
                action_type="checkpoint",
            )
        except Exception:
            logger.warning("Failed to commit incoming A2A message", exc_info=True)

        # Delegate to inner executor if provided
        if self._inner is not None:
            await self._inner.execute(context, event_queue)
        else:
            # Default: echo with agit status
            try:
                from a2a.utils import new_agent_text_message  # type: ignore[import]

                history = self._engine.get_history(limit=5)
                status = f"agit tracking active. {len(history)} recent commits."
                await event_queue.enqueue_event(new_agent_text_message(status))
            except Exception:
                logger.warning("Failed to send default A2A response", exc_info=True)

        # Commit post-execution state
        post_state = self._engine.get_current_state() or {}
        post_state.setdefault("world_state", {})
        if isinstance(post_state.get("world_state"), dict):
            post_state["world_state"]["a2a_task_id"] = task_id
            post_state["world_state"]["a2a_phase"] = "post_execute"
        try:
            self._engine.commit_state(
                post_state,
                message=f"a2a-exec: task={task_id or 'none'}",
                action_type="tool_call",
            )
        except Exception:
            logger.warning("Failed to commit post-execution state", exc_info=True)

    async def cancel(
        self,
        context: Any,
        event_queue: Any,
    ) -> None:
        """Handle A2A task cancellation with agit commit."""
        task_id = self._get_task_id(context)

        # Commit cancellation event
        state = self._engine.get_current_state() or {}
        state.setdefault("world_state", {})
        if isinstance(state.get("world_state"), dict):
            state["world_state"]["a2a_task_id"] = task_id
            state["world_state"]["a2a_phase"] = "cancelled"
        try:
            self._engine.commit_state(
                state,
                message=f"a2a-cancel: task={task_id or 'none'}",
                action_type="system_event",
            )
        except Exception:
            logger.warning("Failed to commit cancellation", exc_info=True)

        # Delegate cancellation to inner executor
        if self._inner is not None and hasattr(self._inner, "cancel"):
            await self._inner.cancel(context, event_queue)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _message_to_state(
        self,
        message: Any,
        context_id: str | None,
        task_id: str | None,
    ) -> dict[str, Any]:
        """Convert an A2A Message into an agit state dict."""
        parts_data: list[dict[str, Any]] = []
        if message and hasattr(message, "parts"):
            for part in message.parts:
                kind = getattr(part, "kind", "unknown")
                if kind == "text":
                    parts_data.append({"kind": "text", "text": getattr(part, "text", "")})
                elif kind == "data":
                    parts_data.append({"kind": "data", "data": getattr(part, "data", {})})
                elif kind == "file":
                    parts_data.append({"kind": "file", "name": getattr(part, "name", "")})
                else:
                    parts_data.append({"kind": kind})

        role = getattr(message, "role", "unknown") if message else "unknown"

        return {
            "memory": {
                "a2a_message": {
                    "role": role,
                    "parts": parts_data,
                    "message_id": getattr(message, "messageId", None) if message else None,
                },
            },
            "world_state": {
                "a2a_context_id": context_id,
                "a2a_task_id": task_id,
                "a2a_phase": "pre_execute",
            },
        }

    @staticmethod
    def _extract_text(message: Any) -> str:
        """Extract the first text content from an A2A message."""
        if message is None:
            return "(empty)"
        parts = getattr(message, "parts", [])
        for part in parts:
            if getattr(part, "kind", None) == "text":
                return getattr(part, "text", "")
        return "(non-text)"

    @staticmethod
    def _get_context_id(context: Any) -> str | None:
        params = getattr(context, "params", None)
        message = getattr(params, "message", None) if params else None
        return getattr(message, "contextId", None) if message else None

    @staticmethod
    def _get_task_id(context: Any) -> str | None:
        params = getattr(context, "params", None)
        message = getattr(params, "message", None) if params else None
        return getattr(message, "taskId", None) if message else None


class AgitA2AClient:
    """Client-side A2A wrapper that commits all interactions to agit.

    Wraps A2A client calls with pre/post commits for full
    audit trail of remote agent interactions.
    """

    def __init__(
        self,
        engine: ExecutionEngine,
        *,
        base_url: str = "http://localhost:9999",
    ) -> None:
        self._engine = engine
        self._base_url = base_url

    async def send_message(
        self,
        text: str,
        *,
        context_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a message to a remote A2A agent and commit the interaction."""
        # Commit outgoing message
        try:
            self._engine.commit_state(
                {
                    "memory": {"outgoing_message": text},
                    "world_state": {
                        "a2a_remote": self._base_url,
                        "a2a_context_id": context_id,
                        "a2a_phase": "send",
                    },
                },
                message=f"a2a-send: {text[:80]}",
                action_type="tool_call",
            )
        except Exception:
            logger.warning("Failed to commit outgoing A2A message", exc_info=True)

        # Perform A2A call
        response: dict[str, Any] = {}
        try:
            import httpx  # type: ignore[import]
            from a2a.client import A2ACardResolver, A2AClient  # type: ignore[import]
            from a2a.types import MessageSendParams, SendMessageRequest  # type: ignore[import]
            from uuid import uuid4

            async with httpx.AsyncClient() as http_client:
                resolver = A2ACardResolver(
                    httpx_client=http_client,
                    base_url=self._base_url,
                )
                card = await resolver.get_agent_card()
                client = A2AClient(httpx_client=http_client, agent_card=card)

                payload = {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": text}],
                        "messageId": uuid4().hex,
                    },
                }
                if context_id:
                    payload["message"]["contextId"] = context_id  # type: ignore[index]

                request = SendMessageRequest(
                    id=str(uuid4()),
                    params=MessageSendParams(**payload),
                )
                result = await client.send_message(request)
                response = result.model_dump(mode="json", exclude_none=True)

        except ImportError:
            logger.error("a2a-sdk not installed. Install with: pip install a2a-sdk")
            response = {"error": "a2a-sdk not installed"}
        except Exception as e:
            logger.warning("A2A call failed: %s", e, exc_info=True)
            response = {"error": str(e)}

        # Commit response
        try:
            self._engine.commit_state(
                {
                    "memory": {"a2a_response": response},
                    "world_state": {
                        "a2a_remote": self._base_url,
                        "a2a_context_id": context_id,
                        "a2a_phase": "recv",
                    },
                },
                message=f"a2a-recv: response from {self._base_url}",
                action_type="llm_response",
            )
        except Exception:
            logger.warning("Failed to commit A2A response", exc_info=True)

        return response

    async def discover(self) -> dict[str, Any]:
        """Discover a remote A2A agent's capabilities and commit the card."""
        card_data: dict[str, Any] = {}
        try:
            import httpx  # type: ignore[import]
            from a2a.client import A2ACardResolver  # type: ignore[import]

            async with httpx.AsyncClient() as http_client:
                resolver = A2ACardResolver(
                    httpx_client=http_client,
                    base_url=self._base_url,
                )
                card = await resolver.get_agent_card()
                card_data = card.model_dump(mode="json", exclude_none=True)

        except ImportError:
            logger.error("a2a-sdk not installed")
            card_data = {"error": "a2a-sdk not installed"}
        except Exception as e:
            logger.warning("A2A discovery failed: %s", e, exc_info=True)
            card_data = {"error": str(e)}

        # Commit discovery event
        try:
            self._engine.commit_state(
                {
                    "memory": {"discovered_agent": card_data},
                    "world_state": {
                        "a2a_remote": self._base_url,
                        "a2a_phase": "discovery",
                    },
                },
                message=f"a2a-discover: {card_data.get('name', self._base_url)}",
                action_type="system_event",
            )
        except Exception:
            logger.warning("Failed to commit discovery event", exc_info=True)

        return card_data


def create_agent_card(
    name: str,
    description: str,
    url: str,
    *,
    version: str = "1.0.0",
    skills: list[dict[str, Any]] | None = None,
    streaming: bool = False,
) -> Any:
    """Helper to create an A2A AgentCard with agit metadata.

    Returns an AgentCard instance if a2a-sdk is installed, else a dict.
    """
    skill_defs = skills or [
        {
            "id": "agit_versioning",
            "name": "State Versioning",
            "description": "Git-like version control for agent state",
            "tags": ["versioning", "audit", "rollback"],
            "examples": ["Track my agent state", "Show commit history"],
        },
    ]

    if _A2A_AVAILABLE:
        return AgentCard(
            name=name,
            description=description,
            url=url,
            version=version,
            default_input_modes=["text", "data"],
            default_output_modes=["text", "data"],
            capabilities=AgentCapabilities(streaming=streaming),
            skills=[
                AgentSkill(**s) if isinstance(s, dict) else s
                for s in skill_defs
            ],
        )

    return {
        "name": name,
        "description": description,
        "url": url,
        "version": version,
        "defaultInputModes": ["text", "data"],
        "defaultOutputModes": ["text", "data"],
        "capabilities": {"streaming": streaming},
        "skills": skill_defs,
    }
