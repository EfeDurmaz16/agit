#!/usr/bin/env python3
"""FIDES (Trusted Agent Protocol) + agit integration demo.

Demonstrates two AI agents establishing trust and making
DID-signed commits to a shared agit repository.

Usage:
    pip install agit pynacl base58
    python examples/fides_demo.py
"""
from __future__ import annotations

import asyncio


def main():
    """Run the FIDES + agit multi-agent trust demo."""
    try:
        from agit.integrations.fides import AgitFidesEngine, FidesIdentity
    except ImportError:
        print("FIDES integration not available.")
        print("Install with: pip install agit pynacl base58")
        return

    print("=== FIDES + agit: Trusted Multi-Agent Demo ===\n")

    # --- Create two agents with fides identities ---
    print("--- Step 1: Create Agent Identities ---\n")

    agent_a_identity = FidesIdentity.generate()
    agent_b_identity = FidesIdentity.generate()

    print(f"  Agent A: {agent_a_identity.did}")
    print(f"  Agent B: {agent_b_identity.did}")

    # --- Agent A: Initialize and commit signed state ---
    print("\n--- Step 2: Agent A Makes DID-Signed Commits ---\n")

    engine_a = AgitFidesEngine(
        repo_path="/tmp/agit-fides-demo",
        agent_id="agent-a",
    )

    async def setup_a():
        await engine_a.init_identity(
            name="research-agent",
            existing_identity=agent_a_identity,
        )

    asyncio.run(setup_a())
    print(f"  Agent A initialized with DID: {engine_a.did}")

    # Agent A commits research findings
    states = [
        {
            "memory": {"findings": ["AI safety paper published", "New benchmark results"]},
            "world_state": {"task": "literature_review", "progress": 0.3},
        },
        {
            "memory": {"findings": ["AI safety paper published", "New benchmark results", "Breakthrough in RLHF"]},
            "world_state": {"task": "literature_review", "progress": 0.7},
        },
        {
            "memory": {
                "findings": ["AI safety paper published", "New benchmark results", "Breakthrough in RLHF"],
                "summary": "3 key papers identified for deep review",
            },
            "world_state": {"task": "literature_review", "progress": 1.0},
        },
    ]

    commit_hashes = []
    for i, state in enumerate(states):
        h = engine_a.signed_commit(state, f"research step {i + 1}/3")
        commit_hashes.append(h)
        print(f"  Commit {i + 1}: {h or 'ok'} (signed by Agent A)")

    # --- Verify Agent A's commits ---
    print("\n--- Step 3: Verify Agent A's Signed Commits ---\n")

    for i, h in enumerate(commit_hashes):
        if h:
            result = engine_a.verify_commit(h)
            status = "VALID" if result.get("valid") else f"INVALID: {result.get('error')}"
            print(f"  Commit {i + 1}: {status}")
            if result.get("valid"):
                print(f"    Signer: {result.get('did')}")

    # --- Agent B: Verify Agent A's work before merging ---
    print("\n--- Step 4: Agent B Verifies Trust Before Merge ---\n")

    engine_b = AgitFidesEngine(
        repo_path="/tmp/agit-fides-demo-b",
        agent_id="agent-b",
    )

    async def setup_b():
        await engine_b.init_identity(
            name="review-agent",
            existing_identity=agent_b_identity,
        )

    asyncio.run(setup_b())
    print(f"  Agent B initialized with DID: {engine_b.did}")

    # Agent B issues trust attestation for Agent A
    async def trust_a():
        return await engine_b.trust_agent(agent_a_identity.did, level=75)

    attestation = asyncio.run(trust_a())
    print(f"  Agent B trusts Agent A at level: 75/100")
    print(f"  Attestation: {attestation}")

    # --- Show the audit trail ---
    print("\n--- Step 5: Audit Trail ---\n")

    try:
        history_a = engine_a.engine.get_history(limit=10)
        print(f"  Agent A's repository ({len(history_a)} commits):")
        for commit in history_a:
            msg = commit.get("message", "")
            print(f"    - {msg}")
    except Exception as e:
        print(f"  (history: {e})")

    try:
        history_b = engine_b.engine.get_history(limit=10)
        print(f"\n  Agent B's repository ({len(history_b)} commits):")
        for commit in history_b:
            msg = commit.get("message", "")
            print(f"    - {msg}")
    except Exception as e:
        print(f"  (history: {e})")

    # --- Summary ---
    print("\n=== Demo Complete ===")
    print("FIDES + agit provides:")
    print("  - Ed25519 DID-signed commits (every state change has a proven identity)")
    print("  - Cryptographic commit verification (detect tampering)")
    print("  - Trust-gated merge (only merge from trusted agents)")
    print("  - Trust attestations in the audit trail")
    print("  - Multi-agent swarm ready: each agent has its own identity + branch")
    print(f"\n  Agent A DID: {agent_a_identity.did}")
    print(f"  Agent B DID: {agent_b_identity.did}")


if __name__ == "__main__":
    main()
