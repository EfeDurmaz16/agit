"""LangGraph integration – BaseCheckpointSaver implementation."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Iterator, Optional

from agit.engine.executor import ExecutionEngine

try:
    from langgraph.checkpoint.base import (  # type: ignore[import]
        BaseCheckpointSaver,
        Checkpoint,
        CheckpointMetadata,
        CheckpointTuple,
        RunnableConfig,
    )

    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False

    # Minimal stubs
    class RunnableConfig(dict):  # type: ignore[no-redef]
        pass

    class CheckpointMetadata(dict):  # type: ignore[no-redef]
        pass

    class Checkpoint(dict):  # type: ignore[no-redef]
        pass

    class CheckpointTuple:  # type: ignore[no-redef]
        def __init__(self, config: Any, checkpoint: Any, metadata: Any, parent_config: Any = None):
            self.config = config
            self.checkpoint = checkpoint
            self.metadata = metadata
            self.parent_config = parent_config

    class BaseCheckpointSaver:  # type: ignore[no-redef]
        """Stub base class."""

        def get_tuple(self, config: Any) -> Optional["CheckpointTuple"]: ...
        def list(self, config: Any, **kwargs: Any) -> Iterator["CheckpointTuple"]: ...
        def put(self, config: Any, checkpoint: Any, metadata: Any) -> Any: ...
        async def aget_tuple(self, config: Any) -> Optional["CheckpointTuple"]: ...
        async def alist(self, config: Any, **kwargs: Any) -> AsyncIterator["CheckpointTuple"]: ...
        async def aput(self, config: Any, checkpoint: Any, metadata: Any) -> Any: ...


class AgitCheckpointSaver(BaseCheckpointSaver):  # type: ignore[misc]
    """LangGraph checkpoint saver that persists every checkpoint as an agit commit.

    Usage::

        engine = ExecutionEngine("./repo", agent_id="langgraph-agent")
        saver = AgitCheckpointSaver(engine)

        graph = StateGraph(...)
        compiled = graph.compile(checkpointer=saver)
    """

    def __init__(self, engine: ExecutionEngine) -> None:
        self._engine = engine
        # In-memory cache: thread_id -> list of (config, checkpoint, metadata)
        self._store: dict[str, list[tuple[Any, Any, Any]]] = {}

    # ------------------------------------------------------------------
    # Sync interface
    # ------------------------------------------------------------------

    def get_tuple(self, config: Any) -> Optional[CheckpointTuple]:  # type: ignore[override]
        thread_id = self._thread_id(config)
        entries = self._store.get(thread_id, [])
        if not entries:
            return None
        cfg, ckpt, meta = entries[-1]
        parent_cfg = None
        if len(entries) > 1:
            parent_cfg, _, _ = entries[-2]
        return CheckpointTuple(config=cfg, checkpoint=ckpt, metadata=meta, parent_config=parent_cfg)  # type: ignore[call-arg]

    def list(  # type: ignore[override]
        self,
        config: Any,
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[Any] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:  # type: ignore[override]
        thread_id = self._thread_id(config)
        entries = list(reversed(self._store.get(thread_id, [])))
        if limit:
            entries = entries[:limit]
        for i, (cfg, ckpt, meta) in enumerate(entries):
            parent_cfg = entries[i + 1][0] if i + 1 < len(entries) else None
            yield CheckpointTuple(config=cfg, checkpoint=ckpt, metadata=meta, parent_config=parent_cfg)  # type: ignore[call-arg]

    def put(  # type: ignore[override]
        self,
        config: Any,
        checkpoint: Any,
        metadata: Any,
        new_versions: Optional[Any] = None,
    ) -> Any:
        thread_id = self._thread_id(config)
        self._store.setdefault(thread_id, []).append((config, checkpoint, metadata))
        self._commit(thread_id, checkpoint, metadata)
        return config

    # ------------------------------------------------------------------
    # Async interface
    # ------------------------------------------------------------------

    async def aget_tuple(self, config: Any) -> Optional[CheckpointTuple]:  # type: ignore[override]
        return self.get_tuple(config)

    async def alist(  # type: ignore[override]
        self,
        config: Any,
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[Any] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:  # type: ignore[override]
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(  # type: ignore[override]
        self,
        config: Any,
        checkpoint: Any,
        metadata: Any,
        new_versions: Optional[Any] = None,
    ) -> Any:
        return self.put(config, checkpoint, metadata, new_versions)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _commit(self, thread_id: str, checkpoint: Any, metadata: Any) -> None:
        """Persist LangGraph checkpoint as an agit commit."""
        try:
            ckpt_dict = checkpoint if isinstance(checkpoint, dict) else vars(checkpoint)
            meta_dict = metadata if isinstance(metadata, dict) else vars(metadata)
            state = {
                "memory": {
                    "langgraph_checkpoint": ckpt_dict,
                    "langgraph_metadata": meta_dict,
                    "thread_id": thread_id,
                },
                "world_state": {},
            }
            step = meta_dict.get("step", "?")
            self._engine.commit_state(
                state,
                message=f"langgraph checkpoint thread={thread_id} step={step}",
                action_type="checkpoint",
            )
        except Exception:
            pass  # Never block LangGraph execution

    @staticmethod
    def _thread_id(config: Any) -> str:
        if isinstance(config, dict):
            return str(config.get("configurable", {}).get("thread_id", "default"))
        return "default"
