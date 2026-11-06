// Synthetic inputs shared by the greedy selector's Node and browser checks.
(function (root) {
  "use strict";
  function makeCase(kind = "three") {
    const rows = [];
    const player = (key, pos, value, market = value, projection = null) => {
      const row = {player_key: key, name: `Synthetic ${key}`, pos, ddfTier: "starter",
        values: {ddf_value: value, ddf_value_projections: projection, usatoday: market, fantasycalc: market, fantasypros: market}};
      rows.push(row);
      return {key, name: row.name, pos, slot: pos};
    };
    const team = id => ({id, name: `Synthetic team ${id}`, entries: [
      player(`${id}-qb`, "QB", 30), player(`${id}-rb`, "RB", 30),
      player(`${id}-wr`, "WR", 30), player(`${id}-te`, "TE", 30)]});
    const mine = team("a"), b = team("b"), c = team("c"), d = team("d");
    rows.find(r => r.player_key === "a-wr").values.ddf_value = 10;
    rows.find(r => r.player_key === "a-te").values.ddf_value = 10;
    const trade = (id, give, receive) => ({opponentId: id, give, receive,
      // Deliberately wrong cached annotations: selection must not read them.
      rank: 99, edge: -999, score: -999, overall: "natural", tier: 0});
    let candidates;
    if (kind === "slot") {
      mine.entries = mine.entries.filter(e => e.pos !== "RB");
      mine.entries.push(player("a-r1", "RB", 5, 40), player("a-r2", "RB", 6, 40));
      b.entries.push(player("b-w", "WR", 45, 10));
      c.entries.push(player("c-t", "TE", 26, 10));
      candidates = [trade("c", ["a-r2"], ["c-t"]), trade("b", ["a-r1"], ["b-w"])];
    } else {
      mine.entries.push(player("a-r", "RB", 5, 20), player("a-w", "WR", 5, 20), player("a-t", "TE", 5, 20));
      b.entries.push(player("b-r", "RB", 12, 10));
      c.entries.push(player("c-w", "WR", 15, 10));
      d.entries.push(player("d-t", "TE", 18, 10));
      candidates = [trade("b", [{key: "a-r"}], [{player_key: "b-r"}]),
        trade("c", ["a-w"], ["c-w"]), trade("d", ["a-t"], ["d-t"])];
    }
    const league = {myTeamId: "a", teams: [mine, b, c, d]};
    const ctx = {rowsByKey: new Map(rows.map(r => [r.player_key, r])),
      shape: {QB: 1, RB: 1, WR: 1, TE: 1, FLEX: 0, SUPERFLEX: 0},
      expected: Object.fromEntries(["QB", "RB", "WR", "TE"].map(p => [p, {lo: 1, hi: 3}])),
      weights: {overall: 0.25}, charts: ["usatoday", "fantasycalc", "fantasypros"],
      market: ["usatoday", "fantasycalc", "fantasypros"]};
    return {league, candidates, ctx};
  }
  const api = {makeCase};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.PackageSearchCases = api;
})(typeof window !== "undefined" ? window : globalThis);
