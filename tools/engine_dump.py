#!/usr/bin/env python3
"""Dump the engine's value pipeline (JEG-508) at every compare setting, headless.

Loads the built engine page (dist/, served like the render tests), sets each
league setting with the page's own controls, and writes the pipeline result
the chart draws -- straight from window.TradeValueCurveHarness.pipeline() and
pipelinePrior(), full precision -- as one JSON document:

  {"version": "engine-dump/1", "settings": [{
      "setting": {"scoring", "teams", "superflex"},
      "pie", "benchShare", "ddfWeights": {"POS|role": w}, "allocation": {...},
      "included": [...], "excluded": [{key, reason}],
      "fixedPieIndexed": bool, "indexedOrderOk": bool,
      "sources": {src: {"adjusted": {pk: v}, "vorp": {pk: v}, "indexed": {pk: v},
                        "estimated": {pk: path}, "weights": {...}, "indexedFactor"}},
      "ddf": {"blended"|"charts"|"projections": {pk: v}},
      "ddfPrior": {...same, or null},
      "tiers": {pk: tier},
      "curveStart": {view: {series: {pos: top value}}}}]}

Null values are left out of the per-player maps (a missing key = null).

Settings: the 12 combos (standard / half_ppr / ppr x 8/10/12/14 teams, the
default roster QB1 RB2 WR3 TE1 FLEX1 BENCH6) plus PPR 12 teams with one
superflex slot -- 13 in all. `--setting ppr:12:1` picks one (scoring:teams:sf).

Usage (build first with `make sync`):
  python3 tools/engine_dump.py --out /tmp/engine-values.json
  python3 tools/engine_dump.py --setting half_ppr:10:0 --out -
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import _dist_server  # noqa: E402

SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)
DEFAULT_SETTINGS = [(s, t, 0) for s in SCORINGS for t in TEAMS] + [("ppr", 12, 1)]

READ = """([scoring, teams, sf]) => {
  const c = window.TradeValueCurveControls;
  c.setScoring(scoring); c.setTeams(teams); c.setRosterSpot('SUPERFLEX', sf);
  const H = window.TradeValueCurveHarness;
  const d = window.TradeValueCurveDiagnostics;
  const result = H.pipeline(), prior = H.pipelinePrior();
  const pick = (rows, src, field) => {
    const out = {};
    Object.entries(rows).forEach(([pk, row]) => {
      const v = row[field][src];
      if (typeof v === 'number' && Number.isFinite(v)) out[pk] = v;
    });
    return out;
  };
  const ddf = res => res ? Object.fromEntries(['blended', 'charts', 'projections'].map(name => [name,
    Object.fromEntries(Object.entries(res.rows).filter(([, r]) => Number.isFinite(r.ddfByVersion[name].value))
      .map(([pk, r]) => [pk, r.ddfByVersion[name].value]))])) : null;
  const sources = {};
  Object.entries(result.sources).forEach(([src, s]) => {
    const estimated = {};
    Object.entries(result.rows).forEach(([pk, row]) => { if (row.estimatedPath[src]) estimated[pk] = row.estimatedPath[src]; });
    sources[src] = {family: s.family, included: s.included, adjusted: pick(result.rows, src, 'adjusted'),
      vorp: pick(result.rows, src, 'vorp'), indexed: pick(result.rows, src, 'indexed'), estimated,
      weights: s.weights, indexedFactor: s.indexedFactor === undefined ? null : s.indexedFactor};
  });
  // Where each series' curve starts: its top value per position, per view.
  const curveStart = {};
  const view = v => document.querySelector(`#viewModeTabs [data-view-mode=${v}]`).click();
  for (const v of ['indexed', 'vorp', 'adj']) {
    view(v);
    const top = {};
    c.getAllRows().forEach(r => Object.entries(r.values).forEach(([k, val]) => {
      if (typeof val !== 'number') return;
      top[k] = top[k] || {};
      if (!(top[k][r.pos] >= val)) top[k][r.pos] = val;
    }));
    curveStart[v] = top;
  }
  view('indexed');
  return {setting: {scoring, teams, superflex: sf}, pie: result.pie, benchShare: result.benchShare,
    ddfWeights: result.ddfWeights, allocation: result.allocation, included: result.included,
    excluded: d.excluded, fixedPieIndexed: d.fixedPieIndexed, indexedOrderOk: d.indexedOrder.ok,
    sources, ddf: ddf(result), ddfPrior: ddf(prior),
    tiers: Object.fromEntries(Object.entries(result.rows).map(([pk, r]) => [pk, r.tier])), curveStart};
}"""


def dump(settings):
    from playwright.sync_api import sync_playwright
    out = []
    with _dist_server.serve() as base, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=_dist_server.chromium_executable(pw),
                                     args=["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"])
        try:
            page = browser.new_page()
            page.goto(f"{base}/{_dist_server.ENGINE_URL}")
            page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()",
                                   timeout=120000)
            for setting in settings:
                out.append(page.evaluate(READ, list(setting)))
        finally:
            browser.close()
    return {"version": "engine-dump/1", "settings": out}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--setting", action="append", help="scoring:teams:superflex, e.g. ppr:12:1 (repeatable)")
    parser.add_argument("--out", default="-", help="output file, or - for stdout")
    args = parser.parse_args(argv)
    settings = DEFAULT_SETTINGS
    if args.setting:
        settings = []
        for text in args.setting:
            scoring, teams, sf = text.split(":")
            settings.append((scoring, int(teams), int(sf)))
    doc = dump(settings)
    text = json.dumps(doc, separators=(",", ":"))
    if args.out == "-":
        sys.stdout.write(text)
    else:
        Path(args.out).write_text(text)
        print(f"wrote {len(doc['settings'])} settings -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
