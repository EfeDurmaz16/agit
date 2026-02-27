/**
 * FIDES (Trusted Agent Protocol) integration for agit.
 *
 * Provides DID-signed commits, trust-gated repository access,
 * and verifiable agent identity for multi-agent swarm versioning.
 *
 * @example
 * ```ts
 * import { AgitFidesClient } from "@agit/sdk";
 * import { Fides } from "@fides/sdk";
 *
 * const fides = new Fides({ discoveryUrl: "...", trustUrl: "..." });
 * const identity = await fides.createIdentity({ name: "my-agent" });
 *
 * const agitFides = new AgitFidesClient(agitClient, fides);
 * await agitFides.signedCommit(state, "checkpoint after tool call");
 * ```
 */

import type { AgitClient } from "../client.js";
import { ActionType } from "../types.js";

/** Fides identity attached to a signed commit. */
export interface FidesCommitIdentity {
  did: string;
  publicKey: string;
  signature: string;
  algorithm: "ed25519";
}

/** A commit that has been signed with a fides DID. */
export interface SignedCommit {
  hash: string;
  did: string;
  signature: string;
  trustLevel?: number;
}

/** Options for trust-gated operations. */
export interface TrustGateOptions {
  /** Minimum trust level (0-100) required for the operation. */
  minTrustLevel: number;
  /** DID of the agent requesting the operation. */
  requesterDid: string;
}

/**
 * AgitFidesClient — agit client with FIDES identity and trust.
 *
 * Every commit is signed with the agent's Ed25519 DID keypair,
 * creating a cryptographically verifiable audit trail where each
 * state change is linked to a proven agent identity.
 */
export class AgitFidesClient {
  private client: AgitClient;
  private fides: any; // Fides instance from @fides/sdk
  private did: string | null = null;

  constructor(client: AgitClient, fides: any) {
    this.client = client;
    this.fides = fides;
  }

  /**
   * Initialize with an existing fides identity or create a new one.
   */
  async init(existingDid?: string): Promise<string> {
    if (existingDid) {
      this.did = existingDid;
    } else {
      const identity = await this.fides.createIdentity({
        name: `agit-agent-${Date.now()}`,
        description: "agit-managed agent with fides identity",
      });
      this.did = identity.did;
    }

    // Commit identity creation as system event
    await this.client.commit({
      memory: {
        fides_identity: {
          did: this.did,
          initialized_at: new Date().toISOString(),
        },
      },
      world_state: { fides_phase: "identity_init" },
      message: `fides-init: ${this.did}`,
      action_type: ActionType.SystemEvent,
    });

    return this.did;
  }

  /**
   * Create a DID-signed commit. The commit message includes the
   * agent's DID and Ed25519 signature over the state hash.
   */
  async signedCommit(
    state: Record<string, unknown>,
    message: string,
    actionType: ActionType = ActionType.Checkpoint
  ): Promise<SignedCommit> {
    if (!this.did) {
      throw new Error("Fides identity not initialized. Call init() first.");
    }

    // Serialize state for signing
    const stateJson = JSON.stringify(state, null, 0);
    const stateRequest = {
      method: "POST",
      url: `agit://commit/${this.did}`,
      headers: {
        "content-type": "application/json",
      } as Record<string, string>,
      body: stateJson,
    };

    // Sign with fides (RFC 9421 HTTP signature)
    const signed = await this.fides.signRequest(stateRequest);
    const signature = signed.headers["Signature"] || signed.headers["signature"] || "";

    // Embed fides identity in the committed state
    const enrichedState = {
      ...state,
      _fides: {
        did: this.did,
        signature,
        algorithm: "ed25519",
        signed_at: new Date().toISOString(),
      } satisfies FidesCommitIdentity & { signed_at: string },
    };

    // Commit with agit
    const commitResult = await this.client.commit({
      memory: enrichedState,
      world_state: state.world_state as Record<string, unknown> | undefined,
      message: `[${this.did.slice(0, 20)}...] ${message}`,
      action_type: actionType,
    });

    return {
      hash: (commitResult as any)?.hash ?? "unknown",
      did: this.did,
      signature,
    };
  }

