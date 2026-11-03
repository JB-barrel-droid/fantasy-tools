// JEG-1412: plain compare_trade uses Compare's band, with and without page dependencies.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { handleRpc } from "../../supabase/functions/mcp/rpc.ts";
import { evalPageModule } from "../../supabase/functions/mcp/analyses.ts";

const T = evalPageModule(readFileSync(new URL("../../app/v2/trade.js", import.meta.url), "utf8"), "trade");
const source = readFileSync(new URL("../../supabase/functions/mcp/tools.ts", import.meta.url), "utf8");
for (const key of ["EVEN_FLOOR", "EVEN_SHARE"]) {
  const definition = source.match(new RegExp(`const ${key} = ([0-9.]+);`));
  assert.ok(definition, `${key} standalone definition missing`);
  assert.equal(Number(definition[1]), T[key], `${key} standalone copy drifted from trade.js`);
}
const fixture = JSON.parse(readFileSync(new URL("../fixtures/connector_even_band.json", import.meta.url), "utf8"));
const call = async (name, args, players, deps) => {
  const response = await handleRpc({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } },
    async (scoring, teams, superflex) => ({
      attribution: "Data Driven Football", as_of: "2026-10-31", setting: { scoring, teams, superflex },
      players, sources_included: ["fantasycalc"], sources_excluded: [],
    }), undefined, deps);
  assert.ok(!response.result.isError, JSON.stringify(response.result));
  return response.result;
};
const makePlayers = (a, b) => [...a, ...b].map((value, i) => ({
  player_key: i + 1, name: `Sentinel ${i + 1}`, pos: "WR", value, tier: "starter",
}));
const rule = /(?:larger|greater) of 1 point (?:or|and) 3% of the average side/;
let checks = 0;
for (const scoring of ["standard", "half_ppr", "ppr"]) {
  for (const withModule of [false, true]) {
    const deps = withModule ? { analysis: { modules: { trade: T } } } : undefined;
    for (const probe of fixture.cases) for (const reverse of [false, true]) {
      const [a, b] = reverse ? [probe.b, probe.a] : [probe.a, probe.b];
      const players = makePlayers(a, b);
      const args = { scoring, side_a: players.slice(0, a.length).map(p => p.name).join(", "),
        side_b: players.slice(a.length).map(p => p.name).join(", ") };
      const result = await call("compare_trade", args, players, deps);
      const got = result.structuredContent;
      assert.equal(got.setting.scoring, scoring, "requested scoring must reach the value fetch");
      const rows = players.map(p => ({ ...p, values: { ddf_value: p.value } }));
      const site = T.tradeVerdict(T.compareTrade(rows.slice(0, a.length), rows.slice(a.length), ["ddf_value"]).rows, "ddf_value");
      const label = `${scoring} module=${withModule} ${probe.label} reverse=${reverse}`;
      assert.equal(site.kind === "even", probe.even, `fixture must match site: ${label}`);
      assert.equal(got.verdict === "roughly even", probe.even, label);
      if (!probe.even) assert.match(got.verdict, site.kind === "win" ? /team A comes out ahead/ : /team B comes out ahead/, label);
      assert.match(result.content[0].text, rule, label);
      assert.doesNotMatch(result.content[0].text, /under (?:about )?2 points|rule of thumb/);
      assert.equal(got.method, "sum_of_ddf_values");
      checks++;
    }
  }
}
const guidance = await call("explain", { topic: "how_to_trade" }, []);
assert.match(guidance.content[0].text, rule);
assert.doesNotMatch(guidance.content[0].text, /under (?:about )?2 points|5 or more/);

// Prove the production dependency is used, rather than an unrelated duplicated rule.
let bandCalls = 0;
const override = { analysis: { modules: { trade: { ...T, evenBand(a, b) { bandCalls++; return 1000; } } } } };
const overridden = await call("compare_trade", { side_a: "Sentinel 1", side_b: "Sentinel 2" }, makePlayers([10], [20]), override);
assert.equal(overridden.structuredContent.verdict, "roughly even");
assert.equal(bandCalls, 1);
console.log(`${checks} scoring/direction/module boundary checks; ok`);
