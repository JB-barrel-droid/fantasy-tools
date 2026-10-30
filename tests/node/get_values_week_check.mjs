// JEG-1179: the week get-values prices. Runs the deployed handler (supabase/functions/get-values/index.ts)
// in node with a stub Deno and a fetch that serves the built dist/, as get_values_handler_check.mjs does,
// on the real week history and on synthetic week transitions made by editing the served history index
// (some sources pushed back one week). Values are compared with the parity runner given the same index;
// tests/test_endpoint_parity.py ties the runner to the page for the same weeks.
// Usage: node --experimental-strip-types tests/node/get_values_week_check.mjs <dist dir>
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const dist = resolve(process.argv[2] || "dist");
const realIndex = JSON.parse(readFileSync(join(dist, "assets/history/index.json"), "utf8"));
const work = mkdtempSync(join(tmpdir(), "gv-week-"));
const SOURCES = ["espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs"];

// One handler instance per scenario (the bundle and its history are cached per instance).
let scenario = 0;
async function handlerFor({ index = realIndex, today = undefined, drop = [], overrides = {} } = {}) {
  let handler = null;
  const env = { DDF_TODAY: today };
  globalThis.Deno = { env: { get: (k) => env[k] }, serve: (h) => { handler = h; } };
  globalThis.fetch = async (url) => {
    const path = new URL(String(url)).pathname.replace(/^\/fantasy-tools/, "");
    if (path === "/assets/history/index.json") {
      return index ? new Response(JSON.stringify(index), { status: 200 }) : new Response("gone", { status: 404 });
    }
    if (drop.some((d) => path.endsWith(d))) return new Response("not found", { status: 404 });
    if (overrides[path]) return new Response(JSON.stringify(overrides[path]), { status: 200 });
    const file = join(dist, path === "/" || path === "" ? "index.html" : path);
    let body;
    try { body = readFileSync(file); } catch { return new Response("not found", { status: 404 }); }
    return new Response(body, { status: 200 });
  };
  scenario += 1;
  await import(`../../supabase/functions/get-values/index.ts?scenario=${scenario}`);
  assert.equal(typeof handler, "function", "index.ts registered a Deno.serve handler");
  let ip = 0;
  return (body) => handler(new Request("https://fn.test/functions/v1/get-values", {
    method: "POST", headers: { "content-type": "application/json", "x-forwarded-for": `10.0.${scenario}.${++ip}` },
    body: JSON.stringify(body) }));
}

function runner(extra, index, today) {
  const args = ["--experimental-strip-types", "--no-warnings", "tests/_edge_pipeline_runner.cjs",
    "--dist", dist, "--with-week", "1", ...extra];
  if (index) {
    const path = join(work, `index-${scenario}-${extra.join("_")}.json`);
    writeFileSync(path, JSON.stringify(index));
    args.push("--history-index", path);
  }
  const env = { ...process.env };
  if (today) env.TRADE_VALUE_TODAY = today; else delete env.TRADE_VALUE_TODAY;
  return JSON.parse(execFileSync("node", args, { maxBuffer: 1 << 28, env }));
}

// The site's rule, restated for the assertions: N+1 only when more than half the DDF Value sources serve it.
function ruleDefault(week, lagging, newest) {
  const all = new Set([...week.sources, ...week.missing_sources]);
  const behind = lagging.filter((k) => all.has(k)).length;
  return 2 * (all.size - behind) > all.size ? newest : newest - 1;
}

function sameValues(body, expected, label) {
  assert.ok(body.players.length > 50, `${label}: priced players`);
  const bad = body.players.filter((p) => Math.abs(p.value - (expected[p.player_key] ?? 0)) > 0.06);
  assert.equal(bad.length, 0, `${label}: ${bad.length} values differ from the runner: ${JSON.stringify(bad.slice(0, 3))}`);
}

// An index where `lagging` serve one week before the newest served week N (a week transition). Only
// sources served from their week's own snapshot are moved: a kept ("superseded") version is tied to its week.
function transitionIndex(count) {
  const idx = structuredClone(realIndex);
  const served = idx.served || {};
  const newest = Math.max(...SOURCES.map((k) => served[k]?.week).filter(Number.isInteger));
  const movable = SOURCES.filter((k) => served[k]?.week === newest && served[k]?.version !== "superseded");
  assert.ok(movable.length >= count, `need ${count} sources on week ${newest} to move back`);
  assert.ok(idx.weeks?.[String(newest - 1)] && idx.weeks?.[String(newest - 2)],
    `weeks ${newest - 1} and ${newest - 2} are saved`);
  const lagging = movable.slice(-count);
  for (const k of lagging) served[k] = { ...served[k], week: newest - 1 };
  return { index: idx, newest, lagging };
}

