#!/usr/bin/env python3
"""Bench-decay evidence benchmark (JEG-1276, parent JEG-948).

Replays the bench-decay research that is already committed (post 1 / PR #846,
JEG-943 / PR #847, JEG-528 / PR #604) from a fixed manifest, offline, and
writes one evidence matrix. It computes nothing new about player value: every
number is either read from a pinned artifact (measured or historical) or is
plain arithmetic on those numbers that the research itself states
(hypothetical, labelled as such).

Checks, all fatal:
- every source's sha256 matches the manifest (a changed artifact needs a new
  manifest, not a silent rerun);
- no capture date after the manifest's as_of date, and no content later than
  its capture date (future or leaked dates);
- every expected horizon is present (content weeks 1-17 for the model series,
  measure weeks 4-16 for the breakout series);
- a missing value stays "missing" and is never shown as 0; a real 0 stays 0.

A required source that is absent is reported as a gap, not filled in.

Usage:
    python3 tools/research/bench-decay-evidence/bench_decay_evidence.py
    python3 tools/research/bench-decay-evidence/bench_decay_evidence.py --check

Research only. No engine, spec, reference, Supabase or value-policy change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "pipelines"))
from nfl_week import CONTENT_WEEK_1_START  # noqa: E402

EVIDENCE_DIR = REPO / "docs" / "research" / "bench-decay-evidence"
MANIFEST = EVIDENCE_DIR / "manifest.json"
OUT_DIR = EVIDENCE_DIR / "output"
POSITIONS = ("QB", "RB", "WR", "TE")
MODEL_WEEKS = tuple(range(1, 18))
BREAKOUT_WEEKS = tuple(range(4, 17))


class EvidenceError(Exception):
    """A manifest or source fails a check. Never caught to keep going."""


class _Missing:
    """A value the source does not have. Distinct from 0 and from n/a."""

    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()
NA = "n/a"  # not a sample statistic (model output, arithmetic)


def get(obj, *path):
    """Walk dicts and lists; return MISSING (never 0) where a key is absent or None."""
    cur = obj
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        elif isinstance(cur, list) and isinstance(key, int) and 0 <= key < len(cur):
            cur = cur[key]
        else:
            return MISSING
        if cur is None:
            return MISSING
    return cur


def show(value):
    """JSON-safe form: MISSING becomes the string 'missing', never 0."""
    if value is MISSING:
        return "missing"
    if isinstance(value, float):
        return round(value, 4)
    return value


def _date(text: str, field: str) -> date:
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field}: not an ISO date: {text!r}") from exc


def content_week_end(season: int, week: int) -> date:
    """Last day (Monday) of a content week, from the one NFL calendar."""
    if season != CONTENT_WEEK_1_START.year:
        raise EvidenceError(f"content week dates exist only for season {CONTENT_WEEK_1_START.year}, not {season}")
    return CONTENT_WEEK_1_START + timedelta(days=7 * week - 1)


def content_end(entry: dict) -> date | None:
    """The latest date the source's content covers (None for a season range checked by year)."""
    content = entry.get("content") or {}
    kind = content.get("kind")
    if kind == "content_weeks":
        return content_week_end(content["season"], content["last_week"])
    if "content_end_date" in content:
        return _date(content["content_end_date"], f"{entry['id']}.content_end_date")
    if kind == "seasons":
        return None
    raise EvidenceError(f"{entry['id']}: content has no end date")


def validate_dates(manifest: dict) -> None:
    as_of = _date(manifest.get("as_of"), "as_of")
    for entry in list(manifest.get("sources", [])) + list(manifest.get("rules", [])):
        eid = entry.get("id", "?")
        capture = _date(entry.get("capture_date"), f"{eid}.capture_date")
        source = _date(entry.get("source_date"), f"{eid}.source_date")
        if capture > as_of:
            raise EvidenceError(f"{eid}: capture date {capture} is after as_of {as_of} (future date)")
        if source > as_of:
            raise EvidenceError(f"{eid}: source date {source} is after as_of {as_of} (future date)")
        if "content" not in entry:
            continue
        end = content_end(entry)
        if end is not None and end > capture:
            raise EvidenceError(f"{eid}: content runs to {end}, after its capture date {capture} (leaked date)")
        content = entry["content"]
        if content.get("kind") == "seasons" and content["last_season"] >= capture.year:
            raise EvidenceError(
                f"{eid}: season {content['last_season']} was not complete at capture {capture} (leaked date)")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_sources(manifest: dict, root: Path) -> tuple[dict, list]:
    """Load every source at its pinned hash. Absent sources become gaps."""
    data, gaps = {}, []
    for entry in manifest.get("sources", []):
        path = root / entry["path"]
        if not path.exists():
            gaps.append({
                "id": f"absent:{entry['id']}",
                "what": f"{entry['path']} is not in the tree",
                "effect": "rows from this source are reported as missing" if entry.get("required")
                else "context only; no rows depend on it",
            })
            data[entry["id"]] = MISSING
            continue
        digest = sha256(path)
        if digest != entry["sha256"]:
            raise EvidenceError(
                f"{entry['id']}: sha256 {digest} does not match the manifest {entry['sha256']}; "
                "the artifact changed, so the manifest must be re-pinned on purpose")
        data[entry["id"]] = json.loads(path.read_text()) if path.suffix == ".json" else None
    return data, gaps


