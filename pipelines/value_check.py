#!/usr/bin/env python3
"""Engine vs Python reference on every chain run (JEG-479).

Jeremy, 2026-10-08: "A disagreement should hold that source and its derived
values for the week, and it should also keep that source and its derived
series out of the consolidated DDF values."

    python pipelines/value_check.py compare [--report P] [--engine-json P] [--today YYYY-MM-DD]
        Runs the engine headless on the built dist/ (default roster and one
        superflex slot, 3 scorings x 8/10/12/14 teams, all three views) and
        pipelines/value_reference.py on the same snapshot, diffs every value,
        and writes output/value-check.json (machine-readable; the fidelity
        pulse reads it) plus a Markdown summary. Exit 0 always unless
        --strict; the verdict is in the JSON.

    python pipelines/value_check.py hold [--report output/value-check.json]
        Holds every disagreeing source and every series derived from it:
        their fixture sections go back to the last published (git HEAD)
        sections, marked `validationHold: {reason, week}`, and the chain status
        lists them as held. The other sources publish.

Tolerance: TOL = 0.05 on the page's 0-70 scale. The page shows one decimal;
0.05 is half of the last shown digit, so two implementations within it can
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
import math
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
SCHEMA = "value-check/1"

# ---------------------------------------------------------------------------
# Source -> derived series: the ONE place this is defined (JEG-479 item 3).
# A disagreement on any series holds its root source and every series here.
# `sections` are the fixture sections restored on a hold (the derived
# *_adjusted section carries the same week label as its raw chart, so both go
# back together). `series` are the page series the root feeds; the published
# charts' VORP vs waivers / Adjusted values views are views of the same series
# key (`<source>` in view vorp/adj), so holding the key holds every view.
# ---------------------------------------------------------------------------
SOURCE_DERIVED = {
    "usatoday": {"sections": ["usatoday", "usatoday_adjusted"],
                 "series": ["usatoday", "usatoday_adjusted"]},
    "fantasycalc": {"sections": ["fantasycalc", "fantasycalc_adjusted"],
                    "series": ["fantasycalc", "fantasycalc_adjusted"]},
    "fantasypros": {"sections": ["fantasypros", "fantasypros_adjusted"],
                    "series": ["fantasypros", "fantasypros_adjusted"]},
    "cbs": {"sections": ["cbs", "cbs_adjusted"], "series": ["cbs", "cbs_adjusted"]},
    "espn": {"sections": ["espn"], "series": ["espn", "espn_vorp"]},
    "cbsros": {"sections": ["cbsros"], "series": ["cbsros", "cbsros_vorp"]},
    "razzball": {"sections": ["razzball"], "series": ["razzball", "razzball_vorp"]},
}
ROOT_OF = {series: root for root, d in SOURCE_DERIVED.items() for series in d["series"]}
VIEWS_WITH_PUBLISHED_ONLY = {"vorp", "adj"}  # only the four charts change in these views


def derived_series(root: str) -> list[str]:
    return list(SOURCE_DERIVED[root]["series"])


# ---------------------------------------------------------------------------
# Engine (headless, the built dist/)
# ---------------------------------------------------------------------------

ENGINE_JS = """async ([settings, views, keys]) => {
  const c = window.TradeValueCurveControls;
  const clickView = mode => {
    const tab = document.querySelector(`#viewModeTabs [data-view-mode="${mode}"]`);
    if (!tab) throw new Error('no view tab ' + mode);
    tab.click();
  };
  const num = v => (typeof v === 'number' && Number.isFinite(v)) ? v : null;
  const out = {};
  for (const s of settings) {
    clickView('indexed');
    c.setScoring(s.scoring, false); c.setTeams(s.teams, false); c.setRosterSpot('SUPERFLEX', s.superflex, false);
    const id = `${s.scoring}/${s.teams}/sf${s.superflex}`;
    const entry = {composite: c.getCompositeInputs(), views: {}, prior: {}};
    for (const view of views) {
      clickView(view);
      const rows = {};
      c.getAllRows().forEach(r => {
        const v = {};
        keys.forEach(k => { v[k] = num(r.values[k]); });
        v.ddf_value = num(r.values.ddf_value);
        v.ddf_count = Number.isInteger(r.ddfCount) ? r.ddfCount : null;
        if ('ddfReason' in r) v.ddf_reason = r.ddfReason;
        rows[r.player_key] = v;
      });
      entry.views[view] = rows;
      try {
        const p = await c.getPriorWeek('ddf_value');
        entry.prior[view] = {available: p.available, reason: p.reason || null, sources: p.sources || [],
          dropped: p.dropped || [], currentWeek: p.currentWeek ?? null, priorWeek: p.priorWeek ?? null,
          values: p.values || {}, counts: p.counts || {}, currentValues: p.currentValues || {}};
      } catch (e) {
        entry.prior[view] = {available: false, reason: String(e)};
      }
    }
    clickView('indexed');
    out[id] = entry;
  }
  return out;
}"""


def run_engine(setting_list: list[dict], today: date, dist: Path | None = None,
               overrides: dict | None = None) -> dict:
    """The engine's rows at every setting and view, read from the live page."""
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
                page.goto(base + "/", wait_until="networkidle")
                page.wait_for_function(
                    "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()",
                    timeout=90000)
                result = page.evaluate(ENGINE_JS, [setting_list, list(ref.VIEWS), list(ref.SERIES_KEYS)])
                return {"settings": result, "page_errors": errors}
        finally:
            browser.close()


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

