// JEG-1049: runs tools/edge_drift_check.mjs against a local fake of the deployed
// mcp and get-values endpoints, so it needs no network. Run by tests/test_edge_drift_check.py.
import assert from "node:assert/strict";
import http from "node:http";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { TOOLS } from "../../supabase/functions/mcp/tools.ts";

const SCRIPT = fileURLToPath(new URL("../../tools/edge_drift_check.mjs", import.meta.url));
const mainNames = TOOLS.map((t) => t.name);
const chartPlayer = { player_key: 1, name: "A", value: 1, chart_values: { x: 1 }, ddf_value_charts: 1, ddf_value_projections: 1 };

function fake({ tools, players }) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        res.setHeader("Content-Type", "application/json");
        if (req.url.startsWith("/mcp")) {
          assert.equal(JSON.parse(body).method, "tools/list");
          res.end(JSON.stringify({ jsonrpc: "2.0", id: 1, result: { tools: tools.map((name) => ({ name })) } }));
        } else {
          assert.match(req.url, /include=charts/);
          res.end(JSON.stringify({ players }));
        }
      });
    }).listen(0, "127.0.0.1", () => resolve(srv));
  });
}

function runScript(port) {
  return new Promise((resolve) => {
    const p = spawn("node", ["--experimental-strip-types", "--no-warnings", SCRIPT], {
      env: { ...process.env, EDGE_MCP_URL: `http://127.0.0.1:${port}/mcp`, EDGE_GET_VALUES_URL: `http://127.0.0.1:${port}/get-values` },
    });
    let out = "";
    p.stdout.on("data", (c) => (out += c));
    p.stderr.on("data", (c) => (out += c));
    p.on("close", (code) => resolve({ code, out }));
  });
}

async function scenario(opts) {
  const srv = await fake(opts);
  try {
    return await runScript(srv.address().port);
  } finally {
    srv.close();
  }
}

let r = await scenario({ tools: mainNames, players: [chartPlayer] });
assert.equal(r.code, 0, r.out);
assert.match(r.out, /^OK:/);

r = await scenario({ tools: [...mainNames.slice(1), "ghost_tool"], players: [chartPlayer] });
assert.notEqual(r.code, 0);
assert.match(r.out, new RegExp(`not deployed: ${mainNames[0]}\\b`));
assert.match(r.out, /not on main: ghost_tool/);

r = await scenario({ tools: mainNames, players: [{ player_key: 1, name: "A", value: 1 }] });
assert.notEqual(r.code, 0);
assert.match(r.out, /get-values include=charts/);

r = await runScript(1); // nothing listens on port 1
assert.equal(r.code, 2);
assert.match(r.out, /cannot reach/);
assert.doesNotMatch(r.out, /\n\s+at /);
console.log("ok");
