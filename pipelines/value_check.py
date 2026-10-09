#!/usr/bin/env python3
"""Engine vs Python reference on every chain run (JEG-479).

Jeremy, 2026-10-08: "A disagreement should hold that source and its derived
values for the week, and it should also keep that source and its derived
series out of the consolidated DDF values."

    python pipelines/value_check.py compare [--report P] [--engine-json P] [--today YYYY-MM-DD]
        Runs the engine headless on the built dist/ (default roster and one
        superflex slot, 3 scorings x 8/10/12/14 teams, all three tabs) and
        pipelines/value_reference.py (the JEG-508 value pipeline) on the same
        snapshot, diffs every value, and writes output/value-check.json
        (machine-readable; the fidelity pulse reads it) plus a Markdown
        summary. Compared (VP-12): the 7 sources in each tab they appear in
        (VP-11), estimated values and the `estimated` flags included; the
        three DDF versions and their counts, current and prior week; the
        included set, ddfWeights, each source's weights, the allocation and
        the pie. The report is per source, per series (and tab), per setting,
        with the worst examples. An engine that does not report the
        reference's value pipeline version (TradeValueCurveDiagnostics.
        valuePipeline.version) is not compared: verdict "incomparable",
        nothing held. Exit 0 always unless --strict; the verdict is in the
        JSON.

    python pipelines/value_check.py hold [--report output/value-check.json]
        Holds every disagreeing source and every series derived from it:
        their fixture sections go back to the last published (git HEAD)
        sections, marked `validationHold: {reason, week}`, and the chain status
        lists them as held. The other sources publish.

Tolerance: TOL = 0.05 on values (weights 1e-4, allocation exact, VP-12).
The page shows one decimal; 0.05 is half of the last shown digit, so two implementations within it can
differ by at most one in the last digit and never by a visible amount
beyond rounding. Both sides run in double precision; a correct port lands
within 1e-9 (the existing parity tests' bound), so anything above 0.05 is a
real difference in the math or the inputs, not float noise. Presence is
exact: a value on one side and none (missing) on the other is a
disagreement, never "within tolerance".
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO))

import value_reference as ref  # noqa: E402

TOL = 0.05
REPORT = REPO / "output" / "value-check.json"
FIXTURE_REL = "data/fixtures/current/comparison-sources-data.json"
STATUS = REPO / "output" / "comparison-chain-status.json"
SCHEMA = "value-check/2"

# ---------------------------------------------------------------------------
# Source -> derived series: the ONE place this is defined (JEG-479 item 3).
# A disagreement on any series holds its root source and every series here.
# `sections` are the fixture sections restored on a hold; `series` are the
# page series the root feeds (JEG-508 VP-11). A chart's three tabs (Indexed,
# VORP vs waivers, Adjusted values) are views of the same series key, so
# holding the key holds every view. The *_adjusted series and sections are
# retired by JEG-508 (VP-10/VP-11): a chart's Adjusted values are its own.
# ---------------------------------------------------------------------------
SOURCE_DERIVED = {
    **{c: {"sections": [c], "series": [c]} for c in ref.PUBLISHED},
    **{p: {"sections": [p], "series": [p, f"{p}_vorp"]} for p in ref.PROJECTIONS},
}
ROOT_OF = {series: root for root, d in SOURCE_DERIVED.items() for series in d["series"]}
# Diagnostic comparisons that belong to one source (VP-11 diagnostics and the
# estimated flags): a disagreement holds that source like a value one.
DIAG_ROOT = {**{f"{s}_estimated": s for s in ref.PUBLISHED},
             **{f"{s}_weights": s for s in ref.SOURCES}}
# League-level comparisons: no single source to blame.
COMPOSITE_SERIES = ("ddf_inputs", "ddf_weights", "allocation", "pie")
WEIGHT_TOL = 1e-4   # VP-12: 1e-4 on weights


def derived_series(root: str) -> list[str]:
    return list(SOURCE_DERIVED[root]["series"])


def root_of(series: str) -> str | None:
    return ROOT_OF.get(series) or DIAG_ROOT.get(series)


# ---------------------------------------------------------------------------
# Engine (headless, the built dist/)
# ---------------------------------------------------------------------------

ENGINE_JS = """async ([settings, views, viewSeries, versions]) => {
  const c = window.TradeValueCurveControls;
  const clickView = mode => {
    const tab = document.querySelector(`#viewModeTabs [data-view-mode="${mode}"]`);
    if (!tab) throw new Error('no view tab ' + mode);
    tab.click();
  };
  const num = v => (typeof v === 'number' && Number.isFinite(v)) ? v : null;
  const int = v => Number.isInteger(v) ? v : null;
  const pipeline = () => {
    const d = window.TradeValueCurveDiagnostics;
    if (!d) return null;
    let vp = d.valuePipeline;
    if (typeof vp === 'function') vp = vp();
    if (!vp) return null;
    try { return JSON.parse(JSON.stringify(vp)); } catch (e) { return {error: String(e)}; }
  };
  const out = {};
  for (const s of settings) {
    clickView('indexed');
    c.setScoring(s.scoring, false); c.setTeams(s.teams, false); c.setRosterSpot('SUPERFLEX', s.superflex, false);
    const id = `${s.scoring}/${s.teams}/sf${s.superflex}`;
    let composite = null;
    try { composite = c.getCompositeInputs(); } catch (e) { composite = {error: String(e)}; }
    const entry = {composite, views: {}, prior: {}, estimated: {}, pipeline: pipeline()};
    for (const view of views) {
      clickView(view);
      const rows = {};
      c.getAllRows().forEach(r => {
        const v = {};
        (viewSeries[view] || []).forEach(k => { v[k] = num(r.values[k]); });
        // JEG-497 / JEG-508 VP-6.3: the three DDF versions and their counts.
        const bv = r.ddfByVersion || {};
        v.ddf_value = num(r.values.ddf_value);
        v.ddf_value_charts = num(r.values.ddf_value_charts);
        v.ddf_value_projections = num(r.values.ddf_value_projections);
        v.ddf_count = int((bv.blended || {}).count ?? r.ddfCount);
        v.ddf_charts_count = int((bv.charts || {}).count ?? r.ddfChartsCount);
        v.ddf_projections_count = int((bv.projections || {}).count ?? r.ddfProjectionsCount);
        rows[r.player_key] = v;
        // VP-11: estimated: {sourceKey: reason}.
        const est = r.estimated && typeof r.estimated === 'object' ? Object.keys(r.estimated) : [];
        if (est.length && view === 'indexed') entry.estimated[r.player_key] = est;
      });
      entry.views[view] = rows;
      entry.prior[view] = {};
      for (const version of versions) {
        try {
          const p = await c.getPriorWeek(version);
          entry.prior[view][version] = {available: p.available, reason: p.reason || null, sources: p.sources || [],
            dropped: p.dropped || [], currentWeek: p.currentWeek ?? null, priorWeek: p.priorWeek ?? null,
            values: p.values || {}, counts: p.counts || {}, currentValues: p.currentValues || {}};
        } catch (e) {
          entry.prior[view][version] = {available: false, reason: String(e)};
        }
      }
    }
    clickView('indexed');
    out[id] = entry;
  }
  return out;
}"""


def run_engine(setting_list: list[dict], today: date, dist: Path | None = None,
               overrides: dict | None = None, init_script: str | None = None) -> dict:
    """The engine's rows at every setting and tab, read from the live page.
    init_script (tests only) runs before the page's own scripts."""
    from tests import _render_env
    from tests._dist_server import DIST, serve
    from playwright.sync_api import sync_playwright

    dist = dist or DIST
    if not (dist / "index.html").exists():
        raise SystemExit(f"{dist}/index.html missing: run make sync first")
    with sync_playwright() as p:
        exe = _render_env.chromium_executable(p)
        browser = p.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        try:
            with serve(dist, overrides) as base:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(today.isoformat())};")
                if init_script:
                    page.add_init_script(init_script)
                page.goto(base + "/", wait_until="networkidle")
                page.wait_for_function(
                    "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()",
                    timeout=90000)
                view_series = {v: list(ref.VIEW_SERIES[v]) for v in ref.VIEWS}
                result = page.evaluate(ENGINE_JS, [setting_list, list(ref.VIEWS), view_series,
                                                   list(ref.DDF_VERSIONS)])
                return {"settings": result, "page_errors": errors}
        finally:
            browser.close()


