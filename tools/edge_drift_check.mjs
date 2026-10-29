// JEG-1049: drift check for the manually deployed Supabase edge functions.
// Compares the deployed `mcp` tools/list with the TOOLS declared on main
// (supabase/functions/mcp/tools.ts) and checks that deployed `get-values`
// answers include=charts with the shape the find_trades finder reads.
// Read-only, no secrets, never deploys. Exits 0 when in sync, 1 on drift,
// 2 when an endpoint cannot be reached or answers something unreadable.
//
// Run: node --experimental-strip-types --no-warnings tools/edge_drift_check.mjs
// Env: EDGE_MCP_URL, EDGE_GET_VALUES_URL override the production endpoints.
import { fileURLToPath } from "node:url";

const BASE = "https://iskiybsimubiujwuchsl.supabase.co/functions/v1";
const MCP_URL = process.env.EDGE_MCP_URL || `${BASE}/mcp`;
const VALUES_URL = process.env.EDGE_GET_VALUES_URL || `${BASE}/get-values`;
const TIMEOUT_MS = 60_000; // get-values is slow on a cold start

class Unreachable extends Error {}

async function request(label, url, init) {
  let res;
  try {
    res = await fetch(url, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS) });
  } catch (e) {
    throw new Unreachable(`${label}: cannot reach ${url} (${e.cause?.code || e.message})`);
  }
  const text = await res.text();
  if (!res.ok) throw new Unreachable(`${label}: ${url} answered HTTP ${res.status}: ${text.slice(0, 200)}`);
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
    throw new Unreachable(`${label}: reply is not JSON: ${text.slice(0, 200)}`);
  }
}

async function deployedTools() {
  const text = await request("mcp tools/list", MCP_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list", params: {} }),
  });
  const reply = parseReply("mcp tools/list", text);
  if (!Array.isArray(reply?.result?.tools)) {
    throw new Unreachable(`mcp tools/list: no result.tools in reply: ${JSON.stringify(reply).slice(0, 200)}`);
  }
  return reply.result.tools.map((t) => t.name);
}

async function valuesProblems() {
  const url = new URL(VALUES_URL);
  url.searchParams.set("scoring", "ppr");
  url.searchParams.set("teams", "12");
  url.searchParams.set("superflex", "0");
  url.searchParams.set("include", "charts");
  const text = await request("get-values", url, { headers: { Accept: "application/json" } });
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Unreachable(`get-values: reply is not JSON: ${text.slice(0, 200)}`);
  }
  if (!Array.isArray(data?.players) || data.players.length === 0) {
    return ["get-values include=charts: no players in reply"];
  }
  const bad = data.players.filter((p) =>
    !p.chart_values || typeof p.chart_values !== "object" ||
    !("ddf_value_charts" in p) || !("ddf_value_projections" in p));
  return bad.length
    ? [`get-values include=charts: ${bad.length} of ${data.players.length} players lack chart_values / ddf_value_charts / ddf_value_projections (deployed get-values is older than main)`]
    : [];
}

async function main() {
  const { TOOLS } = await import(fileURLToPath(new URL("../supabase/functions/mcp/tools.ts", import.meta.url)));
  const onMain = TOOLS.map((t) => t.name);
  const [deployed, valuesIssues] = await Promise.all([deployedTools(), valuesProblems()]);
  const missing = onMain.filter((n) => !deployed.includes(n));
  const extra = deployed.filter((n) => !onMain.includes(n));
  const problems = [];
  if (missing.length) problems.push(`mcp tools on main but not deployed: ${missing.join(", ")}`);
  if (extra.length) problems.push(`mcp tools deployed but not on main: ${extra.join(", ")}`);
  problems.push(...valuesIssues);
  if (problems.length) {
    console.error(`EDGE DRIFT: deployed functions are out of step with main (deploys are manual):\n- ${problems.join("\n- ")}`);
    console.error(`mcp on main: ${onMain.length} tools; deployed: ${deployed.length} tools.`);
    process.exit(1);
  }
  console.log(`OK: deployed mcp lists the same ${onMain.length} tools as main; get-values include=charts has the chart fields.`);
}

main().catch((e) => {
  if (e instanceof Unreachable) {
    console.error(`EDGE CHECK ERROR (could not compare): ${e.message}`);
    process.exit(2);
  }
  throw e;
});
