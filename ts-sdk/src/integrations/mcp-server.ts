/**
 * MCP (Model Context Protocol) server exposing agit operations as tools.
 *
 * Uses `@modelcontextprotocol/sdk` to register the following tools:
 *  - agit_commit
 *  - agit_log
 *  - agit_diff
 *  - agit_branch
 *  - agit_checkout
 *  - agit_merge
 *  - agit_revert
 *  - agit_status
 *
 * @example
 * ```ts
 * import { AgitClient } from "@agit/sdk";
 * import { createAgitMcpServer } from "@agit/sdk/integrations/mcp-server";
 *
 * const client = await AgitClient.open("/path/to/repo");
 * const server = createAgitMcpServer(client);
 * await server.listen(); // or transport of your choice
 * ```
 */

import { AgitClient } from "../client.js";
import { ActionType, MergeStrategy } from "../types.js";

// ---------------------------------------------------------------------------
// MCP SDK stubs – loaded at runtime so the import is optional.
// ---------------------------------------------------------------------------

interface McpServer {
  tool(
    name: string,
    description: string,
    schema: Record<string, unknown>,
    handler: (args: Record<string, unknown>) => Promise<McpToolResult>
  ): void;
  /** Start listening on the given transport. */
  connect(transport: unknown): Promise<void>;
}

