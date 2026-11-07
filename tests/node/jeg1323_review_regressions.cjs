"use strict";
const assert = require("node:assert/strict");
const {test} = require("node:test");
const F = require("../../app/v2/finder.js");
const R = require("../../app/v2/trade-readout.js");
const sentinels = require("../fixtures/jeg1323_review_sentinels.json");
const charts = F.CHART_KEYS.slice();
const shape = {QB: 1, RB: 0, WR: 1, TE: 0, FLEX: 0, SUPERFLEX: 0, K: 1, DST: 1, BENCH: 6};
const player = (key, value) => ({player_key: key, name: key, pos: "WR",
  values: Object.fromEntries([[F.OUR_KEY, value], ...charts.map(k => [k, 20])])});
const input = scoring => ({shape, chartKeys: charts, context: {scoring},
  mine: {rows: [player("give", 10)]}, theirs: {rows: [player("get", 25)]}, give: ["give"], receive: ["get"]});

for (const scoring of ["standard", "half_ppr", "ppr"]) {
  test(`${scoring}: selected basis controls the displayed sell gap and direction`, () => {
    for (const ourKey of ["fantasycalc", "custom_blend"]) {
      for (const {defaultValue, selected, direction} of sentinels.sellGaps) {
        const inp = input(scoring);
        inp.ourKey = ourKey;
        inp.mine.rows[0].values = {...inp.mine.rows[0].values, [F.OUR_KEY]: defaultValue, [ourKey]: selected};
        // Keep the average at 20 even when the selected basis is itself one of the charts.
        if (charts.includes(ourKey)) inp.mine.rows[0].values[charts.find(k => k !== ourKey)] = 40 - selected;
        const before = JSON.stringify(inp);
        const p = R.build(inp).rows.sellGap.players[0];
        assert.equal(p.ddf, selected);
        assert.equal(p.market, 20);
        assert.equal(p.gap, selected - 20);
        assert.equal(p.direction, direction);
        assert.equal(JSON.stringify(inp), before, "basis adaptation never mutates engine rows");
      }
      const missing = input(scoring);
      missing.ourKey = ourKey;
      missing.mine.rows[0].values[ourKey] = null;
      assert.equal(R.build(missing).rows.sellGap.players[0].status, "unpriced");
    }
  });
  test(`${scoring}: moving K/DEF leave acceptance sums alone and still move physically`, () => {
    const baseline = R.build(input(scoring)).rows.accept.charts;
    assert.equal(baseline.priced, charts.length);
    assert.ok(baseline.even > 0);
    for (const pos of sentinels.notEvaluatedPositions) {
      for (const side of ["mine", "theirs"]) {
        const inp = input(scoring);
        inp[side].rows.push({player_key: "extra", name: "Unevaluated throw-in", pos, values: {}});
        inp[side === "mine" ? "give" : "receive"].push("extra");
        const before = JSON.stringify(inp);
        const out = R.build(inp);
        assert.deepEqual(out.rows.accept.charts, baseline, `${pos} on ${side}`);
        assert.equal(out.roster[side].rosterSizeDelta, -1);
        assert.equal(out.roster[side === "mine" ? "theirs" : "mine"].rosterSizeDelta, 1);
        assert.equal(out.rows.sellGap.players.find(p => p.key === "extra").status, "not-evaluated");
        assert.equal(JSON.stringify(inp), before);
      }
    }
    const missing = input(scoring);
    missing.mine.rows[0].values[charts[0]] = null;
    assert.equal(R.build(missing).rows.accept.charts.priced, charts.length - 1,
      "an unpriced evaluated player still invalidates that chart");
  });
  test(`${scoring}: QB context follows known settings without guessing unknown slots`, () => {
    const context = (s, c = {}) => R.build({...input(scoring), shape: s, context: {scoring, ...c}}).rows.context;
    assert.ok(context({...shape, QB: 2}).text.includes("2QB"));
    assert.ok(context({...shape, QB: 1}).text.includes("1QB"));
    assert.ok(context({...shape, QB: 2, SUPERFLEX: 1}).text.includes("Superflex"));
    assert.ok(!context({SUPERFLEX: 0}).text.includes("1QB"));
    assert.equal(context({QB: 2}).superflex, null);
    assert.ok(context({QB: 2}).missing.includes("superflex"));
    assert.ok(!context(null, {superflex: false}).text.includes("1QB"));
  });
}
