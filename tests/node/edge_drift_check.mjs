// JEG-1049 / JEG-1256: runs tools/edge_drift_check.mjs against a local fake of the
// deployed mcp and get-values endpoints, so it needs no network. Run by
// tests/test_edge_drift_check.py. Each case pins the exit code: 0 in sync, 1 drift,
// 2 could not compare. EDGE_DRIFT_SCRIPT points it at another copy of the checker
// (used once to show which cases the #1003 version got wrong; see the JEG-1256 log).
import assert from "node:assert/strict";
import http from "node:http";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { TOOLS } from "../../supabase/functions/mcp/tools.ts";

const SCRIPT = process.env.EDGE_DRIFT_SCRIPT ||
  fileURLToPath(new URL("../../tools/edge_drift_check.mjs", import.meta.url));
const mainNames = TOOLS.map((t) => t.name);

// A row shaped like main's get-values include=charts (supabase/functions/get-values/index.ts).
const row = (over = {}) => ({
  player_key: 1, name: "A", pos: "WR", value: 50.5, tier: 1,
  chart_values: { fantasycalc: 50, ktc: null }, chart_indexed: { fantasycalc: 48, ktc: null },
  ddf_value_charts: 50.5, ddf_value_projections: 49.1, ...over,
});
const without = (r, ...keys) => Object.fromEntries(Object.entries(r).filter(([k]) => !keys.includes(k)));

const json = (body, status = 200) => ({ status, type: "application/json", body: JSON.stringify(body) });
const toolsReply = (names) => json({ jsonrpc: "2.0", id: 1, result: { tools: names.map((name) => ({ name })) } });
const sse = (payload) => ({ status: 200, type: "text/event-stream", body: `event: message\ndata: ${JSON.stringify(payload)}\n\n` });
const valuesReply = (players) => json({ players, bench_share: { QB: 0.2, overall: 0.3 } });
const OK_MCP = toolsReply(mainNames);
const OK_VALUES = valuesReply([row(), row({ player_key: 2, name: "B" })]);

function fake({ mcp, values }) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        let reply;
        if (req.url.startsWith("/mcp")) {
          assert.equal(JSON.parse(body).method, "tools/list");
          reply = mcp;
        } else {
          assert.match(req.url, /include=charts/);
          reply = values;
        }
        res.writeHead(reply.status, { "Content-Type": reply.type });
        res.end(reply.body);
      });
    }).listen(0, "127.0.0.1", () => resolve(srv));
  });
}

function runScript(mcpUrl, valuesUrl) {
  return new Promise((resolve) => {
    const p = spawn("node", ["--experimental-strip-types", "--no-warnings", SCRIPT], {
      env: { ...process.env, EDGE_MCP_URL: mcpUrl, EDGE_GET_VALUES_URL: valuesUrl },
    });
    let out = "";
    p.stdout.on("data", (c) => (out += c));
    p.stderr.on("data", (c) => (out += c));
    p.on("close", (code) => resolve({ code, out }));
  });
}

async function scenario({ mcp = OK_MCP, values = OK_VALUES, deadMcp = false, deadValues = false }) {
  const srv = await fake({ mcp, values });
  const base = `http://127.0.0.1:${srv.address().port}`;
  const dead = "http://127.0.0.1:1"; // nothing listens on port 1
  try {
    return await runScript(deadMcp ? `${dead}/mcp` : `${base}/mcp`, deadValues ? `${dead}/get-values` : `${base}/get-values`);
  } finally {
    srv.close();
  }
}

