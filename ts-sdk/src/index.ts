/**
 * @agit/sdk – TypeScript SDK for agit.
 *
 * Re-exports the high-level client and all public types.
 */

export { AgitClient } from "./client.js";
export type { AgitClientOptions } from "./client.js";

export {
  ActionType,
  ChangeType,
  MergeStrategy,
} from "./types.js";

export type {
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