  /**
   * Verify that a commit was signed by a specific agent DID.
   */
  async verifyCommit(commitHash: string): Promise<{
    valid: boolean;
    did?: string;
    error?: string;
  }> {
    try {
      const state = await this.client.getState(commitHash);
      const fidesData = (state as any)?._fides;

      if (!fidesData?.did || !fidesData?.signature) {
        return { valid: false, error: "Commit has no fides signature" };
      }

      // Resolve the DID to get the public key
      const identity = await this.fides.resolve(fidesData.did);
      if (!identity) {
        return { valid: false, error: `Could not resolve DID: ${fidesData.did}` };
      }

      // Reconstruct the request for verification
      const stateWithoutFides = { ...state };
      delete (stateWithoutFides as any)._fides;

      const request = {
        method: "POST",
        url: `agit://commit/${fidesData.did}`,
        headers: {
          "content-type": "application/json",
          signature: fidesData.signature,
          "signature-input": `sig1=("@method" "@target-uri" "content-type");keyid="${fidesData.did}";alg="ed25519"`,
        },
        body: JSON.stringify(stateWithoutFides, null, 0),
      };

      const result = await this.fides.verifyRequest(request);
      return {
        valid: result.valid,
        did: fidesData.did,
        error: result.error,
      };
    } catch (e) {
      return { valid: false, error: String(e) };
    }
  }

  /**
   * Trust-gated merge: only merge if the source branch's last
   * committer has sufficient trust from the current agent.
   */
  async trustedMerge(
    branch: string,
    options: TrustGateOptions
  ): Promise<{ merged: boolean; reason?: string; trustLevel?: number }> {
    if (!this.did) {
      throw new Error("Fides identity not initialized.");
    }

    // Get the latest commit on the source branch
    const commits = await this.client.log({ branch, limit: 1 });
    if (commits.length === 0) {
      return { merged: false, reason: "Branch has no commits" };
    }

    const state = await this.client.getState(commits[0].hash);
    const committerDid = (state as any)?._fides?.did;

    if (!committerDid) {
      return { merged: false, reason: "Branch head has no fides identity" };
    }

    // Check trust level
    try {
      const reputation = await this.fides.getReputation(committerDid);
      const trustLevel = Math.round(reputation.score * 100);

      if (trustLevel < options.minTrustLevel) {
        // Commit the rejection as audit event
        await this.client.commit({
          memory: {
            trust_gate: {
              action: "merge_rejected",
              branch,
              committer_did: committerDid,
              trust_level: trustLevel,
              required_level: options.minTrustLevel,
            },
          },
          message: `fides-gate: merge rejected (trust=${trustLevel} < required=${options.minTrustLevel})`,
          action_type: ActionType.SystemEvent,
        });

        return {
          merged: false,
          reason: `Insufficient trust: ${trustLevel} < ${options.minTrustLevel}`,
          trustLevel,
        };
      }

      // Trust sufficient — perform merge
      await this.client.merge({ branch, strategy: "three-way" as any });

      // Commit trust verification as audit trail
      await this.client.commit({
        memory: {
          trust_gate: {
            action: "merge_approved",
            branch,
            committer_did: committerDid,
            trust_level: trustLevel,
            required_level: options.minTrustLevel,
          },
        },
        message: `fides-gate: merge approved (trust=${trustLevel} >= required=${options.minTrustLevel})`,
        action_type: ActionType.SystemEvent,
      });

      return { merged: true, trustLevel };
    } catch (e) {
      return { merged: false, reason: `Trust check failed: ${e}` };
    }
  }

  /**
   * Issue a trust attestation to another agent and commit it.
   */
  async trustAgent(
    subjectDid: string,
    level: number
  ): Promise<{ attestation: any; commitHash?: string }> {
    if (!this.did) {
      throw new Error("Fides identity not initialized.");
    }

    const attestation = await this.fides.trust(subjectDid, level);

    // Commit trust attestation as audit trail
    const result = await this.client.commit({
      memory: {
        trust_attestation: {
          issuer: this.did,
          subject: subjectDid,
          level,
          attestation_id: attestation.id,
        },
      },
      world_state: { fides_phase: "trust_attestation" },
      message: `fides-trust: ${this.did.slice(0, 16)}... -> ${subjectDid.slice(0, 16)}... (level=${level})`,
      action_type: ActionType.SystemEvent,
    });

    return { attestation, commitHash: (result as any)?.hash };
  }

  /** Get the current agent's DID. */
  getDid(): string | null {
    return this.did;
  }
}
