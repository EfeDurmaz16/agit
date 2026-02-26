/**
 * AgitClient – high-level ergonomic wrapper around the agit native bindings.
 *
 * Production default is fail-closed when native `@agit/core` is unavailable.
 * A pure-TypeScript in-memory fallback is available only when explicitly
 * enabled (e.g. `forcePureTs` in tests or `AGIT_ALLOW_STUBS=1`).
 */

import type {
  AgentState,
  BranchOptions,
  Commit,
  CommitOptions,
  DiffEntry,
  LogOptions,
  MergeOptions,
  RepoStatus,
  StateDiff,
} from "./types.js";
import { ActionType, ChangeType, MergeStrategy } from "./types.js";

// ---------------------------------------------------------------------------
// Native binding import (optional)
// ---------------------------------------------------------------------------

/** Shape of the native JsRepository exposed by napi-rs. */
interface NativeRepository {
  commit(
    memory_json: string,
    world_state_json: string,
    message: string,
    action_type: string,
    cost?: number,
    metadata_json?: string
  ): Promise<string>;
  branch(name: string, from?: string): Promise<void>;
  checkout(target: string): Promise<AgentState>;
  diff(hash1: string, hash2: string): Promise<StateDiff>;
  merge(branch: string, strategy: string): Promise<string>;
  log(branch?: string, limit?: number): Promise<Commit[]>;
  revert(toHash: string): Promise<AgentState>;
  getState(hash: string): Promise<AgentState>;
  head(): string | null;
  currentBranch(): string | null;
  listBranches(): string[];
}

interface NativeModule {
  JsRepository: {
    open(path: string): Promise<NativeRepository>;
  };
}

let nativeModule: NativeModule | null = null;

try {
  // Dynamic require so that the SDK still loads without the compiled binary.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  nativeModule = require("@agit/core") as NativeModule;
} catch {
  // Native module not available.
}

function envFlag(name: string): boolean {
  if (typeof process === "undefined") return false;
  const raw = process.env?.[name];
  if (!raw) return false;
  return ["1", "true", "yes", "on"].includes(raw.trim().toLowerCase());
}