interface McpToolResult {
  content: Array<{ type: "text"; text: string }>;
  isError?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ok(data: unknown): McpToolResult {
  return {
    content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
  };
}

function fail(message: string): McpToolResult {
  return {
    content: [{ type: "text", text: `Error: ${message}` }],
    isError: true,
  };
}

function str(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

function num(v: unknown, fallback: number): number {
  return typeof v === "number" ? v : fallback;
}

// ---------------------------------------------------------------------------
// Server factory
// ---------------------------------------------------------------------------

/**
 * Create and configure an MCP server exposing agit tools.
 *
 * The returned server object follows the `@modelcontextprotocol/sdk` `Server`
 * interface. Wire it to a transport (stdio, SSE, etc.) using `server.connect()`.
 */
export function createAgitMcpServer(client: AgitClient): McpServer {
  // Attempt to load the MCP SDK.
  let McpServerCtor: new (info: unknown, config: unknown) => McpServer;

  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const sdk = require("@modelcontextprotocol/sdk/server/index.js") as {
      Server: new (info: unknown, config: unknown) => McpServer;
    };
    McpServerCtor = sdk.Server;
  } catch {
    throw new Error(
      'MCP server requires "@modelcontextprotocol/sdk". ' +
        'Install it with: npm install @modelcontextprotocol/sdk'
    );
  }

  const server = new McpServerCtor(
    { name: "agit", version: "0.1.0" },
    { capabilities: { tools: {} } }
  );

  // ---- agit_commit --------------------------------------------------------
  server.tool(
    "agit_commit",
    "Commit the current agent state to the agit repository. Returns the commit hash.",
    {
      type: "object",
      properties: {
        memory: {
          description: "Agent working memory (arbitrary JSON).",
        },
        world_state: {
          description: "External world state snapshot (arbitrary JSON).",
        },
        message: {
          type: "string",
          description: "Commit message describing this checkpoint.",
        },
        action_type: {
          type: "string",
          description:
            "Action type: tool_call | llm_response | user_input | system_event | retry | rollback | merge | checkpoint",
          default: "checkpoint",
        },
        cost: {
          type: "number",
          description: "Cumulative cost (e.g. token spend) at this point.",
        },
      },
      required: ["memory", "message"],
    },
    async (args) => {
      try {
        const hash = await client.commit({
          memory: args["memory"],
          world_state: args["world_state"] ?? {},
          message: str(args["message"], "checkpoint"),
          action_type:
            (str(args["action_type"]) as ActionType) || ActionType.Checkpoint,
          cost: typeof args["cost"] === "number" ? args["cost"] : undefined,
        });
        return ok({ hash });
      } catch (e) {
        return fail(String(e));
      }
    }
  );

  // ---- agit_log -----------------------------------------------------------
  server.tool(
    "agit_log",
    "List commit history for a branch or HEAD.",
    {
      type: "object",
      properties: {
        branch: {
          type: "string",
          description: "Branch name to traverse. Defaults to HEAD.",
        },
        limit: {
          type: "number",
          description: "Maximum number of commits to return. Defaults to 20.",
          default: 20,
        },
      },
    },
    async (args) => {
      try {
        const commits = await client.log({
          branch: str(args["branch"]) || undefined,
          limit: num(args["limit"], 20),
        });
        return ok(commits);
      } catch (e) {
        return fail(String(e));
      }
    }
  );

  // ---- agit_diff ----------------------------------------------------------
  server.tool(
    "agit_diff",
    "Show the diff between two commits.",
    {
      type: "object",
      properties: {
        hash1: { type: "string", description: "Base commit hash." },
        hash2: { type: "string", description: "Target commit hash." },
      },
      required: ["hash1", "hash2"],
    },
    async (args) => {
      try {
        const diff = await client.diff(str(args["hash1"]), str(args["hash2"]));
        return ok(diff);
      } catch (e) {
        return fail(String(e));
      }
    }
  );

  // ---- agit_branch --------------------------------------------------------
  server.tool(
    "agit_branch",
    "Create a new branch at the given source commit or HEAD.",
    {
      type: "object",
      properties: {
        name: { type: "string", description: "New branch name." },
        from: {
          type: "string",
          description:
            "Source branch name or commit hash. Defaults to HEAD.",
        },
      },
      required: ["name"],
    },
    async (args) => {
      try {
        await client.branch({
          name: str(args["name"]),
          from: str(args["from"]) || undefined,
        });
        return ok({ created: str(args["name"]) });
      } catch (e) {
        return fail(String(e));
      }
    }
  );

  // ---- agit_checkout ------------------------------------------------------
  server.tool(
    "agit_checkout",
    "Checkout a branch or commit hash, restoring the stored agent state.",
    {
      type: "object",
      properties: {
        target: {
          type: "string",
          description: "Branch name or commit hash to check out.",
        },
      },
      required: ["target"],
    },
    async (args) => {
      try {
        const state = await client.checkout(str(args["target"]));
        return ok(state);
      } catch (e) {
        return fail(String(e));
      }
    }
  );

  // ---- agit_merge ---------------------------------------------------------
  server.tool(
    "agit_merge",
    "Merge a branch into the current branch.",
    {
      type: "object",
      properties: {
        branch: {
          type: "string",
          description: "Name of the branch to merge in.",
        },
        strategy: {
          type: "string",
          description:
            "Conflict resolution strategy: ours | theirs | three_way. Defaults to ours.",
          default: "ours",
        },
      },
      required: ["branch"],
    },
    async (args) => {
      try {
        const strategyStr = str(args["strategy"], "ours");
        const strategy =
          strategyStr === "theirs"
            ? MergeStrategy.Theirs
            : strategyStr === "three_way"
            ? MergeStrategy.ThreeWay
            : MergeStrategy.Ours;

        const hash = await client.merge({
          branch: str(args["branch"]),
          strategy,
        });
        return ok({ hash });
      } catch (e) {
        return fail(String(e));
      }
    }
  );

  // ---- agit_revert --------------------------------------------------------
  server.tool(
    "agit_revert",
    "Create a revert commit that restores the state from a previous commit.",
    {
      type: "object",
      properties: {
        hash: {
          type: "string",
          description: "Commit hash to revert to.",
        },
      },
      required: ["hash"],
    },
    async (args) => {
      try {
        const state = await client.revert(str(args["hash"]));
        return ok(state);
      } catch (e) {
        return fail(String(e));
      }
    }
  );

  // ---- agit_status --------------------------------------------------------
  server.tool(
    "agit_status",
    "Return repository status: HEAD, current branch, and all branches.",
    { type: "object", properties: {} },
    async () => {
      try {
        return ok(client.status());
      } catch (e) {
        return fail(String(e));
      }
    }
  );

  return server;
}
