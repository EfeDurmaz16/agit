/**
 * TypeScript type definitions for the agit SDK.
 *
 * These mirror the Rust core types exposed via napi-rs bindings.
 */

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

/** The type of agent action that produced a commit. */
export enum ActionType {
  ToolCall = "tool_call",
  LlmResponse = "llm_response",
  UserInput = "user_input",
  SystemEvent = "system_event",
  Retry = "retry",
  Rollback = "rollback",
  Merge = "merge",
  Checkpoint = "checkpoint",
}

/** Strategy used when merging two branches. */
export enum MergeStrategy {
  /** Keep our (current branch) state on conflict. */
  Ours = "ours",
  /** Take their (incoming branch) state on conflict. */
  Theirs = "theirs",
  /** Attempt automatic three-way merge; throws on conflict. */
  ThreeWay = "three_way",
}

/** Type of change in a diff entry. */
export enum ChangeType {
  Added = "added",
  Removed = "removed",
  Changed = "changed",
}

// ---------------------------------------------------------------------------
// Core domain types
// ---------------------------------------------------------------------------

/** Full agent state snapshot stored at each commit. */
export interface AgentState {
  /** Agent's working memory – arbitrary JSON. */
  memory: unknown;
  /** External world state – arbitrary JSON. */
  world_state: unknown;
  /** ISO-8601 timestamp of when this state was recorded. */
  timestamp: string;
  /** Cumulative cost (e.g., token spend) at this point. */
  cost: number;
  /** Optional extra metadata – arbitrary JSON. */
  metadata?: unknown;
}

/** A commit in the agit DAG. */
export interface Commit {
  /** SHA-256 hex hash uniquely identifying this commit. */
  hash: string;
  /** Hash of the state blob (tree) this commit points to. */
  tree_hash: string;
  /** Hashes of parent commit(s); empty for the initial commit. */
  parent_hashes: string[];
  /** Human-readable description. */
  message: string;
  /** Agent or user that authored this commit. */
  author: string;
  /** ISO-8601 creation timestamp. */
  timestamp: string;
  /** The action type that produced this commit. */
  action_type: string;
}

/** A single entry in a state diff. */
export interface DiffEntry {
  /** JSON path segments to the changed value. */
  path: string[];
  /** Nature of the change. */
  change_type: ChangeType | string;
  /** Previous value serialised as JSON string (or undefined if added). */
  old_value?: string;
  /** New value serialised as JSON string (or undefined if removed). */
  new_value?: string;
}

/** The diff between two commits. */
export interface StateDiff {
  /** Hash of the base (older) commit. */
  base_hash: string;
  /** Hash of the target (newer) commit. */
  target_hash: string;
  /** Individual diff entries. */
  entries: DiffEntry[];
}

// ---------------------------------------------------------------------------
// Option interfaces
// ---------------------------------------------------------------------------

/** Options for `AgitClient.commit()`. */
export interface CommitOptions {
  /** Working memory snapshot. */
  memory: unknown;
  /** External world state snapshot. */
  world_state?: unknown;
  /** Commit message. */
  message: string;
  /** Action type (defaults to `ActionType.Checkpoint`). */
  action_type?: ActionType | string;
  /** Cumulative cost at this point. */
  cost?: number;
  /** Extra metadata to store with the commit. */
  metadata?: Record<string, unknown>;
}

/** Options for `AgitClient.branch()`. */
export interface BranchOptions {
  /** Name of the new branch. */
  name: string;
  /** Hash or branch name to branch from (defaults to HEAD). */
  from?: string;
}

/** Options for `AgitClient.log()`. */
export interface LogOptions {
  /** Branch name to traverse (defaults to HEAD). */
  branch?: string;
  /** Maximum number of commits to return (defaults to 50). */
  limit?: number;
}

/** Options for `AgitClient.merge()`. */
export interface MergeOptions {
  /** Branch to merge into the current branch. */
  branch: string;
  /** Conflict resolution strategy (defaults to `MergeStrategy.Ours`). */
  strategy?: MergeStrategy;
}

/** Status information for the repository. */
export interface RepoStatus {
  /** Current HEAD commit hash, or null if no commits yet. */
  head: string | null;
  /** Currently checked-out branch name, or null if in detached HEAD state. */
  current_branch: string | null;
  /** All branch names in the repository. */
  branches: string[];
}
