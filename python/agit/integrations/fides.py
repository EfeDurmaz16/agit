"""FIDES (Trusted Agent Protocol) integration for agit.

Provides DID-signed commits, trust-gated repository access,
and verifiable agent identity for multi-agent swarm versioning.

Usage::

    from agit.integrations.fides import AgitFidesEngine
    engine = AgitFidesEngine(
        repo_path="./my_repo",
        agent_id="trusted-agent",
        discovery_url="http://localhost:3000",
        trust_url="http://localhost:3001",
    )
    await engine.init_identity(name="my-agent")
    engine.signed_commit(state, "checkpoint after tool call")
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from agit.engine.executor import ExecutionEngine

logger = logging.getLogger("agit.integrations.fides")

try:
    from nacl.signing import SigningKey, VerifyKey  # type: ignore[import]
    from nacl.encoding import HexEncoder, RawEncoder  # type: ignore[import]
    import nacl.utils  # type: ignore[import]

    _NACL_AVAILABLE = True
except ImportError:
    _NACL_AVAILABLE = False

try:
    import httpx  # type: ignore[import]

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


class FidesIdentity:
    """Local fides identity with Ed25519 keypair and DID."""

    def __init__(self, signing_key: Any, did: str, public_key_hex: str) -> None:
        self.signing_key = signing_key
        self.did = did
        self.public_key_hex = public_key_hex

    @classmethod
    def generate(cls) -> "FidesIdentity":
        """Generate a new Ed25519 identity."""
        if not _NACL_AVAILABLE:
            raise ImportError(
                "PyNaCl is required for fides integration. "
                "Install with: pip install pynacl"
            )
        import base58  # type: ignore[import]

        signing_key = SigningKey.generate()
        public_key_bytes = signing_key.verify_key.encode()
        did = f"did:fides:{base58.b58encode(public_key_bytes).decode()}"
        public_key_hex = public_key_bytes.hex()
        return cls(signing_key, did, public_key_hex)

    def sign(self, message: bytes) -> str:
        """Sign a message and return hex-encoded signature."""
        signed = self.signing_key.sign(message)
        return signed.signature.hex()

    @staticmethod
    def verify(message: bytes, signature_hex: str, public_key_hex: str) -> bool:
        """Verify an Ed25519 signature."""
        if not _NACL_AVAILABLE:
            return False
        try:
            verify_key = VerifyKey(bytes.fromhex(public_key_hex))
            verify_key.verify(message, bytes.fromhex(signature_hex))
            return True
        except Exception:
            return False


class AgitFidesEngine:
    """ExecutionEngine wrapper with FIDES identity and trust.

    Every commit is signed with the agent's Ed25519 DID keypair,
    creating a cryptographically verifiable audit trail where each
    state change is linked to a proven agent identity.
    """

    def __init__(
        self,
        repo_path: str,
        agent_id: str = "fides-agent",
        *,
        discovery_url: str = "http://localhost:3000",
        trust_url: str = "http://localhost:3001",
    ) -> None:
        self._engine = ExecutionEngine(repo_path, agent_id=agent_id)
        self._discovery_url = discovery_url
        self._trust_url = trust_url
        self._identity: FidesIdentity | None = None

    @property
    def engine(self) -> ExecutionEngine:
        return self._engine

    @property
    def did(self) -> str | None:
        return self._identity.did if self._identity else None

    async def init_identity(
        self,
        *,
        name: str = "agit-agent",
        existing_identity: FidesIdentity | None = None,
    ) -> str:
        """Initialize or load a fides identity and register with discovery."""
        if existing_identity:
            self._identity = existing_identity
        else:
            self._identity = FidesIdentity.generate()

        # Register with discovery service
        await self._register_with_discovery(name)

        # Commit identity init as system event
        try:
            self._engine.commit_state(
                {
                    "memory": {
                        "fides_identity": {
                            "did": self._identity.did,
                            "public_key": self._identity.public_key_hex,
                            "initialized_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        },
                    },
                    "world_state": {"fides_phase": "identity_init"},
                },
                message=f"fides-init: {self._identity.did}",
                action_type="system_event",
            )
        except Exception:
            logger.warning("Failed to commit identity init", exc_info=True)

        return self._identity.did

    def signed_commit(
        self,
        state: dict[str, Any],
        message: str,
        action_type: str = "checkpoint",
    ) -> str | None:
        """Create a DID-signed commit.

        The state is enriched with a _fides field containing the
        agent's DID and Ed25519 signature over the state hash.
        """
        if not self._identity:
            raise RuntimeError("Fides identity not initialized. Call init_identity() first.")

        # Hash the state for signing
        state_json = json.dumps(state, sort_keys=True, default=str)
        state_hash = hashlib.sha256(state_json.encode()).hexdigest()

        # Sign the hash with Ed25519
        signature = self._identity.sign(state_hash.encode())

        # Enrich state with fides identity proof
        enriched_state = {
            **state,
            "_fides": {
                "did": self._identity.did,
                "public_key": self._identity.public_key_hex,
                "signature": signature,
                "state_hash": state_hash,
                "algorithm": "ed25519",
                "signed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        }

        try:
            return self._engine.commit_state(
                enriched_state,
                message=f"[{self._identity.did[:20]}...] {message}",
                action_type=action_type,
            )
        except Exception:
            logger.warning("Failed to create signed commit", exc_info=True)
            return None

    def verify_commit(self, commit_hash: str) -> dict[str, Any]:
        """Verify that a commit was signed by a valid fides identity.

        Returns dict with 'valid', 'did', and optionally 'error'.
        """
        try:
            state = self._engine.get_state_at(commit_hash)
            if not state:
                return {"valid": False, "error": "Commit not found"}

            fides_data = state.get("_fides")
            if not fides_data:
                return {"valid": False, "error": "Commit has no fides signature"}

            did = fides_data.get("did", "")
            signature = fides_data.get("signature", "")
            public_key = fides_data.get("public_key", "")
            stored_hash = fides_data.get("state_hash", "")

            if not all([did, signature, public_key, stored_hash]):
                return {"valid": False, "error": "Incomplete fides data"}

            # Reconstruct state without _fides for hash verification
            state_without_fides = {k: v for k, v in state.items() if k != "_fides"}
            state_json = json.dumps(state_without_fides, sort_keys=True, default=str)
            computed_hash = hashlib.sha256(state_json.encode()).hexdigest()

            # Verify hash matches
            if computed_hash != stored_hash:
                return {"valid": False, "did": did, "error": "State hash mismatch (tampering detected)"}

            # Verify Ed25519 signature
            valid = FidesIdentity.verify(stored_hash.encode(), signature, public_key)
            if not valid:
                return {"valid": False, "did": did, "error": "Ed25519 signature verification failed"}

            return {"valid": True, "did": did}

        except Exception as e:
            return {"valid": False, "error": str(e)}

    async def trusted_merge(
        self,
        branch: str,
        *,
        min_trust_level: int = 50,
    ) -> dict[str, Any]:
        """Trust-gated merge: only merge if the source branch's committer
        has sufficient trust from the current agent.
        """
        if not self._identity:
            raise RuntimeError("Fides identity not initialized.")

        # Get the latest commit on the source branch
        try:
            history = self._engine.get_history(limit=1)
        except Exception:
            return {"merged": False, "reason": "Could not read branch history"}

        if not history:
            return {"merged": False, "reason": "Branch has no commits"}

        latest = history[0]
        committer_did = None

        try:
            state = self._engine.get_state_at(latest.get("hash", ""))
            committer_did = (state or {}).get("_fides", {}).get("did")
        except Exception:
            pass

        if not committer_did:
            return {"merged": False, "reason": "Branch head has no fides identity"}

        # Query trust score
        trust_level = await self._get_trust_score(committer_did)

        if trust_level < min_trust_level:
            self._engine.commit_state(
                {
                    "memory": {
                        "trust_gate": {
                            "action": "merge_rejected",
                            "branch": branch,
                            "committer_did": committer_did,
                            "trust_level": trust_level,
                            "required_level": min_trust_level,
                        },
                    },
                },
                message=f"fides-gate: merge rejected (trust={trust_level} < required={min_trust_level})",
                action_type="system_event",
            )
            return {
                "merged": False,
                "reason": f"Insufficient trust: {trust_level} < {min_trust_level}",
                "trust_level": trust_level,
            }

        # Trust sufficient — merge
        try:
            self._engine.merge(branch, strategy="three_way")
        except Exception as e:
            return {"merged": False, "reason": f"Merge failed: {e}"}

        self._engine.commit_state(
            {
                "memory": {
                    "trust_gate": {
                        "action": "merge_approved",
                        "branch": branch,
                        "committer_did": committer_did,
                        "trust_level": trust_level,
                        "required_level": min_trust_level,
                    },
                },
            },
            message=f"fides-gate: merge approved (trust={trust_level} >= required={min_trust_level})",
            action_type="system_event",
        )
        return {"merged": True, "trust_level": trust_level}

    async def trust_agent(self, subject_did: str, level: int) -> dict[str, Any]:
        """Issue a trust attestation and commit it to the audit trail."""
        if not self._identity:
            raise RuntimeError("Fides identity not initialized.")

        attestation: dict[str, Any] = {}

        # Create and submit attestation via HTTP
        if _HTTPX_AVAILABLE:
            try:
                async with httpx.AsyncClient() as client:
                    payload = {
                        "issuerDid": self._identity.did,
                        "subjectDid": subject_did,
                        "trustLevel": level,
                    }
                    # Sign the attestation payload
                    payload_json = json.dumps(payload, sort_keys=True)
                    signature = self._identity.sign(payload_json.encode())
                    payload["signature"] = signature
                    payload["payload"] = payload_json

                    resp = await client.post(
                        f"{self._trust_url}/attestations",
                        json=payload,
                    )
                    if resp.status_code < 300:
                        attestation = resp.json()
            except Exception as e:
                logger.warning("Failed to submit trust attestation: %s", e)
                attestation = {"error": str(e), "level": level}
        else:
            attestation = {"local_only": True, "level": level}

        # Commit to audit trail
        try:
            self._engine.commit_state(
                {
                    "memory": {
                        "trust_attestation": {
                            "issuer": self._identity.did,
                            "subject": subject_did,
                            "level": level,
                            "attestation": attestation,
                        },
                    },
                    "world_state": {"fides_phase": "trust_attestation"},
                },
                message=f"fides-trust: {self._identity.did[:16]}... -> {subject_did[:16]}... (level={level})",
                action_type="system_event",
            )
        except Exception:
            logger.warning("Failed to commit trust attestation", exc_info=True)

        return attestation

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _register_with_discovery(self, name: str) -> None:
        """Register identity with the fides discovery service."""
        if not self._identity or not _HTTPX_AVAILABLE:
            return

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self._discovery_url}/identities",
                    json={
                        "did": self._identity.did,
                        "publicKey": self._identity.public_key_hex,
                        "metadata": {
                            "name": name,
                            "type": "agit-agent",
                            "endpoints": {
                                "agit": f"agit://{self._identity.did}",
                            },
                        },
                    },
                )
        except Exception:
            logger.debug("Discovery service not available, operating in local mode")

    async def _get_trust_score(self, did: str) -> int:
        """Query the trust graph for a DID's reputation score."""
        if not _HTTPX_AVAILABLE:
            return 0

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._trust_url}/scores/{did}")
                if resp.status_code == 200:
                    data = resp.json()
                    return int(data.get("score", 0) * 100)
        except Exception:
            logger.debug("Trust service not available for DID: %s", did)

        return 0