def engine_pipeline_version(engine_settings: dict) -> str | None:
    """The engine's value-pipeline version if every setting reports the same
    one, else None (an engine from before JEG-508 reports none)."""
    versions = {((e or {}).get("pipeline") or {}).get("version") for e in (engine_settings or {}).values()}
    return versions.pop() if len(versions) == 1 else None


# ---------------------------------------------------------------------------
# Reference
# ---------------------------------------------------------------------------

def run_reference(setting_list: list[dict], today: date, fixture=None, players=None,
                  history=None) -> dict:
    inp = ref.Inputs.load(fixture or ref.FIXTURE, players or ref.PLAYERS, today=today)
    hist = ref.History(history or ref.HISTORY)
    out = {}
    for s in setting_list:
        out[ref.setting_id(s)] = ref.compute(inp, s, hist=hist)
    return out


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

EXAMPLES = 5      # worst examples kept per series
WORST = 25        # worst examples kept for the whole report


def _keyed(rows: dict) -> dict:
    return {int(k): v for k, v in (rows or {}).items()}


def _severity(m: dict) -> tuple:
    """Presence and structural mismatches first, then the largest."""
    return (m.get("kind") == "value", -(m.get("diff") or 0.0))


def diff_rows(engine_rows: dict, ref_rows: dict, series: list[str], tol: float = TOL) -> dict:
    """{series: {"compared", "mismatches": [...], "max_abs_diff"}}."""
    eng, rf = _keyed(engine_rows), _keyed(ref_rows)
    out = {}
    for key in series:
        compared, mism, max_d = 0, [], 0.0
        for pk in sorted(set(eng) | set(rf)):
            e = (eng.get(pk) or {}).get(key)
            r = (rf.get(pk) or {}).get(key)
            if e is None and r is None:
                continue
            compared += 1
            if (e is None) != (r is None):
                mism.append({"player_key": pk, "engine": e, "reference": r, "kind": "presence"})
                continue
            d = abs(float(e) - float(r))
            max_d = max(max_d, d)
            if d > tol:
                mism.append({"player_key": pk, "engine": e, "reference": r, "diff": d, "kind": "value"})
        out[key] = {"compared": compared, "mismatches": mism, "max_abs_diff": max_d}
    return out


