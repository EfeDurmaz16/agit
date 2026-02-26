"""Legal review demo: Contract review with compliance checks.

Demonstrates:
- Versioned analysis steps (every step auto-committed)
- Branch-per-contract review for isolation
- Rollback to pre-review state on rejection
- Full audit trail

Run:
    python examples/legal_review.py
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

REQUIRED_CLAUSES = ["confidentiality", "dispute resolution", "termination", "governing law"]
FORBIDDEN_CLAUSES = ["unlimited liability", "automatic renewal without notice", "no governing law"]

CONTRACTS: dict[str, str] = {
    "CTR-2026-001": """
SAAS SERVICE AGREEMENT

1. SCOPE OF SERVICES
   Provider delivers cloud-based AI infrastructure services.

2. CONFIDENTIALITY
   Both parties agree to maintain strict confidentiality of proprietary information.

3. TERMINATION
   Either party may terminate this agreement with 90 days written notice.

4. DISPUTE RESOLUTION
   All disputes shall be resolved by binding arbitration in New York.

5. GOVERNING LAW
   This agreement is governed by the laws of the State of New York.

6. LIABILITY LIMITATION
   Provider's liability is capped at fees paid in the preceding 12 months.
""",
    "CTR-2026-BAD": """
VENDOR CONSULTING AGREEMENT

1. SERVICES
   Vendor provides consulting services on an ad-hoc basis.

2. UNLIMITED LIABILITY
   Vendor accepts unlimited liability for any and all damages.

3. AUTOMATIC RENEWAL WITHOUT NOTICE
   This agreement auto-renews annually with no cancellation window.

4. PAYMENT
   Client pays within 7 days or incurs 10% monthly penalty.
