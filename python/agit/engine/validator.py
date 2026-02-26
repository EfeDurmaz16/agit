"""ValidatorRegistry – pre/post-condition checks for agent actions."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("agit.engine.validator")


class ValidationStage(str, Enum):
    PRE = "pre"
    POST = "post"


@dataclass
class ValidationResult:
    """Result of running a single validator."""

    name: str
    stage: str
    passed: bool
    message: str = ""

    def __bool__(self) -> bool:
        return self.passed


@dataclass
class ValidationReport:
    """Aggregated results from all validators."""

    results: list[ValidationResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failures(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.passed]

    def raise_on_failure(self) -> None:
        if not self.passed:
            msgs = "; ".join(f"[{r.name}] {r.message}" for r in self.failures)
            raise ValueError(f"Validation failed: {msgs}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "results": [
                {"name": r.name, "stage": r.stage, "passed": r.passed, "message": r.message}
                for r in self.results
            ],
        }


# Type aliases
PreCheckFn = Callable[[dict[str, Any]], bool | tuple[bool, str]]
PostCheckFn = Callable[[dict[str, Any], dict[str, Any]], bool | tuple[bool, str]]


class ValidatorRegistry:
    """Registry of named pre- and post-condition validators.

    Usage::

        registry = ValidatorRegistry()
        registry.register("no_empty_memory", lambda s: bool(s.get("memory")), stage="pre")
        report = registry.validate_pre(state)
        report.raise_on_failure()
    """

    def __init__(self) -> None:
        self._pre: dict[str, PreCheckFn] = {}
        self._post: dict[str, PostCheckFn] = {}
        self._register_builtins()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        check_fn: PreCheckFn | PostCheckFn,
        stage: str = "pre",
    ) -> None:
        """Register a validator.

        Parameters
        ----------
        name:
            Unique name for the validator.
        check_fn:
            For ``stage="pre"``: ``(state) -> bool | (bool, message)``
            For ``stage="post"``: ``(old_state, new_state) -> bool | (bool, message)``
        stage:
            Either ``"pre"`` or ``"post"``.
        """
        if stage == ValidationStage.PRE:
            self._pre[name] = check_fn  # type: ignore[assignment]
        elif stage == ValidationStage.POST:
            self._post[name] = check_fn  # type: ignore[assignment]
        else:
            raise ValueError(f"Unknown stage {stage!r}; expected 'pre' or 'post'")

    def unregister(self, name: str) -> None:
        """Remove a validator by name from both stages."""
        self._pre.pop(name, None)
        self._post.pop(name, None)

    def list_validators(self) -> dict[str, list[str]]:
        return {"pre": list(self._pre), "post": list(self._post)}

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_pre(self, state: dict[str, Any]) -> ValidationReport:
        """Run all pre-condition validators against *state*."""
        results: list[ValidationResult] = []
        for name, fn in self._pre.items():
            try:
                outcome = fn(state)
                passed, msg = self._unpack(outcome)
            except Exception as exc:
                passed, msg = False, f"exception: {exc}"
            results.append(ValidationResult(name=name, stage="pre", passed=passed, message=msg))
        return ValidationReport(results=results)

    def validate_post(
        self,
        old_state: dict[str, Any],
        new_state: dict[str, Any],
    ) -> ValidationReport:
        """Run all post-condition validators."""
        results: list[ValidationResult] = []
        for name, fn in self._post.items():
            try:
                outcome = fn(old_state, new_state)
                passed, msg = self._unpack(outcome)
            except Exception as exc:
                passed, msg = False, f"exception: {exc}"
            results.append(ValidationResult(name=name, stage="post", passed=passed, message=msg))
        return ValidationReport(results=results)

    # ------------------------------------------------------------------
    # Built-in validators
    # ------------------------------------------------------------------

    def _register_builtins(self) -> None:
        self.register("cost_limit", _cost_limit_check, stage="pre")
        self.register("state_size_limit", _state_size_limit_check, stage="pre")
        self.register("state_not_regressed", _state_not_regressed_check, stage="post")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _unpack(outcome: bool | tuple[bool, str]) -> tuple[bool, str]:
        if isinstance(outcome, tuple):
            return outcome[0], str(outcome[1])
        return bool(outcome), ""


# ---------------------------------------------------------------------------
# Built-in check functions (module-level so they can be imported/overridden)
# ---------------------------------------------------------------------------

#: Default maximum cumulative cost allowed in the state (in USD).
DEFAULT_COST_LIMIT: float = 100.0

#: Default maximum state size in bytes (serialised JSON).
DEFAULT_STATE_SIZE_LIMIT: int = 10 * 1024 * 1024  # 10 MB


def _cost_limit_check(
    state: dict[str, Any],
    limit: float = DEFAULT_COST_LIMIT,
) -> tuple[bool, str]:
    """Fail if ``state['memory']['cumulative_cost']`` exceeds *limit*."""
    cost = float(state.get("memory", state).get("cumulative_cost", 0.0))
    if cost > limit:
        return False, f"cumulative_cost {cost:.4f} exceeds limit {limit}"
    return True, ""


def _state_size_limit_check(
    state: dict[str, Any],
    limit: int = DEFAULT_STATE_SIZE_LIMIT,
) -> tuple[bool, str]:
    """Fail if the serialised JSON state exceeds *limit* bytes."""
    try:
        size = len(json.dumps(state).encode())
    except Exception:
        logger.warning("Failed to serialise state for size check", exc_info=True)
        return False, "could not serialise state"
    if size > limit:
        return False, f"state size {size} bytes exceeds limit {limit} bytes"
    return True, ""


def _state_not_regressed_check(
    old_state: dict[str, Any],
    new_state: dict[str, Any],
) -> tuple[bool, str]:
    """Post-condition: warn if the state shrank unexpectedly (memory key count dropped)."""
    old_keys = len(old_state.get("memory", old_state))
    new_keys = len(new_state.get("memory", new_state))
    if new_keys < old_keys // 2 and old_keys > 0:
        return (
            False,
            f"state memory shrank from {old_keys} keys to {new_keys} keys – possible regression",
        )
    return True, ""
