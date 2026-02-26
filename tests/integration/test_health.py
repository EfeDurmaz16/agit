"""Integration test: health agent prescription workflow e2e."""
from __future__ import annotations

from typing import Any

import pytest

from agit import ExecutionEngine, RetryEngine


# ---------------------------------------------------------------------------
# Simulated health domain helpers (no external deps)
# ---------------------------------------------------------------------------

ALLERGY_DB: dict[str, list[str]] = {
    "patient-001": ["penicillin", "aspirin"],
    "patient-002": ["sulfa"],
    "patient-003": [],
}

DRUG_DB: dict[str, dict[str, Any]] = {
    "amoxicillin": {"class": "penicillin", "dosage": "500mg", "frequency": "3x/day"},
    "ibuprofen": {"class": "nsaid", "dosage": "400mg", "frequency": "as needed"},
    "metformin": {"class": "biguanide", "dosage": "500mg", "frequency": "2x/day"},
}


def fetch_patient_history(state: dict[str, Any]) -> dict[str, Any]:
    """Step 1: Fetch patient history."""
    patient_id = state.get("memory", {}).get("patient_id", "patient-001")
    return {
        **state,
        "memory": {
            **state.get("memory", {}),
            "allergies": ALLERGY_DB.get(patient_id, []),
            "history_fetched": True,
            "conditions": ["hypertension", "type2_diabetes"],
        },
    }


def suggest_drug(state: dict[str, Any]) -> dict[str, Any]:
    """Step 2: LLM suggests a drug based on conditions."""
    conditions = state.get("memory", {}).get("conditions", [])
    suggestion = "metformin" if "type2_diabetes" in conditions else "ibuprofen"
    return {
        **state,
        "memory": {
            **state.get("memory", {}),
            "suggested_drug": suggestion,
            "drug_info": DRUG_DB.get(suggestion, {}),
        },
    }


def check_allergies(state: dict[str, Any]) -> dict[str, Any]:
    """Step 3: Check drug against known allergies."""
    memory = state.get("memory", {})
    suggested = memory.get("suggested_drug", "")
    allergies = memory.get("allergies", [])
    drug_info = DRUG_DB.get(suggested, {})
    drug_class = drug_info.get("class", "")

    allergy_conflict = any(a in suggested or a in drug_class for a in allergies)

    if allergy_conflict:
        raise ValueError(f"Allergy conflict: patient allergic, drug class={drug_class}")

    return {
        **state,
        "memory": {
            **memory,
            "allergy_check_passed": True,
            "approved_drug": suggested,
            "prescription_ready": True,
        },
    }