def check_rules(manifest: dict, root: Path) -> list:
    """Each pinned rule line must still be in its file; report the state."""
    out = []
    for rule in manifest.get("rules", []):
        lines = []
        for need in rule["must_contain"]:
            path = root / need["path"]
            text = path.read_text() if path.exists() else ""
            present = any(line.strip() == need["line"].strip() for line in text.splitlines())
            lines.append({"path": need["path"], "present": present})
        out.append({"id": rule["id"], "statement": rule["statement"], "lines": lines,
                    "all_present": all(item["present"] for item in lines)})
    return out


def require_horizons(rows, key: str, expected: tuple, label: str) -> dict:
    if rows is MISSING or not isinstance(rows, list):
        raise EvidenceError(f"{label}: series is missing")
    by_week = {}
    for row in rows:
        week = get(row, key)
        if week is MISSING:
            raise EvidenceError(f"{label}: a row has no {key}")
        if week in by_week:
            raise EvidenceError(f"{label}: {key} {week} appears twice")
        by_week[week] = row
    absent = [w for w in expected if w not in by_week]
    if absent:
        raise EvidenceError(f"{label}: missing horizons {absent}")
    return by_week


def _row(rid, component, evidence, window, cohort, n, metric, values, source, note=""):
    return {"id": rid, "component": component, "evidence": evidence, "window": window,
            "cohort": cohort, "n": show(n), "metric": metric,
            "values": {k: show(v) for k, v in values.items()}, "source": source, "note": note}


def fill_in_rows(data: dict, timing: dict) -> list:
    rows = []
    bvw = data.get("post1_bench_by_week", MISSING)
    if bvw is MISSING:
        return rows
    model = require_horizons(get(bvw, "model_bench_share_by_week"), "content_week", MODEL_WEEKS,
                             "post1_bench_by_week.model_bench_share_by_week")
    fsw = timing["full_season_weeks"]
    for week in MODEL_WEEKS:
        r = model[week]
        rem = get(r, "remaining_weeks")
        if rem is MISSING:
            raise EvidenceError(f"model week {week}: remaining_weeks is missing")
        share = get(r, "bench_share_overall")
        vals = {"remaining_weeks": rem, "bye_share": get(r, "bye_share"), "bench_share": share}
        vals.update({f"bench_share_{p}": get(r, "bench_share_by_pos", p) for p in POSITIONS})
        rows.append(_row(f"F1.w{week:02d}", "fill-in insurance", "measured (engine at capture)",
                         f"content week {week}, {rem} weeks left", "12-team PPR engine fixture", NA,
                         "per-week bench share of the value pie", vals, "post1_bench_by_week"))
        # Same as #604: an empty window (w1 < w0) leaves the factor at 1.
        timing_factor = min(1.0, rem / fsw) if rem >= 1 else 1.0
        hyp = {"remaining_weeks": rem,
               "share_x_weeks": share * rem if share is not MISSING else MISSING,
               "timing_factor_604": timing_factor,
               "share_x_timing_factor_604": share * timing_factor
               if share is not MISSING and timing_factor is not MISSING else MISSING}
        rows.append(_row(f"F4.w{week:02d}", "fill-in insurance", "hypothetical (arithmetic)",
                         f"content week {week}, {rem} weeks left", "12-team PPR engine fixture", NA,
                         "rest-of-season bench share-weeks and the #604 timing series", hyp,
                         "post1_bench_by_week + jeg528_timing_factor",
                         "share x weeks is the artifact's own stated implication; the engine does not compute it"))
    return rows


