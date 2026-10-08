#!/usr/bin/env node
// GAP-CBSROS-8T-NO-QB harness: reprices CBS ROS in the browser's live
// two-tier path (players.json cbsros_ppg, legacy bench mix, surplus pies,
// TwoTier.calibratePositionFeasible at 0.15, one 70/max scale -- the same
// steps as curve-widget.js ddfTwoTierValuesForSource) for all 12 league
// shapes and compares every position against the chain-built CBS ROS
// section in data/fixtures/current/comparison-sources-data.json.
// Pool option: argv[2] === "section-pool" restricts the live pool to the
// players the section prices (the leg's resolved identities), so the
// comparison isolates the calibration math from the identity difference
// (the leg drops suffix-name players as unresolved_identity; the browser
// pool does not -- GAP-CBSROS-LIVE-POOL).
// Since fix/suffix-names the leg resolves suffix spellings, so browser-pool
// and section-pool price the same players (nLive == nSection == n).
// Prints one JSON object: {combo: {withheld, shares, stats: {pos: {n, nSection, nLive, maxErr, top}}}}.
"use strict";
const fs = require("fs");
const path = require("path");
globalThis.window = globalThis;
const ROOT = path.join(__dirname, "..");
require(path.join(ROOT, "app", "trade-value-chart", "assets", "value-model.js"));
require(path.join(ROOT, "app", "trade-value-chart", "assets", "curve-widget.js"));
const T = globalThis.TradeValueTwoTier;

const players = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "fixtures", "current", "players.json"), "utf8")).players;
const fixture = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "fixtures", "current", "comparison-sources-data.json"), "utf8"));
const slugToKey = fixture.player_keys || {};
const SECTION_POOL = process.argv[2] === "section-pool";
const SCORINGS = {full: "ppr", half: "half_ppr", standard: "standard"};
const out = {};

for (const [prefix, field] of Object.entries(SCORINGS)) {
  for (const teams of [8, 10, 12, 14]) {
    const combo = `${prefix}_${teams}`;
    const section = fixture.sources?.cbsros?.combos?.[combo]?.values || {};
    const sectionKeys = new Set(Object.keys(section).map(slug => slugToKey[slug]));
    const lists = {QB: [], RB: [], WR: [], TE: []};
    const posOf = new Map();
    players.forEach(p => {
      const x = Number(p.cbsros_ppg?.[field]);
      if (!T.POSITIONS.includes(p.pos) || !Number.isFinite(x)) return;
      if (SECTION_POOL && !sectionKeys.has(Number(p.player_key))) return;
      const id = Number(p.player_key);
      lists[p.pos].push({id, x});
      posOf.set(id, p.pos);
    });
    const pool = T.buildPositionTiers(lists, {
      teams, slots: {...T.REF_SLOTS}, flexCount: T.REF_FLEX_COUNT,
      flexEligible: [...T.REF_FLEX_ELIGIBLE], benchMix: T.legacyBenchMixFor(teams),
    });
    const withheld = [], shares = {};
    const raw = new Map();
    T.POSITIONS.forEach(pos => {
      const tier = pool.tiers[pos];
      const cal = T.calibratePositionFeasible(tier, Number(tier?.surplus), T.DEFAULT_BENCH_SHARE, pos);
      if (!cal || cal.invalid) { withheld.push(pos); return; }
      shares[pos] = cal.bench_share_used;
      lists[pos].forEach(d => raw.set(d.id, T.priceForProjection(d.x, cal)));
    });
    let mx = 0;
    raw.forEach(v => { if (v > mx) mx = v; });
    const scale = mx > 0 ? 70 / mx : 1;
    const stats = {};
    T.POSITIONS.forEach(pos => { stats[pos] = {n: 0, nSection: 0, nLive: lists[pos].length, maxErr: 0, top: null}; });
    for (const [slug, val] of Object.entries(section)) {
      const key = slugToKey[slug];
      const pos = posOf.get(key);
      if (!pos || val === null || val === undefined) continue;
      const s = stats[pos];
      s.nSection++;
      if (!raw.has(key)) continue;
      const live = raw.get(key) * scale;
      s.n++;
      s.maxErr = Math.max(s.maxErr, Math.abs(live - val));
      if (!s.top || val > s.top.section) s.top = {slug, section: val, live};
    }
    out[combo] = {withheld, shares, stats};
  }
}
process.stdout.write(JSON.stringify(out));
