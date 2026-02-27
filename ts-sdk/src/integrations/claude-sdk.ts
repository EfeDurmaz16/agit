/**
 * Claude SDK integration for agit.
 *
 * Provides PreToolUse/PostToolUse hooks that automatically commit
 * agent state to an agit repository on each tool execution.
 */

import type { AgitClient } from "../client.js";
import { ActionType } from "../types.js";

export interface ClaudeHookContext {
  tool_name: string;
  tool_input?: unknown;
  tool_output?: unknown;
  agent_state?: Record<string, unknown>;
}

export interface ClaudeHooks {
  preToolUse: (ctx: ClaudeHookContext) => Promise<void>;
  postToolUse: (ctx: ClaudeHookContext) => Promise<void>;
}

/**
 * Create agit-integrated Claude SDK hooks.
 *
 * @example
 * ```ts
 * const client = await AgitClient.open("/path/to/repo");
 * const hooks = createAgitClaudeHooks(client);
 * // Register hooks with Claude SDK
 * ```
 */
export function createAgitClaudeHooks(client: AgitClient): ClaudeHooks {
  return {
    preToolUse: async (ctx: ClaudeHookContext) => {
      if (ctx.agent_state) {
        await client.commit({
          memory: ctx.agent_state,
          world_state: { pending_tool: ctx.tool_name, tool_input: ctx.tool_input },
          message: `pre-tool: ${ctx.tool_name}`,
          action_type: ActionType.ToolCall,
        });
      }
    },
    postToolUse: async (ctx: ClaudeHookContext) => {
      if (ctx.agent_state) {
        await client.commit({
          memory: ctx.agent_state,
          world_state: { completed_tool: ctx.tool_name, tool_output: ctx.tool_output },
          message: `post-tool: ${ctx.tool_name}`,
          action_type: ActionType.ToolCall,
        });
      }
    },
  };
}