class _Report:
    """Accumulates per series (and tab) and per setting."""

    def __init__(self):
        self.by_series = {}
        self.by_setting = {}
        self.total = 0

    def series(self, key):
        return self.by_series.setdefault(key, {"compared": 0, "mismatches": 0, "examples": [], "max_abs_diff": 0.0,
                                                "where": [], "settings": [], "by_view": {}})

    def setting(self, sid):
        return self.by_setting.setdefault(sid, {"compared": 0, "mismatches": 0, "max_abs_diff": 0.0,
                                                "series": {}})

    def add(self, key, sid, view, compared, mismatches, max_d):
        agg, st = self.series(key), self.setting(sid)
        agg["compared"] += compared
        st["compared"] += compared
        self.total += compared
        agg["max_abs_diff"] = max(agg["max_abs_diff"], max_d)
        st["max_abs_diff"] = max(st["max_abs_diff"], max_d)
        if view is not None:
            bv = agg["by_view"].setdefault(view, {"compared": 0, "mismatches": 0, "max_abs_diff": 0.0})
            bv["compared"] += compared
            bv["mismatches"] += len(mismatches)
            bv["max_abs_diff"] = max(bv["max_abs_diff"], max_d)
        if mismatches:
            agg["mismatches"] += len(mismatches)
            st["mismatches"] += len(mismatches)
            st["series"][key] = st["series"].get(key, 0) + len(mismatches)
            where = f"{sid}/{view}" if view else sid
            if where not in agg["where"]:
                agg["where"].append(where)
            if sid not in agg["settings"]:
                agg["settings"].append(sid)
            ex = agg["examples"] + [{"setting": sid, **({"view": view} if view else {}), **m}
                                    for m in mismatches]
            ex.sort(key=_severity)
            agg["examples"] = ex[:EXAMPLES]


