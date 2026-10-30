#!/usr/bin/env python3
"""Source divergence soft check (JEG-460): flag sources that disagree with the
consensus of the other sources too often.

A WARNING, never a gate. `make sync` runs it on the fixture it publishes and
writes the result to output/source-divergence.json, dist/modules/source-divergence.json
and a per-source summary into reference-freshness.json (`source_divergence`).
Any error inside the check is reported in the file, never raised to the build.

Metric, per source and saved 12-team scoring combo, over the values the page
shows (trade charts: `reindexed`, the one-factor Indexed values; projection
sources: `values`):

* Sources are compared inside their group: the four published trade charts
  with each other, the three projection sources with each other.
* A player counts when at least MIN_SOURCES sources of the group price him
  above 0 (missing is never read as 0). For each source the consensus is the
  median of the OTHER sources' values (leave-one-out), and the deviation is
  source minus consensus.
* bias = mean signed deviation, mad = mean absolute deviation, outlier_rate =
  share of players with |deviation| > OUTLIER_REL of the consensus and at least
  OUTLIER_MIN_PTS points. All three are also split by position.

Status per source (worst over the three scorings):

* warn: outlier_rate > WARN_OUTLIER_RATE or |bias| > WARN_BIAS (fixed
  ceilings), or, with at least BASELINE_MIN_WEEKS prior weeks, outlier_rate
  above the source's trailing baseline by BASELINE_RATE_MARGIN or bias away
  from its baseline by BASELINE_BIAS_MARGIN.
* investigate: warned this week and last week, or one position (at least
  POSITION_MIN_N players) is far out of line (|bias| > POSITION_BIAS, or
  outlier_rate > POSITION_OUTLIER_RATE with |bias| > WARN_BIAS).
* reviewed: a resolution for this source-week is recorded in
  data/source-divergence-resolutions.json (the computed status is kept).
* excluded: the resolution is 'exclude' — the source-week is removed from
  blends and comparisons (held semantics per JEG-569: grayed out, stays in
  the pool for weights and pie).

Each source-week is labelled by the week the source is served as (JEG-1314:
`week_state.source_weeks`, else the content week), not the content week
alone: on the Tuesday flip content_week moves before the charts publish.
Resolutions and the baseline use that week; a saved week whose inputs have
the served fingerprint is the same chart and never counts as a prior week.
The one exception is 'exclude' (JEG-1337): value_reference applies it by the
content week (`load_divergence_exclusions(week=content_week)`), so the report
does too, whatever the computed status. An 'exclude' recorded only for a
served week that is not the content week is a resolution problem, not an
exclusion, because DDF Value would still blend that source.

The trailing baseline (up to BASELINE_WEEKS weeks before the served week) is computed for the
trade charts from data/history/week-N.json natives times the current fixture's
own Indexed factor for that chart and combo (Indexed is one factor per chart
and setting, JEG-482). Projection history holds per-game points, not chart
values, so projection sources use the fixed ceilings only.

    python3 pipelines/check_source_divergence.py [--fixture PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = REPO / "data" / "fixtures" / "current" / "players.json"
HISTORY = REPO / "data" / "history"
RESOLUTIONS = REPO / "data" / "source-divergence-resolutions.json"
OUT = REPO / "output" / "source-divergence.json"
SCHEMA = "source-divergence-v1"

GROUPS = {
    "trade_charts": ("usatoday", "fantasycalc", "fantasypros", "cbs"),
    "projections": ("espn", "cbsros", "razzball"),
}
GROUP_NOUN = {"trade_charts": "the other charts", "projections": "the other projections"}
LABEL = {"usatoday": "USA Today", "fantasycalc": "FantasyCalc", "fantasypros": "FantasyPros", "cbs": "CBS",
         "espn": "ESPN", "cbsros": "CBS rest of season", "razzball": "Razzball"}
SCORINGS = ("standard", "half", "full")
HISTORY_SCORING = {"standard": "standard", "half": "half_ppr", "full": "ppr"}
POSITIONS = ("QB", "RB", "WR", "TE")

MIN_SOURCES = 3
OUTLIER_REL = 0.35
OUTLIER_MIN_PTS = 2.0
WARN_OUTLIER_RATE = 0.45
WARN_BIAS = 5.0
BASELINE_WEEKS = 4
BASELINE_MIN_WEEKS = 2
BASELINE_RATE_MARGIN = 0.15
BASELINE_BIAS_MARGIN = 3.0
POSITION_MIN_N = 8
POSITION_BIAS = 10.0
POSITION_OUTLIER_RATE = 0.75
RESOLUTION_KINDS = ("parser_fix", "mapping_fix", "accepted", "exclude")
RANK = {"ok": 0, "n/a": 0, "warn": 1, "investigate": 2}

CHECKLIST = [
    "Confirm the source URL and article date match the served week.",
    "Confirm the scraped column (base / scoring / 2QB / TEP).",
    "Compare native -> Indexed -> display values against the chart's Indexed factor for 5 sample players.",
    "Resolve it one way: parser fix, mapping/fit fix, or accept as genuine opinion "
    "(record it in data/source-divergence-resolutions.json with a note and the Linear issue).",
]


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def combo_key(source: str, scoring: str) -> str:
    return f"{scoring}_12_qb1" if source == "fantasycalc" else f"{scoring}_12"


def shown_values(combo: dict) -> dict:
    """The values the page shows for a combo: `values` (projection sources) or
    `reindexed` (published charts' Indexed)."""
    return combo.get("values") or combo.get("reindexed") or {}


def by_key(values: dict, name_to_key: dict) -> dict:
    """{player_key: value} for values priced above 0; unmatched names are dropped."""
    out = {}
    for name, value in values.items():
        key, number = name_to_key.get(name), _num(value)
        if key is not None and number is not None and number > 0:
            out[int(key)] = number
    return out


def _summary(devs: list[tuple[float, float]]) -> dict:
    """devs = [(deviation, consensus)]."""
    n = len(devs)
    if not n:
        return {"n": 0, "bias": None, "mad": None, "outlier_rate": None, "outliers": 0}
    outliers = sum(1 for d, c in devs if abs(d) > OUTLIER_REL * c and abs(d) >= OUTLIER_MIN_PTS)
    return {"n": n, "bias": round(sum(d for d, _ in devs) / n, 2),
            "mad": round(sum(abs(d) for d, _ in devs) / n, 2),
            "outlier_rate": round(outliers / n, 3), "outliers": outliers}


def divergence(values: dict, positions: dict) -> dict:
    """Leave-one-out divergence for each source in one group and combo.

    values: {source: {player_key: value > 0}}. positions: {player_key: pos}.
    Returns {source: {n, bias, mad, outlier_rate, outliers, by_position, examples}}."""
    sources = [s for s in values if values[s]]
    players = set().union(*(values[s].keys() for s in sources)) if sources else set()
    devs = {s: [] for s in sources}
    pos_devs = {s: {} for s in sources}
    examples = {s: [] for s in sources}
    for key in players:
        priced = {s: values[s][key] for s in sources if key in values[s]}
        if len(priced) < MIN_SOURCES:
            continue
        for s, v in priced.items():
            consensus = statistics.median([o for t, o in priced.items() if t != s])
            d = v - consensus
            devs[s].append((d, consensus))
            pos_devs[s].setdefault(positions.get(key, "?"), []).append((d, consensus))
            examples[s].append((abs(d), key, round(v, 1), round(consensus, 1)))
    out = {}
    for s in sources:
        row = _summary(devs[s])
        row["by_position"] = {p: _summary(pos_devs[s][p]) for p in sorted(pos_devs[s])}
        row["examples"] = [{"player_key": k, "value": v, "consensus": c}
                           for _, k, v, c in sorted(examples[s], reverse=True)[:5]]
        out[s] = row
    return out


def fixed_breach(row: dict) -> list[str]:
    why = []
    if row.get("outlier_rate") is not None and row["outlier_rate"] > WARN_OUTLIER_RATE:
        why.append(f"outlier rate {row['outlier_rate']:.0%} > {WARN_OUTLIER_RATE:.0%}")
    if row.get("bias") is not None and abs(row["bias"]) > WARN_BIAS:
        why.append(f"bias {row['bias']:+.1f} pts beyond ±{WARN_BIAS:g}")
    return why


def baseline_of(prior_rows: list[dict]) -> dict | None:
    rows = [r for r in prior_rows if r.get("n")]
    if len(rows) < BASELINE_MIN_WEEKS:
        return None
    return {"weeks": len(rows),
            "outlier_rate": round(statistics.mean(r["outlier_rate"] for r in rows), 3),
            "bias": round(statistics.mean(r["bias"] for r in rows), 2)}


def baseline_breach(row: dict, base: dict | None) -> list[str]:
    if not base or not row.get("n"):
        return []
    why = []
    if row["outlier_rate"] > base["outlier_rate"] + BASELINE_RATE_MARGIN:
        why.append(f"outlier rate {row['outlier_rate']:.0%} vs usual {base['outlier_rate']:.0%}")
    if abs(row["bias"] - base["bias"]) > BASELINE_BIAS_MARGIN:
        why.append(f"bias {row['bias']:+.1f} vs usual {base['bias']:+.1f}")
    return why


def position_breach(row: dict) -> list[str]:
    why = []
    for pos, p in (row.get("by_position") or {}).items():
        if p["n"] < POSITION_MIN_N:
            continue
        # Outlier share alone is noisy where values are small (1QB quarterbacks
        # on projection sources): it counts only with a real bias behind it.
        if abs(p["bias"]) > POSITION_BIAS or (p["outlier_rate"] > POSITION_OUTLIER_RATE and abs(p["bias"]) > WARN_BIAS):
            why.append(f"{pos} far out of line (bias {p['bias']:+.1f}, outliers {p['outlier_rate']:.0%}, n={p['n']})")
    return why


def indexed_factor(combo: dict) -> float | None:
    """The chart's one Indexed factor for this combo (median Indexed / native)."""
    native, indexed = combo.get("native") or {}, combo.get("reindexed") or {}
    ratios = [_num(indexed[k]) / _num(native[k]) for k in indexed
              if k in native and _num(native[k]) and _num(indexed[k]) is not None]
    return statistics.median(ratios) if ratios else None


def history_weeks(history_dir: Path, before_week: int | None,
                  limit: int | None = BASELINE_WEEKS) -> list[tuple[int, dict]]:
    """[(week, doc)] for week files before `before_week`, newest first (at most `limit`)."""
    out = []
    if before_week is None or not history_dir.is_dir():
        return out
    for path in history_dir.glob("week-*.json"):
        try:
            week = int(path.stem.split("-", 1)[1])
        except ValueError:
            continue
        if week < before_week:
            out.append((week, json.loads(path.read_text(encoding="utf-8"))))
    out.sort(key=lambda w: -w[0])
    return out if limit is None else out[:limit]


def history_values(doc: dict, sources, scoring: str, factors: dict) -> dict:
    """Trade-chart values for one past week: natives times the current factor."""
    out = {}
    for s in sources:
        entry = (doc.get("sources") or {}).get(s) or {}
        natives = (entry.get("natives") or {}).get(HISTORY_SCORING[scoring]) or {}
        factor = factors.get(s)
        if not factor or not natives:
            continue
        vals = {int(k): _num(v) * factor for k, v in natives.items() if _num(v) is not None and _num(v) > 0}
        if vals:
            out[s] = vals
    return out


def load_resolutions(path: Path) -> tuple[dict, list[str]]:
    """{(source, week): entry} from the resolutions file, plus any problems."""
    if not path.is_file():
        return {}, []
    doc = json.loads(path.read_text(encoding="utf-8"))
    out, problems = {}, []
    for entry in doc.get("resolutions", []):
        kind = entry.get("resolution")
        if kind not in RESOLUTION_KINDS:
            problems.append(f"{entry.get('source')}/week {entry.get('week')}: unknown resolution {kind!r}")
            continue
        if not entry.get("note"):
            problems.append(f"{entry.get('source')}/week {entry.get('week')}: resolution needs a note")
            continue
        if kind == "exclude" and entry.get("inputs_fingerprint"):
            # value_reference applies exclusions by source and week only.
            problems.append(f"{entry.get('source')}/week {entry.get('week')}: exclude cannot be scoped to inputs_fingerprint")
            continue
        out[(entry.get("source"), entry.get("week"))] = entry
    return out, problems


def read_index(history_dir: Path) -> dict:
    index = history_dir / "index.json"
    return json.loads(index.read_text(encoding="utf-8")) if index.is_file() else {}


def served_weeks(fixture: dict, index: dict, content_week: int | None) -> dict:
    """{source: (week, basis, fingerprint)}: the week each source's values are
    served as (JEG-1314), by the shared definition `week_state.source_weeks`
    (the history index's fingerprint match, else the section's own label),
    else the content week. On the Tuesday flip content_week moves before the
    charts publish the new week; labelling a still-served week-N chart N+1
    filed a false "week N+1" flag against week N's article (JEG-1172).
    fingerprint is the served inputs' (index), None when unknown."""
    from week_state import source_weeks
    served = index.get("served") or {}
    out = {}
    for source, rec in source_weeks(fixture, index).items():
        week, basis = rec.get("served_week"), rec.get("basis")
        if not isinstance(week, int) or isinstance(week, bool):
            week, basis = content_week, "content_week"
        fp = (served.get(source) or {}).get("fingerprint") if rec.get("basis") == "history_index" else None
        out[source] = (week, basis, fp)
    return out


def history_fingerprint(doc: dict, source: str) -> str | None:
    return ((doc.get("sources") or {}).get(source) or {}).get("fingerprint")


def message(source: str, group: str, status: str, row: dict, base: dict | None) -> str:
    rate = row.get("outlier_rate")
    if rate is None:
        return f"{LABEL[source]}: not enough shared players to compare."
    usual = f" (usually {base['outlier_rate']:.0%})" if base else ""
    text = f"{LABEL[source]} disagrees with {GROUP_NOUN[group]} on {rate:.0%} of players this week{usual}."
    if status in ("warn", "investigate"):
        text += " Under review."
    elif status == "excluded":
        text += " Excluded from blends."
    elif status == "reviewed":
        text += " Reviewed."
    return text


def run(fixture_path: Path = FIXTURE, players_path: Path = PLAYERS, history_dir: Path = HISTORY,
        resolutions_path: Path = RESOLUTIONS, now: datetime | None = None) -> dict:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    positions = {p["player_key"]: p.get("pos") for p in
                 json.loads(players_path.read_text(encoding="utf-8")).get("players", [])}
    name_to_key = fixture.get("player_keys") or {}
    index = read_index(history_dir)
    week = index.get("content_week") if isinstance(index.get("content_week"), int) else None
    weeks = served_weeks(fixture, index, week)
    # Every saved week before the newest week any source serves; each source
    # then keeps the BASELINE_WEEKS before its own served week.
    newest = max([w for w, _, _ in weeks.values() if isinstance(w, int)] + ([week] if week else []), default=None)
    past = history_weeks(history_dir, None if newest is None else newest + 1, limit=None)
    resolutions, resolution_problems = load_resolutions(resolutions_path)
    sections = fixture.get("sources") or {}

    report_sources = {}
    for group, members in GROUPS.items():
        per_scoring = {}
        for scoring in SCORINGS:
            values, factors = {}, {}
            for s in members:
                combo = ((sections.get(s) or {}).get("combos") or {}).get(combo_key(s, scoring))
                if not combo:
                    continue
                values[s] = by_key(shown_values(combo), name_to_key)
                if group == "trade_charts":
                    factors[s] = indexed_factor(combo)
            now_rows = divergence(values, positions)
            prior = []
            if group == "trade_charts":
                for w, doc in past:
                    prior.append((w, divergence(history_values(doc, members, scoring, factors), positions)))
            per_scoring[scoring] = (now_rows, prior)

        for s in members:
            if s not in sections:
                continue
            s_week, s_basis, s_fp = weeks.get(s, (week, "content_week", None))
            # A saved week with the very inputs served now is the same chart,
            # not a prior week: never its own baseline or "also warned".
            same = {w for w, doc in past if s_fp and history_fingerprint(doc, s) == s_fp}
            combos, status, reasons, chosen = {}, "ok", [], None
            for scoring, (now_rows, prior_all) in per_scoring.items():
                prior = [(w, p) for w, p in prior_all
                         if (s_week is None or w < s_week) and w not in same][:BASELINE_WEEKS]
                row = now_rows.get(s)
                if not row:
                    continue
                prior_rows = [p[s] for _, p in prior if s in p]
                base = baseline_of(prior_rows)
                why = fixed_breach(row) + baseline_breach(row, base)
                pos_why = position_breach(row)
                st = "warn" if why else "ok"
                last = prior[0][1].get(s) if prior else None
                last_base = baseline_of([p[s] for _, p in prior[1:] if s in p]) if prior else None
                last_warned = bool(last and (fixed_breach(last) + baseline_breach(last, last_base)))
                if pos_why or (why and last_warned):
                    st = "investigate"
                    if why and last_warned:
                        why = why + [f"also warned in week {prior[0][0]}"]
                combos[combo_key(s, scoring)] = {**row, "status": st, "baseline": base,
                                                 "reasons": why + pos_why,
                                                 "prior_weeks": [{"week": w, **{k: p[s][k] for k in ("n", "bias", "mad", "outlier_rate")}}
                                                                 for w, p in prior if s in p]}
                # Headline: the worst scoring; on a tie, full PPR (the evidence combo).
                if chosen is None or RANK[st] > RANK[status] or (RANK[st] == RANK[status] and scoring == "full"):
                    status, chosen = st, scoring
                    reasons = [f"{scoring}: {r}" for r in why + pos_why]
            if chosen is None:
                report_sources[s] = {"label": LABEL[s], "group": group, "status": "n/a", "week": s_week,
                                     "week_basis": s_basis,
                                     "message": message(s, group, "n/a", {}, None), "combos": {}}
                continue
            head = combos[combo_key(s, chosen)]
            resolution = resolutions.get((s, s_week))
            # A resolution scoped to the inputs it was decided on (JEG-1314)
            # does not carry over to other inputs served under the same week.
            if resolution and resolution.get("inputs_fingerprint") and resolution["inputs_fingerprint"] != s_fp:
                resolution = None
            # JEG-1337: 'exclude' is keyed by the content week, the week
            # value_reference.load_divergence_exclusions uses, so the report and
            # DDF Value agree on which sources are hidden during the flip.
            if resolution and resolution.get("resolution") == "exclude" and s_week != week:
                resolution_problems.append(
                    f"{s}/week {s_week}: exclude applies by the content week (week {week}); "
                    "DDF Value still blends this source")
                resolution = None
            excluded = resolutions.get((s, week))
            if excluded and excluded.get("resolution") == "exclude":
                resolution = excluded
            # JEG-610 item 2: 'exclude' resolution -> status 'excluded' (hidden from blends
            # and comparisons, held semantics per JEG-569). Other resolutions -> 'reviewed'.
            if resolution and resolution.get("resolution") == "exclude":
                shown = "excluded"
            elif resolution and status != "ok":
                shown = "reviewed"
            else:
                shown = status
            report_sources[s] = {
                "label": LABEL[s], "group": group, "week": s_week, "week_basis": s_basis,
                "status": shown, "computed_status": status,
                "headline_combo": combo_key(s, chosen), "reasons": reasons,
                "n": head["n"], "bias": head["bias"], "mad": head["mad"], "outlier_rate": head["outlier_rate"],
                "usual_outlier_rate": (head["baseline"] or {}).get("outlier_rate"),
                "message": message(s, group, shown, head, head["baseline"]),
                "resolution": resolution, "combos": combos,
            }

    flagged = [v["label"] for v in report_sources.values() if v["status"] in ("warn", "investigate")]
    return {
        "schema": SCHEMA,
        "generated_at": (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
        "fixture_built_at": fixture.get("built_at"),
        "week": week,
        "blocking": False,
        "status": "warn" if flagged else "ok",
        "thresholds": {"min_sources": MIN_SOURCES, "outlier_rel": OUTLIER_REL, "outlier_min_pts": OUTLIER_MIN_PTS,
                       "warn_outlier_rate": WARN_OUTLIER_RATE, "warn_bias": WARN_BIAS,
                       "baseline_weeks": BASELINE_WEEKS, "baseline_min_weeks": BASELINE_MIN_WEEKS,
                       "baseline_rate_margin": BASELINE_RATE_MARGIN, "baseline_bias_margin": BASELINE_BIAS_MARGIN,
                       "position_min_n": POSITION_MIN_N, "position_bias": POSITION_BIAS,
                       "position_outlier_rate": POSITION_OUTLIER_RATE},
        "summary": {"flagged": flagged,
                    "investigate": [v["label"] for v in report_sources.values() if v["status"] == "investigate"],
                    "reviewed": [v["label"] for v in report_sources.values() if v["status"] == "reviewed"],
                    "excluded": [s for s, v in report_sources.items() if v["status"] == "excluded"],
                    "resolution_problems": resolution_problems},
        "checklist": CHECKLIST,
        "sources": report_sources,
    }


def freshness_summary(report: dict) -> dict:
    """The per-source slice written into reference-freshness.json."""
    return {s: {k: v.get(k) for k in ("label", "status", "message", "outlier_rate", "usual_outlier_rate",
                                       "bias", "headline_combo", "week")}
            | {"resolution_issue": (v.get("resolution") or {}).get("issue"),
               "resolution_kind": (v.get("resolution") or {}).get("resolution")}
            for s, v in report.get("sources", {}).items()}


def run_soft(out: Path = OUT, copies=(), **kwargs) -> dict:
    """Run the check without ever raising: any error becomes status 'error' in
    the written report. This is what `make sync` calls."""
    try:
        report = run(**kwargs)
    except Exception as exc:  # noqa: BLE001 -- a soft check never stops the build
        report = {"schema": SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                  "blocking": False, "status": "error", "error": f"{type(exc).__name__}: {exc}",
                  "summary": {"flagged": [], "investigate": [], "reviewed": [], "resolution_problems": []},
                  "sources": {}}
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    for path in (out, *copies):
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"WARNING: source divergence report not written to {path}: {exc}", file=sys.stderr)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fixture", type=Path, default=FIXTURE)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--players", type=Path, default=PLAYERS)
    ap.add_argument("--history", type=Path, default=HISTORY)
    args = ap.parse_args(argv)
    report = run_soft(args.out, fixture_path=args.fixture, players_path=args.players, history_dir=args.history)
    for s, v in report.get("sources", {}).items():
        print(f"{v['status']:<11} {v['label']:<20} {v['message']}" + (f"  [{'; '.join(v.get('reasons') or [])}]" if v.get("reasons") else ""))
    if report.get("error"):
        print("ERROR (non-blocking):", report["error"])
    return 0  # a warning, never a gate


if __name__ == "__main__":
    raise SystemExit(main())
