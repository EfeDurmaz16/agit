"""Pydantic models for request/response schemas."""
from __future__ import annotations

import sys
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Maximum request body size: 10 MB
MAX_STATE_SIZE_BYTES = 10 * 1024 * 1024


class CommitRequest(BaseModel):
    state: dict[str, Any] = Field(description="Agent state to commit")
    message: str = Field(max_length=4096, description="Commit message")
    action_type: str = Field(default="checkpoint", max_length=64, description="Action type")

    @field_validator("state")
    @classmethod
    def validate_state_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        estimated = sys.getsizeof(str(v))
        if estimated > MAX_STATE_SIZE_BYTES:
            raise ValueError(f"State too large: {estimated} bytes (max {MAX_STATE_SIZE_BYTES})")
        return v


class CommitResponse(BaseModel):
    ok: bool = True
    hash: str
    message: str


class CommitDetail(BaseModel):
    hash: str
    message: str
    author: str
    timestamp: str
    action_type: str
    parent_hashes: list[str] = []


class CommitWithState(BaseModel):
    commit: CommitDetail
    state: dict[str, Any]


class CommitsResponse(BaseModel):
    ok: bool = True
    commits: list[CommitDetail]
    count: int


class DiffEntry(BaseModel):
    path: str
    change_type: str
    old_value: Any = None
    new_value: Any = None


class DiffResponse(BaseModel):
    ok: bool = True
    base_hash: str
    target_hash: str
    entries: list[DiffEntry]


class BranchRequest(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,254}$", description="Branch name")
    from_ref: str | None = Field(default=None, max_length=255, description="Source ref")


class BranchResponse(BaseModel):
    ok: bool = True
    name: str
    hash: str = ""


class BranchList(BaseModel):
    ok: bool = True
    branches: dict[str, str]
    current: str | None = None


class CheckoutRequest(BaseModel):
    target: str = Field(max_length=255, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,254}$", description="Branch name or commit hash")


class CheckoutResponse(BaseModel):
    ok: bool = True
    target: str
    state: dict[str, Any]


class MergeRequest(BaseModel):
    branch: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,254}$", description="Branch to merge into HEAD")
    strategy: str = Field(default="three_way", pattern=r"^(ours|theirs|three_way)$")


class MergeResponse(BaseModel):
    ok: bool = True
    merge_commit: str


class RevertRequest(BaseModel):
    commit_hash: str = Field(max_length=128, pattern=r"^[a-fA-F0-9]{4,128}$", description="Commit to revert to")


class RevertResponse(BaseModel):
    ok: bool = True
    reverted_to: str
    state: dict[str, Any]


class AuditEntry(BaseModel):
    id: str = ""
    timestamp: str = ""
    agent_id: str = ""
    action: str = ""
    message: str = ""
    commit_hash: str | None = None


class AuditResponse(BaseModel):
    ok: bool = True
    entries: list[AuditEntry]
    count: int


class SearchResponse(BaseModel):
    ok: bool = True
    results: list[CommitDetail]
    count: int


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"


class ErrorResponse(BaseModel):
    ok: bool = False
    error: str
