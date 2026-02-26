"""Tests for PII masking middleware."""
from __future__ import annotations

import pytest

from agit.engine.pii_masker import PiiMasker, MaskedField


class TestPiiMasker:
    """Test PII detection and masking."""

    def test_mask_email(self) -> None:
        masker = PiiMasker(patterns=["email"])
        state = {"memory": {"contact": "user@example.com"}}
        result = masker.mask(state)
        assert result["memory"]["contact"] == "[REDACTED:email]"

    def test_mask_phone(self) -> None:
        masker = PiiMasker(patterns=["phone"])
        state = {"data": "Call me at 555-123-4567"}
        result = masker.mask(state)
        assert "[REDACTED:phone]" in result["data"]
        assert "555-123-4567" not in result["data"]

    def test_mask_ssn(self) -> None:
        masker = PiiMasker(patterns=["ssn"])
        state = {"ssn": "123-45-6789"}
        result = masker.mask(state)
        assert result["ssn"] == "[REDACTED:ssn]"

    def test_mask_credit_card(self) -> None:
        masker = PiiMasker(patterns=["credit_card"])
        state = {"payment": "4111-1111-1111-1111"}
        result = masker.mask(state)
        assert result["payment"] == "[REDACTED:credit_card]"

    def test_mask_api_key(self) -> None:
        masker = PiiMasker(patterns=["api_key"])
        state = {"config": "sk-abcdef1234567890abcdef"}
        result = masker.mask(state)
        assert "[REDACTED:api_key]" in result["config"]

    def test_mask_jwt(self) -> None:
        masker = PiiMasker(patterns=["jwt"])
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        state = {"auth": {"token": jwt}}
        result = masker.mask(state)
        assert "[REDACTED:jwt]" in result["auth"]["token"]

    def test_mask_ip_address(self) -> None:
        masker = PiiMasker(patterns=["ip_address"])
        state = {"log": "Connection from 192.168.1.100"}
        result = masker.mask(state)
        assert "[REDACTED:ip_address]" in result["log"]
        assert "192.168.1.100" not in result["log"]

    def test_mask_all_patterns(self) -> None:
        masker = PiiMasker()  # All patterns enabled
        state = {
            "email": "test@example.com",
            "phone": "555-123-4567",
            "ssn": "123-45-6789",
        }
        result = masker.mask(state)
        assert "[REDACTED:email]" in result["email"]
        assert "[REDACTED:ssn]" in result["ssn"]

    def test_mask_nested_objects(self) -> None:
        masker = PiiMasker(patterns=["email", "phone"])
        state = {
            "level1": {
                "level2": {
                    "contact": "user@test.com",
                    "phone": "555-111-2222",
                }
            }
        }
        result = masker.mask(state)
        assert result["level1"]["level2"]["contact"] == "[REDACTED:email]"
        assert "[REDACTED:phone]" in result["level1"]["level2"]["phone"]

    def test_mask_lists(self) -> None:
        masker = PiiMasker(patterns=["email"])
        state = {"emails": ["a@b.com", "c@d.com", "not-an-email"]}
        result = masker.mask(state)
        assert result["emails"][0] == "[REDACTED:email]"
        assert result["emails"][1] == "[REDACTED:email]"
        assert result["emails"][2] == "not-an-email"

    def test_mask_with_audit(self) -> None:
        masker = PiiMasker(patterns=["email", "ssn"])
        state = {"email": "user@test.com", "id": "123-45-6789"}
        masked, audit = masker.mask_with_audit(state)
        assert len(audit) == 2
        assert any(a.pii_type == "email" for a in audit)
        assert any(a.pii_type == "ssn" for a in audit)

    def test_custom_patterns(self) -> None:
        masker = PiiMasker(
            patterns=["email"],
            custom_patterns={"patient_id": r"PATIENT-\d+"},
        )
        state = {"ref": "PATIENT-12345", "email": "doc@hospital.com"}
        result = masker.mask(state)
        assert result["ref"] == "[REDACTED:patient_id]"
        assert result["email"] == "[REDACTED:email]"

    def test_no_pii_unchanged(self) -> None:
        masker = PiiMasker()
        state = {"message": "Hello world", "count": 42, "active": True}
        result = masker.mask(state)
        assert result == state

    def test_original_not_mutated(self) -> None:
        masker = PiiMasker(patterns=["email"])
        state = {"email": "user@test.com"}
        _ = masker.mask(state)
        assert state["email"] == "user@test.com"

    def test_non_string_values_preserved(self) -> None:
        masker = PiiMasker()
        state = {"count": 42, "ratio": 3.14, "active": True, "empty": None}
        result = masker.mask(state)
        assert result["count"] == 42
        assert result["ratio"] == 3.14
        assert result["active"] is True
        assert result["empty"] is None

    def test_selective_patterns(self) -> None:
        masker = PiiMasker(patterns=["email"])
        state = {"email": "user@test.com", "ssn": "123-45-6789"}
        result = masker.mask(state)
        assert result["email"] == "[REDACTED:email]"
        # SSN should NOT be masked since only email pattern is active
        assert result["ssn"] == "123-45-6789"

    def test_active_patterns_property(self) -> None:
        masker = PiiMasker(patterns=["email", "phone"])
        assert sorted(masker.active_patterns) == ["email", "phone"]

    def test_multiple_pii_in_one_string(self) -> None:
        masker = PiiMasker(patterns=["email", "phone"])
        state = {"info": "Contact user@test.com or call 555-123-4567"}
        result = masker.mask(state)
        assert "[REDACTED:email]" in result["info"]
        assert "[REDACTED:phone]" in result["info"]
        assert "user@test.com" not in result["info"]
        assert "555-123-4567" not in result["info"]
