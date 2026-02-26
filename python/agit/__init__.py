"""agit - Git-like version control for AI agents."""
from __future__ import annotations

# Attempt to import the native Rust extension. Fall back to pure-Python stubs
# so the package remains importable even when the native wheel is not yet built.
try:
    import agit_core  # type: ignore[import]

    PyRepository = agit_core.PyRepository
    PyAgentState = agit_core.PyAgentState
    PyCommit = agit_core.PyCommit
    PyStateDiff = agit_core.PyStateDiff
    PyDiffEntry = agit_core.PyDiffEntry
    NATIVE_AVAILABLE = True
except ImportError:
    from agit._stubs import (  # type: ignore[import]
        PyAgentState,
        PyCommit,
        PyDiffEntry,
        PyRepository,
        PyStateDiff,
    )

    NATIVE_AVAILABLE = False

from agit.engine.executor import ExecutionEngine
from agit.engine.retry import RetryEngine
from agit.engine.validator import ValidatorRegistry

__all__ = [
    # Engine
    "ExecutionEngine",
    "RetryEngine",
    "ValidatorRegistry",
    # Core types (native or stub)
    "PyRepository",
    "PyAgentState",
    "PyCommit",
    "PyStateDiff",
    "PyDiffEntry",
    "NATIVE_AVAILABLE",
]

__version__ = "0.1.0"