def compare(engine: dict, reference: dict, tol: float = TOL) -> dict:
    """Per-source disagreement report (schema value-check/2): per source, per
    series (and tab), per setting, with the worst examples."""
    rep = _Report()
    ddf = [*ref.DDF_VERSIONS, *ref.DDF_COUNT_FIELD.values()]
    for sid, r in reference.items():
        e = engine.get(sid)
        if e is None:
            for key in (*ref.SERIES_KEYS, *ref.DDF_VERSIONS):
                rep.add(key, sid, None, 1, [{"kind": "missing_setting",
                                             "detail": "engine has no rows for this setting"}], 0.0)
            continue
        for view in ref.VIEWS:
            series = [*ref.VIEW_SERIES[view], *ddf]
            d = diff_rows((e.get("views") or {}).get(view), (r.get("views") or {}).get(view), series, tol)
            for key, res in d.items():
                rep.add(key, sid, view, res["compared"], res["mismatches"], res["max_abs_diff"])
            for version in ref.DDF_VERSIONS:
                _diff_prior(rep, sid, view, ((e.get("prior") or {}).get(view) or {}).get(version),
                            ((r.get("prior") or {}).get(view) or {}).get(version), tol, version)
        if "estimated" in r:
            _diff_estimated(rep, sid, e.get("estimated") or {}, r.get("estimated") or {})
        _diff_pipeline(rep, sid, e, r, tol)
    return attribute(rep, tol)


def _diff_estimated(rep: _Report, sid: str, eng: dict, rf: dict) -> None:
    """VP-11 `estimated`: the same (player, chart) pairs on both sides."""
    def pairs(m):
        out = set()
        for pk, srcs in (m or {}).items():
            for s in (srcs.keys() if isinstance(srcs, dict) else srcs or []):
                out.add((int(pk), s))
        return out
    pe, pr = pairs(eng), pairs(rf)
    for src in ref.PUBLISHED:
        a = {pk for pk, s in pe if s == src}
        b = {pk for pk, s in pr if s == src}
        mism = [{"player_key": pk, "engine": pk in a, "reference": pk in b, "kind": "presence"}
                for pk in sorted(a ^ b)]
        rep.add(f"{src}_estimated", sid, None, len(a | b), mism, 0.0)


def _num_map(rep: _Report, key: str, sid: str, a: dict | None, b: dict | None, tol: float) -> None:
    mism, max_d, n = [], 0.0, 0
    for g in sorted(set(a or {}) | set(b or {})):
        x, y = (a or {}).get(g), (b or {}).get(g)
        n += 1
        if not (ref._finite(x) and ref._finite(y)):
            if not (x is None and y is None):
                mism.append({"group": g, "engine": x, "reference": y, "kind": "presence"})
            continue
        d = abs(float(x) - float(y))
        max_d = max(max_d, d)
        if d > tol:
            mism.append({"group": g, "engine": x, "reference": y, "diff": d, "kind": "value"})
    rep.add(key, sid, None, n, mism, max_d)


