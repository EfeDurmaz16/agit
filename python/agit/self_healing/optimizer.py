"""Retry strategy optimization from historical failure data."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any


@dataclass
class RetryStrategy:
    """Parameters for a retry strategy.

    Attributes
    ----------
    max_retries:
        Maximum number of retry attempts.
    base_delay:
        Initial delay in seconds before the first retry.
    backoff_factor:
        Exponential backoff multiplier applied between retries.
    jitter:
        Maximum random jitter added to each delay (seconds), to avoid
        thundering-herd problems.
    """

    max_retries: int
    base_delay: float
    backoff_factor: float
    jitter: float

    def delay_for_attempt(self, attempt: int) -> float:
        """Compute the deterministic (no jitter) delay for *attempt* (0-based)."""
        return self.base_delay * (self.backoff_factor ** attempt)

    def max_total_delay(self) -> float:
        """Upper-bound total wait time across all retries (excluding jitter)."""
        return sum(self.delay_for_attempt(i) for i in range(self.max_retries))

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "backoff_factor": self.backoff_factor,
            "jitter": self.jitter,
        }


# Default strategies per failure type
_DEFAULT_STRATEGIES: dict[str, RetryStrategy] = {
    "transient": RetryStrategy(max_retries=5, base_delay=0.5, backoff_factor=2.0, jitter=0.5),
    "resource_limit": RetryStrategy(max_retries=4, base_delay=5.0, backoff_factor=3.0, jitter=2.0),
    "validation": RetryStrategy(max_retries=1, base_delay=0.0, backoff_factor=1.0, jitter=0.0),
    "logic": RetryStrategy(max_retries=0, base_delay=0.0, backoff_factor=1.0, jitter=0.0),
    "dependency": RetryStrategy(max_retries=3, base_delay=2.0, backoff_factor=2.0, jitter=1.0),
    "unknown": RetryStrategy(max_retries=3, base_delay=1.0, backoff_factor=2.0, jitter=0.5),
}


class RetryOptimizer:
    """Optimise retry strategies from historical failure/success logs.

    The optimiser analyses past retry logs (as produced by
    :class:`~agit.engine.retry.RetryEngine`) and adjusts retry parameters
    based on observed success rates and inter-attempt timing.

    Example::

        optimizer = RetryOptimizer()
        logs = engine.get_retry_history()

        analysis = optimizer.analyze(logs)
        strategy = optimizer.suggest_strategy("transient")
        print(strategy)
    """

    def __init__(self) -> None:
        # Learned per-type overrides (populated by analyze())
        self._learned: dict[str, RetryStrategy] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, logs: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyse historical retry logs and update learned strategies.

        Parameters
        ----------
        logs:
            List of retry history dicts as returned by
            :meth:`~agit.engine.retry.RetryEngine.get_retry_history`.
            Each entry has ``"attempts"`` (list of attempt dicts with
            ``"success"``, ``"elapsed"``, ``"error"``).

        Returns
        -------
        dict:
            Analysis summary with ``"success_rate"``, ``"avg_attempts"``,
            ``"optimal_backoff"``, and ``"recommendation"``.
        """
        if not logs:
            return {
                "success_rate": None,
                "avg_attempts": None,
                "optimal_backoff": None,
                "recommendation": "No data – using defaults",
            }

        success_rate = self._compute_success_rate(logs)
        optimal_backoff = self._optimal_backoff(logs)
        avg_attempts = self._average_attempts(logs)

        # Update learned strategies for common failure types
        self._update_learned_strategies(logs, success_rate, optimal_backoff)

        recommendation: str
        if success_rate >= 0.9:
            recommendation = "Strategy is performing well; minor tuning may improve efficiency"
        elif success_rate >= 0.7:
            recommendation = "Moderate success rate; consider increasing max_retries or base_delay"
        elif success_rate >= 0.5:
            recommendation = "Low success rate; increase backoff factor and add jitter"
        else:
            recommendation = "Very low success rate; review failure types and consider circuit-breaker"

        return {
            "success_rate": round(success_rate, 4),
            "avg_attempts": round(avg_attempts, 2),
            "optimal_backoff": round(optimal_backoff, 3),
            "recommendation": recommendation,
            "total_actions": len(logs),
        }

    def suggest_strategy(self, failure_type: str) -> RetryStrategy:
        """Return the recommended :class:`RetryStrategy` for *failure_type*.

        Returns a learned strategy if one has been derived from logs,
        otherwise falls back to built-in defaults.

        Parameters
        ----------
        failure_type:
            Failure type string (e.g. ``"transient"``, ``"resource_limit"``).
        """
        key = failure_type.lower()
        if key in self._learned:
            return self._learned[key]
        return _DEFAULT_STRATEGIES.get(key, _DEFAULT_STRATEGIES["unknown"])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_success_rate(self, logs: list[dict[str, Any]]) -> float:
        """Return the fraction of log entries that ultimately succeeded."""
        if not logs:
            return 0.0
        successes = sum(1 for entry in logs if entry.get("succeeded", False))
        return successes / len(logs)

    def _optimal_backoff(self, logs: list[dict[str, Any]]) -> float:
        """Compute the backoff factor that best fits observed inter-attempt delays.

        Uses the ratio of consecutive attempt elapsed times, averaged across
        all multi-attempt log entries.
        """
        ratios: list[float] = []

        for entry in logs:
            attempts = entry.get("attempts", [])
            # Only consider entries with at least two elapsed measurements
            elapsed_vals = [
                float(a["elapsed"])
                for a in attempts
                if isinstance(a.get("elapsed"), (int, float)) and float(a["elapsed"]) > 0
            ]
            for i in range(1, len(elapsed_vals)):
                if elapsed_vals[i - 1] > 0:
                    ratios.append(elapsed_vals[i] / elapsed_vals[i - 1])

        if not ratios:
            return 2.0  # default

        median_ratio = statistics.median(ratios)
        # Clamp to a sensible range [1.1, 10.0]
        return max(1.1, min(10.0, median_ratio))

    def _average_attempts(self, logs: list[dict[str, Any]]) -> float:
        """Return the average number of attempts per action."""
        if not logs:
            return 0.0
        counts = [int(entry.get("total_attempts", 1)) for entry in logs]
        return statistics.mean(counts)

    def _update_learned_strategies(
        self,
        logs: list[dict[str, Any]],
        success_rate: float,
        optimal_backoff: float,
    ) -> None:
        """Update learned strategies based on aggregate log statistics."""
        avg_attempts = self._average_attempts(logs)

        # Heuristic: if success rate is low, increase retries; if high, reduce
        for failure_type, default_strategy in _DEFAULT_STRATEGIES.items():
            if failure_type in ("logic", "validation"):
                # Never retry logic or validation errors more aggressively
                self._learned[failure_type] = default_strategy
                continue

            if success_rate < 0.5:
                new_max_retries = min(default_strategy.max_retries + 2, 10)
                new_base_delay = default_strategy.base_delay * 1.5
            elif success_rate > 0.9 and avg_attempts < 2.0:
                new_max_retries = max(default_strategy.max_retries - 1, 1)
                new_base_delay = max(default_strategy.base_delay * 0.75, 0.1)
            else:
                new_max_retries = default_strategy.max_retries
                new_base_delay = default_strategy.base_delay

            self._learned[failure_type] = RetryStrategy(
                max_retries=new_max_retries,
                base_delay=round(new_base_delay, 3),
                backoff_factor=round(optimal_backoff, 3),
                jitter=default_strategy.jitter,
            )

    def list_strategies(self) -> dict[str, dict[str, Any]]:
        """Return all strategies (learned + defaults) as plain dicts."""
        merged: dict[str, dict[str, Any]] = {}
        for key, strategy in _DEFAULT_STRATEGIES.items():
            merged[key] = {"source": "default", **strategy.to_dict()}
        for key, strategy in self._learned.items():
            merged[key] = {"source": "learned", **strategy.to_dict()}
        return merged
