"""Integration test: legal contract review agent workflow e2e."""
from __future__ import annotations

from typing import Any

import pytest

from agit import ExecutionEngine, RetryEngine


# ---------------------------------------------------------------------------
# Simulated legal domain helpers (no external deps)
# ---------------------------------------------------------------------------

FORBIDDEN_CLAUSES = [
    "unlimited liability",
    "no governing law",
    "automatic renewal without notice",
]

REQUIRED_CLAUSES = [
    "dispute resolution",
    "confidentiality",
    "termination clause",
]

SAMPLE_CONTRACT = """
SERVICE AGREEMENT

1. SCOPE OF SERVICES
   Provider will deliver software development services.

2. CONFIDENTIALITY
   Both parties agree to maintain strict confidentiality.

3. TERMINATION CLAUSE
   Either party may terminate with 30 days written notice.

4. DISPUTE RESOLUTION
   Disputes shall be resolved via arbitration in New York.

5. GOVERNING LAW
   This agreement is governed by the laws of New York State.

6. LIABILITY
   Provider liability limited to fees paid in prior 3 months.
"""

PROBLEMATIC_CONTRACT = """
VENDOR AGREEMENT

1. SERVICES
   Vendor provides consulting services.

2. UNLIMITED LIABILITY
   Vendor accepts unlimited liability for all damages.

3. AUTOMATIC RENEWAL WITHOUT NOTICE
   Contract auto-renews unless cancelled 1 year in advance.
"""


def parse_contract(state: dict[str, Any]) -> dict[str, Any]:
    """Step 1: Parse the contract text into clauses."""
    memory = state.get("memory", {})
    text = memory.get("contract_text", SAMPLE_CONTRACT)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    clauses = []
    current_clause = ""
    for line in lines:
        if line[0].isdigit() and "." in line[:3]:
            if current_clause:
                clauses.append(current_clause.strip())
            current_clause = line
        else:
            current_clause += " " + line
    if current_clause:
        clauses.append(current_clause.strip())

    return {
        **state,
        "memory": {
            **memory,
            "clauses": clauses,
            "clause_count": len(clauses),
            "parsing_complete": True,
        },
    }


def check_forbidden_clauses(state: dict[str, Any]) -> dict[str, Any]:
    """Step 2: Identify forbidden/problematic clauses."""
    memory = state.get("memory", {})
    clauses = memory.get("clauses", [])
    full_text = " ".join(clauses).lower()
    found_forbidden = [fc for fc in FORBIDDEN_CLAUSES if fc.lower() in full_text]

    return {
        **state,
        "memory": {
            **memory,
            "forbidden_clauses_found": found_forbidden,
            "has_forbidden": len(found_forbidden) > 0,
            "clause_check_complete": True,
        },
    }


def check_required_clauses(state: dict[str, Any]) -> dict[str, Any]:
    """Step 3: Verify all required clauses are present."""
    memory = state.get("memory", {})
    clauses = memory.get("clauses", [])
    full_text = " ".join(clauses).lower()
    missing = [rc for rc in REQUIRED_CLAUSES if rc.lower() not in full_text]

    return {
        **state,
        "memory": {
            **memory,
            "missing_required_clauses": missing,
            "all_required_present": len(missing) == 0,
            "required_check_complete": True,
        },
    }