// 1. The real history: the default week, its sources, no missing source, the runner's values.
let ask = await handlerFor();
let res = await ask({ scoring: "ppr", teams: 12 });
assert.equal(res.status, 200);
let body = await res.json();
let expected = runner(["--scoring", "ppr", "--teams", "12"]);
assert.equal(body.week, expected.week.week);
assert.equal(body.default_week, body.week, "no week asked: the default week");
assert.ok(Number.isInteger(body.week) && body.weeks.includes(body.week));
assert.deepEqual(body.missing_sources, expected.week.missing_sources);
sameValues(body, expected.values, "default week");
// The default week asked for by number is the same answer.
res = await ask({ scoring: "ppr", teams: 12, week: body.week });
const byNumber = await res.json();
assert.equal(byNumber.week, body.week);
assert.deepEqual(byNumber.players.slice(0, 20), body.players.slice(0, 20));

// 2. A week with no published sources is a clear error that names the weeks there are, not an empty list.
res = await ask({ scoring: "ppr", teams: 12, week: Math.max(...body.weeks) + 1 });
assert.equal(res.status, 400);
let err = await res.json();
assert.equal(err.code, "week_unavailable");
assert.match(err.error, /has no published sources/);
assert.deepEqual(err.weeks, body.weeks);
assert.equal(err.default_week, body.default_week);
res = await ask({ scoring: "ppr", teams: 12, week: "eight" });
assert.equal(res.status, 400);
assert.match((await res.json()).error, /invalid week/);

// 3. JEG-1157: on the Tuesday flip, before any chart has published the new week, the calendar says
// week N+1 while every chart serves week N. The site's default stays on week N, so values are priced.
const calendarAhead = (() => {
  const d = new Date(Date.UTC(2026, 8, 8) + ((Math.max(...body.weeks) + 1) - 1) * 7 * 86400000);
  return d.toISOString().slice(0, 10); // the Tuesday the week after the newest served week starts
})();
ask = await handlerFor({ today: calendarAhead });
res = await ask({ scoring: "half_ppr", teams: 10 });
body = await res.json();
assert.equal(res.status, 200);
assert.equal(body.week, Math.max(...body.weeks), "the gap prices the newest served week");
sameValues(body, runner(["--scoring", "half_ppr", "--teams", "10"], null, calendarAhead).values, "gap");

// 4. A transition with fewer than half the sources lagging (N+1 = newest, default newest): the lagging
// sources are missing from the newest week, never carried forward; the week before prices all of them.
{
  const t = transitionIndex(3);
  ask = await handlerFor({ index: t.index });
  res = await ask({ scoring: "ppr", teams: 12 });
  body = await res.json();
  assert.equal(res.status, 200);
  expected = runner(["--scoring", "ppr", "--teams", "12"], t.index);
  assert.deepEqual(body.weeks, [t.newest, t.newest - 1]);
  assert.equal(body.week, expected.week.default_week);
  assert.equal(body.default_week, expected.week.default_week);
  assert.deepEqual(body.missing_sources, expected.week.missing_sources);
  assert.equal(body.week, ruleDefault(expected.week, t.lagging, t.newest));
  res = await ask({ scoring: "ppr", teams: 12, week: t.newest });
  const newest = await res.json();
  assert.equal(newest.week, t.newest);
  for (const k of t.lagging) {
    assert.ok(newest.missing_sources.includes(k), `${k} lags: missing from week ${t.newest}`);
    assert.ok(!newest.sources_included.includes(k), `${k} lags: not carried forward into week ${t.newest}`);
  }
  sameValues(body, expected.values, "transition, default week");

  res = await ask({ scoring: "ppr", teams: 12, week: t.newest - 1 });
  const prev = await res.json();
  assert.equal(res.status, 200);
  const prevExpected = runner(["--scoring", "ppr", "--teams", "12", "--week", String(t.newest - 1)], t.index);
  assert.equal(prev.week, t.newest - 1);
  assert.equal(prev.default_week, body.default_week);
  assert.deepEqual(prev.missing_sources, prevExpected.week.missing_sources);
  for (const k of t.lagging) assert.ok(prev.sources_included.includes(k), `${k} priced on week ${t.newest - 1}`);
  sameValues(prev, prevExpected.values, "transition, week N");
  assert.ok(prev.players.some((p) => Math.abs(p.value - (newest.players.find((q) => q.player_key === p.player_key)?.value ?? 0)) > 0.1),
    "the two weeks price differently");

  res = await ask({ scoring: "ppr", teams: 12, week: t.newest - 2 });
  assert.equal(res.status, 400);
  err = await res.json();
  assert.equal(err.code, "week_unavailable");
  assert.deepEqual(err.weeks, [t.newest, t.newest - 1]);
  assert.match(err.error, new RegExp(`Weeks available: ${t.newest}, ${t.newest - 1} \\(default ${body.default_week}\\)`));
}

