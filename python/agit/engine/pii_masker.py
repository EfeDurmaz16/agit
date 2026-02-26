"""PII detection and masking middleware for agit.

Masks sensitive data (emails, phones, SSNs, credit cards, API keys, JWTs, IPs)
before committing agent state to prevent plaintext PII in storage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MaskedField:
    """Record of a single masked field."""
    path: str
    pii_type: str
    original_length: int


# ---------------------------------------------------------------------------
# Built-in PII patterns
# ---------------------------------------------------------------------------

BUILTIN_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    ),
    "phone": re.compile(
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    ),
    "ssn": re.compile(
        r"\b\d{3}-\d{2}-\d{4}\b"
    ),
    "credit_card": re.compile(
        r"\b(?:\d{4}[-\s]?){3}\d{1,4}\b"
    ),
    "api_key": re.compile(
        r"\b(?:sk|pk|api|key|token|secret|AKIA)[_-]?[A-Za-z0-9]{16,}\b",
        re.IGNORECASE,
    ),
    "jwt": re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    ),
    "ip_address": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
    "aws_access_key": re.compile(
        r"\bAKIA[0-9A-Z]{16}\b"
    ),
    "private_key": re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
    ),
    "iban": re.compile(
        r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}(?:[A-Z0-9]{0,18})\b"
    ),
    "bearer_token": re.compile(
        r"\bBearer\s+[A-Za-z0-9_\-\.]{20,}\b",
        re.IGNORECASE,
    ),
}


class PiiMasker:
    """Detects and masks PII in agent state dictionaries.

    Parameters
    ----------
    patterns:
        List of built-in pattern names to enable.
        Defaults to all built-in patterns.
    custom_patterns:
        Additional regex patterns as ``{name: pattern_string}`` dict.
    """

    def __init__(
        self,
        patterns: list[str] | None = None,
        custom_patterns: dict[str, str] | None = None,
    ) -> None:
        self._patterns: dict[str, re.Pattern[str]] = {}

        # Load built-in patterns
        if patterns is None:
            self._patterns.update(BUILTIN_PATTERNS)
        else:
            for name in patterns:
                if name in BUILTIN_PATTERNS:
                    self._patterns[name] = BUILTIN_PATTERNS[name]

        # Load custom patterns
        if custom_patterns:
            for name, pattern_str in custom_patterns.items():
                self._patterns[name] = re.compile(pattern_str)

    @property
    def active_patterns(self) -> list[str]:
        """Return names of active patterns."""
        return list(self._patterns.keys())

    def mask(self, state: dict[str, Any]) -> dict[str, Any]:
        """Mask PII in a state dict, returning a new dict with redacted values.

        Parameters
        ----------
        state:
            Agent state dictionary to mask.

        Returns
        -------
        dict:
            New dict with PII replaced by ``[REDACTED:<type>]`` markers.
        """
        masked, _ = self.mask_with_audit(state)
        return masked

    def mask_with_audit(
        self, state: dict[str, Any]
    ) -> tuple[dict[str, Any], list[MaskedField]]:
        """Mask PII and return audit trail of what was masked.

        Returns
        -------
        (masked_dict, audit_list):
            The masked state and a list of MaskedField records.
        """
        audit: list[MaskedField] = []
        masked = self._mask_recursive(state, "", audit)
        return masked, audit

    def _mask_recursive(
        self, obj: Any, path: str, audit: list[MaskedField]
    ) -> Any:
        if isinstance(obj, dict):
            return {
                k: self._mask_recursive(v, f"{path}.{k}" if path else k, audit)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [
                self._mask_recursive(v, f"{path}[{i}]", audit)
                for i, v in enumerate(obj)
            ]
        elif isinstance(obj, str):
            return self._mask_string(obj, path, audit)
        return obj

    def _mask_string(
        self, value: str, path: str, audit: list[MaskedField]
    ) -> str:
        result = value
        for pii_type, pattern in self._patterns.items():
            matches = list(pattern.finditer(result))
            if matches:
                for match in reversed(matches):
                    audit.append(
                        MaskedField(
                            path=path,
                            pii_type=pii_type,
                            original_length=len(match.group()),
                        )
                    )
                result = pattern.sub(f"[REDACTED:{pii_type}]", result)
        return result