def _keyed(rows: dict) -> dict:
    return {int(k): v for k, v in (rows or {}).items()}


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


def compare(engine: dict, reference: dict, tol: float = TOL) -> dict:
    """Per-source disagreement report (schema value-check/1)."""
    per_setting, by_series = [], {}
    total_compared = 0
    for sid, r in reference.items():
        e = engine.get(sid)
        if e is None:
            per_setting.append({"setting": sid, "error": "engine has no rows for this setting"})
            for key in ref.SERIES_KEYS:
                by_series.setdefault(key, {"compared": 0, "mismatches": 0, "examples": [], "max_abs_diff": 0.0,
                                            "where": []})["mismatches"] += 1
            continue
        for view in ref.VIEWS:
            series = list(ref.SERIES_KEYS) + [ref.COMPOSITE_KEY, "ddf_count"]
            if view in VIEWS_WITH_PUBLISHED_ONLY:
                series = list(ref.PUBLISHED) + [ref.COMPOSITE_KEY, "ddf_count"]
            d = diff_rows(e["views"].get(view), r["views"].get(view), series, tol)
            for key, res in d.items():
                agg = by_series.setdefault(key, {"compared": 0, "mismatches": 0, "examples": [],
                                                 "max_abs_diff": 0.0, "where": []})
                agg["compared"] += res["compared"]
                total_compared += res["compared"]
                agg["max_abs_diff"] = max(agg["max_abs_diff"], res["max_abs_diff"])
                if res["mismatches"]:
                    agg["mismatches"] += len(res["mismatches"])
                    agg["where"].append(f"{sid}/{view}")
                    for m in res["mismatches"][: max(0, 5 - len(agg["examples"]))]:
                        agg["examples"].append({"setting": sid, "view": view, **m})
        for view in ref.VIEWS:
            _diff_prior(by_series, sid, view, (e.get("prior") or {}).get(view),
                        (r.get("prior") or {}).get(view), tol)
        inputs_e = (e.get("composite") or {}).get("inputs")
        if inputs_e is not None and sorted(inputs_e) != sorted(r["composite_inputs"]):
            agg = by_series.setdefault("ddf_inputs", {"compared": 0, "mismatches": 0, "examples": [],
                                                      "max_abs_diff": 0.0, "where": []})
            agg["mismatches"] += 1
            agg["where"].append(sid)
            if len(agg["examples"]) < 5:
                agg["examples"].append({"setting": sid, "engine": inputs_e, "reference": r["composite_inputs"]})
    return attribute(by_series, total_compared, tol)