const CASES = [
  // In sync.
  { name: "positive", code: 0, out: /^OK:/ },
  { name: "positive, mcp answers SSE", mcp: sse({ jsonrpc: "2.0", id: 1, result: { tools: mainNames.map((name) => ({ name })) } }), code: 0, out: /^OK:/ },
  { name: "legitimate zero is numeric, not unavailable", values: valuesReply([row({ value: 0, ddf_value_charts: 0, ddf_value_projections: 0, chart_values: { fantasycalc: 0 } })]), code: 0, out: /^OK:/ },
  { name: "null ddf_value_* on some players is allowed (main types it number | null)", values: valuesReply([row({ ddf_value_charts: null, ddf_value_projections: null }), row({ player_key: 2 })]), code: 0, out: /^OK:/ },
  { name: "no bench_share is not checked (policy held, JEG-1256)", values: json({ players: [row()] }), code: 0, out: /^OK:/ },

  // Drift.
  { name: "missing and extra tools", mcp: toolsReply([...mainNames.slice(1), "ghost_tool"]), code: 1,
    out: new RegExp(`not deployed: ${mainNames[0]}\\b[\\s\\S]*not on main: ghost_tool`) },
  { name: "every player lacks the chart fields (older get-values)", values: valuesReply([without(row(), ...["chart_values", "chart_indexed", "ddf_value_charts", "ddf_value_projections"])]),
    code: 1, out: /no player has chart_values[\s\S]*no player has ddf_value_charts[\s\S]*no player has ddf_value_projections/ },
  { name: "every player lacks one required field", values: valuesReply([without(row(), "ddf_value_projections"), without(row({ player_key: 2 }), "ddf_value_projections")]),
    code: 1, out: /no player has ddf_value_projections/ },
  { name: "drift on mcp still wins when get-values is unavailable", mcp: toolsReply(mainNames.slice(1)), values: valuesReply([]),
    code: 1, out: /not deployed[\s\S]*Also could not compare:[\s\S]*players list is empty/ },

  // Could not compare (exit 2).
  { name: "empty players", values: valuesReply([]), code: 2, out: /could not compare[\s\S]*players list is empty/ },
  { name: "ddf_value_* null on every player", values: valuesReply([row({ ddf_value_charts: null }), row({ player_key: 2, ddf_value_charts: null })]),
    code: 2, out: /ddf_value_charts is null on all 2 players/ },
  { name: "non-numeric ddf_value_*", values: valuesReply([row({ ddf_value_projections: "49.1" })]), code: 2, out: /non-numeric ddf_value_projections/ },
  { name: "missing value", values: valuesReply([without(row(), "value")]), code: 2, out: /missing or non-numeric value/ },
  { name: "non-numeric value", values: valuesReply([row({ value: "NaN" })]), code: 2, out: /missing or non-numeric value/ },
  { name: "null chart_values", values: valuesReply([row({ chart_values: null })]), code: 2, out: /chart_values that is not an object/ },
  { name: "chart_values with a non-numeric entry", values: valuesReply([row({ chart_values: { fantasycalc: "50" } })]), code: 2, out: /chart_values that is not an object/ },
  { name: "chart_values all null", values: valuesReply([row({ chart_values: { fantasycalc: null, ktc: null } })]), code: 2, out: /chart_values has no numeric value/ },
  { name: "some players lack a required field", values: valuesReply([row(), without(row({ player_key: 2 }), "ddf_value_charts")]),
    code: 2, out: /1 of 2 players lack ddf_value_charts while the rest have it/ },
  { name: "a player row is null", values: valuesReply([row(), null]), code: 2, out: /1 of 2 players are not objects/ },
  { name: "players is not a list", values: json({ players: { a: 1 } }), code: 2, out: /no players list/ },
  { name: "get-values JSON null", values: json(null), code: 2, out: /no players list/ },
  { name: "get-values not JSON", values: { status: 200, type: "text/html", body: "<html>gateway</html>" }, code: 2, out: /reply is not JSON/ },
  { name: "get-values 403", values: json({ msg: "forbidden" }, 403), code: 2, out: /get-values[\s\S]*HTTP 403/ },
  { name: "mcp 403", mcp: json({ msg: "forbidden" }, 403), code: 2, out: /mcp tools\/list[\s\S]*HTTP 403/ },
  { name: "mcp JSON-RPC error", mcp: json({ jsonrpc: "2.0", id: 1, error: { code: -32601, message: "no" } }), code: 2, out: /JSON-RPC error/ },
  { name: "mcp lists no tools", mcp: toolsReply([]), code: 2, out: /lists no tools/ },
  { name: "mcp tool without a name", mcp: json({ jsonrpc: "2.0", id: 1, result: { tools: [...mainNames.map((name) => ({ name })), { title: "x" }] } }),
    code: 2, out: /1 of \d+ tools have no name/ },
  { name: "mcp SSE with no data line", mcp: { status: 200, type: "text/event-stream", body: "event: ping\n\n" }, code: 2, out: /reply is not JSON/ },
  { name: "mcp unreachable", deadMcp: true, code: 2, out: /mcp tools\/list: cannot reach/ },
  { name: "both unreachable", deadMcp: true, deadValues: true, code: 2, out: /cannot reach[\s\S]*cannot reach/ },
];

const failures = [];
for (const c of CASES) {
  const r = await scenario(c);
  const ok = r.code === c.code && c.out.test(r.out) && !/\n\s+at /.test(r.out) &&
    (c.code !== 0 || !/EDGE (DRIFT|CHECK ERROR)/.test(r.out));
  console.log(`${ok ? "pass" : "FAIL"} [exit ${r.code}, want ${c.code}] ${c.name}`);
  if (!ok) failures.push(`${c.name}: exit ${r.code} (want ${c.code})\n${r.out}`);
}
assert.equal(failures.length, 0, `\n${failures.join("\n\n")}`);
console.log("ok");
