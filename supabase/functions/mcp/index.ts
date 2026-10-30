// JEG-1012: remote MCP endpoint (Streamable HTTP) for Claude.ai connectors,
// ChatGPT apps and any MCP client. Public, no keys, read-only. It calls the
// get-values function, so every number matches the site (one source of truth).
//
// Deploy: supabase functions deploy mcp --no-verify-jwt
// URL:    https://<project>.supabase.co/functions/v1/mcp

import { handleRpc, setMcpBuild } from "./rpc.ts";
import { MCP_BUILD_SHA } from "./build.ts";
import type { Codec, Deps } from "./state.ts";
import { type ChartValuesResponse, type FetchValues, type FetchValuesWithCharts, type ValuesResponse } from "./tools.ts";
import { evalFinder, type Finder } from "./find-trades.ts";
import type { FinderDeps } from "./tools.ts";
import { type AnalysisResponse, evalPageModule, type FetchAnalysis, PAGE_MODULE_FILES, type PageModules } from "./analyses.ts";
import type { ValueContextText } from "./value-context.ts";
import { readValuesResponse, requestValuesWith } from "./values-client.ts";

setMcpBuild(Deno.env.get("DDF_BUILD_SHA") || MCP_BUILD_SHA);

// Same site origin as get-values; DDF_SITE_ORIGIN overrides it once the custom domain is live.
const SITE_ORIGIN = (Deno.env.get("DDF_SITE_ORIGIN") ||
  "https://jb-barrel-droid.github.io/fantasy-tools").replace(/\/+$/, "");

const VALUES_URL = Deno.env.get("DDF_API_URL") ||
  `${(Deno.env.get("SUPABASE_URL") || "").replace(/\/+$/, "")}/functions/v1/get-values`;

// get-values is slow on a cold start (about 3.7 MB of inputs), so keep each
// league setting's answer for 5 minutes, the same TTL get-values uses.
const CACHE_TTL_MS = 5 * 60 * 1000;
const cache = new Map<string, { at: number; data: ValuesResponse }>();

const CACHE_MAX = 12;

// JEG-1179: a week with no published sources comes back from get-values as a 400 with
// code "week_unavailable" and a message naming the weeks there are; the tool shows that message.
// JEG-1343: a refused link value context (400, 413, 422, 503 with its code) is the tool's message too (values-client.ts).
const readValues = readValuesResponse;
const requestValues = (
  scoring: string, teams: number, superflex: number, league: Record<string, unknown> | undefined,
  week: number | null | undefined, include: string | null, context: ValueContextText | null | undefined,
) => requestValuesWith(fetch, VALUES_URL, scoring, teams, superflex, league, week, include, context);

const contextKey = (context: ValueContextText | null | undefined) =>
  context ? `|b:${context.basis ?? ""}|o:${context.ov ?? ""}` : "";

