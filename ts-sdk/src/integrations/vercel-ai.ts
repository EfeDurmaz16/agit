/**
 * Vercel AI SDK middleware for agit.
 *
 * Automatically commits agent state after every LLM generation, giving you a
 * full audit trail of the conversation with zero extra boilerplate.
 *
 * @example
 * ```ts
 * import { AgitClient } from "@agit/sdk";
 * import { createAgitMiddleware } from "@agit/sdk/integrations/vercel-ai";
 * import { wrapLanguageModel } from "ai";
 *
 * const client = await AgitClient.open("/path/to/repo");
 * const middleware = createAgitMiddleware(client);
 *
 * const model = wrapLanguageModel({ model: openai("gpt-4o"), middleware });
 * ```
 */

import { AgitClient } from "../client.js";
import { ActionType } from "../types.js";

// ---------------------------------------------------------------------------
// Vercel AI SDK type stubs (only the subset we need)
// ---------------------------------------------------------------------------

/** Partial shape of a Vercel AI LanguageModelV1CallOptions. */
interface LanguageModelCallOptions {
  prompt?: unknown;
  system?: string;
  messages?: unknown[];
  temperature?: number;
  maxTokens?: number;
  [key: string]: unknown;
}

/** Partial shape of a Vercel AI LanguageModelV1StreamPart result. */
interface GenerateResult {
  text?: string;
  usage?: {
    promptTokens?: number;
    completionTokens?: number;
    totalTokens?: number;
  };
  finishReason?: string;
  [key: string]: unknown;
}

/** Minimal LanguageModelMiddleware interface from the Vercel AI SDK. */
export interface LanguageModelMiddleware {
  wrapGenerate?: (options: {
    doGenerate: () => Promise<GenerateResult>;
    params: LanguageModelCallOptions;
  }) => Promise<GenerateResult>;
  wrapStream?: (options: {
    doStream: () => Promise<unknown>;
    params: LanguageModelCallOptions;
  }) => Promise<unknown>;
}

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------

export interface AgitMiddlewareOptions {
  /**
   * Custom function to extract agent memory from generation parameters.
   * Defaults to capturing the full `params` object.
   */
  extractMemory?: (params: LanguageModelCallOptions) => unknown;

  /**
   * Custom function to extract world state from generation parameters.
   * Defaults to `undefined` (empty object stored).
   */
  extractWorldState?: (params: LanguageModelCallOptions) => unknown;

  /**
   * Custom function to build the commit message.
   * Receives the params and result.
   */
  buildMessage?: (
    params: LanguageModelCallOptions,
    result: GenerateResult
  ) => string;

  /**
   * Whether to also wrap streaming calls (wrapStream).
   * Defaults to `false` because streaming results may be partial.
   */
  wrapStream?: boolean;

  /**
   * When set, commits are only created if `shouldCommit` returns `true`.
   */
  shouldCommit?: (
    params: LanguageModelCallOptions,
    result: GenerateResult
  ) => boolean;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Create a Vercel AI SDK `LanguageModelMiddleware` that auto-commits agent
 * state after every generation.
 */
export function createAgitMiddleware(
  client: AgitClient,
  options: AgitMiddlewareOptions = {}
): LanguageModelMiddleware {
  const {
    extractMemory = (params) => ({
      messages: params.messages,
      system: params.system,
      prompt: params.prompt,
    }),
    extractWorldState = () => ({}),
    buildMessage = (_params, result) => {
      const tokens = result.usage?.totalTokens;
      const reason = result.finishReason ?? "unknown";
      return `llm_response: finish=${reason}${tokens !== undefined ? `, tokens=${tokens}` : ""}`;
    },
    shouldCommit = () => true,
  } = options;

  const wrapGenerate: LanguageModelMiddleware["wrapGenerate"] = async ({
    doGenerate,
    params,
  }) => {
    const result = await doGenerate();

    if (shouldCommit(params, result)) {
      try {
        const memory = extractMemory(params);
        const worldState = extractWorldState(params);
        const message = buildMessage(params, result);
        const totalTokens = result.usage?.totalTokens ?? 0;
        // Rough cost proxy: 1 unit per token (override via extractWorldState).
        const cost = totalTokens * 0.000001;

        const metadata: Record<string, unknown> = {};
        if (result.usage) metadata["usage"] = result.usage;
        if (result.finishReason) metadata["finish_reason"] = result.finishReason;
        if (result.text) metadata["text_preview"] = result.text.slice(0, 200);

        await client.commit({
          memory,
          world_state: worldState,
          message,
          action_type: ActionType.LlmResponse,
          cost,
          metadata,
        });
      } catch (err) {
        // Commit errors must never break the generation pipeline.
        console.warn("[agit] commit failed:", err);
      }
    }

    return result;
  };

  const middleware: LanguageModelMiddleware = { wrapGenerate };

  if (options.wrapStream) {
    middleware.wrapStream = async ({ doStream, params: _params }) => {
      // For streaming we simply pass through – committing a partial stream is
      // not generally meaningful. Users can call client.commit() manually once
      // the stream completes.
      return doStream();
    };
  }

  return middleware;
}
