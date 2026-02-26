"""Health agent demo: Prescription workflow with agit versioning.

Demonstrates:
- Auto-commit on every agent action
- Branch-per-retry for transient failures
- Rollback when allergy conflict is detected
- Full audit trail for compliance

Run:
    python examples/health_agent.py
"""
from __future__ import annotations

import json
import tempfile
from typing import Any

from agit.engine.executor import ExecutionEngine
from agit.engine.retry import RetryEngine


# ---------------------------------------------------------------------------
# Domain data
# ---------------------------------------------------------------------------

PATIENT_DB: dict[str, dict[str, Any]] = {
    "P-12345": {
        "name": "Jane Doe",
        "allergies": ["penicillin", "sulfa"],
        "conditions": ["hypertension", "type2_diabetes"],
        "current_meds": ["metformin", "lisinopril"],
    },
    "P-99999": {
        "name": "John Smith",
        "allergies": [],
        "conditions": ["type2_diabetes"],
        "current_meds": ["metformin"],
    },
}

DRUG_PROTOCOLS: dict[str, dict[str, Any]] = {
    "glipizide":    {"class": "sulfonylurea", "dose": "5mg",  "freq": "daily"},
    "sitagliptin":  {"class": "dpp4",         "dose": "100mg","freq": "daily"},
    "metformin":    {"class": "biguanide",     "dose": "500mg","freq": "2x/day"},
    "amlodipine":   {"class": "ccb",           "dose": "5mg",  "freq": "daily"},
}


# ---------------------------------------------------------------------------
# Agent action functions
# ---------------------------------------------------------------------------


def fetch_patient_history(state: dict[str, Any]) -> dict[str, Any]:
    """Step 1: Fetch patient history from EHR system."""
    patient_id = state["memory"].get("patient_id", "P-12345")
    patient = PATIENT_DB.get(patient_id, PATIENT_DB["P-12345"])
    state["memory"]["patient"] = {**patient, "id": patient_id}
    state["world_state"]["step"] = "history_fetched"
    print(f"  [1] Fetched history for {patient['name']} (allergies: {patient['allergies']})")
    return state


def suggest_medication(state: dict[str, Any]) -> dict[str, Any]:
    """Step 2: LLM suggests medication based on patient conditions."""
    patient = state["memory"]["patient"]
    conditions = patient.get("conditions", [])
    # Safe suggestion: prefer DPP-4 inhibitor over sulfonylurea (avoids sulfa allergy class)
    if "type2_diabetes" in conditions:
        drug = "sitagliptin"
    elif "hypertension" in conditions:
        drug = "amlodipine"
    else:
        drug = "metformin"
    state["memory"]["suggestion"] = {
        "drug": drug,
        **DRUG_PROTOCOLS.get(drug, {}),
        "reason": f"indicated for {', '.join(conditions)}",
    }
    state["world_state"]["step"] = "medication_suggested"
    print(f"  [2] LLM suggested: {drug}")
    return state


def check_allergies(state: dict[str, Any]) -> dict[str, Any]:
    """Step 3: Validate drug against patient allergy profile."""
    patient = state["memory"]["patient"]
    suggestion = state["memory"]["suggestion"]
    drug = suggestion["drug"].lower()
    drug_class = suggestion.get("class", "").lower()
    allergies = [a.lower() for a in patient.get("allergies", [])]

    conflict = any(a in drug or a in drug_class for a in allergies)
    if conflict:
        raise ValueError(
            f"ALLERGY ALERT: {drug} (class={drug_class}) conflicts with {allergies}"
        )

    state["memory"]["allergy_check"] = {"passed": True, "drug": drug}
    state["world_state"]["step"] = "allergy_cleared"
    print(f"  [3] Allergy check PASSED for {drug}")
    return state


def generate_prescription(state: dict[str, Any]) -> dict[str, Any]:
    """Step 4: Generate and record final prescription."""
    patient = state["memory"]["patient"]
    suggestion = state["memory"]["suggestion"]
    state["memory"]["prescription"] = {
        "patient_id": patient["id"],
        "patient_name": patient["name"],
        "drug": suggestion["drug"],
        "dose": suggestion.get("dose", "N/A"),
        "freq": suggestion.get("freq", "N/A"),
        "status": "approved",
    }
    state["world_state"]["step"] = "prescription_generated"
    print(f"  [4] Prescription issued: {suggestion['drug']} {suggestion.get('dose')} {suggestion.get('freq')}")
    return state


# ---------------------------------------------------------------------------
# Demo orchestration
# ---------------------------------------------------------------------------


def run_workflow(patient_id: str = "P-12345") -> None:
    print(f"\n{'='*60}")
    print(f"  Health Agent: Prescription Workflow  (patient={patient_id})")
    print(f"{'='*60}\n")

    with tempfile.TemporaryDirectory() as tmp:
        engine = ExecutionEngine(repo_path=tmp, agent_id="health-agent")
        retry = RetryEngine(engine, max_retries=3, base_delay=0.0)

        initial_state: dict[str, Any] = {
            "memory": {"patient_id": patient_id, "cumulative_cost": 0.0},
            "world_state": {"step": "start"},
        }

        # Step 1 – fetch history
        result1, h1 = engine.execute(fetch_patient_history, initial_state, "fetch patient history")

        # Step 2 – suggest medication
        result2, h2 = engine.execute(suggest_medication, result1, "suggest medication", "llm_response")

        # Step 3 – allergy check with retry
        print("  [3] Running allergy check (with retry support) ...")
        try:
            result3, history = retry.execute_with_retry(
                check_allergies, result2, "allergy check"
            )
            print(f"      Completed after {history.total_attempts} attempt(s)")
        except (RuntimeError, ValueError) as exc:
            print(f"      ALLERGY CONFLICT DETECTED: {exc}")
            print("      Rolling back to post-history state and trying alternative drug ...")
            result2 = engine.revert(h1)
            result2["memory"]["patient_id"] = patient_id
            result2, h2b = engine.execute(suggest_medication, result2, "suggest alternative", "llm_response")
            # Force safe drug
            result2["memory"]["suggestion"] = {
                "drug": "amlodipine",
                **DRUG_PROTOCOLS["amlodipine"],
                "reason": "alternative - allergy-safe",
            }
            result3, _ = engine.execute(check_allergies, result2, "allergy check - alternative")

        # Step 4 – issue prescription
        result4, h4 = engine.execute(generate_prescription, result3, "generate prescription")

        # Show results
        rx = result4["memory"].get("prescription", {})
        print(f"\n  Prescription:")
        print(json.dumps(rx, indent=4))

        # Audit trail
        print("\n  Commit History:")
        for i, c in enumerate(engine.get_history(limit=15)):
            print(f"    [{i+1}] {c['hash'][:12]}  {c['action_type']:16}  {c['message'][:45]}")

        # Diff first to last
        history_list = engine.get_history(limit=15)
        if len(history_list) >= 2:
            diff = engine.diff(history_list[-1]["hash"], history_list[0]["hash"])
            print(f"\n  Diff (first vs last): {len(diff['entries'])} changed fields")

        print(f"\n{'='*60}\n")


def main() -> None:
    # Patient with allergies – triggers rollback demo
    run_workflow("P-12345")
    # Patient with no allergies – clean workflow
    run_workflow("P-99999")


if __name__ == "__main__":
    main()