def _diff_pipeline(rep: _Report, sid: str, e: dict, r: dict, tol: float) -> None:
    """VP-12: the included set, ddfWeights (1e-4), the allocation (exact),
    the pie (TOL) and each source's weights (1e-4)."""
    rp, ep = r.get("pipeline") or {}, e.get("pipeline") or {}
    inputs_e = ep.get("included")
    if inputs_e is None:
        inputs_e = (e.get("composite") or {}).get("inputs")
    if inputs_e is not None and "composite_inputs" in r:
        bad = sorted(inputs_e) != sorted(r["composite_inputs"])
        rep.add("ddf_inputs", sid, None, 1,
                [{"kind": "inputs", "engine": inputs_e, "reference": r["composite_inputs"]}] if bad else [], 0.0)
    if not rp:
        return
    if not ep:
        rep.add("pie", sid, None, 1,
                [{"kind": "presence", "detail": "engine reports no valuePipeline diagnostics"}], 0.0)
        return
    _num_map(rep, "pie", sid, {"pie": ep.get("pie")}, {"pie": rp.get("pie")}, tol)
    _num_map(rep, "ddf_weights", sid, ep.get("ddfWeights"), rp.get("ddfWeights"), WEIGHT_TOL)
    alloc_m, n = [], 0
    for p in ref.POSITIONS:
        a, b = (ep.get("allocation") or {}).get(p) or {}, (rp.get("allocation") or {}).get(p) or {}
        for f in ("dedicated", "superflex", "flex", "bench", "starters", "rostered"):
            n += 1
            if a.get(f) != b.get(f):
                alloc_m.append({"group": f"{p}.{f}", "engine": a.get(f), "reference": b.get(f), "kind": "exact"})
    rep.add("allocation", sid, None, n, alloc_m, 0.0)
    for src, rs in (rp.get("sources") or {}).items():
        es = (ep.get("sources") or {}).get(src) or {}
        _num_map(rep, f"{src}_weights", sid, es.get("weights"), rs.get("weights"), WEIGHT_TOL)


def _diff_prior(rep: _Report, sid: str, view: str, e: dict | None, r: dict | None, tol: float,
                version: str = "ddf_value") -> None:
    """A DDF version's prior-week pair: availability, the included sources,
    the prior week's values and the current side."""
    if r is None:
        return
    e = e or {}
    key = f"{version}_prior"
    if bool(e.get("available")) != bool(r.get("available")):
        rep.add(key, sid, view, 1, [{"kind": "availability", "engine": e.get("available"),
                                     "reference": r.get("available"), "engine_reason": e.get("reason"),
                                     "reference_reason": r.get("reason")}], 0.0)
        return
    rep.add(key, sid, view, 1, [], 0.0)
    if not r.get("available"):
        return
    if sorted(e.get("sources") or []) != sorted(r.get("sources") or []):
        rep.add(key, sid, view, 0, [{"kind": "inputs", "engine": e.get("sources"),
                                     "reference": r.get("sources")}], 0.0)
        return
    for field in ("values", "currentValues"):
        res = diff_rows({k: {"v": v} for k, v in (e.get(field) or {}).items()},
                        {k: {"v": v} for k, v in (r.get(field) or {}).items()}, ["v"], tol)["v"]
        mism = [{**m, "kind": f"{field}:{m['kind']}"} for m in res["mismatches"]]
        rep.add(key, sid, view, res["compared"], mism, res["max_abs_diff"])


