"""agit - Git-like version control for AI agents."""
from __future__ import annotations

# Attempt to import the native Rust extension. Fall back to pure-Python stubs
# so the package remains importable even when the native wheel is not yet built.
try:
    import agit_core  # type: ignore[import]

    # Native module exports names without Py prefix
    PyRepository = getattr(agit_core, "PyRepository", None) or agit_core.Repository
    PyAgentState = getattr(agit_core, "PyAgentState", None) or agit_core.AgentState
    PyCommit = getattr(agit_core, "PyCommit", None) or agit_core.Commit
    PyStateDiff = getattr(agit_core, "PyStateDiff", None) or agit_core.StateDiff
    PyDiffEntry = getattr(agit_core, "PyDiffEntry", None) or agit_core.DiffEntry
    NATIVE_AVAILABLE = True
except (ImportError, AttributeError):
    import warnings

    from agit._stubs import (  # type: ignore[import]
        PyAgentState,
        PyCommit,
        PyDiffEntry,
        PyRepository,
        PyStateDiff,
    )

    NATIVE_AVAILABLE = False
    warnings.warn(
        "agit-core native module not found; using pure-Python stubs. "
        "Install agit-core for better performance: pip install agit[native]",
        ImportWarning,
        stacklevel=2,
    )

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
