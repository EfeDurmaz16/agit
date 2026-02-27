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

// Integration exports
export { createAgitClaudeHooks, type ClaudeHooks, type ClaudeHookContext } from "./integrations/claude-sdk.js";
export { AgitAgentHooks, type ToolEvent } from "./integrations/openai-agents.js";
export { AgitCheckpointSaver, type Checkpoint, type CheckpointTuple, type CheckpointMetadata } from "./integrations/langgraph.js";
export { AgitA2AHooks, type A2AMessage, type A2APart, type A2ATaskEvent, type A2AArtifact } from "./integrations/a2a.js";
export { AgitFidesClient, type FidesCommitIdentity, type SignedCommit, type TrustGateOptions } from "./integrations/fides.js";
