// JEG-1012: remote MCP endpoint (Streamable HTTP) for Claude.ai connectors,
// ChatGPT apps and any MCP client. Public, no keys, read-only. It calls the
// get-values function, so every number matches the site (one source of truth).
//
// Deploy: supabase functions deploy mcp --no-verify-jwt
// URL:    https://<project>.supabase.co/functions/v1/mcp

import { handleRpc } from "./rpc.ts";
import type { FetchValues, ValuesResponse } from "./tools.ts";

const VALUES_URL = Deno.env.get("DDF_API_URL") ||
  `${(Deno.env.get("SUPABASE_URL") || "").replace(/\/+$/, "")}/functions/v1/get-values`;

// get-values is slow on a cold start (about 3.7 MB of inputs), so keep each
// league setting's answer for 5 minutes, the same TTL get-values uses.
const CACHE_TTL_MS = 5 * 60 * 1000;
const cache = new Map<string, { at: number; data: ValuesResponse }>();

const fetchValues: FetchValues = async (scoring, teams, superflex) => {
  const key = `${scoring}|${teams}|${superflex}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_TTL_MS) return hit.data;
  const url = new URL(VALUES_URL);
  url.searchParams.set("scoring", scoring);
  url.searchParams.set("teams", String(teams));
  url.searchParams.set("superflex", String(superflex));
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`get-values ${res.status}`);
  const data = await res.json() as ValuesResponse;
  cache.set(key, { at: Date.now(), data });
  return data;
};

// MCP clients are not browsers, but browser-based inspectors send CORS preflights.
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Accept, Mcp-Session-Id, Mcp-Protocol-Version",
  "Access-Control-Max-Age": "86400",
};

const rateBuckets = new Map<string, { count: number; resetAt: number }>();
const RATE_LIMIT = 60;
const RATE_WINDOW_MS = 60_000;

function checkRate(ip: string): boolean {
  const now = Date.now();
  let b = rateBuckets.get(ip);
  if (!b || now >= b.resetAt) {
    b = { count: 0, resetAt: now + RATE_WINDOW_MS };
    rateBuckets.set(ip, b);
  }
  return ++b.count <= RATE_LIMIT;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  // Stateless server: no SSE stream to open and no session to close.
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: { ...cors, Allow: "POST, OPTIONS" } });
  }

  const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
  if (!checkRate(ip)) {
    return Response.json({ jsonrpc: "2.0", id: null, error: { code: -32000, message: "rate limited" } }, { status: 429, headers: cors });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }, { status: 400, headers: cors });
  }

  const batch = Array.isArray(body);
  const responses = (await Promise.all((batch ? body : [body]).map((m) => handleRpc(m, fetchValues))))
    .filter((r) => r !== null);
  if (!responses.length) return new Response(null, { status: 202, headers: cors });
  return Response.json(batch ? responses : responses[0], { headers: cors });
});
