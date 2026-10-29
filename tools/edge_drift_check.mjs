// JEG-1049: drift check for the manually deployed Supabase edge functions.
// Compares the deployed `mcp` tools/list with the TOOLS declared on main
// (supabase/functions/mcp/tools.ts) and checks that deployed `get-values`
// answers include=charts with the shape the find_trades finder reads.
// Read-only, no secrets, never deploys.
//
// Exit codes (JEG-1256):
//   0  in sync: both sides were read and match main.
//   1  drift: a side was read and differs from main (tool names, or every player
//      lacks a chart field main returns). Proven drift wins over an unavailable side.
//   2  could not compare: an endpoint was unreachable, answered non-2xx or something
//      unreadable, or its evidence was empty, inconsistent or non-numeric. Never
//      reported as healthy, never reported as drift.
//
// Run: node --experimental-strip-types --no-warnings tools/edge_drift_check.mjs
// Env: EDGE_MCP_URL, EDGE_GET_VALUES_URL override the production endpoints.
import { fileURLToPath } from "node:url";

const BASE = "https://iskiybsimubiujwuchsl.supabase.co/functions/v1";
const MCP_URL = process.env.EDGE_MCP_URL || `${BASE}/mcp`;
const VALUES_URL = process.env.EDGE_GET_VALUES_URL || `${BASE}/get-values`;
const TIMEOUT_MS = 60_000; // get-values is slow on a cold start

// Fields main's get-values adds under include=charts (supabase/functions/get-values/index.ts).
// All three are on every row, so a deploy either returns them on every player or on none.
const CHART_FIELDS = ["chart_values", "ddf_value_charts", "ddf_value_projections"];
// Main types these as number | null (mcp/tools.ts); null on one player is legitimate.
const NULLABLE_NUMBERS = ["ddf_value_charts", "ddf_value_projections"];
// Fields every get-values build returns as numbers (rows without a finite value are skipped).
const REQUIRED_NUMBERS = ["player_key", "value"];

class Unavailable extends Error {}

const isNumber = (v) => typeof v === "number" && Number.isFinite(v);
const isPlainObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

async function request(label, url, init) {
  let res;
  try {
    res = await fetch(url, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS) });
  } catch (e) {
    throw new Unavailable(`${label}: cannot reach ${url} (${e.cause?.code || e.message})`);
  }
  let text;
  try {
    text = await res.text();
  } catch (e) {
    throw new Unavailable(`${label}: ${url} reply was cut off (${e.cause?.code || e.message})`);
  }
  if (!res.ok) throw new Unavailable(`${label}: ${url} answered HTTP ${res.status}: ${text.slice(0, 200)}`);
  return text;
}

// The mcp function is stateless (no initialize needed) and answers plain JSON, but a
// Streamable HTTP server may legally answer with SSE, so accept `data:` lines too.
function parseReply(label, text) {
  const body = text.trimStart().startsWith("{")
    ? text
    : text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("");
  try {
    return JSON.parse(body);
  } catch {
    throw new Unavailable(`${label}: reply is not JSON: ${text.slice(0, 200)}`);
  }
}

async function deployedTools() {
  const text = await request("mcp tools/list", MCP_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list", params: {} }),
  });
  const reply = parseReply("mcp tools/list", text);
  if (reply?.error) {
    throw new Unavailable(`mcp tools/list: JSON-RPC error: ${JSON.stringify(reply.error).slice(0, 200)}`);
  }
  const tools = reply?.result?.tools;
  if (!Array.isArray(tools)) {
    throw new Unavailable(`mcp tools/list: no result.tools in reply: ${JSON.stringify(reply).slice(0, 200)}`);
  }
  if (tools.length === 0) throw new Unavailable("mcp tools/list: reply lists no tools");
  const unnamed = tools.filter((t) => !isPlainObject(t) || typeof t.name !== "string" || t.name === "");
  if (unnamed.length) {
    throw new Unavailable(`mcp tools/list: ${unnamed.length} of ${tools.length} tools have no name`);
  }
  return tools.map((t) => t.name);
}

