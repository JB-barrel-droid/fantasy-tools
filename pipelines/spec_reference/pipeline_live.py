"""Clean-room value pipeline (JEG-508) on the live snapshot, every value dumped.

Run (also reachable as `compare.py pipeline ...`):

    python3 pipelines/spec_reference/compare.py pipeline \
        [--fixture data/fixtures/current/comparison-sources-data.json] \
        [--players data/fixtures/current/players.json] [--history data/history] \
        [--out output/spec-reference/pipeline-values.json]

Inputs (data files only):
- current week: the fixture's sections. Projections (espn, cbsros, razzball):
  `combos["<scoring>_<T>"].native` (points per game, keyed by name). Charts
  (cbs, fantasycalc, fantasypros, usatoday): the saved 12-team list
  `combos["<scoring>_12"]` (fantasycalc `_12_qb1`) `.native`, with
  `.native_superflex` overlaid at SF >= 1. Names map to player_key through
  the fixture's `player_keys`.
- positions: the naming table `players.json` (`player_key` -> `pos`).
- prior week: `data/history/week-<content_week - 1>.json` (`natives[scoring]`
  for charts, `ppg[key][scoring index]` for projections); the content week
  and each source's served week come from `data/history/index.json`.

Output shape (schema "spec-reference-pipeline/1"):

    {schema, version, generated_at,
     inputs: {fixture, fixture_built_at, players, history_index, content_week,
              prior_week, dropped_unpositioned: {source: n}},
     settings: {"<scoring>/<teams>/sf<SF>": {
        setting: {scoring, teams, slots, flex, superflex, bench_per_team, bench_share},
        included: [source], excluded: [{key, reason}], has_prior_week: bool,
        pie, bench_share_applied, ddf_weights: {"POS|starter"|"POS|bench": w},
        starter_mix_mean, bench_mix_mean,
        allocation: {pos: {dedicated, superflex, flex, bench, starters, rostered}},
        fill_sets: {pos: [player_key]},
        sources: {source: {family, status, groups, total_vorp, weights,
                  starter_mix, bench_mix, rates, unfunded_moved,
                  unfunded_groups, vorp_factor, indexed_factor,
                  positions: {pos: {method, waiver, starter_line, starters,
                     rostered, listed, n_estimated,
                     estimates: {player_key: {path, peers, curve, raw, cap,
                                              capped, value}}}}}},
        values: {view: {series: {player_key: value | null}}},
        rows: {player_key: {pos, mean_ppg, ddf_tier, estimated: {source: path},
               ddf: {blended|charts|projections: {value, count, sources,
                     low_confidence, reason?, prior, prior_count,
                     prior_low_confidence, change}}}},
        prior: {included, ddf_weights, allocation, pie} | null}}}

`values` follows the front-end contract (VP-11): view "indexed" (charts:
Indexed; projections: Adjusted), "vorp" (charts: V; `<proj>_vorp`: V),
"adjusted" (all seven: A), and in every view `ddf_value`,
`ddf_value_charts`, `ddf_value_projections` plus their `*_prior`. Every row
player appears in every series (null where VP-6.2 gives null). Player keys
are JSON strings of the integer player_key.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "spec_reference"  # noqa: A001

from spec_reference import value_pipeline as vp  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SCHEMA = "spec-reference-pipeline/1"
PROJECTIONS = ("espn", "cbsros", "razzball")
CHARTS = ("cbs", "fantasycalc", "fantasypros", "usatoday")
SOURCE_ORDER = PROJECTIONS + CHARTS
SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)
COMBO_SCORING = {"standard": "standard", "half_ppr": "half", "ppr": "full"}
HIST_INDEX = {"standard": 0, "half_ppr": 1, "ppr": 2}
# Default roster (SA-12): QB1 RB2 WR3 TE1 FLEX1 BENCH6, 8 starters per team.
DEFAULT_SLOTS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
SUPERFLEX_COMBO = ("ppr", 12)


def settings_list() -> list:
    out = [(sc, t, 0) for sc in SCORINGS for t in TEAMS]
    out.append((SUPERFLEX_COMBO[0], SUPERFLEX_COMBO[1], 1))
    return out


def setting_id(scoring: str, teams: int, sf: int) -> str:
    return f"{scoring}/{teams}/sf{sf}"


def default_paths(repo: Path = REPO) -> dict:
    return {"fixture": repo / "data" / "fixtures" / "current" / "comparison-sources-data.json",
            "players": repo / "data" / "fixtures" / "current" / "players.json",
            "history": repo / "data" / "history",
            "out": repo / "output" / "spec-reference" / "pipeline-values.json"}


def load(paths: dict) -> dict:
    fx = json.loads(Path(paths["fixture"]).read_text(encoding="utf-8"))
    players = json.loads(Path(paths["players"]).read_text(encoding="utf-8"))["players"]
    hist_dir = Path(paths["history"])
    index_path = hist_dir / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    content_week = index.get("content_week")
    prior = None
    if content_week:
        p = hist_dir / f"week-{int(content_week) - 1}.json"
        if p.exists():
            prior = json.loads(p.read_text(encoding="utf-8"))
    pos_of = {int(p["player_key"]): p.get("pos") for p in players
              if p.get("pos") in vp.POS_ORDER}
    names = {int(p["player_key"]): p.get("name") for p in players}
    return {"fixture": fx, "pos_of": pos_of, "names": names, "index": index,
            "content_week": content_week, "prior": prior, "paths": paths}


def _combo(section: dict, scoring: str, teams: int) -> dict | None:
    combos = section.get("combos") or {}
    key = f"{COMBO_SCORING[scoring]}_{teams}"
    return combos.get(key) or combos.get(key + "_qb1")


def current_natives(data: dict, s: str, scoring: str, teams: int, sf: int, dropped: dict) -> dict | None:
    fx = data["fixture"]
    section = (fx.get("sources") or {}).get(s)
    if not section:
        return None
    combo = _combo(section, scoring, teams if s in PROJECTIONS else 12)
    if not combo or not combo.get("native"):
        return None
    name_keys = fx.get("player_keys") or {}
    out = {}
    miss = 0

    def put(name, value, overlay=False):
        nonlocal miss
        k = name_keys.get(name)
        if k is None or value is None or int(k) not in data["pos_of"]:
            miss += 1
            return
        if overlay and int(k) not in out:
            return     # SA-2: the overlay replaces, it never adds a player
        out[int(k)] = float(value)

    for name, v in combo["native"].items():
        put(name, v)
    if sf >= 1 and s in CHARTS:
        for name, v in (combo.get("native_superflex") or {}).items():
            put(name, v, overlay=True)
    dropped[s] = dropped.get(s, 0) + miss
    return out


def prior_natives(data: dict, s: str, scoring: str) -> dict | None:
    week = data["prior"]
    if not week:
        return None
    entry = (week.get("sources") or {}).get(s)
    if not entry or not entry.get("complete"):
        return None
    pos_of = data["pos_of"]
    if s in CHARTS:
        nat = (entry.get("natives") or {}).get(scoring)
        if not nat:
            return None
        return {int(k): float(v) for k, v in nat.items() if v is not None and int(k) in pos_of}
    ppg = entry.get("ppg") or {}
    i = HIST_INDEX[scoring]
    out = {int(k): float(v[i]) for k, v in ppg.items()
           if isinstance(v, list) and len(v) > i and v[i] is not None and int(k) in pos_of}
    return out or None


def eligibility(data: dict, s: str, natives: dict | None) -> str | None:
    """VP-1.1: None when eligible, else the reason."""
    section = (data["fixture"].get("sources") or {}).get(s) or {}
    if section.get("validationHold") or section.get("promotionHold"):
        return "held"
    served = ((data["index"].get("served") or {}).get(s) or {}).get("week")
    cw = data["content_week"]
    if s in CHARTS and served is not None and cw is not None and served < cw:
        return "unpublished"
    if not natives:
        return "no values at this setting"
    return None


def _jkeys(d: dict | None) -> dict | None:
    if d is None:
        return None
    return {str(k): v for k, v in d.items()}


def run_setting(data: dict, scoring: str, teams: int, sf: int, dropped: dict) -> dict:
    setting = vp.Setting(teams=teams, slots=dict(DEFAULT_SLOTS), flex=1, superflex=sf,
                         bench_per_team=6, bench_share=vp.DEFAULT_BENCH_SHARE)
    current, prior, eligible, excluded = {}, {}, [], []
    for s in SOURCE_ORDER:
        nat = current_natives(data, s, scoring, teams, sf, dropped)
        reason = eligibility(data, s, nat)
        fam = vp.PROJECTION if s in PROJECTIONS else vp.CHART
        if nat:
            current[s] = {"family": fam, "values": nat, "status": reason or "eligible"}
        if reason:
            excluded.append({"key": s, "reason": reason})
            continue
        eligible.append(s)
        pn = prior_natives(data, s, scoring)
        if pn:
            prior[s] = {"family": fam, "values": pn}
    included, has_prior = vp.included_set(eligible, {s: s in prior for s in eligible})
    for s in eligible:
        if s not in included:
            excluded.append({"key": s, "reason": "no prior week"})
            current[s]["status"] = "no prior week"
    res = vp.run(setting, data["pos_of"], current, prior if has_prior else None, included,
                 names=data["names"])
    cur = res["current"]
    views = {"indexed": {}, "vorp": {}, "adjusted": {}}
    for s in current:
        a = {str(k): r["adjusted"][s] for k, r in cur["rows"].items()}
        v = {str(k): r["vorp_vs_waivers"][s] for k, r in cur["rows"].items()}
        views["adjusted"][s] = a
        if s in CHARTS:
            views["indexed"][s] = {str(k): r["indexed"].get(s) for k, r in cur["rows"].items()}
            views["vorp"][s] = v
        else:
            views["indexed"][s] = a
            views["vorp"][f"{s}_vorp"] = v
    for key, fld in (("ddf_value", "ddf_blended"), ("ddf_value_charts", "ddf_charts"),
                     ("ddf_value_projections", "ddf_projections")):
        series = {str(k): r[fld]["value"] for k, r in cur["rows"].items()}
        prior_series = {str(k): r[fld].get("prior") for k, r in cur["rows"].items()}
        for view in views.values():
            view[key] = series
            view[f"{key}_prior"] = prior_series
    sources = {}
    for s, r in cur["sources"].items():
        pos = {}
        for p, info in r["positions"].items():
            est = info.get("imputation_ratios") or {}
            pos[p] = {"method": info["method"], "waiver": info["waiver_value"],
                      "starter_line": info["starter_line"], "starters": info["starters"],
                      "rostered": info["rostered"], "listed": info["listed"], "n_estimated": len(est),
                      "estimates": {str(k): e for k, e in est.items()}}
        sources[s] = {"family": r["family"], "status": r["status"], "groups": r["groups"],
                      "total_vorp": r["total_vorp"], "weights": r["weights"],
                      "starter_mix": r["starter_mix"], "bench_mix": r["bench_mix"], "rates": r["rates"],
                      "unfunded_moved": r["unfunded_moved"], "unfunded_groups": r["unfunded_groups"],
                      "vorp_factor": r["vorp_display_factor"], "indexed_factor": r.get("indexed_factor"),
                      "positions": pos}
    rows = {}
    for k, r in cur["rows"].items():
        rows[str(k)] = {"pos": r["pos"], "mean_ppg": r["mean_ppg"], "ddf_tier": r["ddf_tier"],
                        "estimated": r["estimated"],
                        "ddf": {"blended": r["ddf_blended"], "charts": r["ddf_charts"],
                                "projections": r["ddf_projections"]}}
    pw = res["prior"]
    return {
        "setting": {"scoring": scoring, "teams": teams, "slots": setting.slots, "flex": setting.flex,
                    "superflex": sf, "bench_per_team": setting.bench_per_team,
                    "bench_share": setting.bench_share},
        "included": cur["included"], "excluded": excluded, "has_prior_week": has_prior,
        "pie": cur["pie"], "bench_share_applied": cur["bench_share_applied"],
        "ddf_weights": cur["ddf_weights"], "starter_mix_mean": cur["starter_mix_mean"],
        "bench_mix_mean": cur["bench_mix_mean"], "allocation": cur["allocation"],
        "fill_sets": cur["fill_sets"], "sources": sources, "values": views, "rows": rows,
        "prior": ({"included": pw["included"], "ddf_weights": pw["ddf_weights"],
                   "allocation": pw["allocation"], "pie": pw["pie"]} if pw else None),
    }


def build(paths: dict | None = None, only: list | None = None) -> dict:
    paths = {**default_paths(), **(paths or {})}
    data = load(paths)
    dropped: dict = {}
    settings = {}
    for sc, t, sf in settings_list():
        sid = setting_id(sc, t, sf)
        if only and sid not in only:
            continue
        settings[sid] = run_setting(data, sc, t, sf, dropped)
    return {
        "schema": SCHEMA,
        "version": "spec-reference/2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {"fixture": str(paths["fixture"]),
                   "fixture_built_at": data["fixture"].get("built_at"),
                   "players": str(paths["players"]), "history_index": str(Path(paths["history"]) / "index.json"),
                   "content_week": data["content_week"],
                   "prior_week": (data["prior"] or {}).get("week"),
                   "dropped_unpositioned": dropped},
        "settings": settings,
    }


def summary(rep: dict) -> list:
    lines = []
    for sid, s in rep["settings"].items():
        blended = [r["ddf"]["blended"]["value"] for r in s["rows"].values()]
        numeric = [v for v in blended if v is not None]
        zero = sum(1 for v in numeric if v == 0)
        est = sum(src["positions"][p]["n_estimated"] for src in s["sources"].values()
                  for p in src["positions"])
        lines.append(f"{sid:18s} pie {s['pie']:7.0f}  I={','.join(s['included'])}  rows {len(blended)}  "
                     f"DDF numeric {len(numeric)} zero {zero}  estimates {est}  "
                     f"prior {'yes' if s['prior'] else 'no'}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    d = default_paths()
    ap.add_argument("--fixture", default=str(d["fixture"]))
    ap.add_argument("--players", default=str(d["players"]))
    ap.add_argument("--history", default=str(d["history"]))
    ap.add_argument("--out", default=str(d["out"]))
    ap.add_argument("--only", action="append", help="setting id, e.g. ppr/12/sf0 (repeatable)")
    args = ap.parse_args(argv)
    rep = build({"fixture": Path(args.fixture), "players": Path(args.players),
                 "history": Path(args.history)}, args.only)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, separators=(",", ":"), default=str), encoding="utf-8")
    for line in summary(rep):
        print(line)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