function parseJsonValue(value: unknown): unknown {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function normalizeState(state: AgentState): AgentState {
  return {
    ...state,
    memory: parseJsonValue(state.memory),
    world_state: parseJsonValue(state.world_state),
    metadata: parseJsonValue(state.metadata),
  };
}

// ---------------------------------------------------------------------------
// Pure-TypeScript fallback implementation
// ---------------------------------------------------------------------------

function sha256Sync(data: string): string {
  // Minimal deterministic hash using a simple djb2 variant.
  // Only used in the fallback when the native binary is absent.
  let h = 5381n;
  for (let i = 0; i < data.length; i++) {
    h = ((h << 5n) + h + BigInt(data.charCodeAt(i))) & 0xffffffffffffffffn;
  }
  return h.toString(16).padStart(16, "0").repeat(4);
}

interface InMemoryBranches {
  [name: string]: string; // branch name -> commit hash
}

class PureTsRepository implements NativeRepository {
  private commits = new Map<string, Commit & { state: AgentState }>();
  private branches: InMemoryBranches = {};
  private headRef: string | null = null; // branch name when attached
  private detachedHash: string | null = null;
  private _currentBranch: string | null = "main";

  private resolveHead(): string | null {
    if (this._currentBranch !== null) {
      return this.branches[this._currentBranch] ?? null;
    }
    return this.detachedHash;
  }

  async commit(
    memory_json: string,
    world_state_json: string,
    message: string,
    action_type: string,
    cost?: number,
    metadata?: unknown
  ): Promise<string> {
    const now = new Date().toISOString();
    const parentHash = this.resolveHead();
    const parent_hashes = parentHash ? [parentHash] : [];

    const memory = parseJsonValue(memory_json);
    const world_state = parseJsonValue(world_state_json);

    const state: AgentState = {
      memory,
      world_state: world_state ?? {},
      timestamp: now,
      cost: cost ?? 0,
      metadata: parseJsonValue(metadata),
    };

    const treeHash = sha256Sync(JSON.stringify(state));
    const hashInput = JSON.stringify({
      tree_hash: treeHash,
      parent_hashes,
      message,
      action_type,
      timestamp: now,
    });
    const hash = sha256Sync(hashInput);

    const commit: Commit & { state: AgentState } = {
      hash,
      tree_hash: treeHash,
      parent_hashes,
      message,
      author: "default",
      timestamp: now,
      action_type,
      state,
    };

    this.commits.set(hash, commit);

    if (this._currentBranch !== null) {
      this.branches[this._currentBranch] = hash;
    } else {
      this.detachedHash = hash;
    }

    return hash;
  }

  async branch(name: string, from?: string): Promise<void> {
    const sourceHash =
      from !== undefined
        ? (this.branches[from] ?? from)
        : (this.resolveHead() ?? "");
    if (!sourceHash) throw new Error("No commits yet");
    this.branches[name] = sourceHash;
  }

  async checkout(target: string): Promise<AgentState> {
    if (target in this.branches) {
      this._currentBranch = target;
      this.detachedHash = null;
      const hash = this.branches[target];
      const entry = this.commits.get(hash);
      if (!entry) throw new Error(`Object not found: ${hash}`);
      return entry.state;
    }
    // Try as commit hash
    const entry = this.commits.get(target);
    if (entry) {
      this._currentBranch = null;
      this.detachedHash = target;
      return entry.state;
    }
    throw new Error(`Ref not found: ${target}`);
  }

  async diff(hash1: string, hash2: string): Promise<StateDiff> {
    const e1 = this.commits.get(hash1);
    const e2 = this.commits.get(hash2);
    if (!e1) throw new Error(`Object not found: ${hash1}`);
    if (!e2) throw new Error(`Object not found: ${hash2}`);

    const entries: DiffEntry[] = diffValues(
      e1.state as unknown as Record<string, unknown>,
      e2.state as unknown as Record<string, unknown>,
      []
    );

    return { base_hash: hash1, target_hash: hash2, entries };
  }

  async merge(branch: string, strategy: string): Promise<string> {
    if (!(branch in this.branches)) throw new Error(`Branch not found: ${branch}`);
    const theirHash = this.branches[branch];
    const theirEntry = this.commits.get(theirHash);
    if (!theirEntry) throw new Error(`Object not found: ${theirHash}`);

    const ourHash = this.resolveHead();
    if (!ourHash) throw new Error("No commits on current branch");
    const ourEntry = this.commits.get(ourHash);
    if (!ourEntry) throw new Error(`Object not found: ${ourHash}`);

    let mergedState: AgentState;
    if (strategy === MergeStrategy.Theirs) {
      mergedState = theirEntry.state;
    } else {
      mergedState = ourEntry.state;
    }

    const currentBranch = this._currentBranch ?? "HEAD";
    return this.commit(
      JSON.stringify(mergedState.memory),
      JSON.stringify(mergedState.world_state),
      `merge branch '${branch}' into '${currentBranch}'`,
      ActionType.Merge,
      mergedState.cost,
      mergedState.metadata as Record<string, unknown> | undefined
    );
  }

  async log(branch?: string, limit?: number): Promise<Commit[]> {
    const startHash =
      branch !== undefined
        ? this.branches[branch]
        : this.resolveHead();
    if (!startHash) return [];

    const lim = limit ?? 50;
    const result: Commit[] = [];
    const visited = new Set<string>();
    const queue = [startHash];

    while (queue.length > 0 && result.length < lim) {
      const h = queue.shift()!;
      if (visited.has(h)) continue;
      visited.add(h);
      const entry = this.commits.get(h);
      if (!entry) continue;
      result.push(entry);
      for (const parent of entry.parent_hashes) {
        if (!visited.has(parent)) queue.push(parent);
      }
    }

    return result.sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
  }

  async revert(toHash: string): Promise<AgentState> {
    const entry = this.commits.get(toHash);
    if (!entry) throw new Error(`Object not found: ${toHash}`);
    await this.commit(
      JSON.stringify(entry.state.memory),
      JSON.stringify(entry.state.world_state),
      `revert to ${toHash.slice(0, 8)}`,
      ActionType.Rollback,
      entry.state.cost,
      entry.state.metadata as Record<string, unknown> | undefined
    );
    return entry.state;
  }

  async getState(hash: string): Promise<AgentState> {
    const entry = this.commits.get(hash);
    if (!entry) throw new Error(`Object not found: ${hash}`);
    return entry.state;
  }

  head(): string | null {
    return this.resolveHead();
  }

  currentBranch(): string | null {
    return this._currentBranch;
  }

  listBranches(): string[] {
    return Object.keys(this.branches);
  }
}

// Recursive JSON diff helper for the pure-TS fallback.
function diffValues(
  base: Record<string, unknown>,
  target: Record<string, unknown>,
  path: string[]
): DiffEntry[] {
  const entries: DiffEntry[] = [];
  const allKeys = new Set([...Object.keys(base), ...Object.keys(target)]);

  for (const key of allKeys) {
    const currentPath = [...path, key];
    const bVal = base[key];
    const tVal = target[key];

    if (!(key in base)) {
      entries.push({
        path: currentPath,
        change_type: ChangeType.Added,
        new_value: JSON.stringify(tVal),
      });
    } else if (!(key in target)) {
      entries.push({
        path: currentPath,
        change_type: ChangeType.Removed,
        old_value: JSON.stringify(bVal),
      });
    } else if (
      typeof bVal === "object" &&
      bVal !== null &&
      !Array.isArray(bVal) &&
      typeof tVal === "object" &&
      tVal !== null &&
      !Array.isArray(tVal)
    ) {
      entries.push(
        ...diffValues(
          bVal as Record<string, unknown>,
          tVal as Record<string, unknown>,
          currentPath
        )
      );
    } else if (JSON.stringify(bVal) !== JSON.stringify(tVal)) {
      entries.push({
        path: currentPath,
        change_type: ChangeType.Changed,
        old_value: JSON.stringify(bVal),
        new_value: JSON.stringify(tVal),
      });
    }
  }

  return entries;
}

// ---------------------------------------------------------------------------
// AgitClient
// ---------------------------------------------------------------------------

/** Options for constructing an `AgitClient`. */
export interface AgitClientOptions {
  /**
   * Agent identifier written to commit author fields.
   * Defaults to `"default"`.
   */
  agentId?: string;
  /**
   * When `true`, always use the pure-TypeScript fallback even if the native
   * module is available. Useful for testing.
   */
  forcePureTs?: boolean;
}

/**
 * High-level client for interacting with an agit repository.
 *
 * @example
 * ```ts
 * const client = await AgitClient.open("/path/to/repo");
 * const hash = await client.commit({
 *   memory: { step: 1 },
 *   message: "first checkpoint",
 * });
 * ```
 */
export class AgitClient {
  private repo: NativeRepository;

  private constructor(repo: NativeRepository) {
    this.repo = repo;
  }

  /**
   * Open (or initialise) an agit repository at `repoPath`.
   *
   * Production default is fail-closed: if the native `@agit/core` binary is
   * missing, this throws unless fallback is explicitly enabled.
   * Enable fallback with `forcePureTs: true` (tests) or `AGIT_ALLOW_STUBS=1`.
   */
  static async open(
    repoPath: string,
    options: AgitClientOptions = {}
  ): Promise<AgitClient> {
    const allowStubs = options.forcePureTs || envFlag("AGIT_ALLOW_STUBS");
    const usePureTs = options.forcePureTs || (nativeModule === null && allowStubs);

    let repo: NativeRepository;
    if (usePureTs) {
      repo = new PureTsRepository();
    } else {
      if (nativeModule === null) {
        throw new Error(
          "Native @agit/core module is required. Set AGIT_ALLOW_STUBS=1 only for local development/testing."
        );
      }
      repo = await nativeModule!.JsRepository.open(repoPath);
    }

    return new AgitClient(repo);
  }

  /**
   * Commit an agent state snapshot.
   *
   * @returns The SHA-256 hash of the new commit.
   */
  async commit(options: CommitOptions): Promise<string> {
    const {
      memory,
      world_state = {},
      message,
      action_type = ActionType.Checkpoint,
      cost,
      metadata,
    } = options;

    return this.repo.commit(
      JSON.stringify(memory),
      JSON.stringify(world_state),
      message,
      typeof action_type === "string" ? action_type : action_type,
      cost,
      metadata === undefined ? undefined : JSON.stringify(metadata)
    );
  }

  /**
   * Create a new branch.
   */
  async branch(options: BranchOptions): Promise<void> {
    return this.repo.branch(options.name, options.from);
  }

  /**
   * Checkout a branch or commit by name/hash.
   *
   * @returns The agent state at the checked-out point.
   */
  async checkout(target: string): Promise<AgentState> {
    return normalizeState(await this.repo.checkout(target));
  }

  /**
   * Compute the diff between two commits.
   */
  async diff(hash1: string, hash2: string): Promise<StateDiff> {
    return this.repo.diff(hash1, hash2);
  }

  /**
   * Merge a branch into the current branch.
   *
   * @returns Hash of the resulting merge commit.
   */
  async merge(options: MergeOptions): Promise<string> {
    const strategy = options.strategy ?? MergeStrategy.Ours;
    return this.repo.merge(options.branch, strategy);
  }

  /**
   * Retrieve commit history.
   */
  async log(options: LogOptions = {}): Promise<Commit[]> {
    return this.repo.log(options.branch, options.limit);
  }

  /**
   * Create a revert commit that restores state from `toHash`.
   *
   * @returns The restored agent state.
   */
  async revert(toHash: string): Promise<AgentState> {
    return normalizeState(await this.repo.revert(toHash));
  }

  /**
   * Retrieve the agent state stored at a specific commit.
   */
  async getState(hash: string): Promise<AgentState> {
    return normalizeState(await this.repo.getState(hash));
  }

  /**
   * Return repository status information.
   */
  status(): RepoStatus {
    return {
      head: this.repo.head(),
      current_branch: this.repo.currentBranch(),
      branches: this.repo.listBranches(),
    };
  }
}