def hazard_rows(data: dict) -> list:
    snap = data.get("jeg528_lineup_m", MISSING)
    if snap is MISSING:
        return []
    rows = []
    for pos in POSITIONS:
        m_all = get(snap, "positions", pos, "m", "all")
        rows.append(_row(f"F2.{pos}", "fill-in insurance", "historical",
                         "seasons 2015-2025", f"{pos}, per game", MISSING,
                         "missed-game rate m (all seasons, recency-weighted) and m_late (playoff weeks)",
                         {"m_all": m_all, "m_recent": get(snap, "positions", pos, "m", "recent"),
                          "m_late_all": get(snap, "positions", pos, "m_late", "all"),
                          "m_late_recent": get(snap, "positions", pos, "m_late", "recent")},
                         "jeg528_lineup_m", "the config holds rates only; game counts are not in it"))
        vals = {}
        for k in (12, 8, 3, 1):
            vals[f"p_miss_ge1_in_{k}"] = 1 - (1 - m_all) ** k if m_all is not MISSING else MISSING
        rows.append(_row(f"F3.{pos}", "fill-in insurance", "hypothetical (arithmetic)",
                         "k weeks left", f"{pos} starter", NA,
                         "chance of at least one missed game in k weeks, 1-(1-m)^k",
                         vals, "jeg528_lineup_m", "assumes weeks are independent, as JEG-528's 86%/39% figures do"))
    return rows


def option_rows(data: dict) -> list:
    rows = []
    bvw = data.get("post1_bench_by_week", MISSING)
    if bvw is not MISSING:
        series = require_horizons(get(bvw, "breakout_rate_by_week"), "measure_week", BREAKOUT_WEEKS,
                                  "post1_bench_by_week.breakout_rate_by_week")
        for week in BREAKOUT_WEEKS:
            r = series[week]
            rows.append(_row(f"O1.w{week:02d}", "option value", "historical",
                             f"measured from week {week}, {show(get(r, 'weeks_remaining'))} weeks left (approx)",
                             "every non-starter with a game log, 12-team tiers", MISSING,
                             "share who finish in the starter tier",
                             {p: get(r, "breakout_rate", p) for p in POSITIONS}, "post1_bench_by_week",
                             "the artifact stores rates only; cohort sizes and breakout counts are missing"))
    br = data.get("post1_breakout_rate", MISSING)
    if br is not MISSING:
        for pos in POSITIONS:
            p = get(br, "positions", pos)
            lo, hi = get(p, "rate_range", 0), get(p, "rate_range", 1)
            rows.append(_row(f"O2.{pos}", "option value", "historical", "measured from week 9",
                             f"{pos}, every non-starter with a game log", get(p, "bench_at_mid"),
                             "breakout rate, with the range across 11 seasons",
                             {"breakouts": get(p, "breakouts"), "rate": get(p, "overall_rate"),
                              "season_low": lo, "season_high": hi}, "post1_breakout_rate"))
            for depth in (1, 2, 3):
                d = get(p, "by_depth", f"depth_{depth}")
                rows.append(_row(f"O3.{pos}.d{depth}", "option value", "historical", "measured from week 9",
                                 f"{pos} backup #{depth} (12 teams x 11 seasons)", get(d, "total"),
                                 "breakout rate by depth", {"breakouts": get(d, "breakouts"),
                                                            "rate": get(d, "rate")}, "post1_breakout_rate"))
    risk = data.get("post1_starter_bench_risk", MISSING)
    if risk is not MISSING:
        for pos in POSITIONS + ("overall",):
            p = get(risk, "positions", pos)
            rows.append(_row(f"O4.{pos}", "option value", "measured (engine at capture)",
                             "one snapshot at capture, no by-week series",
                             f"{pos}, engine starters and bench", get(p, "bench_count"),
                             "bench upside vs starter downside, % of pie",
                             {"bench_upside_pct": get(p, "bench_upside_pct_of_pie"),
                              "starter_downside_pct": get(p, "starter_downside_pct_of_pie")},
                             "post1_starter_bench_risk",
                             "n is the bench players priced; the overall row has no count"))
    return rows