def compliance_decision(state: dict[str, Any]) -> dict[str, Any]:
    """Step 4: Make final compliance decision."""
    memory = state.get("memory", {})
    has_forbidden = memory.get("has_forbidden", False)
    all_required = memory.get("all_required_present", False)

    if has_forbidden:
        issues = memory.get("forbidden_clauses_found", [])
        raise ValueError(f"Contract non-compliant: forbidden clauses found: {issues}")

    status = "approved" if all_required else "conditional_approval"
    return {
        **state,
        "memory": {
            **memory,
            "compliance_status": status,
            "review_complete": True,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def legal_engine() -> ExecutionEngine:
    return ExecutionEngine(":memory:", agent_id="legal-agent")


class TestContractReviewWorkflow:
    """Test full contract review pipeline with agit versioning."""

    def test_compliant_contract_approved(self, legal_engine: ExecutionEngine) -> None:
        """Standard contract should be approved."""
        state: dict[str, Any] = {
            "memory": {
                "contract_text": SAMPLE_CONTRACT,
                "contract_id": "CTR-001",
                "cumulative_cost": 0.0,
            },
            "world_state": {"environment": "legal-review"},
        }

        r1, h1 = legal_engine.execute(parse_contract, state, "parse contract")
        assert r1["memory"]["parsing_complete"] is True
        assert r1["memory"]["clause_count"] > 0

        r2, h2 = legal_engine.execute(check_forbidden_clauses, r1, "check forbidden clauses")
        assert r2["memory"]["clause_check_complete"] is True
        assert r2["memory"]["has_forbidden"] is False

        r3, h3 = legal_engine.execute(check_required_clauses, r2, "check required clauses")
        assert r3["memory"]["required_check_complete"] is True
        assert r3["memory"]["all_required_present"] is True

        r4, h4 = legal_engine.execute(compliance_decision, r3, "compliance decision")
        assert r4["memory"]["compliance_status"] == "approved"
        assert r4["memory"]["review_complete"] is True

    def test_problematic_contract_rejected(self, legal_engine: ExecutionEngine) -> None:
        """Contract with forbidden clauses should be rejected."""
        state: dict[str, Any] = {
            "memory": {
                "contract_text": PROBLEMATIC_CONTRACT,
                "contract_id": "CTR-002",
                "cumulative_cost": 0.0,
            },
            "world_state": {},
        }

        r1, h1 = legal_engine.execute(parse_contract, state, "parse contract")
        r2, h2 = legal_engine.execute(check_forbidden_clauses, r1, "check forbidden")
        assert r2["memory"]["has_forbidden"] is True

        with pytest.raises(ValueError, match="non-compliant"):
            legal_engine.execute(compliance_decision, r2, "compliance - should fail")

        # Error must appear in history
        history = legal_engine.get_history(limit=20)
        messages = [c["message"] for c in history]
        assert any("error:" in m for m in messages)

    def test_all_steps_recorded_in_history(self, legal_engine: ExecutionEngine) -> None:
        """Every review step must be versioned in agit history."""
        state: dict[str, Any] = {
            "memory": {
                "contract_text": SAMPLE_CONTRACT,
                "cumulative_cost": 0.0,
            },
            "world_state": {},
        }

        for fn, msg in [
            (parse_contract, "parse"),
            (check_forbidden_clauses, "check forbidden"),
            (check_required_clauses, "check required"),
        ]:
            state, _ = legal_engine.execute(fn, state, msg)

        history = legal_engine.get_history(limit=30)
        # Each execute creates 2 commits (pre + post), plus we ran 3 steps
        assert len(history) >= 3
        step_msgs = [c["message"] for c in history]
        assert any("parse" in m for m in step_msgs)
        assert any("forbidden" in m for m in step_msgs)
        assert any("required" in m for m in step_msgs)

    def test_diff_between_review_steps(self, legal_engine: ExecutionEngine) -> None:
        """Diff between parse step and clause-check step shows added fields."""
        state: dict[str, Any] = {
            "memory": {
                "contract_text": SAMPLE_CONTRACT,
                "cumulative_cost": 0.0,
            },
            "world_state": {},
        }

        _, h1 = legal_engine.execute(parse_contract, state, "parse contract")
        state = legal_engine.get_current_state() or state
        _, h2 = legal_engine.execute(check_forbidden_clauses, state, "check forbidden")

        diff = legal_engine.diff(h1, h2)
        assert diff["base_hash"] == h1
        assert diff["target_hash"] == h2

    def test_rollback_after_rejection(self, legal_engine: ExecutionEngine) -> None:
        """Can roll back to pre-clause-check state after rejection."""
        state: dict[str, Any] = {
            "memory": {
                "contract_text": PROBLEMATIC_CONTRACT,
                "contract_id": "CTR-003",
                "cumulative_cost": 0.0,
            },
            "world_state": {},
        }

        h_base = legal_engine.commit_state(state, "contract received", "checkpoint")
        r1, h1 = legal_engine.execute(parse_contract, state, "parse")
        r2, h2 = legal_engine.execute(check_forbidden_clauses, r1, "check forbidden")

        with pytest.raises(ValueError):
            legal_engine.execute(compliance_decision, r2, "decision - fail")

        # Rollback to before parse
        restored = legal_engine.revert(h_base)
        assert restored["memory"]["contract_id"] == "CTR-003"
        assert "clauses" not in restored.get("memory", {})

    def test_versioned_analysis_branch_per_contract(
        self, legal_engine: ExecutionEngine
    ) -> None:
        """Each contract review gets its own branch."""
        base: dict[str, Any] = {
            "memory": {"cumulative_cost": 0.0},
            "world_state": {},
        }
        h_base = legal_engine.commit_state(base, "start", "checkpoint")

        for contract_id, text in [
            ("CTR-A", SAMPLE_CONTRACT),
            ("CTR-B", PROBLEMATIC_CONTRACT),
        ]:
            branch = f"review/{contract_id.lower()}"
            legal_engine.branch(branch, from_ref=h_base)
            legal_engine.checkout(branch)
            s = {**base, "memory": {**base["memory"], "contract_text": text, "contract_id": contract_id}}
            legal_engine.execute(parse_contract, s, f"parse {contract_id}")
            legal_engine.checkout("main")

        branches = legal_engine.list_branches()
        assert "review/ctr-a" in branches
        assert "review/ctr-b" in branches

    def test_retry_on_transient_parsing_failure(
        self, legal_engine: ExecutionEngine
    ) -> None:
        """RetryEngine recovers from transient parsing errors."""
        call_count = {"n": 0}

        def flaky_parse(state: dict[str, Any]) -> dict[str, Any]:
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise IOError("parsing service unavailable")
            return parse_contract(state)

        initial: dict[str, Any] = {
            "memory": {"contract_text": SAMPLE_CONTRACT, "cumulative_cost": 0.0},
            "world_state": {},
        }
        retry_eng = RetryEngine(legal_engine, max_retries=3, base_delay=0.0)
        result, history = retry_eng.execute_with_retry(flaky_parse, initial, "parse contract")
        assert history.succeeded
        assert result["memory"]["parsing_complete"] is True
