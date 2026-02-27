/**
 * Google A2A (Agent-to-Agent) protocol integration for agit.
 *
 * Provides hooks for versioning A2A message exchanges and task
 * lifecycle events in an agit repository.
 */

import type { AgitClient } from "../client.js";
import { ActionType } from "../types.js";

/** A2A message part (text, file, or data). */
export interface A2APart {
  kind: "text" | "file" | "data";
  text?: string;
  data?: Record<string, unknown>;
  name?: string;
  mimeType?: string;
}

/** A2A message exchanged between agents. */
export interface A2AMessage {
  role: "user" | "agent";
  parts: A2APart[];
  messageId?: string;
  contextId?: string;
  taskId?: string;
}

/** A2A task status update event. */
export interface A2ATaskEvent {
  taskId: string;
  status: "submitted" | "working" | "completed" | "input-required" | "failed" | "canceled" | "rejected";
  message?: A2AMessage;
}

/** A2A artifact produced by an agent. */
export interface A2AArtifact {
  artifactId: string;
  name?: string;
  parts: A2APart[];
  metadata?: Record<string, unknown>;
}

/**
 * AgitA2AHooks — A2A protocol lifecycle hooks backed by agit.
 *
 * Commits agent state at each phase of an A2A interaction:
 * discovery, message send/receive, task status updates, and artifacts.
 */
export class AgitA2AHooks {
  private client: AgitClient;
  private branchPerContext: boolean;

  constructor(client: AgitClient, options?: { branchPerContext?: boolean }) {
    this.client = client;
    this.branchPerContext = options?.branchPerContext ?? true;
  }

  /** Called when discovering a remote agent's capabilities. */
  async onDiscovery(agentCard: Record<string, unknown>): Promise<void> {
    await this.client.commit({
      memory: { discovered_agent: agentCard },
      world_state: { a2a_phase: "discovery" },
      message: `a2a-discover: ${(agentCard.name as string) ?? "unknown"}`,
      action_type: ActionType.SystemEvent,
    });
  }

  /** Called before sending a message to a remote agent. */
  async onMessageSend(message: A2AMessage): Promise<void> {
    if (this.branchPerContext && message.contextId) {
      await this.ensureBranch(`a2a/${message.contextId}`);
    }

    await this.client.commit({
      memory: { a2a_message: this.serializeMessage(message) },
      world_state: {
        a2a_context_id: message.contextId,
        a2a_task_id: message.taskId,
        a2a_phase: "send",
      },
      message: `a2a-send: ${this.extractText(message).slice(0, 80)}`,
      action_type: ActionType.ToolCall,
    });
  }

  /** Called when receiving a response from a remote agent. */
  async onMessageReceive(message: A2AMessage): Promise<void> {
    await this.client.commit({
      memory: { a2a_response: this.serializeMessage(message) },
      world_state: {
        a2a_context_id: message.contextId,
        a2a_task_id: message.taskId,
        a2a_phase: "recv",
      },
      message: `a2a-recv: ${this.extractText(message).slice(0, 80)}`,
      action_type: ActionType.LlmResponse,
    });
  }

  /** Called when a task status changes. */
  async onTaskUpdate(event: A2ATaskEvent): Promise<void> {
    await this.client.commit({
      memory: { a2a_task_status: event.status },
      world_state: {
        a2a_task_id: event.taskId,
        a2a_phase: "task_update",
        a2a_status: event.status,
      },
      message: `a2a-task: ${event.taskId} -> ${event.status}`,
      action_type: ActionType.SystemEvent,
    });
  }

  /** Called when an agent produces an artifact. */
  async onArtifact(taskId: string, artifact: A2AArtifact): Promise<void> {
    await this.client.commit({
      memory: {
        a2a_artifact: {
          artifactId: artifact.artifactId,
          name: artifact.name,
          parts: artifact.parts.map((p) => ({
            kind: p.kind,
            ...(p.text ? { text: p.text } : {}),
            ...(p.data ? { data: p.data } : {}),
            ...(p.name ? { name: p.name } : {}),
          })),
        },
      },
      world_state: {
        a2a_task_id: taskId,
        a2a_phase: "artifact",
        a2a_artifact_id: artifact.artifactId,
      },
      message: `a2a-artifact: ${artifact.name ?? artifact.artifactId}`,
      action_type: ActionType.ToolCall,
    });
  }

  /** Called when a task is cancelled. */
  async onCancel(taskId: string): Promise<void> {
    await this.client.commit({
      memory: { a2a_cancelled: taskId },
      world_state: {
        a2a_task_id: taskId,
        a2a_phase: "cancelled",
      },
      message: `a2a-cancel: ${taskId}`,
      action_type: ActionType.SystemEvent,
    });
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  private serializeMessage(msg: A2AMessage): Record<string, unknown> {
    return {
      role: msg.role,
      parts: msg.parts.map((p) => ({
        kind: p.kind,
        ...(p.text ? { text: p.text } : {}),
        ...(p.data ? { data: p.data } : {}),
        ...(p.name ? { name: p.name } : {}),
      })),
      messageId: msg.messageId,
      contextId: msg.contextId,
      taskId: msg.taskId,
    };
  }

  private extractText(msg: A2AMessage): string {
    for (const part of msg.parts) {
      if (part.kind === "text" && part.text) return part.text;
    }
    return "(non-text)";
  }

  private async ensureBranch(name: string): Promise<void> {
    try {
      const status = this.client.status();
      if (!status.branches.includes(name)) {
        await this.client.branch({ name });
      }
    } catch {
      // Branch may already exist
    }
  }
}