""",
}


# ---------------------------------------------------------------------------
# Agent action functions
# ---------------------------------------------------------------------------


def parse_contract(state: dict[str, Any]) -> dict[str, Any]:
    """Step 1: Parse contract text into structured clauses."""
    text = state["memory"].get("contract_text", "")
    contract_id = state["memory"].get("contract_id", "UNKNOWN")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    clauses: list[dict[str, str]] = []
    current = {"title": "", "text": ""}
    for line in lines:
        if len(line) < 80 and line[0].isdigit() and "." in line[:3]:
            if current["text"]:
                clauses.append(dict(current))
            title = line.split(".", 1)[-1].strip() if "." in line else line
            current = {"title": title, "text": ""}
        else:
            current["text"] += " " + line
    if current["text"]:
        clauses.append(dict(current))

    state["memory"]["clauses"] = clauses
    state["memory"]["clause_count"] = len(clauses)
    state["memory"]["parsing_complete"] = True
    state["world_state"]["step"] = "parsed"
    print(f"  [1] Parsed {len(clauses)} clauses from {contract_id}")
    return state


def check_clauses(state: dict[str, Any]) -> dict[str, Any]:
    """Step 2: Check for required and forbidden clauses."""
    clauses = state["memory"].get("clauses", [])
    full_text = " ".join(c["text"] + " " + c["title"] for c in clauses).lower()

    missing_required = [r for r in REQUIRED_CLAUSES if r.lower() not in full_text]
    found_forbidden = [f for f in FORBIDDEN_CLAUSES if f.lower() in full_text]

    findings: list[dict[str, Any]] = []
    for clause in clauses:
        title_lower = clause["title"].lower()
        text_lower = clause["text"].lower()
        status = "compliant"
        note = ""
        if any(fb.lower() in title_lower or fb.lower() in text_lower for fb in FORBIDDEN_CLAUSES):
            status = "FORBIDDEN"
            note = "Contains a forbidden clause"
        elif any(rq.lower() in title_lower or rq.lower() in text_lower for rq in REQUIRED_CLAUSES):
            status = "compliant"
            note = "Required clause present"
        findings.append({"title": clause["title"], "status": status, "note": note})

    state["memory"]["findings"] = findings
    state["memory"]["missing_required"] = missing_required
    state["memory"]["found_forbidden"] = found_forbidden
    state["memory"]["has_issues"] = bool(missing_required or found_forbidden)
    state["world_state"]["step"] = "reviewed"
    print(f"  [2] Clause check: {len(found_forbidden)} forbidden, {len(missing_required)} missing required")
    return state


def compliance_decision(state: dict[str, Any]) -> dict[str, Any]:
    """Step 3: Make compliance decision and raise on forbidden clauses."""
    memory = state["memory"]
    forbidden = memory.get("found_forbidden", [])
    missing = memory.get("missing_required", [])

    if forbidden:
        raise ValueError(f"NON-COMPLIANT: forbidden clauses found: {forbidden}")

    status = "APPROVED" if not missing else "CONDITIONAL_APPROVAL"
    state["memory"]["report"] = {
        "contract_id": memory.get("contract_id", "UNKNOWN"),
        "total_clauses": memory.get("clause_count", 0),
        "missing_required": missing,
        "forbidden_found": forbidden,
        "status": status,
        "recommendation": "sign" if status == "APPROVED" else "negotiate_missing_clauses",
    }
    state["world_state"]["step"] = "decided"
    print(f"  [3] Compliance decision: {status}")
    return state


# ---------------------------------------------------------------------------
# Demo orchestration
# ---------------------------------------------------------------------------


def review_contract(engine: ExecutionEngine, contract_id: str, h_base: str) -> None:
    branch = f"review/{contract_id.lower()}"
    print(f"\n  Review branch: {branch}")
    engine.branch(branch, from_ref=h_base)
    engine.checkout(branch)

    state: dict[str, Any] = {
        "memory": {
            "contract_id": contract_id,
            "contract_text": CONTRACTS.get(contract_id, ""),
            "cumulative_cost": 0.0,
        },
        "world_state": {"environment": "legal-review"},
    }

    h_init = engine.commit_state(state, f"contract {contract_id} received", "checkpoint")
    result1, h1 = engine.execute(parse_contract, state, "parse contract")
    result2, h2 = engine.execute(check_clauses, result1, "check clauses")

    try:
        result3, h3 = engine.execute(compliance_decision, result2, "compliance decision")
        report = result3["memory"]["report"]
        print(f"  Report: {json.dumps(report, indent=4)}")
    except ValueError as exc:
        print(f"  REJECTED: {exc}")
        print("  Rolling back to pre-parse state ...")
        engine.revert(h_init)

    engine.checkout("main")


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  Legal Agent: Contract Review Demo")
    print(f"{'='*60}\n")

    with tempfile.TemporaryDirectory() as tmp:
        engine = ExecutionEngine(repo_path=tmp, agent_id="legal-agent")
        retry_eng = RetryEngine(engine, max_retries=2, base_delay=0.0)

        # Establish baseline
        base: dict[str, Any] = {
            "memory": {"cumulative_cost": 0.0, "session": "2026-02-26"},
            "world_state": {"queue": list(CONTRACTS.keys())},
        }
        h_base = engine.commit_state(base, "review session start", "checkpoint")
        print(f"  Baseline committed: {h_base[:12]}")

        # Review all contracts
        for cid in CONTRACTS:
            print(f"\n  {'─'*50}")
            print(f"  Reviewing {cid} ...")
            review_contract(engine, cid, h_base)

        # Audit trail
        print(f"\n{'─'*60}")
        print("  Commit History (all branches):")
        for i, c in enumerate(engine.get_history(limit=20)):
            print(f"    [{i+1:2d}] {c['hash'][:12]}  {c['action_type']:16}  {c['message'][:42]}")

        print("\n  Audit Log:")
        for entry in engine.audit_log(limit=20):
            print(f"    {entry['timestamp']}  {entry['action']:8}  {entry['message'][:50]}")

        print(f"\n{'='*60}\n  Demo complete.\n{'='*60}\n")


if __name__ == "__main__":
    main()
