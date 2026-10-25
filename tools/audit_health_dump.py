#!/usr/bin/env python3
"""Dump reduced getInspection() shapes for the Health check page (JEG-1011), headless.

For each (week, scoring, teams) it runs the value pipeline on that saved week's
inputs at the given league setting (the same inputs the page's history reader
uses, assets/history/week-<N>.json) and writes the fields audit-pie.js reads:

  {"week", "scoring", "teams",
   "inspection": {"valuePipeline": {...diagnostics...},
                  "players": {src: {pk: {pos, role, adjusted, estimated}}},
                  "rows": {pk: {"indexed": {src: v}, "ddf": blended DDF Value}}}}

Week == the served week is also read straight from getInspection() so the
history-built run can be checked against the live engine (`liveMatch`).

Usage (build first: the render tests do it, or python3 pipelines/sync_dashboard_artifacts.py):
  python3 tools/audit_health_dump.py --weeks 3 4 5 6 7 --out DIR
  python3 tools/audit_health_dump.py --weeks 7 --teams 4 --scorings ppr --out DIR
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import _dist_server  # noqa: E402

READ = """async ([week, scoring, teams]) => {
  const C = window.TradeValueCurveControls, H = window.TradeValueCurveHarness;
  C.setScoring(scoring); C.setTeams(teams);
  const live = C.getInspection();
  const reduce = (diag, players, rows) => ({
    valuePipeline: diag,
    players: Object.fromEntries(Object.entries(players).map(([src, ps]) => [src, Object.fromEntries(Object.entries(ps).map(([pk, p]) =>
      [pk, {pos: p.pos, role: p.role, adjusted: p.adjusted, estimated: Boolean(p.estimated)}]))])),
    rows: Object.fromEntries(Object.entries(rows).map(([pk, r]) => [pk, {indexed: r.indexed || {}, ddf: r.ddfByVersion && r.ddfByVersion.blended ? r.ddfByVersion.blended.value : null}])),
  });
  const get = async path => (await fetch(path)).json();
  const index = await get('assets/history/index.json');
  const doc = await get(index.weeks[String(week)].file.replace(/^\\.?\\/?/, ''));
  let served = null;
  try { served = await get('assets/history/served.json'); } catch (e) {}
  const canon = new Set(Object.keys(live.rows));
  const idx = {standard: 0, half_ppr: 1, ppr: 2}[scoring];
  const proj = new Set(['espn', 'cbsros', 'razzball']);
  const sources = {};
  for (const key of Object.keys(live.natives)) {
    let entry = doc.sources[key];
    const rec = index.served && index.served[key];
    if (rec && rec.week === week && rec.version === 'superseded' && served && served.sources[key]) entry = served.sources[key];
    if (!entry || entry.week !== week) continue;
    const values = {};
    if (proj.has(key)) Object.entries(entry.ppg || {}).forEach(([pk, t]) => { const v = Number(t && t[idx]); if (canon.has(pk) && Number.isFinite(v)) values[pk] = v; });
    else Object.entries((entry.natives || {})[scoring] || {}).forEach(([pk, raw]) => { const v = Number(raw); if (canon.has(pk) && Number.isFinite(v)) values[pk] = v; });
    if (Object.keys(values).length) sources[key] = {family: proj.has(key) ? 'projection' : 'chart', status: live.included.includes(key) ? 'included' : 'excluded', values, label: key};
  }
  const included = live.included.filter(k => sources[k]);
  const result = H.runPipelineWith({sources, included});
  const diag = window.ValueModel.valuePipelineDiagnostics(result);
  const players = Object.fromEntries(Object.entries(result.sources).map(([k, s]) => [k, s.players]));
  const out = {week, scoring, teams, dropped: Object.keys(live.natives).filter(k => !sources[k]), inspection: reduce(diag, players, result.rows)};
  out.liveMatch = null;
  if (week === index.content_week) {
    const l = reduce(live.valuePipeline, live.players, live.rows);
    out.liveMatch = Object.keys(l.players).every(src => Object.entries(l.players[src]).every(([pk, p]) =>
      out.inspection.players[src] && out.inspection.players[src][pk] && Math.abs(out.inspection.players[src][pk].adjusted - p.adjusted) < 1e-9));
  }
  return out;
}"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weeks", type=int, nargs="+", required=True)
    parser.add_argument("--scorings", nargs="+", default=["standard", "half_ppr", "ppr"])
    parser.add_argument("--teams", type=int, nargs="+", default=[8, 10, 12, 14])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    from playwright.sync_api import sync_playwright
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    with _dist_server.serve() as base, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=_dist_server.chromium_executable(pw),
                                     args=["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"])
        try:
            page = browser.new_page()
            page.on("pageerror", lambda e: print("pageerror", e, file=sys.stderr))
            page.goto(f"{base}/{_dist_server.ENGINE_URL}")
            page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=120000)
            for week in args.weeks:
                for scoring in args.scorings:
                    for teams in args.teams:
                        doc = page.evaluate(READ, [week, scoring, teams])
                        path = out_dir / f"w{week}_{scoring}_{teams}.json"
                        path.write_text(json.dumps(doc, separators=(",", ":")))
                        print(path.name, "dropped", doc["dropped"], "liveMatch", doc["liveMatch"], file=sys.stderr)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
