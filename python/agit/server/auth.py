"""API key authentication middleware.

Supports two modes:
- Environment-based: Set AGIT_API_KEYS as a JSON object mapping keys to {tenant, agent_id}.
- Programmatic: Call register_api_key() at startup.

No hardcoded keys. No default authentication bypass.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from enum import Enum
from typing import Any

from fastapi import Header, HTTPException, Request


class Role(str, Enum):
    ADMIN = "admin"
    WRITE = "write"
    READ = "read"


class Permission(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


# Role -> permissions mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {Permission.READ, Permission.WRITE, Permission.ADMIN},
    Role.WRITE: {Permission.READ, Permission.WRITE},
    Role.READ: {Permission.READ},
}

logger = logging.getLogger("agit.server.auth")

# API key store -- populated from environment or programmatic registration.
_API_KEYS: dict[str, dict[str, str]] = {}


def _load_keys_from_env() -> None:
    """Load API keys from AGIT_API_KEYS environment variable.

    Expected format: JSON object mapping key strings to {tenant, agent_id} objects.
    Example: AGIT_API_KEYS='{"sk-prod-abc": {"tenant": "acme", "agent_id": "agent-1"}}'
    """
    raw = os.environ.get("AGIT_API_KEYS", "")
    if not raw:
        return
    try:
        keys = json.loads(raw)
        if isinstance(keys, dict):
            for key, info in keys.items():
                if isinstance(info, dict) and "tenant" in info:
                    entry: dict[str, str] = {
                        "tenant": info["tenant"],
                        "agent_id": info.get("agent_id", "api-agent"),
                    }
                    if "role" in info:
                        entry["role"] = info["role"]
                    _API_KEYS[key] = entry
            logger.info("Loaded %d API key(s) from AGIT_API_KEYS env var", len(_API_KEYS))
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(
            "Failed to parse AGIT_API_KEYS env var: %s. "
            "Server will start with no API keys configured.",
            exc,
        )


# Load keys from environment at module import time.
_load_keys_from_env()


def register_api_key(key: str, tenant: str, agent_id: str = "api-agent", role: str | None = None) -> None:
    """Register an API key for a tenant programmatically."""
    entry: dict[str, str] = {"tenant": tenant, "agent_id": agent_id}
    if role is not None:
        entry["role"] = role
    _API_KEYS[key] = entry


def validate_api_key(
    x_api_key: str = Header(..., description="API key for authentication"),
) -> dict[str, str]:
    """Validate the X-API-Key header and return tenant info.

    Uses constant-time comparison to prevent timing attacks.

    Returns dict with 'tenant' and 'agent_id' keys.
    Raises 401 if no key provided or key is invalid.
    """
    if not _API_KEYS:
        raise HTTPException(
            status_code=503,
            detail="No API keys configured. Set AGIT_API_KEYS env var or call register_api_key().",
        )
    # Constant-time comparison to prevent timing side-channel attacks.
    for stored_key, info in _API_KEYS.items():
        if hmac.compare_digest(stored_key, x_api_key):
            return info
    logger.warning("Invalid API key attempt (key prefix: %s...)", x_api_key[:8] if len(x_api_key) > 8 else "***")
    raise HTTPException(status_code=401, detail="Invalid API key")


def _resolve_key(api_key: str) -> dict[str, str] | None:
    """Resolve an API key string to its metadata dict, or None if invalid.

    Uses constant-time comparison to prevent timing side-channel attacks.
    """
    for stored_key, info in _API_KEYS.items():
        if hmac.compare_digest(stored_key, api_key):
            return info
    return None


def require_permission(permission: Permission):
    """FastAPI dependency that checks API key has the required permission."""
    async def _check(request: Request) -> dict[str, str]:
        if not _API_KEYS:
            raise HTTPException(
                status_code=503,
                detail="No API keys configured. Set AGIT_API_KEYS env var or call register_api_key().",
            )

        api_key = request.headers.get("x-api-key")
        if not api_key:
            raise HTTPException(status_code=401, detail="Missing API key")

        key_info = _resolve_key(api_key)
        if key_info is None:
            logger.warning(
                "Invalid API key attempt (key prefix: %s...)",
                api_key[:8] if len(api_key) > 8 else "***",
            )
            raise HTTPException(status_code=401, detail="Invalid API key")

        role_str = key_info.get("role", "read")
        try:
            role = Role(role_str)
        except ValueError:
            role = Role.READ

        if permission not in ROLE_PERMISSIONS.get(role, set()):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions: requires {permission.value}",
            )

        return key_info

    return _check
