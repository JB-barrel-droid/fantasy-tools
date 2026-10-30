// JEG-1179: explicit superflex must win in both pricing input and the site link.
import assert from "node:assert/strict";
import codec from "../../app/v2/ddf-state.js";
import { prepare, finish } from "../../supabase/functions/mcp/state.ts";
import { mapLeague } from "../../supabase/functions/get-values/league.ts";

const deps = { codec, siteOrigin: "https://example.test/fantasy-tools" };
for (const [pastedSf, explicitSf] of [[1, false], [0, true]]) {
  const pasted = { v: 1, league: { scoring: "half_ppr", teams: 10,
    roster: { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, SUPERFLEX: pastedSf, BENCH: 6 } },
    work: { view: "finder", mine: [{ name: "Josh Allen" }] } };
  const prepared = prepare({ state: codec.encodeBlock(pasted), superflex: explicitSf }, deps);
  assert.equal(prepared.args.superflex, explicitSf, "explicit argument is the engine input");
  assert.equal(prepared.args.league.roster.SUPERFLEX, undefined, "pasted slot cannot override it");
  const priced = mapLeague({ ...prepared.args.league, scoring: prepared.args.scoring,
    teams: prepared.args.teams, roster: { ...prepared.args.league.roster,
      SUPERFLEX: Number(prepared.args.superflex) } }, null);
  assert.equal(priced.setting.superflex, Number(explicitSf));
  const result = finish({ content: [{ type: "text", text: "priced" }] },
    { prepared, deps, settings: { scoring: "half_ppr", teams: 10,
      superflex: priced.setting.superflex }, view: "finder" });
  const linked = codec.decodeBlock(result.structuredContent.site_url).state;
  assert.equal(linked.league.roster.SUPERFLEX, Number(explicitSf), "link opens the priced league");
  assert.equal(mapLeague(linked.league, null).setting.superflex, priced.setting.superflex);
  assert.equal(linked.league.roster.WR, 3);
  assert.equal(linked.league.roster.BENCH, 6);
  assert.equal(linked.league.scoring, "half_ppr");
  assert.equal(linked.league.teams, 10);
  assert.deepEqual(prepare({ state: result.structuredContent.site_url }, deps).state?.league, linked.league,
    "read_state input round-trips through the link");
}
console.log("ok");