def attribute(rep: _Report, tol: float) -> dict:
    """Map series disagreements to the root sources to hold."""
    by_series = rep.by_series
    roots, composite_only = {}, []
    for key, agg in by_series.items():
        if not agg["mismatches"]:
            continue
        root = root_of(key)
        if root:
            roots.setdefault(root, []).append(key)
        else:
            composite_only.append(key)
    # A DDF Value disagreement is explained by a disagreeing input: holding
    # that input's source removes it from the DDF Value. Only a DDF
    # disagreement with every input agreeing points at the composite rule.
    composite_only = [] if roots else composite_only
    sources = {}
    for root in SOURCE_DERIVED:
        bad = roots.get(root, [])
        mine = [k for k in by_series if root_of(k) == root]
        sources[root] = {
            "status": "disagree" if bad else "agree",
            "series": derived_series(root),
            "disagreeing_series": sorted(bad),
            "hold": sorted(SOURCE_DERIVED[root]["sections"]) if bad else [],
            "compared": sum(by_series[k]["compared"] for k in mine),
            "mismatches": sum(by_series[k]["mismatches"] for k in mine),
            "max_abs_diff": max((by_series[k]["max_abs_diff"] for k in mine), default=0.0),
            "settings": sorted({sid for k in bad for sid in by_series[k]["settings"]}),
        }
    disagree = sorted(r for r, s in sources.items() if s["status"] == "disagree")
    worst = sorted(({"series": k, **ex} for k, agg in by_series.items() for ex in agg["examples"]),
                   key=_severity)[:WORST]
    # A DDF disagreement with every input agreeing is the composite rule
    # itself; no source is to blame, so it is reported (and fails the
    # verdict) without holding any source.
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_version": ref.VERSION,
        "pipeline_version": ref.PIPELINE_VERSION,
        "tolerance": tol,
        "weight_tolerance": WEIGHT_TOL,
        "tolerance_reason": ("half of the page's last shown digit (values display to one decimal); "
                             "weights to 1e-4 (VP-12); allocation exact; presence must match exactly"),
        "values_compared": rep.total,
        "verdict": "agree" if not disagree and not composite_only else "disagree",
        "disagreeing_sources": disagree,
        "composite_disagreements": sorted(composite_only),
        "hold": {r: sources[r]["hold"] for r in disagree},
        "sources": sources,
        "series": by_series,
        "by_setting": rep.by_setting,
        "worst": worst,
    }


def incomparable(engine_version: str | None, tol: float = TOL) -> dict:
    """The report when the built engine does not run the reference's
    pipeline (an engine from before JEG-508, or broken diagnostics): nothing
    is compared and nothing is held. Diffing the JEG-508 reference against an
    older engine would disagree on every source and hold the whole page."""
    report = attribute(_Report(), tol)
    # No per-source entries: a source that was not compared is not "agree"
    # (the fidelity pulse shows n/a, the value_check_agree check fails).
    report.update({"verdict": "incomparable", "engine_pipeline_version": engine_version, "sources": {},
                   "reason": (f"engine reports value pipeline {engine_version!r}; the reference implements "
                              f"{ref.PIPELINE_VERSION!r}. Nothing compared, nothing held.")})
    return report


