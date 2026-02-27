/**
 * OpenAI Agents SDK integration for agit.
 *
 * Provides lifecycle hooks for tool execution tracking.
 */

import type { AgitClient } from "../client.js";
import { ActionType } from "../types.js";

export interface ToolEvent {
  tool_name: string;
  arguments?: Record<string, unknown>;
  result?: unknown;
  agent_state?: Record<string, unknown>;
}

/**
 * AgitAgentHooks — OpenAI Agents lifecycle hooks backed by agit.
 */
export class AgitAgentHooks {
  private client: AgitClient;

  constructor(client: AgitClient) {
    this.client = client;
  }

  /** Called before a tool execution starts. */
  async onToolStart(event: ToolEvent): Promise<void> {
    if (event.agent_state) {
      await this.client.commit({
        memory: event.agent_state,
        world_state: { tool: event.tool_name, args: event.arguments, phase: "start" },
        message: `tool-start: ${event.tool_name}`,
        action_type: ActionType.ToolCall,
      });
    }
  }

  /** Called after a tool execution completes. */
  async onToolEnd(event: ToolEvent): Promise<void> {
    if (event.agent_state) {
      await this.client.commit({
        memory: event.agent_state,
        world_state: { tool: event.tool_name, result: event.result, phase: "end" },
        message: `tool-end: ${event.tool_name}`,
        action_type: ActionType.ToolCall,
      });
    }
  }

  /** Called when an agent produces a response. */
  async onAgentResponse(state: Record<string, unknown>, message: string): Promise<void> {
    await this.client.commit({
      memory: state,
      message,
      action_type: ActionType.LlmResponse,
    });
  }
}