def aggregation_rows(data: dict) -> list:
    sa = data.get("jeg943_source_accuracy", MISSING)
    if sa is MISSING:
        return []
    rows = []
    for name in ("espn", "cbsros", "razzball", "espn_weekly", "equal_mean"):
        s = get(sa, "summary", name)
        rows.append(_row(f"A1.{name}", "projection accuracy over time", "measured",
                         "2026 content weeks 2-6", f"{name} rest-of-season per game vs weekly actuals",
                         get(s, "n"), "MAE with 95% CI",
                         {"mae": get(s, "mae"), "ci_lo": get(s, "mae_ci_lo"), "ci_hi": get(s, "mae_ci_hi")},
                         "jeg943_source_accuracy",
                         "no lead-time split: it cannot show how accuracy decays with weeks ahead"))
    return rows


# Gaps found in the committed research. Each one is a fact about an artifact or
# its generator at the pinned commit, found by reading it; none is fixed here.
METHOD_GAPS = [
    {"id": "G1", "what": "The breakout-by-week series stores rates without cohort sizes or breakout counts.",
     "effect": "No sample count or confidence interval for the option-value decay curve.",
     "owner": "post 1 research script (JEG-544 lane)"},
    {"id": "G2", "what": "tools/research/bench_value_by_week.py and breakout_rate.py score breakouts with half_ppr, falling back to std, then 0, though the actuals file has a ppr column and the by-week artifact is labelled ppr.",
     "effect": "The scoring of the option-value series differs from its label, and a blank score is read as 0.",
     "owner": "post 1 research script (JEG-544 lane)"},
    {"id": "G3", "what": "A breakout is defined by full-season points per game, which includes the weeks before the measure week.",
     "effect": "A player who scores like a starter for the weeks left but not for the season is not counted, so part of the late fall comes from the target definition, not runway alone.",
     "owner": "post 1 research script (JEG-544 lane)"},
    {"id": "G4", "what": "weeks_remaining in the breakout series is 17 minus the measure week for every season, though 2021-2025 have 18 weeks.",
     "effect": "The weeks-left axis is approximate for half the seasons.",
     "owner": "post 1 research script (JEG-544 lane)"},
    {"id": "G5", "what": "The breakout cohort is every non-starter with a game log, not rostered bench players.",
     "effect": "The by-week rates (1-6%) are not on the same scale as the by-depth rates (2-27%).",
     "owner": "post 1 research script (JEG-544 lane)"},
    {"id": "G6", "what": "No week-ahead projections are stored by lead time; the JEG-943 backtest compares rest-of-season projections with single weeks over 5 weeks.",
     "effect": "No measured basis for a per-week discount (JEG-528 item 2); its Done-when is unmet.",
     "owner": "JEG-943 / JEG-944 storage"},
    {"id": "G7", "what": "Option value (#604 optionValue) and starter-vs-bench risk exist only as one snapshot, not by content week.",
     "effect": "No measured option-value decay on the engine itself.",
     "owner": "JEG-530 series"},
    {"id": "G8", "what": "Post 1's sensitivity table gives 10.0% bench share at PPR/12; the by-week artifact gives 8.7% at week 1 for the same setting.",
     "effect": "The two published numbers come from different engine states or definitions; which one holds today is unchecked.",
     "owner": "post 1 (JEG-544)"},
    {"id": "G10", "what": "At content week 17 the objective window is empty (week 18 to 17), and the #604 timing rule then leaves its factor at 1, so the timing series goes from 1/17 at week 16 back to full at week 17.",
     "effect": "The existing timing series is not monotone at the last week; it is a separate series, not DDF Value.",
     "owner": "JEG-528 (#604 series)"},
    {"id": "G9", "what": "The engine fixture date behind the by-week model series is not recorded; game counts behind m are not in the config.",
     "effect": "The model series' content date is bounded by its capture date only, and m has no sample count here.",
     "owner": "post 1 research script; derive_lineup_parameters.py"},
]