def finalize_prescription(state: dict[str, Any]) -> dict[str, Any]:
    """Step 4: Finalize and record prescription."""
    memory = state.get("memory", {})
    drug = memory.get("approved_drug", "")
    info = DRUG_DB.get(drug, {})
    return {
        **state,
        "memory": {
            **memory,
            "prescription": {
                "drug": drug,
                "dosage": info.get("dosage"),
                "frequency": info.get("frequency"),
                "status": "issued",
            },
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def health_engine() -> ExecutionEngine:
    return ExecutionEngine(":memory:", agent_id="health-agent")


class TestPrescriptionWorkflow:
    """Simulate full prescription workflow with agit versioning."""

    def test_full_workflow_no_allergies(self, health_engine: ExecutionEngine) -> None:
        state: dict[str, Any] = {
            "memory": {
                "patient_id": "patient-003",  # no allergies
                "cumulative_cost": 0.0,
                "step": 0,
            },
            "world_state": {"environment": "clinical"},
        }

        # Step 1: fetch history
        result1, h1 = health_engine.execute(fetch_patient_history, state, "fetch patient history")
        assert result1["memory"]["history_fetched"] is True
        assert result1["memory"]["allergies"] == []

        # Step 2: suggest drug
        result2, h2 = health_engine.execute(suggest_drug, result1, "suggest drug", "llm_response")
        assert "suggested_drug" in result2["memory"]

        # Step 3: allergy check
        result3, h3 = health_engine.execute(check_allergies, result2, "check allergies")
        assert result3["memory"]["allergy_check_passed"] is True

        # Step 4: finalize
        result4, h4 = health_engine.execute(finalize_prescription, result3, "finalize prescription")
        assert result4["memory"]["prescription"]["status"] == "issued"

        # Verify audit trail
        history = health_engine.get_history(limit=20)
        assert len(history) >= 4

    def test_allergy_detection_triggers_rollback(self, health_engine: ExecutionEngine) -> None:
        """Patient with penicillin allergy should get allergy conflict on amoxicillin."""
        state: dict[str, Any] = {
            "memory": {
                "patient_id": "patient-001",  # allergic to penicillin
                "cumulative_cost": 0.0,
                "conditions": ["infection"],
            },
            "world_state": {},
        }

        result1, h1 = health_engine.execute(fetch_patient_history, state, "fetch history")

        # Force suggest amoxicillin (penicillin class)
        def suggest_amoxicillin(s: dict[str, Any]) -> dict[str, Any]:
            return {
                **s,
                "memory": {
                    **s.get("memory", {}),
                    "suggested_drug": "amoxicillin",
                    "drug_info": DRUG_DB["amoxicillin"],
                },
            }

        result2, h2 = health_engine.execute(suggest_amoxicillin, result1, "suggest amoxicillin")

        # Allergy check should fail
        with pytest.raises(ValueError, match="Allergy conflict"):
            health_engine.execute(check_allergies, result2, "check allergies - should fail")

        # Verify error was recorded in history
        history = health_engine.get_history(limit=20)
        messages = [c["message"] for c in history]
        assert any("error:" in m for m in messages)

        # Rollback to before amoxicillin suggestion
        reverted = health_engine.revert(h1)
        assert reverted["memory"]["history_fetched"] is True
        assert "suggested_drug" not in reverted.get("memory", {})

    def test_audit_trail_completeness(self, health_engine: ExecutionEngine) -> None:
        """All steps must appear in audit log."""
        state: dict[str, Any] = {
            "memory": {"patient_id": "patient-002", "cumulative_cost": 0.0},
            "world_state": {},
        }
        result1, _ = health_engine.execute(fetch_patient_history, state, "fetch history")
        result2, _ = health_engine.execute(suggest_drug, result1, "suggest drug")

        audit = health_engine.audit_log(limit=50)
        assert len(audit) >= 2
        actions = [e["action"] for e in audit]
        assert "commit" in actions

    def test_branch_per_prescription_attempt(self, health_engine: ExecutionEngine) -> None:
        """Each prescription attempt uses its own branch for isolation."""
        initial: dict[str, Any] = {
            "memory": {"patient_id": "patient-003", "cumulative_cost": 0.0},
            "world_state": {},
        }
        h_base = health_engine.commit_state(initial, "patient admitted", "checkpoint")

        # Branch for attempt 1
        health_engine.branch("prescription/attempt-1", from_ref=h_base)
        health_engine.checkout("prescription/attempt-1")
        r1, _ = health_engine.execute(fetch_patient_history, initial, "attempt 1: fetch")
        r1, _ = health_engine.execute(suggest_drug, r1, "attempt 1: suggest")

        # Go back to main and branch for attempt 2
        health_engine.checkout("main")
        health_engine.branch("prescription/attempt-2", from_ref=h_base)
        health_engine.checkout("prescription/attempt-2")
        r2, _ = health_engine.execute(fetch_patient_history, initial, "attempt 2: fetch")

        branches = health_engine.list_branches()
        assert "prescription/attempt-1" in branches
        assert "prescription/attempt-2" in branches

    def test_retry_on_transient_allergy_check_failure(
        self, health_engine: ExecutionEngine
    ) -> None:
        """RetryEngine should recover prescription workflow on transient failures."""
        call_count = {"n": 0}

        def flaky_allergy_check(state: dict[str, Any]) -> dict[str, Any]:
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise ConnectionError("allergy DB temporarily unavailable")
            return {
                **state,
                "memory": {**state.get("memory", {}), "allergy_check_passed": True},
            }

        initial: dict[str, Any] = {
            "memory": {"cumulative_cost": 0.0, "suggested_drug": "metformin"},
            "world_state": {},
        }

        retry_eng = RetryEngine(health_engine, max_retries=3, base_delay=0.0)
        result, history = retry_eng.execute_with_retry(
            flaky_allergy_check, initial, "allergy check with retry"
        )
        assert history.succeeded
        assert result["memory"]["allergy_check_passed"] is True