// Returns drift messages; throws Unavailable when the reply can't serve as evidence.
async function valuesDrift() {
  const url = new URL(VALUES_URL);
  url.searchParams.set("scoring", "ppr");
  url.searchParams.set("teams", "12");
  url.searchParams.set("superflex", "0");
  url.searchParams.set("include", "charts");
  const label = "get-values include=charts";
  const text = await request(label, url, { headers: { Accept: "application/json" } });
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Unavailable(`${label}: reply is not JSON: ${text.slice(0, 200)}`);
  }
  if (!isPlainObject(data) || !Array.isArray(data.players)) {
    throw new Unavailable(`${label}: reply has no players list: ${text.slice(0, 200)}`);
  }
  const players = data.players;
  const n = players.length;
  if (n === 0) throw new Unavailable(`${label}: players list is empty`);
  const notRows = players.filter((p) => !isPlainObject(p)).length;
  if (notRows) throw new Unavailable(`${label}: ${notRows} of ${n} players are not objects`);

  const unreadable = [];
  for (const f of REQUIRED_NUMBERS) {
    const bad = players.filter((p) => !isNumber(p[f])).length;
    if (bad) unreadable.push(`${bad} of ${n} players have a missing or non-numeric ${f}`);
  }

  const drift = [];
  for (const f of CHART_FIELDS) {
    const lacking = players.filter((p) => !(f in p)).length;
    if (lacking === n) {
      drift.push(`${label}: no player has ${f} (deployed get-values is older than main)`);
      continue;
    }
    if (lacking) {
      // Main writes these on every row, so a partial set fits no deploy: unreadable, not drift.
      unreadable.push(`${lacking} of ${n} players lack ${f} while the rest have it`);
      continue;
    }
    if (f === "chart_values") {
      const bad = players.filter((p) => !isPlainObject(p.chart_values) ||
        Object.values(p.chart_values).some((v) => v !== null && !isNumber(v))).length;
      if (bad) unreadable.push(`${bad} of ${n} players have chart_values that is not an object of numbers or nulls`);
      else if (players.every((p) => Object.values(p.chart_values).every((v) => v === null))) {
        unreadable.push(`chart_values has no numeric value on any of ${n} players`);
      }
    } else if (NULLABLE_NUMBERS.includes(f)) {
      const bad = players.filter((p) => p[f] !== null && !isNumber(p[f])).length;
      if (bad) unreadable.push(`${bad} of ${n} players have a non-numeric ${f}`);
      else if (players.every((p) => p[f] === null)) unreadable.push(`${f} is null on all ${n} players`);
    }
  }
  if (unreadable.length) throw new Unavailable(`${label}: ${unreadable.join("; ")}`);
  return drift;
}

async function mainTools() {
  try {
    const { TOOLS } = await import(fileURLToPath(new URL("../supabase/functions/mcp/tools.ts", import.meta.url)));
    return TOOLS.map((t) => t.name);
  } catch (e) {
    throw new Unavailable(`main: cannot read TOOLS from supabase/functions/mcp/tools.ts (${e.message})`);
  }
}

// Any failure while reading a side, expected or not, means that side could not be compared.
const reason = (e) => (e instanceof Unavailable ? e.message : `unexpected error: ${e?.message || e}`);

async function main() {
  const onMain = await mainTools();
  const [tools, values] = await Promise.allSettled([deployedTools(), valuesDrift()]);
  const drift = [];
  const unavailable = [];
  let deployed = null;
  if (tools.status === "fulfilled") {
    deployed = tools.value;
    const missing = onMain.filter((n) => !deployed.includes(n));
    const extra = deployed.filter((n) => !onMain.includes(n));
    if (missing.length) drift.push(`mcp tools on main but not deployed: ${missing.join(", ")}`);
    if (extra.length) drift.push(`mcp tools deployed but not on main: ${extra.join(", ")}`);
  } else {
    unavailable.push(reason(tools.reason));
  }
  if (values.status === "fulfilled") drift.push(...values.value);
  else unavailable.push(reason(values.reason));

  if (drift.length) {
    console.error(`EDGE DRIFT: deployed functions are out of step with main (deploys are manual):\n- ${drift.join("\n- ")}`);
    if (deployed) console.error(`mcp on main: ${onMain.length} tools; deployed: ${deployed.length} tools.`);
    if (unavailable.length) console.error(`Also could not compare:\n- ${unavailable.join("\n- ")}`);
    process.exit(1);
  }
  if (unavailable.length) {
    console.error(`EDGE CHECK ERROR (could not compare): this is not a healthy result and not a drift verdict.\n- ${unavailable.join("\n- ")}`);
    process.exit(2);
  }
  console.log(`OK: deployed mcp lists the same ${onMain.length} tools as main; get-values include=charts has the chart fields.`);
}

main().catch((e) => {
  console.error(`EDGE CHECK ERROR (could not compare): ${reason(e)}`);
  process.exit(2);
});