def build(manifest: dict, root: Path) -> dict:
    validate_dates(manifest)
    data, absent = load_sources(manifest, root)
    rules = check_rules(manifest, root)
    timing = next((r for r in manifest.get("rules", []) if r["id"] == "jeg528_timing_factor"), None)
    if timing is None:
        raise EvidenceError("the #604 timing rule is not in the manifest")
    rows = fill_in_rows(data, timing) + hazard_rows(data) + option_rows(data) + aggregation_rows(data)
    rows.sort(key=lambda r: r["id"])
    gaps = absent + sorted(METHOD_GAPS, key=lambda g: int(g["id"][1:]))
    for rule in rules:
        if not rule["all_present"]:
            gaps.append({"id": f"rule:{rule['id']}", "what": "a pinned rule line is no longer in the code",
                         "effect": "the memo's description of the #604 series may be stale",
                         "owner": "JEG-528"})
    return {
        "schema": "bench-decay-evidence-matrix/1",
        "ticket": manifest["ticket"],
        "as_of": manifest["as_of"],
        "baseline": manifest["baseline"],
        "setting": manifest["setting"],
        "sources": [{k: e.get(k) for k in ("id", "path", "origin", "source_date", "capture_date", "sha256")}
                    for e in manifest["sources"]],
        "rules": rules,
        "evidence_classes": {
            "measured (engine at capture)": "the engine's own output when the artifact was captured",
            "measured": "computed on 2026 data",
            "historical": "computed on 2015-2025 game logs",
            "hypothetical (arithmetic)": "arithmetic on the numbers above; not a model output",
        },
        "rows": rows,
        "gaps": gaps,
    }


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_md(result: dict) -> str:
    out = ["# Bench-decay evidence matrix", "",
           f"Ticket {result['ticket']}. As of {result['as_of']}. Baseline {result['baseline']['branch']} "
           f"{result['baseline']['commit']}. Setting {result['setting']['scoring']} / {result['setting']['teams']} teams.",
           "", "Generated by `tools/research/bench-decay-evidence/bench_decay_evidence.py`. Do not edit by hand.",
           "", "## Sources", "", "| Id | Path | Origin | Source date | Capture date | sha256 |", "|---|---|---|---|---|---|"]
    for s in result["sources"]:
        out.append(f"| {s['id']} | `{s['path']}` | {s['origin']} | {s['source_date']} | {s['capture_date']} | "
                   f"`{s['sha256'][:12]}` |")
    out += ["", "## Pinned rules", ""]
    for r in result["rules"]:
        state = "present" if r["all_present"] else "NOT PRESENT"
        out.append(f"- {r['id']}: {r['statement']} Lines {state} in "
                   + ", ".join(f"`{x['path']}`" for x in r["lines"]) + ".")
    out += ["", "## Evidence classes", ""]
    out += [f"- {k}: {v}" for k, v in result["evidence_classes"].items()]
    groups = {}
    for row in result["rows"]:
        groups.setdefault(row["id"].split(".")[0], []).append(row)
    for gid in sorted(groups):
        rows = groups[gid]
        first = rows[0]
        keys = list(first["values"].keys())
        out += ["", f"## {gid}: {first['component']}, {first['evidence']}", "",
                f"Metric: {first['metric']}. Source: {first['source']}." + (f" Note: {first['note']}" if first["note"] else ""),
                "", "| Id | Window | Cohort | n | " + " | ".join(keys) + " |",
                "|---|---|---|---|" + "---|" * len(keys)]
        for row in rows:
            out.append(f"| {row['id']} | {row['window']} | {row['cohort']} | {_fmt(row['n'])} | "
                       + " | ".join(_fmt(row["values"].get(k, "missing")) for k in keys) + " |")
    out += ["", "## Gaps", "", "| Id | What | Effect | Owner |", "|---|---|---|---|"]
    for g in result["gaps"]:
        out.append(f"| {g['id']} | {g['what']} | {g['effect']} | {g.get('owner', '')} |")
    return "\n".join(out) + "\n"


def outputs(result: dict) -> dict:
    return {"evidence_matrix.json": json.dumps(result, indent=1, sort_keys=True) + "\n",
            "evidence_matrix.md": render_md(result)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--root", type=Path, default=REPO)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--check", action="store_true", help="fail if the committed outputs differ from a rerun")
    args = ap.parse_args(argv)
    try:
        result = build(json.loads(args.manifest.read_text()), args.root)
    except EvidenceError as exc:
        print(f"bench-decay evidence: FAIL: {exc}", file=sys.stderr)
        return 2
    files = outputs(result)
    if args.check:
        stale = [n for n, text in files.items()
                 if not (args.out_dir / n).exists() or (args.out_dir / n).read_text() != text]
        if stale:
            print(f"bench-decay evidence: outputs differ from a rerun: {stale}", file=sys.stderr)
            return 1
        print(f"bench-decay evidence: OK, {len(result['rows'])} rows, {len(result['gaps'])} gaps, outputs match")
        return 0
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (args.out_dir / name).write_text(text)
    print(f"bench-decay evidence: wrote {len(result['rows'])} rows, {len(result['gaps'])} gaps to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
