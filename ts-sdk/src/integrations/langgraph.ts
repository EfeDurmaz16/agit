/**
 * LangGraph integration for agit.
 *
 * Provides a checkpoint saver that persists LangGraph workflow
 * state to an agit repository with thread-aware branching.
 */

import type { AgitClient } from "../client.js";
import { ActionType } from "../types.js";

export interface CheckpointMetadata {
  source?: string;
  step?: number;
  [key: string]: unknown;
}

export interface Checkpoint {
  v: number;
  id: string;
  ts: string;
  channel_values: Record<string, unknown>;
}

export interface CheckpointTuple {
  config: Record<string, unknown>;
  checkpoint: Checkpoint;
  metadata: CheckpointMetadata;
}

/**
 * AgitCheckpointSaver — LangGraph checkpoint saver backed by agit.
 *
 * Each thread gets its own agit branch for isolated state tracking.
 */
export class AgitCheckpointSaver {
  private client: AgitClient;

  constructor(client: AgitClient) {
    this.client = client;
  }

  /** Save a checkpoint for a given thread. */
  async put(
    config: Record<string, unknown>,
    checkpoint: Checkpoint,
    metadata: CheckpointMetadata = {}
  ): Promise<void> {
    const threadId = this.getThreadId(config);
    const branchName = `langgraph/${threadId}`;

    // Ensure branch exists
    const status = this.client.status();
    if (!status.branches.includes(branchName)) {
      try {
        await this.client.branch({ name: branchName });
      } catch {
        // Branch may already exist
      }
    }

    await this.client.commit({
      memory: checkpoint.channel_values,
      world_state: { checkpoint_id: checkpoint.id, metadata },
      message: `checkpoint ${checkpoint.id} (step ${metadata.step ?? "?"})`,
      action_type: ActionType.Checkpoint,
    });
  }

  /** Retrieve the latest checkpoint for a thread. */
  async get(config: Record<string, unknown>): Promise<CheckpointTuple | null> {
    const threadId = this.getThreadId(config);
    const branchName = `langgraph/${threadId}`;

    try {
      const commits = await this.client.log({ branch: branchName, limit: 1 });
      if (commits.length === 0) return null;

      const state = await this.client.getState(commits[0].hash);
      return {
        config,
        checkpoint: {
          v: 1,
          id: commits[0].hash,
          ts: commits[0].timestamp,
          channel_values: state.memory as Record<string, unknown>,
        },
        metadata: (state.world_state as Record<string, unknown>)?.metadata as CheckpointMetadata ?? {},
      };
    } catch {
      return null;
    }
  }

  /** List checkpoint history for a thread. */
  async list(
    config: Record<string, unknown>,
    options: { limit?: number } = {}
  ): Promise<CheckpointTuple[]> {
    const threadId = this.getThreadId(config);
    const branchName = `langgraph/${threadId}`;
    const limit = options.limit ?? 10;

    try {
      const commits = await this.client.log({ branch: branchName, limit });
      const results: CheckpointTuple[] = [];

      for (const commit of commits) {
        const state = await this.client.getState(commit.hash);
        results.push({
          config,
          checkpoint: {
            v: 1,
            id: commit.hash,
            ts: commit.timestamp,
            channel_values: state.memory as Record<string, unknown>,
          },
          metadata: (state.world_state as Record<string, unknown>)?.metadata as CheckpointMetadata ?? {},
        });
      }

      return results;
    } catch {
      return [];
    }
  }

  private getThreadId(config: Record<string, unknown>): string {
    const configurable = config.configurable as Record<string, unknown> | undefined;
    return (configurable?.thread_id as string) ?? "default";
  }
}
