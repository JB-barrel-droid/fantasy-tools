#!/usr/bin/env node
// JEG-432 R5/R1 test harness. Loads product-data.js (and, for the default-set
// checks, value-model.js + curve-widget.js) in Node with no DOM and runs one
// command from a JSON payload on stdin.
//
// payload.mutations: optional [[from, to], ...] applied to the named source
// file's text before it is evaluated. This is how the tests simulate a
// broken implementation (negative tests): each `from` must occur in the file,
// or the harness exits non-zero so a stale mutation cannot pass silently.
//
// Commands:
//   {cmd: "weeks", days: [...]}                        -> {weeks: {...}}
//   {cmd: "freshness", sources, today}                 -> buildSourceFreshness()
//   {cmd: "registry", fixturePath, indexPath, sources?, scoring, teams, today,
//    minShared?, pausedSeries?: [...]}                 -> buildPairRegistry()
//   {cmd: "defaults", inputsPath, excluded, active, deselected}
//        -> {defaults, satisfied} from curve-widget's TradeValueCurvePause
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ASSETS = path.join(__dirname, "..", "app", "trade-value-chart", "assets");

function loadSource(file, mutations) {
  let text = fs.readFileSync(path.join(ASSETS, file), "utf8");
  (mutations || []).forEach(([from, to]) => {
    if (!text.includes(from)) {
      console.error(`mutation target not found in ${file}: ${from.slice(0, 80)}`);
      process.exit(3);
    }
    text = text.split(from).join(to);
  });
  return text;
}

function evalModule(file, mutations, sandbox) {
  const module = {exports: {}};
  const context = sandbox || vm.createContext({console, Intl, Date, Math, Number, String, Object,
    Array, Set, Map, JSON, RegExp, Error, Promise, setTimeout, clearTimeout});
  context.module = module;
  vm.runInContext(loadSource(file, mutations), context, {filename: file});
  return {exports: module.exports, context};
}

function playersFromIndex(indexPath) {
  const html = fs.readFileSync(indexPath, "utf8");
  const match = html.match(/id="players-data"[^>]*>([\s\S]*?)<\/script>/);
  return match ? JSON.parse(match[1]).players : [];
}

const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const mutations = payload.mutations || [];
let out;

if (payload.cmd === "defaults") {
  const context = vm.createContext({console, Intl, Date, Math, Number, String, Object, Array, Set,
    Map, JSON, RegExp, Error, Promise, setTimeout, clearTimeout});
  context.globalThis = context;
  context.window = context;
  vm.runInContext(fs.readFileSync(path.join(ASSETS, "value-model.js"), "utf8"), context);
  vm.runInContext(loadSource("curve-widget.js", mutations), context);
  const P = context.TradeValueCurvePause;
  const inputs = JSON.parse(fs.readFileSync(payload.inputsPath, "utf8"));
  const excluded = new Set(payload.excluded || []);
  out = {
    defaults: P.defaultIndexedSourceKeys(inputs, excluded),
    satisfied: P.defaultCurvesSatisfied(inputs, new Set(payload.active || []),
      new Set(payload.deselected || []), excluded),
  };
} else {
  const pd = evalModule("product-data.js", mutations).exports;
  if (payload.cmd === "weeks") {
    const weeks = {};
    payload.days.forEach(day => { weeks[day] = pd.contentWeekForDay(day); });
    out = {weeks};
  } else if (payload.cmd === "freshness") {
    out = pd.buildSourceFreshness(payload.sources, {today: payload.today});
  } else if (payload.cmd === "registry") {
    const detail = JSON.parse(fs.readFileSync(payload.fixturePath, "utf8"));
    const sources = payload.sources || detail.sources;
    const map = new Map(Object.entries(detail.player_keys || {}).map(([k, v]) => [k, Number(v)]));
    const paused = new Set(payload.pausedSeries || []);
    out = pd.buildPairRegistry({
      sources,
      players: playersFromIndex(payload.indexPath),
      playerKeysBySourceId: map,
      scoring: payload.scoring,
      teams: payload.teams,
      minShared: payload.minShared || 40,
      freshness: pd.buildSourceFreshness(sources, {today: payload.today}),
      isAdjustedPaused: key => paused.has(key),
    });
  } else {
    console.error(`unknown cmd ${payload.cmd}`);
    process.exit(2);
  }
}
process.stdout.write(JSON.stringify(out));