def _diff_prior(by_series: dict, sid: str, view: str, e: dict | None, r: dict | None, tol: float) -> None:
    """The DDF Value prior-week pair: availability, the paired input set, the
    prior week's values and the current side over the same inputs."""
    if r is None:
        return
    e = e or {}
    agg = by_series.setdefault("ddf_value_prior", {"compared": 0, "mismatches": 0, "examples": [],
                                                   "max_abs_diff": 0.0, "where": []})

    def flag(detail):
        agg["mismatches"] += 1
        agg["where"].append(f"{sid}/{view}")
        if len(agg["examples"]) < 5:
            agg["examples"].append({"setting": sid, "view": view, **detail})
    agg["compared"] += 1
    if bool(e.get("available")) != bool(r.get("available")):
        flag({"kind": "availability", "engine": e.get("available"), "reference": r.get("available"),
              "engine_reason": e.get("reason"), "reference_reason": r.get("reason")})
        return
    if not r.get("available"):
        return
    if sorted(e.get("sources") or []) != sorted(r.get("sources") or []):
        flag({"kind": "inputs", "engine": e.get("sources"), "reference": r.get("sources")})
        return
    for field in ("values", "currentValues"):
        res = diff_rows({k: {"v": v} for k, v in (e.get(field) or {}).items()},
                        {k: {"v": v} for k, v in (r.get(field) or {}).items()}, ["v"], tol)["v"]
        agg["compared"] += res["compared"]
        agg["max_abs_diff"] = max(agg["max_abs_diff"], res["max_abs_diff"])
        for m in res["mismatches"][:1]:
            flag({"kind": f"{field}:{m['kind']}", **m, "count": len(res["mismatches"])})


def attribute(by_series: dict, total_compared: int, tol: float) -> dict:
    """Map series disagreements to the root sources to hold."""
    roots, composite_only = {}, []
    for key, agg in by_series.items():
        if not agg["mismatches"]:
            continue
        root = ROOT_OF.get(key)
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
        series = derived_series(root)
        bad = roots.get(root, [])
        sources[root] = {
            "status": "disagree" if bad else "agree",
            "series": series,
            "disagreeing_series": sorted(bad),
            "hold": sorted(SOURCE_DERIVED[root]["sections"]) if bad else [],
        }
    disagree = sorted(r for r, s in sources.items() if s["status"] == "disagree")
    # A DDF disagreement with every input agreeing is the composite rule
    # itself; no source is to blame, so it is reported (and fails the
    # verdict) without holding any source.
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tolerance": tol,
        "tolerance_reason": ("half of the page's last shown digit (values display to 0.1 on the "
                             "0-70 scale); presence must match exactly"),
        "values_compared": total_compared,
        "verdict": "agree" if not disagree and not composite_only else "disagree",
        "disagreeing_sources": disagree,
        "composite_disagreements": sorted(composite_only),
        "hold": {r: sources[r]["hold"] for r in disagree},
        "sources": sources,
        "series": by_series,
    }


def summary_md(report: dict) -> str:
    lines = [f"## Engine vs Python reference ({report['schema']})", "",
             f"Verdict: **{report['verdict']}** - {report['values_compared']} values compared, "
             f"tolerance {report['tolerance']} ({report['tolerance_reason']}).", ""]
    lines.append("| Source | Status | Series held |")
    lines.append("| --- | --- | --- |")
    for root, s in report["sources"].items():
        lines.append(f"| {root} | {s['status']} | {', '.join(s['hold']) or '-'} |")
    lines.append("")
    for key, agg in sorted(report["series"].items()):
        if agg["mismatches"]:
            lines.append(f"- `{key}`: {agg['mismatches']} mismatches (max |diff| {agg['max_abs_diff']:.4f}) "
                         f"in {', '.join(agg['where'][:6])}")
            for ex in agg["examples"][:3]:
                lines.append(f"  - {json.dumps(ex)}")
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
    report = compare(engine["settings"], reference, args.tol)
    report["today"] = today.isoformat()
    report["page_errors"] = engine.get("page_errors") or []
    report["settings"] = [ref.setting_id(s) for s in setting_list]
    report["held_sections"] = held_sections()
    report_path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    summary_path.write_text(summary_md(report), encoding="utf-8")
    print(summary_md(report))
    return 1 if (args.strict and report["verdict"] != "agree") else 0


def cmd_hold(args) -> int:
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
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
