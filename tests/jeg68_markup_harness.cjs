#!/usr/bin/env node
// JEG-68 harness: replicates the pool-level math of curve-widget.js
// buildVorpRows() (the `${vorpKey}-starter-markup` ChartHealth check) using
// the REAL ValueModel (projectionRoles, stableTiebreak, starterMarkupSane)
// and the REAL fixture players.json -- only the DOM-dependent inputs
// (players-data blob, league defaults) are re-supplied here.
//
// Usage:
//   node jeg68_markup_harness.cjs --fixture <players.json>
//     --ppg-field cbsros_ppg --scoring ppr --teams 12 [--simulate-prevalued]
// Output JSON: {n, starterRaw, benchRaw, rawStarterShare, markup, sane}
//
// --simulate-prevalued: first runs the ppg pool through
// ValueModel.normalizeToFixedPie (the "already run through a valuation
// model" defect the check guards against, ~91% starter share), then prices
// the raw VORP off those pre-valued inputs. A working guard must flag it.
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const ValueModel = require(path.join(ROOT, "app", "trade-value-chart", "assets", "value-model.js"));
const POSITION_ORDER = ValueModel.POSITION_ORDER;

function arg(name, dflt) {
  const i = process.argv.indexOf(name);
  return i === -1 ? dflt : process.argv[i + 1];
}
const fixturePath = arg("--fixture");
const ppgField = arg("--ppg-field", "cbsros_ppg");
const scoring = arg("--scoring", "ppr");
const teams = Number(arg("--teams", "12"));
const simulatePrevalued = process.argv.includes("--simulate-prevalued");
const STARTER_SHARE = 0.85;

const payload = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const rosterShape = { QB: 1, RB: 2, WR: 3, TE: 1, FLEX: 1, BENCH: 6, K: 0, DST: 0 };

// canonicalByKey, mirroring buildCanonicalMap() for the priced positions.
const players = [];
(payload.players || []).forEach(p => {
  const key = Number(p.player_key);
  if (!Number.isInteger(key) || !POSITION_ORDER.includes(p.pos)) return;
  const ppg = p[ppgField];
  players.push({ player_key: key, pos: p.pos, ppg: ppg ? ppg[scoring] : undefined });
});

function pricePool(ppgOf) {
  const priced = players
    .map(pl => ({ player: pl, ppg: Number(ppgOf(pl)) }))
    .filter(r => Number.isFinite(r.ppg))
    .sort((a, b) => b.ppg - a.ppg || ValueModel.stableTiebreak(a.player, b.player));
  const ppgByKey = new Map(priced.map(r => [r.player.player_key, r.ppg]));
  const roles = ValueModel.projectionRoles({
    pool: priced.map(r => r.player), teams, shape: rosterShape,
    rankOf: pl => Number(ppgByKey.get(pl.player_key)),
  }).roles;
  const baselineByPos = new Map();
  POSITION_ORDER.forEach(pos => {
    const rows = priced.filter(r => r.player.pos === pos);
    const waiver = rows
      .filter(r => (roles.get(r.player.player_key) || "waiver") === "waiver")
      .sort((a, b) => b.ppg - a.ppg)[0];
    const fallback = rows.sort((a, b) => b.ppg - a.ppg).at(-1);
    baselineByPos.set(pos, Number(waiver?.ppg ?? fallback?.ppg ?? 0));
  });
  let starterRaw = 0, benchRaw = 0;
  priced.forEach(r => {
    const role = roles.get(r.player.player_key) || "waiver";
    if (role === "waiver") return;
    const v = Math.max(0, r.ppg - (baselineByPos.get(r.player.pos) || 0));
    if (role === "starter") starterRaw += v; else benchRaw += v;
  });
  return { priced, roles, starterRaw, benchRaw };
}

let ppgOf = pl => pl.ppg;
if (simulatePrevalued) {
  // Pre-value the pool through the fixed pie, then price raw VORP off it.
  const first = pricePool(ppgOf);
  const values = new Map(first.priced.map(r => [r.player.player_key, r.ppg]));
  const scaled = ValueModel.normalizeToFixedPie({
    values, share: 1 - STARTER_SHARE, roles: first.roles,
  });
  ppgOf = pl => scaled.get(pl.player_key);
}

const { priced, starterRaw, benchRaw } = pricePool(ppgOf);
const rawTotal = starterRaw + benchRaw;
const rawStarterShare = rawTotal > 0 ? starterRaw / rawTotal : NaN;
// Pool-level scales mirror the widget: targetTotal cancels out of the ratio.
const rawScale = rawTotal > 0 ? 1 / rawTotal : 1;
const starterScale = starterRaw > 0 ? STARTER_SHARE / starterRaw : 0;
const markup = starterScale / rawScale;

process.stdout.write(JSON.stringify({
  n: priced.length,
  starterRaw: Number(starterRaw.toFixed(2)),
  benchRaw: Number(benchRaw.toFixed(2)),
  rawStarterShare: Number(rawStarterShare.toFixed(6)),
  markup: Number(markup.toFixed(6)),
  sane: ValueModel.starterMarkupSane(markup),
  saneLow: ValueModel.STARTER_MARKUP_SANE_LOW,
  saneHigh: ValueModel.STARTER_MARKUP_SANE_HIGH,
  simulatedPrevalued: simulatePrevalued,
}));
