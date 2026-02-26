"""REST API routes for agit operations."""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, Query

from agit.engine.executor import ExecutionEngine

from .auth import validate_api_key
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
    if key not in _engines:
        repo_path = os.path.join(_STORAGE_ROOT, tenant)
        os.makedirs(repo_path, exist_ok=True)
        _engines[key] = ExecutionEngine(repo_path=repo_path, agent_id=agent_id)
        logger.info("Created engine for tenant=%s agent=%s", tenant, agent_id)
    return _engines[key]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@router.post("/commits", response_model=CommitResponse)
async def create_commit(
    req: CommitRequest,
    tenant_info: dict[str, str] = Depends(validate_api_key),
) -> CommitResponse:
    """Commit agent state."""
    engine = _get_engine(tenant_info)
    h = engine.commit_state(req.state, req.message, req.action_type)
    return CommitResponse(hash=h, message=req.message)


@router.get("/commits", response_model=CommitsResponse)
async def list_commits(
    limit: int = Query(default=50, le=500),
    tenant_info: dict[str, str] = Depends(validate_api_key),
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
    tenant_info: dict[str, str] = Depends(validate_api_key),
) -> CommitWithState:
    """Get state at a specific commit."""
    engine = _get_engine(tenant_info)
    current = engine.current_branch() or "main"
    state = engine.checkout(commit_hash)
    engine.checkout(current)
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
    tenant_info: dict[str, str] = Depends(validate_api_key),
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
    tenant_info: dict[str, str] = Depends(validate_api_key),
) -> BranchResponse:
    """Create a new branch."""
    engine = _get_engine(tenant_info)
    engine.branch(req.name, from_ref=req.from_ref)
    branches = engine.list_branches()
    return BranchResponse(name=req.name, hash=branches.get(req.name, ""))


@router.get("/branches", response_model=BranchList)
async def list_branches(
    tenant_info: dict[str, str] = Depends(validate_api_key),
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
    tenant_info: dict[str, str] = Depends(validate_api_key),
) -> CheckoutResponse:
    """Checkout a branch or commit."""
    engine = _get_engine(tenant_info)
    state = engine.checkout(req.target)
    return CheckoutResponse(target=req.target, state=state)


@router.post("/merge", response_model=MergeResponse)
async def merge(
    req: MergeRequest,
    tenant_info: dict[str, str] = Depends(validate_api_key),
) -> MergeResponse:
    """Merge a branch into HEAD."""
    engine = _get_engine(tenant_info)
    h = engine.merge(req.branch, strategy=req.strategy)
    return MergeResponse(merge_commit=h)


@router.post("/revert", response_model=RevertResponse)
async def revert(
    req: RevertRequest,
    tenant_info: dict[str, str] = Depends(validate_api_key),
) -> RevertResponse:
    """Revert to a previous commit."""
    engine = _get_engine(tenant_info)
    state = engine.revert(req.commit_hash)
    return RevertResponse(reverted_to=req.commit_hash, state=state)


@router.get("/audit", response_model=AuditResponse)
async def audit_log(
    limit: int = Query(default=100, le=1000),
    tenant_info: dict[str, str] = Depends(validate_api_key),
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


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(description="Search query"),
    action_type: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    tenant_info: dict[str, str] = Depends(validate_api_key),
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
