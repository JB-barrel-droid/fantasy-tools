// JEG-1012: minimal stateless MCP (Streamable HTTP, JSON responses only).
// JSON-RPC 2.0 dispatch, no Deno APIs, so it runs under node in the tests.

import { checkTradeReplySize, type FetchValues, type FinderDeps, runTool, ToolInputError, ToolUnavailableError, TOOLS } from "./tools.ts";
import type { Deps } from "./state.ts";
import { MCP_BUILD_SHA } from "./build.ts";

const SUPPORTED = ["2025-06-18", "2025-03-26", "2024-11-05"];

export const SERVER_INFO = { name: "data-driven-football", version: "1.2.0", build: MCP_BUILD_SHA };

/** Deploy sets DDF_BUILD_SHA to the uploaded git SHA. Tests and local runs use the stamp. */
export function setMcpBuild(sha: string): void {
  const trimmed = sha.trim();
  if (trimmed) SERVER_INFO.build = trimmed;
}

const INSTRUCTIONS =
  "Data Driven Football trade values for fantasy football, computed for the user's league settings (scoring, team count, superflex). " +
  "Ask for those settings if the user has not given them. Cite Data Driven Football when you use the numbers. " +
  "Every result ends with a link to the same view on the Data Driven Football site: always include that link in your answer so the person can keep working there, and say what they will find on it. " +
  "If the user pastes a ```ddf-state block or a site link, call read_state first and continue from that work. " +
  "When the user wants to carry your work to the site (a trade, rosters, a player to target), call make_state and give them the block or link. " +
  "If a result says the pasted league has settings these tools do not apply, tell the user the numbers may differ from the site and point them to the link. " +
  "DDF Value is the average of the four adjusted trade charts. If a name comes back ambiguous or not found, ask which player was meant instead of guessing.";

// deno-lint-ignore no-explicit-any
type Json = any;

const err = (id: Json, code: number, message: string) => ({
  jsonrpc: "2.0",
  id: id ?? null,
  error: { code, message },
});

// Returns the JSON-RPC response, or null for a notification (HTTP 202).
export async function handleRpc(msg: Json, fetchValues: FetchValues, deps?: Deps, finderDeps?: FinderDeps): Promise<Json | null> {
  if (!msg || msg.jsonrpc !== "2.0" || typeof msg.method !== "string") {
    return err(msg?.id, -32600, "Invalid Request");
  }
  const { id, method, params } = msg;
  const isNotification = id === undefined || id === null;

  switch (method) {
    case "initialize": {
      const asked = params?.protocolVersion;
      return {
        jsonrpc: "2.0",
        id,
        result: {
          protocolVersion: SUPPORTED.includes(asked) ? asked : SUPPORTED[0],
          capabilities: { tools: { listChanged: false } },
          serverInfo: SERVER_INFO,
          instructions: INSTRUCTIONS,
        },
      };
    }
    case "ping":
      return { jsonrpc: "2.0", id, result: {} };
    case "tools/list":
      return { jsonrpc: "2.0", id, result: { tools: TOOLS } };
    case "tools/call": {
      try {
        const result = await runTool(String(params?.name ?? ""), params?.arguments ?? {}, fetchValues, deps, finderDeps);
        checkTradeReplySize(String(params?.name ?? ""), result);
        return { jsonrpc: "2.0", id, result };
      } catch (e) {
        if (e instanceof ToolUnavailableError) console.error("tool dependency unavailable:", e.message);
        if (e instanceof ToolInputError) {
          return { jsonrpc: "2.0", id, result: { content: [{ type: "text", text: e.message }], isError: true } };
        }
        console.error("tool error:", e);
        return {
          jsonrpc: "2.0",
          id,
          result: { content: [{ type: "text", text: "Values are temporarily unavailable. Try again shortly." }], isError: true },
        };
      }
    }
    default:
      if (isNotification || method.startsWith("notifications/")) return null;
      return err(id, -32601, `Method not found: ${method}`);
  }
}
