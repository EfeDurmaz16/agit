"""RetryEngine – branch-per-retry with exponential backoff."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from agit.engine.executor import ExecutionEngine

logger = logging.getLogger("agit.engine.retry")


@dataclass
class RetryAttempt:
    """Record of a single retry attempt."""

    attempt_number: int
    branch_name: str
    success: bool
    commit_hash: str | None = None
    error: str | None = None
    elapsed: float = 0.0
    timestamp: str = ""


@dataclass
class RetryHistory:
    """Aggregated history of all retry attempts for one logical action."""

    action_message: str
    attempts: list[RetryAttempt] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return any(a.success for a in self.attempts)

    @property
    def total_attempts(self) -> int:
        return len(self.attempts)

    def summary(self) -> dict[str, Any]:
        return {
            "action": self.action_message,
            "total_attempts": self.total_attempts,
            "succeeded": self.succeeded,
            "attempts": [
                {
                    "attempt": a.attempt_number,
                    "branch": a.branch_name,
                    "success": a.success,
                    "commit_hash": a.commit_hash,
                    "error": a.error,
                    "elapsed": a.elapsed,
                    "timestamp": a.timestamp,
                }
                for a in self.attempts
            ],
        }


class RetryEngine:
    """Execute agent actions with automatic retry and branch-per-attempt isolation.

    On each failure a new branch is created from the pre-action state so that
    every retry attempt is fully isolated and auditable.

    Parameters
    ----------
    executor:
        An already-initialised :class:`ExecutionEngine`.
    max_retries:
        Maximum number of retry attempts (not counting the initial attempt).
    base_delay:
        Base delay in seconds for exponential backoff.
    """

    def __init__(
        self,
        executor: ExecutionEngine,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        self._executor = executor
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._history: list[RetryHistory] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_with_retry(
        self,
        action_fn: Callable[..., Any],
        state: dict[str, Any],
        message: str,
        action_type: str = "tool_call",
    ) -> tuple[Any, RetryHistory]:
        """Execute *action_fn* with retry-on-failure.

        Returns
        -------
        (result, retry_history):
            The successful result (or raises if all attempts exhausted) and the
            full :class:`RetryHistory` for this invocation.
        """
        run_id = uuid.uuid4().hex[:8]
        history = RetryHistory(action_message=message)
        self._history.append(history)

        # Save the pre-action state so each retry starts from the same baseline
        base_branch = self._executor.current_branch() or "main"
        pre_state_hash = self._executor.commit_state(state, f"pre-retry-base: {message}", "checkpoint")

        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            branch_name = f"retry/{run_id}/attempt-{attempt}" if attempt > 0 else base_branch
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            if attempt > 0:
                # Create an isolated branch from the pre-action snapshot
                try:
                    self._executor.branch(branch_name, from_ref=pre_state_hash)
                    self._executor.checkout(branch_name)
                except Exception:
                    logger.warning("Failed to create retry branch %s", branch_name, exc_info=True)
                    try:
                        self._executor.checkout(base_branch)
                    except Exception:
                        logger.warning("Failed to restore base branch %s", base_branch, exc_info=True)

                # Exponential backoff
                delay = self._base_delay * (2 ** (attempt - 1))
                logger.info("Retry attempt %d/%d for '%s' (delay=%.1fs)", attempt, self._max_retries, message, delay)
                time.sleep(delay)

            start_ts = time.monotonic()
            try:
                result, commit_hash = self._executor.execute(action_fn, state, message, action_type)
                elapsed = time.monotonic() - start_ts

                history.attempts.append(
                    RetryAttempt(
                        attempt_number=attempt,
                        branch_name=branch_name,
                        success=True,
                        commit_hash=commit_hash,
                        elapsed=elapsed,
                        timestamp=timestamp,
                    )
                )

                # If we succeeded on a retry branch, merge back to base
                if attempt > 0:
                    try:
                        self._executor.checkout(base_branch)
                        self._executor.merge(branch_name, strategy="theirs")
                        logger.info("Retry succeeded on attempt %d, merged %s -> %s", attempt, branch_name, base_branch)
                    except Exception:
                        logger.warning("Failed to merge retry branch %s back to %s", branch_name, base_branch, exc_info=True)

                return result, history

            except Exception as exc:
                elapsed = time.monotonic() - start_ts
                last_exc = exc
                history.attempts.append(
                    RetryAttempt(
                        attempt_number=attempt,
                        branch_name=branch_name,
                        success=False,
                        error=str(exc),
                        elapsed=elapsed,
                        timestamp=timestamp,
                    )
                )

                logger.warning("Attempt %d failed for '%s': %s", attempt, message, exc)

                # Return to base branch for next iteration
                if attempt > 0:
                    try:
                        self._executor.checkout(base_branch)
                    except Exception:
                        logger.warning("Failed to restore base branch after failed attempt", exc_info=True)

        logger.error("Action '%s' exhausted all %d retries", message, self._max_retries + 1)
        raise RuntimeError(
            f"Action '{message}' failed after {self._max_retries + 1} attempts. "
            f"Last error: {last_exc}"
        ) from last_exc

    def get_retry_history(self) -> list[dict[str, Any]]:
        """Return all retry histories as plain dicts."""
        return [h.summary() for h in self._history]

    def clear_history(self) -> None:
        """Clear the in-memory retry history."""
        self._history.clear()
