"""Failure type classification from error logs."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Union


class FailureType(Enum):
    """Categories of failure that the classifier can identify."""

    TRANSIENT = "transient"
    RESOURCE_LIMIT = "resource_limit"
    VALIDATION = "validation"
    LOGIC = "logic"
    DEPENDENCY = "dependency"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedFailure:
    """Result of classifying a single failure.

    Attributes
    ----------
    failure_type:
        The :class:`FailureType` assigned to this failure.
    confidence:
        Classification confidence in ``[0.0, 1.0]``.
    suggested_action:
        Human-readable remediation hint.
    original_error:
        The original error string or exception message.
    """

    failure_type: FailureType
    confidence: float
    suggested_action: str
    original_error: str

    def is_retryable(self) -> bool:
        """Return True for failure types that are worth retrying automatically."""
        return self.failure_type in (
            FailureType.TRANSIENT,
            FailureType.RESOURCE_LIMIT,
            FailureType.DEPENDENCY,
        )


# Built-in patterns: (regex, FailureType, confidence, suggested_action)
_DEFAULT_PATTERNS: list[tuple[str, FailureType, float, str]] = [
    # Transient / network
    (r"timeout|timed?\s*out|connection\s+reset|connection\s+refused", FailureType.TRANSIENT, 0.9, "Retry with exponential backoff"),
    (r"temporary\s+failure|try\s+again|service\s+unavailable|503|502|504", FailureType.TRANSIENT, 0.85, "Retry after a short delay"),
    (r"network\s+error|socket\s+error|read\s+timeout|write\s+timeout", FailureType.TRANSIENT, 0.85, "Check network connectivity and retry"),
    # Rate limits
    (r"rate\s+limit|too\s+many\s+requests|429|quota\s+exceeded|throttl", FailureType.RESOURCE_LIMIT, 0.95, "Back off and retry after rate-limit window"),
    # Resource / memory
    (r"out\s+of\s+memory|oom|memory\s+error|cannot\s+allocate|killed", FailureType.RESOURCE_LIMIT, 0.9, "Reduce batch size or increase memory allocation"),
    (r"disk\s+full|no\s+space\s+left|quota\s+disk|storage\s+limit", FailureType.RESOURCE_LIMIT, 0.9, "Free disk space or increase storage quota"),
    (r"cpu\s+limit|compute\s+quota|resource\s+exhausted", FailureType.RESOURCE_LIMIT, 0.85, "Reduce parallelism or increase resource limits"),
    # Validation
    (r"validation\s+error|invalid\s+(input|value|argument|parameter|format)", FailureType.VALIDATION, 0.9, "Fix input data before retrying"),
    (r"schema\s+error|type\s+error|assertion\s+error|constraint\s+violation", FailureType.VALIDATION, 0.85, "Verify data schema and constraints"),
    (r"json\s+decode\s+error|parse\s+error|syntax\s+error", FailureType.VALIDATION, 0.8, "Correct the malformed payload"),
    # Logic / application
    (r"key\s+error|attribute\s+error|not\s+implemented|abstract\s+method", FailureType.LOGIC, 0.8, "Review code logic – this is likely a bug"),
    (r"divide\s+by\s+zero|zero\s+division|overflow|underflow", FailureType.LOGIC, 0.85, "Fix arithmetic in the agent code"),
    (r"recursion\s+limit|maximum\s+recursion|stack\s+overflow", FailureType.LOGIC, 0.85, "Refactor recursive logic to avoid deep recursion"),
    # Dependency
    (r"import\s+error|module\s+not\s+found|no\s+module\s+named", FailureType.DEPENDENCY, 0.9, "Install missing dependency: pip install <package>"),
    (r"file\s+not\s+found|no\s+such\s+file|permission\s+denied", FailureType.DEPENDENCY, 0.8, "Ensure required files/directories exist with correct permissions"),
    (r"connection\s+error|cannot\s+connect|host\s+not\s+found|dns", FailureType.DEPENDENCY, 0.8, "Verify external service is reachable"),
    (r"authentication\s+error|unauthorized|401|403|forbidden", FailureType.DEPENDENCY, 0.85, "Check API keys and authentication credentials"),
]


class FailureClassifier:
    """Classify failures by matching error messages against a pattern library.

    The classifier ships with built-in patterns covering the most common
    failure categories.  Additional patterns can be registered at runtime.

    Example::

        classifier = FailureClassifier()

        try:
            result = call_external_api()
        except Exception as exc:
            failure = classifier.classify(exc)
            if failure.is_retryable():
                retry(...)
            else:
                raise
    """

    def __init__(self) -> None:
        # List of (compiled_regex, FailureType, confidence, suggested_action)
        self._patterns: list[tuple[re.Pattern[str], FailureType, float, str]] = []

        for pattern_str, ftype, confidence, action in _DEFAULT_PATTERNS:
            self._patterns.append(
                (re.compile(pattern_str, re.IGNORECASE), ftype, confidence, action)
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, error: Union[Exception, str]) -> ClassifiedFailure:
        """Classify *error* and return a :class:`ClassifiedFailure`.

        Parameters
        ----------
        error:
            An exception or a plain error string.

        Returns
        -------
        ClassifiedFailure:
            Classification result with ``failure_type``, ``confidence``,
            ``suggested_action``, and ``original_error``.
        """
        if isinstance(error, BaseException):
            # Include the exception type name for richer matching
            error_str = f"{type(error).__name__}: {error}"
        else:
            error_str = str(error)

        failure_type, confidence = self._match_patterns(error_str)

        suggested_action = self._action_for(failure_type, error_str)

        return ClassifiedFailure(
            failure_type=failure_type,
            confidence=confidence,
            suggested_action=suggested_action,
            original_error=error_str,
        )

    def register_pattern(
        self,
        pattern: str,
        failure_type: FailureType,
        confidence: float = 0.8,
        suggested_action: str = "",
    ) -> None:
        """Register a custom regex pattern.

        Parameters
        ----------
        pattern:
            A regular expression string (case-insensitive).
        failure_type:
            The :class:`FailureType` to assign on match.
        confidence:
            Classification confidence in ``[0.0, 1.0]`` (default ``0.8``).
        suggested_action:
            Human-readable remediation hint (optional).
        """
        compiled = re.compile(pattern, re.IGNORECASE)
        # Insert at the front so custom patterns take precedence
        self._patterns.insert(0, (compiled, failure_type, confidence, suggested_action))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _match_patterns(self, error_str: str) -> tuple[FailureType, float]:
        """Return the best-matching (FailureType, confidence) pair.

        Chooses the pattern with the highest confidence among all matches.
        Returns ``(UNKNOWN, 0.5)`` if no pattern matches.
        """
        best_type = FailureType.UNKNOWN
        best_confidence = 0.5

        for regex, ftype, confidence, _ in self._patterns:
            if regex.search(error_str):
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_type = ftype

        return best_type, best_confidence

    def _action_for(self, failure_type: FailureType, error_str: str) -> str:
        """Return the suggested action for *failure_type* by finding the first matching pattern."""
        for regex, ftype, _, action in self._patterns:
            if ftype == failure_type and regex.search(error_str):
                return action

        # Fallback generic actions
        _fallback: dict[FailureType, str] = {
            FailureType.TRANSIENT: "Retry with exponential backoff",
            FailureType.RESOURCE_LIMIT: "Reduce load and retry after a delay",
            FailureType.VALIDATION: "Fix input data and retry",
            FailureType.LOGIC: "Review agent code for bugs",
            FailureType.DEPENDENCY: "Check external dependencies",
            FailureType.UNKNOWN: "Investigate error manually",
        }
        return _fallback.get(failure_type, "Investigate error manually")

    def describe_patterns(self) -> list[dict[str, str]]:
        """Return all registered patterns as a list of dicts (for debugging)."""
        return [
            {
                "pattern": p.pattern,
                "failure_type": ft.value,
                "confidence": str(conf),
                "suggested_action": action,
            }
            for p, ft, conf, action in self._patterns
        ]