const fetchValues: FetchValues = async (scoring, teams, superflex, league, week, context) => {
  const key = `${scoring}|${teams}|${superflex}|${league ? JSON.stringify(league) : ""}|${week ?? ""}${contextKey(context)}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_TTL_MS) return hit.data;
  const res = await requestValues(scoring, teams, superflex, league, week, null, context);
  const data = await readValues(res) as ValuesResponse;
  if (cache.size >= CACHE_MAX) cache.delete(cache.keys().next().value as string);
  cache.set(key, { at: Date.now(), data });
  return data;
};

// The DDF state codec is the site's own app/v2/ddf-state.js, loaded the way get-values loads
// value-model.js, so the page and these tools read and write one format. If it cannot be loaded the
// tools still answer from their plain arguments and say the pasted state was not read.
let codecCache: { at: number; codec: Codec | null } | null = null;
async function loadCodec(): Promise<Codec | null> {
  if (codecCache && Date.now() - codecCache.at < CACHE_TTL_MS) return codecCache.codec;
  let codec: Codec | null = null;
  try {
    const res = await fetch(`${SITE_ORIGIN}/v2/ddf-state.js`);
    if (res.ok) {
      // deno-lint-ignore no-eval
      const evalFn = eval;
      evalFn(await res.text());
      // deno-lint-ignore no-explicit-any
      const c = (globalThis as any).DDFState;
      if (c && typeof c.decodeBlock === "function" && typeof c.encodeQuery === "function") codec = c as Codec;
    } else {
      console.error(`ddf-state load failed: ${res.status} from ${SITE_ORIGIN}/v2/ddf-state.js`);
    }
  } catch (e) {
    console.error("ddf-state load failed:", e);
  }
  // A failure is remembered for one minute, not five, so a fixed deploy is picked up quickly.
  codecCache = { at: codec ? Date.now() : Date.now() - CACHE_TTL_MS + 60_000, codec };
  return codec;
}

// Chart-enriched fetch: get-values with include=charts for the finder.
const chartCache = new Map<string, { at: number; data: ChartValuesResponse }>();
const fetchCharts: FetchValuesWithCharts = async (scoring, teams, superflex, league, week, context) => {
  const key = `${scoring}|${teams}|${superflex}|${league ? JSON.stringify(league) : ""}|${week ?? ""}${contextKey(context)}`;
  const hit = chartCache.get(key);
  if (hit && Date.now() - hit.at < CACHE_TTL_MS) return hit.data;
  const res = await requestValues(scoring, teams, superflex, league, week, "charts", context);
  const data = await readValues(res) as ChartValuesResponse;
  chartCache.set(key, { at: Date.now(), data });
  return data;
};

// JEG-1029: get-values with the analysis blocks (include=series, prior, audit) for risers_fallers,
// compare_trade by_source and audit_values. Not cached here: get-values caches each answer itself.
const fetchAnalysis: FetchAnalysis = async (scoring, teams, superflex, league, week, includes, context) => {
  const res = await requestValues(scoring, teams, superflex, league, week, includes.join(","), context);
  return await readValues(res) as AnalysisResponse;
};

// JEG-1029: the page modules the analyses read (movers.js, trade.js, audit-pie.js, audit-source.js),
// loaded from the published site like finder.js. A module that cannot be loaded makes its tool say so.
let modulesCache: { at: number; modules: PageModules } | null = null;
async function loadPageModules(): Promise<PageModules> {
  if (modulesCache && Date.now() - modulesCache.at < CACHE_TTL_MS) return modulesCache.modules;
  const entries = await Promise.all(Object.entries(PAGE_MODULE_FILES).map(async ([name, meta]) => {
    try {
      const res = await fetch(`${SITE_ORIGIN}/${meta.file}`);
      if (res.ok) return [name, evalPageModule(await res.text(), name as keyof PageModules)];
      console.error(`${meta.file} load failed: ${res.status}`);
    } catch (e) {
      console.error(`${meta.file} load failed:`, e);
    }
    return [name, null];
  }));
  const modules = Object.fromEntries(entries) as PageModules;
  const complete = Object.values(modules).every(Boolean);
  // As for the finder: a failure is retried after one minute, not five.
  modulesCache = { at: complete ? Date.now() : Date.now() - CACHE_TTL_MS + 60_000, modules };
  return modules;
}

// The finder is the site's app/v2/finder.js, loaded like the codec. It exports
// findTrades and the constants the search uses. If it cannot be loaded, the
// find_trades tool says it is unavailable.
let finderCache: { at: number; finder: Finder | null } | null = null;
async function loadFinder(): Promise<Finder | null> {
  if (finderCache && Date.now() - finderCache.at < CACHE_TTL_MS) return finderCache.finder;
  let finder: Finder | null = null;
  try {
    const res = await fetch(`${SITE_ORIGIN}/v2/finder.js`);
    if (res.ok) {
      // deno-lint-ignore no-eval
      const evalFn = eval;
      finder = evalFinder(await res.text(), evalFn);
    } else {
      console.error(`finder.js load failed: ${res.status} from ${SITE_ORIGIN}/v2/finder.js`);
    }
  } catch (e) {
    console.error("finder.js load failed:", e);
  }
  finderCache = { at: finder ? Date.now() : Date.now() - CACHE_TTL_MS + 60_000, finder };
  return finder;
}

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

  const deps: Deps = { codec: await loadCodec(), siteOrigin: SITE_ORIGIN };
  const fDeps: FinderDeps = { finder: await loadFinder(), fetchCharts, analysis: { fetchAnalysis, modules: await loadPageModules() } };
  const batch = Array.isArray(body);
  const responses = (await Promise.all((batch ? body : [body]).map((m) => handleRpc(m, fetchValues, deps, fDeps))))
    .filter((r) => r !== null);
  if (!responses.length) return new Response(null, { status: 202, headers: cors });
  return Response.json(batch ? responses : responses[0], { headers: cors });
});