// 5. More than half lagging: the default stays on week N; week N+1 can be asked for and names what it lacks.
// Without the saved week N the sources that moved on have no copy of it and are named missing.
{
  const t = transitionIndex(4);
  ask = await handlerFor({ index: t.index });
  res = await ask({ scoring: "standard", teams: 14, superflex: 1 });
  body = await res.json();
  expected = runner(["--scoring", "standard", "--teams", "14", "--superflex", "1"], t.index);
  assert.equal(body.week, ruleDefault(expected.week, t.lagging, t.newest));
  assert.equal(body.week, t.newest - 1, "most sources lag: stay on the week before");
  assert.equal(body.default_week, t.newest - 1);
  assert.deepEqual(body.missing_sources, expected.week.missing_sources);
  sameValues(body, expected.values, "transition, majority lagging");

  res = await ask({ scoring: "standard", teams: 14, superflex: 1, week: t.newest });
  const ahead = await res.json();
  assert.equal(ahead.week, t.newest);
  assert.deepEqual([...ahead.missing_sources].sort(), [...t.lagging].sort());

  const missingDoc = realIndex.weeks[String(t.newest - 1)].file;
  ask = await handlerFor({ index: t.index, drop: [missingDoc] });
  res = await ask({ scoring: "standard", teams: 14, superflex: 1 });
  body = await res.json();
  assert.equal(body.week, t.newest - 1);
  const movedOn = expected.week.sources.filter((k) => !t.lagging.includes(k));
  assert.ok(movedOn.length > 0);
  for (const k of movedOn) assert.ok(body.missing_sources.includes(k), `${k} has no saved week ${t.newest - 1}: missing`);
  for (const k of movedOn) assert.ok(!body.sources_included.includes(k), `${k} is not priced on another week's data`);
}

// 6. A history index from another build (or none) falls back to the calendar's week, as the page does.
ask = await handlerFor({ index: { ...realIndex, fixture_built_at: "1999-01-01T00:00:00+00:00" } });
res = await ask({ scoring: "ppr", teams: 12 });
body = await res.json();
assert.equal(res.status, 200);
assert.equal(body.weeks.length, 1);

// 7. A divergence exclusion is read where the page reads it (the bundle's top level, written by
// sync_dashboard_artifacts.py): the excluded source leaves DDF Value and the week's source count.
{
  const bundlePath = "/assets/comparison-sources-data.json";
  const detail = JSON.parse(readFileSync(join(dist, bundlePath), "utf8"));
  const base = await (await (await handlerFor())({ scoring: "ppr", teams: 12 })).json();
  const chart = ["usatoday", "fantasypros", "cbs", "fantasycalc"].find((k) => base.sources_included.includes(k));
  assert.ok(chart, "a chart feeds DDF Value");
  ask = await handlerFor({ overrides: { [bundlePath]: { ...detail, divergence_exclusions: [chart] } } });
  body = await (await ask({ scoring: "ppr", teams: 12 })).json();
  const moved = body.players.filter((p) => Math.abs(p.value - (base.players.find((q) => q.player_key === p.player_key)?.value ?? 0)) > 0.1);
  assert.ok(moved.length > 10, `excluding ${chart} by divergence changes DDF Value (${moved.length} players moved)`);
}

rmSync(work, { recursive: true, force: true });
console.log("ok");
