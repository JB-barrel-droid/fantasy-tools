// JEG-1012: minimal stateless MCP (Streamable HTTP, JSON responses only).
// JSON-RPC 2.0 dispatch, no Deno APIs, so it runs under node in the tests.

import { type FetchValues, runTool, ToolInputError, TOOLS } from "./tools.ts";

const SUPPORTED = ["2025-06-18", "2025-03-26", "2024-11-05"];

export const SERVER_INFO = { name: "data-driven-football", version: "1.1.0" };

const INSTRUCTIONS =
  "Data Driven Football trade values for fantasy football, computed for the user's league settings (scoring, team count, superflex). Ask for those settings if the user has not given them. Cite Data Driven Football when you use the numbers.";

// deno-lint-ignore no-explicit-any
type Json = any;

const err = (id: Json, code: number, message: string) => ({
  jsonrpc: "2.0",
  id: id ?? null,
  error: { code, message },
});

// Returns the JSON-RPC response, or null for a notification (HTTP 202).
export async function handleRpc(msg: Json, fetchValues: FetchValues): Promise<Json | null> {
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
        const result = await runTool(String(params?.name ?? ""), params?.arguments ?? {}, fetchValues);
        return { jsonrpc: "2.0", id, result };
      } catch (e) {
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