def summary_md(report: dict) -> str:
    lines = [f"## Engine vs Python reference ({report['schema']})", "",
             f"Verdict: **{report['verdict']}** - {report['values_compared']} values compared, "
             f"tolerance {report['tolerance']} ({report['tolerance_reason']}).", ""]
    if report.get("reason"):
        lines += [report["reason"], ""]
    lines.append("| Source | Status | Compared | Mismatches | Max abs diff | Settings | Held |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for root, s in report["sources"].items():
        lines.append(f"| {root} | {s['status']} | {s.get('compared', 0)} | {s.get('mismatches', 0)} | "
                     f"{s.get('max_abs_diff', 0.0):.4f} | {len(s.get('settings') or [])} | "
                     f"{', '.join(s['hold']) or '-'} |")
    lines.append("")
    bad_settings = {sid: st for sid, st in (report.get("by_setting") or {}).items() if st["mismatches"]}
    if bad_settings:
        lines.append("| Setting | Compared | Mismatches | Max abs diff | Worst series |")
        lines.append("| --- | --- | --- | --- | --- |")
        for sid, st in sorted(bad_settings.items()):
            top = ", ".join(f"{k} {n}" for k, n in sorted(st["series"].items(), key=lambda kv: -kv[1])[:4])
            lines.append(f"| {sid} | {st['compared']} | {st['mismatches']} | {st['max_abs_diff']:.4f} | {top} |")
        lines.append("")
    for key, agg in sorted(report["series"].items()):
        if agg["mismatches"]:
            views = ", ".join(f"{v} {b['mismatches']}" for v, b in agg.get("by_view", {}).items()
                              if b["mismatches"])
            lines.append(f"- `{key}`: {agg['mismatches']} mismatches (max |diff| {agg['max_abs_diff']:.4f})"
                         + (f", by tab: {views}" if views else "") + f" in {', '.join(agg['where'][:6])}")
            for ex in agg["examples"][:3]:
                lines.append(f"  - {json.dumps(ex, default=str)}")
    if report.get("worst"):
        lines += ["", "Worst examples:"]
        for ex in report["worst"][:10]:
            lines.append(f"- {json.dumps(ex, default=str)}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Hold (JEG-479 item 3): reuse the per-source hold -- the held source keeps
# its last good section, labelled with its own (older) week, others publish.
# ---------------------------------------------------------------------------

def last_published_fixture(repo: Path = REPO, rev: str = "HEAD") -> dict | None:
    proc = subprocess.run(["git", "show", f"{rev}:{FIXTURE_REL}"], cwd=str(repo),
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        return None
    return json.loads(proc.stdout)


def apply_holds(fixture: dict, last_good: dict | None, holds: dict, week: int | None,
                reason_of: dict | None = None) -> dict:
    """Return a fixture with every held root's sections restored from
    `last_good` and marked validationHold. holds: {root: [sections]}."""
    out = copy.deepcopy(fixture)
    sources = out.setdefault("sources", {})
    prior = (last_good or {}).get("sources") or {}
    for root, sections in holds.items():
        reason = (reason_of or {}).get(root) or f"engine and Python reference disagree on {root}"
        for sec in sections:
            if sec in prior:
                sources[sec] = copy.deepcopy(prior[sec])
                kept_week = ref.section_week(prior[sec], date.today())[0]
            else:
                kept_week = None  # nothing published before: keep this run's, still held
            target = sources.get(sec)
            if isinstance(target, dict):
                target["validationHold"] = {"reason": reason, "week": week,
                                            "root": root, "kept_week": kept_week}
    return out


def release_holds(fixture: dict, disagreeing: list[str]) -> list[str]:
    """Remove validationHold (in place) from sections whose root agrees now."""
    released = []
    for sec, section in (fixture.get("sources") or {}).items():
        if not isinstance(section, dict) or "validationHold" not in section:
            continue
        root = (section.get("validationHold") or {}).get("root") or ROOT_OF.get(sec)
        if root not in disagreeing:
            del section["validationHold"]
            released.append(sec)
    return sorted(released)


def update_chain_status(status: dict, report: dict, week: int | None) -> dict:
    """List validation-held roots in the chain status, like a review hold."""
    status = copy.deepcopy(status or {})
    held = set(status.get("held") or [])
    detail = dict(status.get("held_detail") or {})
    for root in report.get("disagreeing_sources") or []:
        held.add(root)
        detail[root] = {"reason": "validation hold: engine and Python reference disagree",
                        "held_series": derived_series(root),
                        "sections": report["hold"].get(root, []),
                        "hold_severity": "amber", "week": week}
    status["held"] = sorted(held)
    status["held_detail"] = detail
    status["value_check"] = {"verdict": report.get("verdict"),
                             "disagreeing_sources": report.get("disagreeing_sources") or [],
                             "composite_disagreements": report.get("composite_disagreements") or [],
                             "values_compared": report.get("values_compared")}
    if held and status.get("status") == "green":
        status["status"] = "published_with_holds"
    return status


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def dumps_for(report_path: Path) -> tuple[Path, Path, Path]:
    """(summary .md, engine dump, reference dump) beside a report path."""
    stem = Path(report_path).with_suffix("")
    return stem.with_suffix(".md"), Path(f"{stem}-engine.json"), Path(f"{stem}-reference.json")


def held_sections(fixture_path: Path = REPO / FIXTURE_REL) -> dict:
    """{section: validationHold} in the fixture being published."""
    try:
        fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {sec: s["validationHold"] for sec, s in (fixture.get("sources") or {}).items()
            if isinstance(s, dict) and s.get("validationHold")}


def spec_reference_section(engine_settings: dict) -> dict:
    """Second, non-blocking comparison: the clean-room spec reference
    (pipelines/spec_reference). It never changes the verdict or holds."""
    try:
        from spec_reference import compare as spec_compare
        return spec_compare.compare(engine_settings)
    except Exception as exc:  # noqa: BLE001 - informational only
        return {"schema": "spec-reference/1", "blocking": False, "error": repr(exc)}


def cmd_compare(args) -> int:
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    setting_list = ref.settings(superflex_too=not args.no_superflex)
    report_path = Path(args.report)
    summary_path, engine_path, reference_path = dumps_for(report_path)
    if args.engine_json and Path(args.engine_json).exists() and not args.rerun_engine:
        engine = json.loads(Path(args.engine_json).read_text(encoding="utf-8"))
    else:
        engine = run_engine(setting_list, today)
        engine_path.parent.mkdir(parents=True, exist_ok=True)
        engine_path.write_text(json.dumps(engine, separators=(",", ":")), encoding="utf-8")
    reference = run_reference(setting_list, today)
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    reference_path.write_text(json.dumps(reference, separators=(",", ":"), default=str), encoding="utf-8")
    engine_version = engine_pipeline_version(engine["settings"])
    if engine_version != ref.PIPELINE_VERSION:
        report = incomparable(engine_version, args.tol)
    else:
        report = compare(engine["settings"], reference, args.tol)
    report["today"] = today.isoformat()
    report["page_errors"] = engine.get("page_errors") or []
    report["settings"] = [ref.setting_id(s) for s in setting_list]
    report["held_sections"] = held_sections()
    report["spec_reference"] = spec_reference_section(engine["settings"])
    report_path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    summary_path.write_text(summary_md(report), encoding="utf-8")
    print(summary_md(report))
    return 1 if (args.strict and report["verdict"] != "agree") else 0


def cmd_hold(args) -> int:
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    if report.get("verdict") == "incomparable":
        # Nothing was compared: hold nothing new and release nothing.
        print(f"value check: incomparable ({report.get('reason')}); holds left as they are")
        return 0
    from nfl_week import current_nfl_week
    week = args.week or current_nfl_week(datetime.now(timezone.utc).date())
    fixture_path = REPO / FIXTURE_REL
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    # A hold lasts while the disagreement does: a section still carrying a
    # validationHold from an earlier run is released when its root agrees now.
    released = release_holds(fixture, report.get("disagreeing_sources") or [])
    for sec in released:
        print(f"value check: released validationHold on {sec} (engine and reference agree now)")
    if not report.get("hold"):
        if released:
            fixture_path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
        print("value check: no source to hold")
        return 0
    held = apply_holds(fixture, last_published_fixture(), report["hold"], week)
    fixture_path.write_text(json.dumps(held, indent=2) + "\n", encoding="utf-8")
    try:
        status = json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = {}
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(update_chain_status(status, report, week), indent=2) + "\n",
                      encoding="utf-8")
    for root, sections in report["hold"].items():
        print(f"::warning title=Value check hold ({root})::engine and Python reference disagree; "
              f"{', '.join(sections)} kept on the last published section, marked validationHold")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--engine-json", default=None, help="reuse a saved engine dump")
    c.add_argument("--rerun-engine", action="store_true")
    c.add_argument("--today", default=None)
    c.add_argument("--tol", type=float, default=TOL)
    c.add_argument("--no-superflex", action="store_true")
    c.add_argument("--strict", action="store_true", help="exit 1 on any disagreement")
    c.add_argument("--report", default=str(REPORT), help="report path (dumps go beside it)")
    c.set_defaults(func=cmd_compare)
    h = sub.add_parser("hold")
    h.add_argument("--report", default=str(REPORT))
    h.add_argument("--week", type=int, default=None)
    h.set_defaults(func=cmd_hold)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
