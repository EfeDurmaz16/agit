"""REST API routes for agit operations."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from agit.engine.executor import ExecutionEngine

from .auth import Permission, require_permission, validate_api_key
from .models import (
    AuditEntry,
    AuditResponse,
    BranchList,
    BranchRequest,
    BranchResponse,
    CheckoutRequest,
    CheckoutResponse,
    CommitDetail,
    CommitRequest,
    CommitResponse,
    CommitsResponse,
    CommitWithState,
    DiffEntry,
    DiffResponse,
    ErrorResponse,
    HealthResponse,
    MergeRequest,
    MergeResponse,
    RevertRequest,
    RevertResponse,
    SearchResponse,
)

logger = logging.getLogger("agit.server.routes")

router = APIRouter(prefix="/api/v1")

# Tenant-isolated engines
_engines: dict[str, ExecutionEngine] = {}
_ENGINE_CACHE_ENABLED = os.environ.get("AGIT_ENGINE_CACHE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Configurable storage root (default: platform-appropriate data dir)
_STORAGE_ROOT = os.environ.get("AGIT_STORAGE_ROOT", os.path.join(os.path.expanduser("~"), ".agit", "tenants"))

# Regex for valid tenant/agent identifiers (prevents path traversal)
_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,254}$")


def _get_engine(tenant_info: dict[str, str]) -> ExecutionEngine:
    """Get or create an ExecutionEngine for the tenant."""
    tenant = tenant_info["tenant"]
    agent_id = tenant_info["agent_id"]

    # Validate tenant and agent_id to prevent path traversal
    if not _SAFE_ID.match(tenant):
        raise ValueError(f"Invalid tenant identifier: {tenant}")
    if not _SAFE_ID.match(agent_id):
        raise ValueError(f"Invalid agent_id identifier: {agent_id}")

    key = f"{tenant}:{agent_id}"
    repo_path = os.path.join(_STORAGE_ROOT, tenant)
    os.makedirs(repo_path, exist_ok=True)

    if not _ENGINE_CACHE_ENABLED:
        return ExecutionEngine(repo_path=repo_path, agent_id=agent_id)

    if key not in _engines:
        _engines[key] = ExecutionEngine(repo_path=repo_path, agent_id=agent_id)
        logger.info("Created cached engine for tenant=%s agent=%s", tenant, agent_id)
    return _engines[key]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@router.post("/commits", response_model=CommitResponse)
async def create_commit(
    req: CommitRequest,
    tenant_info: dict[str, str] = Depends(require_permission(Permission.WRITE)),
) -> CommitResponse:
    """Commit agent state."""
    engine = _get_engine(tenant_info)
    h = engine.commit_state(req.state, req.message, req.action_type)
    # Emit event
    from .event_bus import get_event_bus, AgitEvent
    bus = get_event_bus()
    await bus.publish(AgitEvent(
        event_type="commit_created",
        data={"hash": h, "message": req.message, "action_type": req.action_type},
    ))
    return CommitResponse(hash=h, message=req.message)


@router.get("/commits", response_model=CommitsResponse)
async def list_commits(
    limit: int = Query(default=50, le=500),
    tenant_info: dict[str, str] = Depends(require_permission(Permission.READ)),
) -> CommitsResponse:
    """List commit history."""
    engine = _get_engine(tenant_info)
    commits = engine.get_history(limit)
    items = [
        CommitDetail(
            hash=c.get("hash", ""),
            message=c.get("message", ""),
            author=c.get("author", ""),
            timestamp=c.get("timestamp", ""),
            action_type=c.get("action_type", ""),
            parent_hashes=c.get("parent_hashes", []),
        )
        for c in commits
    ]
    return CommitsResponse(commits=items, count=len(items))


@router.get("/commits/{commit_hash}", response_model=CommitWithState)
async def get_commit_state(
    commit_hash: str,
    tenant_info: dict[str, str] = Depends(require_permission(Permission.READ)),
) -> CommitWithState:
    """Get state at a specific commit."""
    engine = _get_engine(tenant_info)
    state = engine.get_state_at(commit_hash)
    commits = engine.get_history(500)
    commit_data = next((c for c in commits if c.get("hash") == commit_hash), {})
    return CommitWithState(
        commit=CommitDetail(
            hash=commit_data.get("hash", commit_hash),
            message=commit_data.get("message", ""),
            author=commit_data.get("author", ""),
            timestamp=commit_data.get("timestamp", ""),
            action_type=commit_data.get("action_type", ""),
            parent_hashes=commit_data.get("parent_hashes", []),
        ),
        state=state,
    )


@router.get("/diff", response_model=DiffResponse)
async def get_diff(
    hash1: str = Query(description="Base commit hash"),
    hash2: str = Query(description="Target commit hash"),
    tenant_info: dict[str, str] = Depends(require_permission(Permission.READ)),
) -> DiffResponse:
    """Get diff between two commits."""
    engine = _get_engine(tenant_info)
    d = engine.diff(hash1, hash2)
    entries = [
        DiffEntry(
            path=e.get("path", ""),
            change_type=e.get("change_type", ""),
            old_value=e.get("old_value"),
            new_value=e.get("new_value"),
        )
        for e in d.get("entries", [])
    ]
    return DiffResponse(
        base_hash=d.get("base_hash", hash1),
        target_hash=d.get("target_hash", hash2),
        entries=entries,
    )


@router.post("/branches", response_model=BranchResponse)
async def create_branch(
    req: BranchRequest,
    tenant_info: dict[str, str] = Depends(require_permission(Permission.WRITE)),
) -> BranchResponse:
    """Create a new branch."""
    engine = _get_engine(tenant_info)
    engine.branch(req.name, from_ref=req.from_ref)
    branches = engine.list_branches()
    # Emit event
    from .event_bus import get_event_bus, AgitEvent
    bus = get_event_bus()
    await bus.publish(AgitEvent(
        event_type="branch_created",
        data={"name": req.name, "from_ref": req.from_ref or "HEAD"},
    ))
    return BranchResponse(name=req.name, hash=branches.get(req.name, ""))


@router.get("/branches", response_model=BranchList)
async def list_branches(
    tenant_info: dict[str, str] = Depends(require_permission(Permission.READ)),
) -> BranchList:
    """List all branches."""
    engine = _get_engine(tenant_info)
    return BranchList(
        branches=engine.list_branches(),
        current=engine.current_branch(),
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(
    req: CheckoutRequest,
    tenant_info: dict[str, str] = Depends(require_permission(Permission.WRITE)),
) -> CheckoutResponse:
    """Checkout a branch or commit."""
    engine = _get_engine(tenant_info)
    state = engine.checkout(req.target)
    return CheckoutResponse(target=req.target, state=state)


@router.post("/merge", response_model=MergeResponse)
async def merge(
    req: MergeRequest,
    tenant_info: dict[str, str] = Depends(require_permission(Permission.WRITE)),
) -> MergeResponse:
    """Merge a branch into HEAD."""
    engine = _get_engine(tenant_info)
    h = engine.merge(req.branch, strategy=req.strategy)
    # Emit event
    from .event_bus import get_event_bus, AgitEvent
    bus = get_event_bus()
    await bus.publish(AgitEvent(
        event_type="merge_completed",
        data={"merge_hash": h, "branch": req.branch, "strategy": req.strategy},
    ))
    return MergeResponse(merge_commit=h)


@router.post("/revert", response_model=RevertResponse)
async def revert(
    req: RevertRequest,
    tenant_info: dict[str, str] = Depends(require_permission(Permission.WRITE)),
) -> RevertResponse:
    """Revert to a previous commit."""
    engine = _get_engine(tenant_info)
    state = engine.revert(req.commit_hash)
    # Emit event
    from .event_bus import get_event_bus, AgitEvent
    bus = get_event_bus()
    await bus.publish(AgitEvent(
        event_type="revert_performed",
        data={"commit_hash": req.commit_hash},
    ))
    return RevertResponse(reverted_to=req.commit_hash, state=state)


@router.get("/audit", response_model=AuditResponse)
async def audit_log(
    limit: int = Query(default=100, le=1000),
    tenant_info: dict[str, str] = Depends(require_permission(Permission.READ)),
) -> AuditResponse:
    """Get audit log entries."""
    engine = _get_engine(tenant_info)
    logs = engine.audit_log(limit)
    entries = [
        AuditEntry(
            id=e.get("id", ""),
            timestamp=e.get("timestamp", ""),
            agent_id=e.get("agent_id", ""),
            action=e.get("action", ""),
            message=e.get("message", ""),
            commit_hash=e.get("commit_hash"),
        )
        for e in logs
    ]
    return AuditResponse(entries=entries, count=len(entries))


@router.post("/bisect/start")
async def bisect_start(
    good_hash: str = Query(description="Known good commit"),
    bad_hash: str = Query(description="Known bad commit"),
    tenant_info: dict[str, str] = Depends(require_permission(Permission.WRITE)),
):
    """Start a bisect session."""
    engine = _get_engine(tenant_info)
    result = engine.bisect_start(good_hash, bad_hash)
    return {"ok": True, **result}


@router.post("/bisect/step")
async def bisect_step(
    mark: str = Query(description="Mark current as 'good' or 'bad'", pattern="^(good|bad)$"),
    tenant_info: dict[str, str] = Depends(require_permission(Permission.WRITE)),
):
    """Step through bisect session."""
    engine = _get_engine(tenant_info)
    result = engine.bisect_step(mark)
    return {"ok": True, **result}


@router.post("/bisect/reset")
async def bisect_reset(
    tenant_info: dict[str, str] = Depends(require_permission(Permission.WRITE)),
):
    """Reset bisect session."""
    engine = _get_engine(tenant_info)
    engine.bisect_reset()
    return {"ok": True}


@router.get("/causal")
async def get_causal_graph(
    head_hash: str | None = Query(default=None, description="Start from this commit"),
    depth: int = Query(default=50, le=200, description="Max depth to traverse"),
    tenant_info: dict[str, str] = Depends(require_permission(Permission.READ)),
):
    """Get causal dependency graph."""
    engine = _get_engine(tenant_info)
    graph = engine.get_causal_graph(head_hash, depth)
    return {"ok": True, **graph}


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(description="Search query"),
    action_type: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    tenant_info: dict[str, str] = Depends(require_permission(Permission.READ)),
) -> SearchResponse:
    """Search commits by message or action type."""
    engine = _get_engine(tenant_info)
    commits = engine.get_history(limit * 5)
    query_lower = q.lower()
    results = []
    for c in commits:
        msg = c.get("message", "").lower()
        at = c.get("action_type", "")
        if query_lower in msg or query_lower in at:
            if action_type and at != action_type:
                continue
            results.append(
                CommitDetail(
                    hash=c.get("hash", ""),
                    message=c.get("message", ""),
                    author=c.get("author", ""),
                    timestamp=c.get("timestamp", ""),
                    action_type=c.get("action_type", ""),
                    parent_hashes=c.get("parent_hashes", []),
                )
            )
            if len(results) >= limit:
                break
    return SearchResponse(results=results, count=len(results))


# ---------------------------------------------------------------------------
# Event Streaming (SSE + WebSocket)
# ---------------------------------------------------------------------------

@router.get("/events/stream")
async def event_stream(
    last_event_id: str | None = Query(default=None, alias="Last-Event-ID"),
    tenant_info: dict[str, str] = Depends(require_permission(Permission.READ)),
):
    """Server-Sent Events stream for real-time updates."""
    from .event_bus import get_event_bus

    bus = get_event_bus()
    queue = await bus.subscribe()

    async def generate():
        try:
            # Send initial connection event
            yield f"event: connected\ndata: {{\"subscriber_count\": {bus.subscriber_count}}}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    import json as _json
                    data = _json.dumps({
                        "event_type": event.event_type,
                        "data": event.data,
                        "timestamp": event.timestamp,
                        "event_id": event.event_id,
                    })
                    yield f"id: {event.event_id}\nevent: {event.event_type}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await bus.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/events/history")
async def event_history(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=500),
    tenant_info: dict[str, str] = Depends(require_permission(Permission.READ)),
):
    """Get historical events."""
    from .event_bus import get_event_bus

    bus = get_event_bus()
    events = await bus.events_since(offset)
    limited = events[:limit]
    return {
        "ok": True,
        "events": [
            {
                "event_type": e.event_type,
                "data": e.data,
                "timestamp": e.timestamp,
                "event_id": e.event_id,
            }
            for e in limited
        ],
        "total": bus.event_count,
        "offset": offset,
    }


@router.get("/events/status")
async def event_status(
    tenant_info: dict[str, str] = Depends(require_permission(Permission.READ)),
):
    """Get event bus status."""
    from .event_bus import get_event_bus

    bus = get_event_bus()
    return {
        "ok": True,
        "subscribers": bus.subscriber_count,
        "total_events": bus.event_count,
    }
