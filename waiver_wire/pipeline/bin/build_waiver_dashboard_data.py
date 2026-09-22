#!/usr/bin/env python3
"""Assemble the waiver-decisions dashboard data file.

Unified mechanics: ONE value-change re-ranking drives the whole board.
Every player is re-ranked by week-over-week value change (waiver_value:
tier-crossing bonus + option-value change), shown in trade-value terms
(implied_trade_value prev -> cur; chart leg frozen, so movement is the
lottery option leg at full precision).

  add      - top of the re-ranking, gated to waiver-available players
             (roster < 70%). Ranked by waiver_value desc. Aggression badges.
  dont_add - ranked by hype (Sleeper 24h adds desc), model-grounded rejection.
  drop     - bottom of the SAME re-ranking among rosterable players,
             paired one-for-one with the adds. Conviction badges separate
             real cuts from weekly drift.

Monday-safe: no ECR-dependent inputs.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from board_week import board_stem, board_week_label, board_week_n  # noqa: E402
from chart_paths import CHART_PLAYERS_JSON  # noqa: E402


# Per-scoring carried legs (bin/impute_monday_tv.py -> results/imputed_proj_<scoring>.json).
# Each leg chains every tracked player's Monday-updated per-game projection
# (scale-free points) plus the news/injury ROS multiplier. This builder prices
# the pool through the chart's own expected-lineup (starter-weighted) model
# (bin/starter_model.py) - the waiver board is the trade value chart
# recomputed on Monday's information. The 70-point scale is pinned to the
# frozen chart per (scoring, teams) so one star's big week can't move
# anyone else's number; ranks, weights and the replacement line stay live.
# This builder never invents its own imputation - it reads each leg's neutral
# values and applies only the dashboard display floors: adds floor at 1 (a
# trade value implies bench worthiness), confirmed not-rosterable players
# stay 0.
#
# Client contract (artifact waiver-dashboard): the baked `pool` carries every
# player's per-game projection under three sources - monday (Monday-updated),
# frozen_blend (the chart's frozen ESPN-first blend), ecr (frozen
# experts-only) - for all three scorings, plus pos/mult/edge. The client
# carries the starter-model JS (ported from the trade value chart) and prices
# any settings vector as:
#   scale = 70 / max(raw over the frozen_blend pool at the active vector)
#           (the chart's own scale, derived live - the Monday update never
#           moves it; for ecr mode the scale is 70/max(raw over the ecr pool))
#   base(pid) = pg > repl ? max(1, round(raw*scale)) : 0
#   tv(pid)   = max(0, round(base * mult)) + (edge if upside on)
# Row floor "add" -> max(1, tv); floor "zero" -> 0. The baked row imputed_tv
# is this value at the default vector (half-PPR, 12 teams, ESPN-first blend, upside on).
SCORINGS = ("standard", "half", "full")
BKEY = {"standard": "standard", "half": "half_ppr", "full": "ppr"}
TEAM_COUNTS = (8, 10, 12, 14)

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from starter_model import build_model as _build_model, DEFAULT_STATE, load_pies
from leg_files import load_leg as _load_leg

_PROJ = {}  # scoring -> picked leg file (reassessed -> current -> Monday)
_PROJ_LABEL = {}  # scoring -> "reassessed:<date>" | "current:<date>" | "monday"
_POOL = None  # baked pool for the client (built once)


def _proj(scoring):
    # Leg preference (2026-09-16): newest valid reassessed -> newest dated
    # current -> Monday market step. Records are keyed by chart pid via
    # waiver_boundary (alias-normalized, one record per human), so every
    # name-keyed lookup below (pool, notes, mults, client repricing) agrees
    # with the boundary's values. (2026-09-19: the builder used to read the
    # raw leg while the boundary read another file entirely - values and
    # the "reassessed <date>" label disagreed.)
    if scoring not in _PROJ:
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        from waiver_boundary import _load_leg_with_label
        recs, label = _load_leg_with_label(scoring)
        _PROJ[scoring] = recs
        _PROJ_LABEL[scoring] = label
        print(f"leg {scoring}: {label}", file=_sys.stderr)
    return _PROJ[scoring]


def _proj_label(scoring):
    _proj(scoring)
    return _PROJ_LABEL[scoring]


def _leg_as_of():
    """Freshest date among the priced Monday-leg labels.

    Labels are 'reassessed:<date>' | 'current:<date>' | 'monday'. 'monday'
    carries no date, so it never wins; fallback is today's date rather
    than a stale literal.
    """
    best = ""
    for s in SCORINGS:
        lab = _proj_label(s)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", lab or "")
        if m and m.group(1) > best:
            best = m.group(1)
    if best:
        return best
    from datetime import date as _date
    return _date.today().isoformat()


def _edge_map():
    board = json.loads((RES / (board_stem() + ".json")).read_text())
    d = {}
    for sec in ("lottery_tickets", "upside_stashes", "on_the_radar"):
        for p in board[sec]:
            d.setdefault(norm_name(p["player"]), p.get("lottery_edge_tv") or 0)
    return d


def _pool():
    """Whole-market pool for client-side pricing. Returns dict with
    monday/ecr per-scoring per-game projections (pid -> pg), pos, mult, edge,
    and meta (frozen scale anchors per scoring/teams). pid = norm_name."""
    global _POOL
    if _POOL is not None:
        return _POOL
    chart = json.load(open(CHART_PLAYERS_JSON))
    cplayers = chart["players"] if isinstance(chart, dict) else chart
    pos, frozen_blend = {}, {}
    for p in cplayers:
        k = norm_name(p["name"])
        if p.get("pos") in ("QB", "RB", "WR", "TE"):
            pos[k] = p["pos"]
    edge = _edge_map()
    monday, ecr = {}, {}
    for s in SCORINGS:
        bkey = BKEY[s]
        vf, ef, up = {}, {}, {}
        leg = _proj(s)
        for p in cplayers:
            k = norm_name(p["name"])
            if k not in pos:
                continue
            b = (p.get("blend_ppg") or {}).get(bkey)
            vf[k] = float(b) if b is not None else None
            e = (p.get("ecr_ppg") or {}).get(bkey)
            ef[k] = float(e) if e is not None else None
            r = leg.get(k) or {}
            pg = r.get("proj_pg")
            up[k] = float(pg) if pg is not None else None
        monday[s], ecr[s] = up, ef
        frozen_blend[s] = vf
    mult = {}
    for s in SCORINGS:
        for k, r in _proj(s).items():
            m = r.get("mult") or 1.0
            if abs(m - 1.0) > 1e-9:
                mult[k] = m
    # Pinned scale anchors: 70 / max frozen raw per (scoring, teams).
    frozen_max_raw = {}
    for s in SCORINGS:
        frozen_max_raw[s] = {}
        for teams in TEAM_COUNTS:
            st = dict(DEFAULT_STATE)
            st["teams"] = teams
            proj = {(k, pos[k]): v for k, v in frozen_blend[s].items()
                    if v is not None and k in pos}
            m = _build_model(proj, st, pies=load_pies(BKEY[s], teams))
            mx = max([0.0] + list(m["raw"].values()))
            frozen_max_raw[s][teams] = 70.0 / mx if mx > 0 else 1.0
    _POOL = {"monday": monday, "ecr": ecr, "pos": pos, "mult": mult,
             "edge": {k: v for k, v in edge.items() if v},
             "frozen_blend": frozen_blend,
             "meta": {"model": "starter expected-lineup (chart port v1)",
                      "frozen_max_raw": frozen_max_raw,
                      "default_vector": {"scoring": "half", "teams": 12,
                                         "slots": dict(DEFAULT_STATE["slots"]),
                                         "bench": 6,
                                         "bench_mix": dict(DEFAULT_STATE["bench_mix"])}}}
    return _POOL


_DEFAULT_TV = None  # pid -> Monday base TV at the default vector


_SB_NOTES = None  # latest Supabase monday/half notes by player_key
_SB_WARNED = False


def _supabase_monday_note(key):
    """Latest qualitative Monday note from Supabase player_value_notes
    (value_kind='monday', scoring='half'). Loud warning + empty on failure;
    the caller falls back to the local leg note."""
    global _SB_NOTES, _SB_WARNED
    if _SB_NOTES is not None:
        return _SB_NOTES.get(key)
    try:
        _sys.path.insert(0, os.path.join(os.path.expanduser("~"), "workspace", "skills", "supabase-mgmt", "bin"))
        from mgmt import query
        rows = query(
            "SELECT player_key, note FROM player_value_notes "
            "WHERE value_kind='monday' AND scoring='half' AND as_of = "
            "(SELECT max(as_of) FROM player_value_notes "
            "WHERE value_kind='monday' AND scoring='half');")
        _SB_NOTES = {r["player_key"]: r["note"] for r in rows}
    except Exception as e:
        if not _SB_WARNED:
            print(f"WARNING: Supabase value notes unreachable ({e}); "
                  f"using local Monday leg notes.", file=_sys.stderr, flush=True)
            _SB_WARNED = True
        _SB_NOTES = {}
    return _SB_NOTES.get(key)


def _default_tv():
    """Monday base trade values at the default vector (half-PPR, 12 teams),
    via the starter model with the scale pinned to the frozen chart."""
    global _DEFAULT_TV
    if _DEFAULT_TV is not None:
        return _DEFAULT_TV
    from starter_model import trade_values_pinned, load_pies
    pool = _pool()
    proj, frozen = {}, {}
    for k, pg in pool["monday"]["half"].items():
        if pg is not None:
            proj[(k, pool["pos"][k])] = pg
    for k, pg in pool["frozen_blend"]["half"].items():
        if pg is not None:
            frozen[(k, pool["pos"][k])] = pg
    vals, _ = trade_values_pinned(proj, frozen,
                                    pies=load_pies("half_ppr", 12))
    _DEFAULT_TV = {pid[0]: v for pid, v in vals.items()}
    return _DEFAULT_TV


_SLICE = {}  # norm_name -> slice record (reference vector); sections stamped at end of main()


def _pmm_note(note):
    # PMM pass over the pipeline's already-computed notes (build_note in
    # impute_monday_tv.py carries the fixed templates going forward; this
    # stays as a no-op safety net for older wordings).
    note = (note.replace("expected pts/g", "expected points a game")
                .replace("% snaps", "% of snaps")
                .replace("of priced upside from the stash board",
                         "of upside the model prices in"))
    note = re.sub(r"The chart prices \w+ at", "The chart prices him at", note)
    note = re.sub(r"Note: -([\d.]+) under expected",
                  r"Note: he scored \1 under expected", note)
    note = re.sub(r"Caution: \+([\d.]+) of the Week (\d+) line was efficiency "
                  r"over expected",
                  r"Caution: \1 of his Week \2 points were scoring over expected",
                  note)
    return note


def _imputed(name, pos, not_rosterable=False, is_add=False):
    """Monday value on the chart's starter-weighted scale + one-line notes.
    The default vector (Half PPR, 12 teams) stays the top-level
    imputed_tv/imputed_tv_note the dashboard has always read; the settings
    strip reprices any vector client-side from the baked pool (see the
    client contract at the top of this file)."""
    key = norm_name(name)
    pool = _pool()
    base = _default_tv().get(key, 0)
    mult = pool["mult"].get(key, 1.0)
    edge = pool["edge"].get(key, 0)
    tv = max(0, round(base * mult) + edge)
    rec = _proj("half").get(key) or {}
    note = _pmm_note(rec.get("note") or "Not priced in the Monday run.")
    sb_note = _supabase_monday_note(key)
    if sb_note:
        note = _pmm_note(sb_note)
    floor = None
    if not_rosterable:
        tv, note, floor = 0, "No value - off the board.", "zero"
    elif is_add:
        tv, floor = max(1, tv), "add"
    _SLICE[key] = {"name": name, "pos": pos,
                   "imputed_tv": tv,
                   "imputed_tv_note": note,
                   "mult": mult, "edge": edge,
                   "debug": rec.get("debug", {})}
    return {"imputed_tv": tv,
            "imputed_tv_note": note,
            "monday_value": {"mult": mult, "edge": edge, "floor": floor}}

LOT = Path(__file__).resolve().parent.parent
RES = LOT / "results"
DATA = LOT / "data"

# ---- Value-basis week labels (2026-09-16) ----
# Every dashboard that shows ESPN / ECR / Monday (post-weekend adjusted)
# values labels each basis with its NFL week. _nfl_week() maps a calendar
# date to the 2026 NFL week (nflverse numbering: Week 1 = Wed 2026-09-09 ..
# Mon 2026-09-14; each later week Tue..Mon). The Monday/post-weekend value
# is labeled with the week it applies to = observed week + 1, where the
# observed week is explicit in results/imputed_proj_meta.json ("week").
_SEASON_W1_START = "2026-09-09"  # bump each season (first game of Week 1)

def _nfl_week(date_str):
    """NFL week number for a YYYY-MM-DD date under the season anchor."""
    from datetime import date as _d
    d = _d.fromisoformat(str(date_str)[:10])
    anchor = _d.fromisoformat(_SEASON_W1_START)
    return 1 + (d - anchor).days // 7

def _value_weeks():
    """Week labels for the three value bases, derived from data dates."""
    weeks = {"monday": None, "ecr": None, "espn": None}
    try:
        meta = json.loads((RES / "imputed_proj_meta.json").read_text())
        w = meta.get("week")
        if isinstance(w, int):
            weeks["monday"] = w + 1
    except Exception as e:
        print(f"WARNING: imputed_proj_meta.json unreadable ({e})", file=_sys.stderr)
    try:
        chart = json.load(open(CHART_PLAYERS_JSON))
        cm = chart.get("meta", {})
        # ECR week follows the content vintage (ecr_content_date), not the
        # pull date — a fresh pull of unchanged projections keeps Week 1.
        if cm.get("ecr_content_date") or cm.get("ecr_snapshot"):
            weeks["ecr"] = _nfl_week(cm.get("ecr_content_date") or cm["ecr_snapshot"])
        if cm.get("espn_snapshot"):
            weeks["espn"] = _nfl_week(cm["espn_snapshot"])
    except Exception as e:
        print(f"WARNING: chart players.json meta unreadable ({e})", file=_sys.stderr)
    return weeks


def _sources_manifest():
    """Top-level input-source manifest with content-vintage snapshot dates.

    Powers the dashboard's collapsed Data sources panel and its staleness
    gates. Staleness = content vintage, never pull/download time: each entry
    records the snapshot_date of the data actually baked in, plus
    max_age_days. The client marks a source stale when
    (today - snapshot_date) > max_age_days; a missing/unparseable
    snapshot_date fails closed (treated as stale). `gates` lists the client
    feature ids this source powers, so a stale source disables and grays
    out exactly those features.
    """
    import csv as _csv
    from datetime import date as _date

    def _mtime_date(path):
        try:
            return _date.fromtimestamp(Path(path).stat().st_mtime).isoformat()
        except OSError:
            return None

    def _latest_dated(directory, prefix):
        files = sorted(
            p for p in Path(directory).glob(f"{prefix}_*.json")
            if re.search(rf"{prefix}_\d{{4}}-\d{{2}}-\d{{2}}\.json$", p.name))
        return files[-1] if files else None

    signals = Path(os.environ.get("WAIVER_SIGNALS_JSON",
        "/home/hatch/workspace/football-signal/data/signals_wk2_v4.json"))
    espn_csv = LOT.parent / "files" / "espn_weekly_projections.csv"
    board_file = RES / (board_stem() + ".json")

    # ESPN weekly projections: content vintage from the CSV's own
    # espn_snapshot_date column for the board week - never the file mtime.
    # A byte-identical repull resets nothing.
    espn_snap = None
    try:
        with open(espn_csv) as f:
            for r in _csv.DictReader(f):
                if r.get("week") == str(board_week_n()):
                    d = (r.get("espn_snapshot_date") or "").strip()
                    if d and (espn_snap is None or d > espn_snap):
                        espn_snap = d
    except OSError:
        espn_snap = None

    sleeper_file = _latest_dated(DATA, "sleeper_trending")
    espn_roster_file = _latest_dated(DATA, "espn_roster")

    def _dated_name_date(path):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", Path(path).name)
        return m.group(1) if m else None

    return [
        {"id": "sleeper_trending",
         "label": "Sleeper trending adds",
         "snapshot_date": _dated_name_date(sleeper_file) if sleeper_file else None,
         "max_age_days": 1,
         "gates": ["hot_pickups"],
         "note": "Most-added since Sunday drives the Hot pickups order."},
        {"id": "espn_roster",
         "label": "ESPN roster rates",
         "snapshot_date": _dated_name_date(espn_roster_file) if espn_roster_file else None,
         "max_age_days": 1,
         "gates": ["availability", "roster_tool"],
         "note": "Authoritative roster%; powers the availability gates and filters."},
        {"id": "monday_values",
         "label": "Reassessed values (current)",
         "snapshot_date": _leg_as_of(),
         "max_age_days": 2,
         "gates": ["values", "roster_tool"],
         "note": "Monday market step plus the midweek news layer, repriced per league settings."},
        {"id": "upside_edge",
         "label": "Lottery upside edge",
         "snapshot_date": _mtime_date(board_file),
         "max_age_days": 7,
         "gates": ["upside"],
         "note": ("The model's upside leg, recomputed with the weekly lottery "
                  "board - fresh for the board week. The Include-upside toggle "
                  "only renders when this is fresh.")},
        {"id": "week2_ecr",
         "label": "Week 2 expert projections",
         "snapshot_date": _mtime_date(signals),
         "max_age_days": 7,
         "gates": ["week2_source_ecr"],
         "note": "Expert-consensus leg of the Week 2 projection comparison."},
        {"id": "week2_vegas",
         "label": "Week 2 Vegas projections",
         "snapshot_date": _mtime_date(signals),
         "max_age_days": 7,
         "gates": ["week2_source_vegas"],
         "note": "Vegas-implied leg of the Week 2 projection comparison."},
        {"id": "week2_espn",
         "label": "Week 2 ESPN projections",
         "snapshot_date": espn_snap,
         "max_age_days": 7,
         "gates": ["week2_source_espn"],
         "note": "ESPN leg of the Week 2 projection comparison."},
    ]
TRENDS = json.loads((LOT.parent / "waiver-trends" / "results"
                     / "trends_latest.json").read_text())


# ---- Week 2 projections by source (2026-09-18) ----
# Toggleable Week 2 fantasy-point projections: ECR + Vegas from
# football-signal's signals_wk2_v4.json (expert_* / vegas_* legs), ESPN from
# the weekly projections CSV (week=2). ESPN ships half-PPR only; standard and
# full are derived arithmetically from receptions
# (std = half - 0.5*rec, full = half + 0.5*rec). Keys are norm_name;
# unmatched names stay absent (the client renders an em dash), never guessed.
_SIG2 = None
_ESPN_WK2 = None

def _week2_projections():
    """{scoring: {norm_name: {"ecr": x, "vegas": y, "espn": z}}} for Week 2."""
    global _SIG2, _ESPN_WK2
    if _SIG2 is None:
        _SIG2 = json.load(open(os.environ.get("WAIVER_SIGNALS_JSON",
            "/home/hatch/workspace/football-signal/data/signals_wk2_v4.json")))
    if _ESPN_WK2 is None:
        import csv as _csv
        _ESPN_WK2 = {}
        with open(LOT.parent / "files" / "espn_weekly_projections.csv") as f:
            for r in _csv.DictReader(f):
                if r.get("week") != "2":
                    continue
                try:
                    half = float(r["half_ppr"])
                    rec = float(r.get("r_receptions") or 0)
                except (ValueError, TypeError):
                    continue
                _ESPN_WK2[norm_name(r["player"])] = {
                    "half": round(half, 2),
                    "standard": round(half - 0.5 * rec, 2),
                    "full": round(half + 0.5 * rec, 2),
                }
    sigmap = {"standard": "std", "half": "half", "full": "ppr"}
    out = {}
    for s in SCORINGS:
        leg = sigmap[s]
        players = {}
        for r in _SIG2:
            k = norm_name(r.get("player_key") or r.get("name") or "")
            if not k:
                continue
            # Duplicate keys exist (same player split across rows); merge
            # per-source so a vegas-carrying row is never clobbered by a
            # vegas-less row for the same player.
            cell = players.get(k) or {}
            e = r.get("expert_" + leg)
            v = r.get("vegas_" + leg)
            if e is not None and "ecr" not in cell:
                cell["ecr"] = round(float(e), 2)
            if v is not None and "vegas" not in cell:
                cell["vegas"] = round(float(v), 2)
            es = (_ESPN_WK2.get(k) or {}).get(s)
            if es is not None and "espn" not in cell:
                cell["espn"] = es
            if cell:
                players[k] = cell
        # ESPN-only names missing from signals still get their ESPN cell
        for k, per in _ESPN_WK2.items():
            if k not in players and per.get(s) is not None:
                players[k] = {"espn": per[s]}
        out[s] = players
    return {"week": 2, "scoring": out,
            "meta": {"signals": "signals_wk2_v4.json",
                     "espn": "espn_weekly_projections.csv week=2"}}

# ---- ESPN roster% overlay (2026-09-15): ESPN is the pipeline's roster%
# source. Trend records carry FP values (or nothing for players missing
# from the panel); overlay ESPN so every availability gate sees one
# source. A player missing from ESPN keeps the record's own value.
_sys.path.insert(0, str(LOT / "engine"))
import espn_roster as _espn_roster  # noqa: E402
_ESPN_LOOKUP = _espn_roster.build_lookup(date_tag=_espn_roster.latest_tag())
_n_over = 0
for _k, _t in TRENDS.items():
    _v = _ESPN_LOOKUP.get(_k)
    if _v is None:
        _v = _ESPN_LOOKUP.get(_espn_roster.norm_name(_t.get("name", "")))
    if _v is not None:
        _t["roster_pct"] = round(float(_v), 1)
        _t["roster_source"] = "espn"
        _n_over += 1
print(f"ESPN roster overlay: {_n_over}/{len(TRENDS)} trend records", flush=True)
del _k, _t, _v, _n_over


def _espn_pct(name):
    """ESPN roster% for any display name (hype-loop fallback for players
    missing from the trends panel). None if ESPN has no row."""
    v = _ESPN_LOOKUP.get(_espn_roster.norm_name(name or ""))
    return round(float(v), 1) if v is not None else None


def load(name):
    return json.loads((RES / name).read_text())


def board_index(board):
    d = {}
    for sec in ("lottery_tickets", "upside_stashes", "on_the_radar"):
        for p in board[sec]:
            d.setdefault(p["player"], p)
    return d



TV_PLAYERS_JSON = str(CHART_PLAYERS_JSON)


def chart_tv_map():
    """Chart trade value (0-70) per normalized name: the live Trade Value
    Chart's own starter-weighted (expected-lineup) model on the frozen ESPN-first
    blend, Half PPR, 12 teams - the chart's default view. (The previous
    full-roster VORP replication priced a retired model; the live chart
    weights by expected lineup slot and normalizes the top to 70.)"""
    from starter_model import trade_values, load_pies
    data = json.load(open(TV_PLAYERS_JSON))
    proj = {}
    for p in data["players"]:
        if p.get("pos") not in ("QB", "RB", "WR", "TE"):
            continue
        b = (p.get("blend_ppg") or {}).get("half_ppr")
        if b is not None:
            proj[(p["name"], p["pos"])] = float(b)
    vals, _ = trade_values(proj, pies=load_pies("half_ppr", 12))
    return {norm_name(pid[0]): v for pid, v in vals.items()}


CHART_TV = None  # filled after norm_name is defined


def tv_fields(name, board_idx=None):
    """Trade value for a dashboard card: chart TV + lottery edge.

    trade_value matches the number on the Trade Value Chart (0-70). Where the
    lottery board prices an edge, trade_value_upside matches the chart's
    default "Include upside" view.
    """
    tv = CHART_TV.get(norm_name(name), 0)
    edge = (board_idx or {}).get(name, {}).get("lottery_edge_tv") or 0
    return {"trade_value": tv, "lottery_edge_tv": edge,
            "trade_value_upside": tv + edge}


OWNERSHIP_GATE = 70.0  # adds must be under this roster% (waiver-available)
HIGH_VALUE_GATE = 50.0  # players worth >= HIGH_VALUE_FLOOR must clear this stricter bar
HIGH_VALUE_FLOOR = 10  # a 14-17 value player at 60% rostered is likely not on your wire


def availability_gate(monday_tv):
    """Roster% ceiling for an add. High-value players are rarely on real wires,
    so the broad-market roster% overstates their availability - they need to be
    genuinely available (under 50%), not just under the 70% broad-market line."""
    return HIGH_VALUE_GATE if (monday_tv or 0) >= HIGH_VALUE_FLOOR else OWNERSHIP_GATE


def movement_bucket(name, monday_tv):
    """The user's value-movement taxonomy (2026-09-15):
    - 'exclude_higher': was high value, became more valuable - not a waiver story.
    - 'exciting': moved from low to high value - the exciting adds.
    - 'hold': moved from high to low but non-zero - hold, don't drop.
    - 'drop': moved to 0 - drop.
    High = HIGH_VALUE_FLOOR (10)."""
    prior = CHART_TV.get(norm_name(name), 0)
    cur = monday_tv or 0
    if prior >= HIGH_VALUE_FLOOR and cur >= HIGH_VALUE_FLOOR and cur >= prior:
        return "exclude_higher"
    if prior < HIGH_VALUE_FLOOR and cur >= HIGH_VALUE_FLOOR:
        return "exciting"
    if prior >= HIGH_VALUE_FLOOR and cur < prior and cur > 0:
        return "hold"
    if cur == 0 and prior > 0:
        return "drop"
    return "other"
PREV_BASELINE = "2026-09-13"  # waiver_delta.py PRV_FILE; overrides newer than this are corrections


def norm_name(n):
    return re.sub(r"[^a-z ]", "", n.lower()).strip()


CHART_TV = chart_tv_map()


AGG_LADDER = ["Light", "Moderate", "Aggressive"]
CONV_LADDER = ["Hold", "Consider", "Drop"]

# Canonical card-copy maps (single source of truth; audit_waiver.py imports
# these - never duplicate the strings in the audit).
AGGR_NOTES = {
    "Light": "Marginal gain - newly rosterable, add only if the roster fit is right.",
    "Moderate": "Worth a real bid - newly rosterable with meaningful value.",
    "Aggressive": "Top priority add - newly worth a roster spot with real value; bid to win.",
}
CONV_NOTES = {
    "Drop": "No longer worth a roster spot - make the cut.",
    "Hold": "Declined but still rosterable - hold your nerve.",
}
VERDICT_LABEL = {1: "Breaking out", -1: "Cooling off", 0: "No signal"}

TEAM_NAMES = {
    "ARI": "Arizona", "ATL": "Atlanta", "BAL": "Baltimore", "BUF": "Buffalo",
    "CAR": "Carolina", "CHI": "Chicago", "CIN": "Cincinnati", "CLE": "Cleveland",
    "DAL": "Dallas", "DEN": "Denver", "DET": "Detroit", "GB": "Green Bay",
    "HOU": "Houston", "IND": "Indianapolis", "JAX": "Jacksonville",
    "KC": "Kansas City", "LAC": "LA Chargers", "LAR": "LA Rams",
    "LV": "Las Vegas", "MIA": "Miami", "MIN": "Minnesota", "NE": "New England",
    "NO": "New Orleans", "NYG": "NY Giants", "NYJ": "NY Jets",
    "PHI": "Philadelphia", "PIT": "Pittsburgh", "SEA": "Seattle",
    "SF": "San Francisco", "TB": "Tampa Bay", "TEN": "Tennessee",
    "WAS": "Washington",
}


def _delta_word(v, dec=0):
    """Plain-words delta vs last year: +41 -> 'up 41', -5 -> 'down 5', 0 -> 'flat'."""
    v = v or 0
    if abs(v) < 0.05:
        return "flat"
    return f"{'up' if v > 0 else 'down'} {abs(v):.{dec}f}"


def _ease_word(e):
    if e is None:
        return "an average matchup"
    if e >= 1.10:
        return "a soft matchup"
    if e <= 0.85:
        return "a tough matchup"
    return "an average matchup"


def _pmm_why(raw, short=False):
    """Plain-words translation of the board's `why` telemetry, e.g.
    'stays bench_viable (emergent path P4 23.0%, cond 9.1 PPR/g); premium +0.83
    within tier' -> 'Essentially nothing - he stays a bench stash: about a 1-in-4
    chance over the next month he earns a bigger role on his own (9.1 points a
    game if it hits).' Returns None when the raw string matches no template."""
    if not raw:
        return None
    tier_word = {"starter_viable": "a starter-level stash",
                 "bench_viable": "a bench stash",
                 "not_rosterable": "off the board"}

    def case(path, p, c):
        desc = {"emergent": "he earns a bigger role on his own",
                "contingent": "an injury ahead of him opens the job",
                "ambiguous": "his role is bigger than it looks",
                "consolidation": "his targets grow with teammates out"}.get(path, path)
        if p >= 99.5:
            return f"already happening: {desc}"
        n = max(1, round(100.0 / p)) if p > 0 else 1
        chance = ("about even money over the next month" if n == 1
                  else f"about a 1-in-{n} chance over the next month")
        return f"{chance} {desc} ({c:g} points a game if it hits)"

    m = re.match(r"stays (\w+) \((\w+) path P4 ([\d.]+)%, cond ([\d.]+) PPR/g\); "
                 r"premium ([+-]?[\d.]+) within tier", raw)
    if m:
        tier, path, p, c = m.group(1), m.group(2), float(m.group(3)), float(m.group(4))
        s = case(path, p, c)
        return (s[0].upper() + s[1:] + ".") if short else \
               f"Essentially nothing - he stays {tier_word.get(tier, tier)}: {s}."
    m = re.match(r"stays (\w+) \(\); premium ([+-]?[\d.]+) within tier", raw)
    if m:
        tier = m.group(1)
        return "Off the board." if short else \
               f"Essentially nothing - he stays {tier_word.get(tier, tier)}."
    m = re.match(r"(\w+) -> (\w+) \((\w+) path P4 ([\d.]+)%, cond ([\d.]+) PPR/g\); "
                 r"premium ([\d.]+) -> ([\d.]+)", raw)
    if m:
        a, b = tier_word.get(m.group(1), m.group(1)), tier_word.get(m.group(2), m.group(2))
        s = case(m.group(3), float(m.group(4)), float(m.group(5)))
        return f"Moved from {a} to {b}: {s}."
    m = re.match(r"(\w+) -> (\w+) \(was (\w+) P4 ([\d.]+)%\); premium ([\d.]+) -> ([\d.]+)",
                 raw)
    if m:
        a, b = tier_word.get(m.group(1), m.group(1)), tier_word.get(m.group(2), m.group(2))
        past = {"emergent": "he'd earn a bigger role",
                "contingent": "an injury ahead of him would open the job",
                "ambiguous": "his role was bigger than it looked"}.get(m.group(3), m.group(3))
        return f"Fell from {a} to {b} - the chance {past} died."
    return None


def trend_of(name):
    t = TRENDS.get(norm_name(name))
    if t and t.get("verdict") == 0 and norm_name(name) not in _CURATED_NORMS:
        ev = _evidence_verdict(t)
        if ev:
            t = dict(t, verdict=ev)
    return t


# Cards with hand-written what_changed copy, curated against the trend rows
# (2026-09-15): the curator already weighed the evidence, so the evidence
# override never second-guesses them. Coker's copy was rewritten 2026-09-15
# for the starter-model contract - the original was written when he was a
# 10-15 on the retired VORP model ("upside priced in"), which contradicted
# the rebased chart value of 1. Lesson: hand-curated copy must be re-verified
# whenever the valuation contract changes; the _move_what_changed guard only
# catches "Essentially nothing" phrasing.
_CURATED_NORMS = {norm_name(n) for n in
                  ("Seth McGowan", "Cooper Kupp", "Jalen Coker", "Rashod Bateman")}


def _evidence_verdict(t):
    """Decisive usage evidence, for when the trends screen didn't flag the player.

    The screen's 0 means 'not on the ADD/FADE/DROP lists' - often just the 70%
    roster gate (Golden: 77.8% rostered) - not 'nothing changed'. When the
    evidence itself is decisive, trust the evidence. Needs 2 of 3 usage legs
    to move, so single-metric noise (Bateman's snaps +25 on a flat target
    share) stays No signal.
    """
    if not t:
        return 0
    snap = t.get("snap_d1") or 0
    share = t.get("share_d1") or 0
    xfp = t.get("xfp_d1") or 0
    up = (snap >= 20) + (share >= 10) + (xfp >= 5)
    dn = (snap <= -20) + (share <= -10) + (xfp <= -5)
    if up >= 2:
        return 1
    if dn >= 2:
        return -1
    return 0


def _move_what_changed(name, monday_tv, chart_tv, why_raw, imputed_note):
    """WHAT CHANGED must never say 'essentially nothing' when the Monday value
    moved materially. For big movers the lottery path ('stays a bench stash')
    is stale - the role already changed. Describes the role change from the
    trend evidence; falls back to the value-move note when evidence is thin.
    Returns None when there's no contradiction to fix (small move, or the
    lottery path already says something substantive)."""
    move = (monday_tv or 0) - (chart_tv or 0)
    if abs(move) < 5:
        return None
    if not (_pmm_why(why_raw) or "").startswith("Essentially nothing"):
        return None
    t = TRENDS.get(norm_name(name))
    bits = []
    if t:
        if (t.get("snap_d1") or 0) >= 15:
            bits.append(f"{t['snap_share']:.0f}% of snaps "
                        f"({_delta_word(t['snap_d1'])} vs last year)")
        if (t.get("share_d1") or 0) >= 10:
            sk = "target share" if t.get("share_kind") == "tgt" else "rush share"
            bits.append(f"{t['share']:.0f}% {sk} ({_delta_word(t['share_d1'])})")
        if (t.get("xfp_d1") or 0) >= 5:
            bits.append(f"{t['xfp']:.1f} expected points a game "
                        f"({_delta_word(t['xfp_d1'], 1)})")
    if len(bits) >= 2:
        verb = "surged" if move > 0 else "collapsed"
        return (f"What changed: his role {verb} - " + ", ".join(bits) +
                f". That role change is what moved him from {chart_tv} to {monday_tv}.")
    return f"His value moved from {chart_tv} to {monday_tv}: {imputed_note}"


def trend_line(t):
    """Week 1 evidence in plain words - no model codes. Deltas are vs last year."""
    if not t:
        return None
    share_word = "target share" if t["share_kind"] == "tgt" else "rush share"
    fpoe = t["fpoe"] or 0
    if abs(fpoe) < 0.05:
        eff = "scored right at expected"
    else:
        eff = f"scored {abs(fpoe):.1f} {'above' if fpoe > 0 else 'below'} expected"
    bits = [
        f"{t['snap_share']:.0f}% of snaps ({_delta_word(t['snap_d1'])} vs last year)",
        f"{t['share'] or 0}% {share_word} ({_delta_word(t['share_d1'])})",
        f"{t['xfp'] or 0} expected points a game ({_delta_word(t['xfp_d1'], 1)})",
        eff,
    ]
    if t["residual"] is not None:
        r = t["residual"]
        bits.append(f"{'beat' if r >= 0 else 'missed'} expectations by {abs(r):.1f}")
    bits.append(f"next up: {TEAM_NAMES.get(t['opp'], t['opp'])} ({_ease_word(t['sched_ease'])})")
    if t["team_change_note"]:
        note = t["team_change_note"].replace(" baseline", "").replace("->", "\u2192")
        bits.append(f"changed teams ({note}) \u2014 compare loosely")
    return " \u00b7 ".join(bits)


def step_level(level, ladder, direction):
    i = ladder.index(level)
    return ladder[min(len(ladder) - 1, max(0, i + direction))]


def trend_card(name):
    t = trend_of(name)
    if not t:
        return {"verdict": "No data", "evidence": None, "effect": None}
    return {"verdict": VERDICT_LABEL[t["verdict"]],
            "evidence": trend_line(t), "effect": None}


def _trend_with_effect(name, side):
    """Conviction modulation: the trends module's own ADD/FADE/DROP verdicts
    (same Week 1 games, different lens) move conviction one step. Confirming
    trend promotes; contradicting trend demotes. Returns the trend card dict
    with effect filled in when the verdict moved the needle."""
    card = trend_card(name)
    t = trend_of(name)
    if not t:
        return card
    v = t["verdict"]
    if side == "add":
        if v == 1:
            card["effect"] = ("Bumped up a notch: the trends check agrees - usage is up, "
                              "expected points are up, and he beat expectations.")
        elif v == -1:
            card["effect"] = ("Bumped down a notch: the trends check disagrees - usage is "
                              "down and he's underperforming.")
    else:
        if v == 1:
            card["effect"] = ("Moved toward Hold: the trends check flags him an add "
                              "(usage surging) - that argues against the drop. "
                              + ("He changed teams, so treat the trend as noisy. "
                                 if t["team_change_note"] else ""))
        elif v == -1:
            card["effect"] = ("Moved toward Drop: the trends check agrees he's fading.")
    return card


def correction_overrides():
    """Players whose valuation changed because WE fixed our data/logic this week
    (depth_chart_overrides entries dated after the prev baseline) - not because
    the market moved. These must never masquerade as market movers."""
    ov = json.loads((DATA / "depth_chart_overrides.json").read_text())

    out = {}
    for name, e in ov.items():
        if name.startswith("_"):
            continue
        if isinstance(e, dict) and e.get("date", "") > PREV_BASELINE:
            out[norm_name(name)] = e
    return out


def _hold_note(hold_rows, zero_names):
    """Section note for Hold your nerve: honest empty state, and the
    zero-value names accounted for (off the board - never presented as
    holds, because a hold needs positive value)."""
    bits = []
    if not hold_rows:
        bits.append("No genuine holds this week - nobody the surface says to "
                    "cut but the usage says to keep.")
    if zero_names:
        bits.append("Valued at 0 (off the board - not holds): "
                    + ", ".join(zero_names) + ".")
    return " ".join(bits)


def main():
    """Finite-capacity waiver board (2026-09-15 redesign).

    Sections come from the ranked boundary, not from value-change thresholds:
      capacity = teams x (starters + bench); the complete 546-player pool is
      ranked twice (old = chart upside-ON; new = Monday value under the vector);
      the top-capacity available players by each form the old/new rosterable sets.
      Adds = entrants; Drops = displaced; Holds = in-both decliners (merged);
      Hold-steady = in-both, still positive, not a hold ("didn't move,
      but should be rostered").
    Every section ranked by highest updated (Monday) value.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from waiver_boundary import boundary as _boundary, DEFAULT_SLOTS, visible_sections

    # Default vector: Half PPR, 12 teams, 1/2/3/1/1, bench 6, upside ON.
    bnd = _boundary(teams=12, slots=dict(DEFAULT_SLOTS), bench=6, scoring="half")
    values = bnd["values"]   # pid -> {"old": int, "new": int}
    pool = bnd["pool"]       # pid -> {"name": display, "pos":, "team":}
    espn = bnd["roster"]     # pid -> espn roster%

    cur = board_index(load(board_stem() + ".json"))

    def roster_pct(pid):
        r = espn.get(pid)
        if r is None:
            ks = re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", pid).strip()
            r = espn.get(ks)
        return r

    # ---------------- section membership (pids) ----------------
    # The boundary is the single source of truth for sections (user taxonomy
    # 2026-09-15, refined 2026-09-16):
    #   Hot pickups = most-added since Sunday (available, priced, not
    #           holds/drops), ranked by adds. Each card carries a verdict:
    #           ADD (entrant or new>=4) or PASS (fringe/zero).
    #   Adds  = "Other pickups we like": available entrants NOT on the hot
    #           list. Ranked by highest updated value. Never a 0->0 card.
    #   Drops = genuinely displaced AND moved to 0. Never a 0->0 card.
    #           Visible Add and Drop counts need not match.
    #   Holds = fell from >=10 to sub-10 but stayed positive
    #           + displaced-but-positive.
    #   Hold-steady = in-both, still positive, not a hold: "didn't move,
    #           but should be rostered". Available players plus big value
    #           jumps (delta >= 5) under 90% rostered.
    # visible_sections is fail-closed: boundary parity (entrants==displaced),
    # every drop genuinely displaced with new==0 and old>0.
    adds, drops = visible_sections(bnd)
    holds = list(bnd["holds"])

    # ---------------- row builders ----------------
    def _base_row(pid):
        info = pool[pid]
        name = info["name"]
        old, new = values[pid]["old"], values[pid]["new"]
        why = (cur.get(name) or {}).get("why")
        imp = _imputed(name, info["pos"])
        # Canonical value: the boundary's new. _imputed's internal value uses
        # the legacy pool; the boundary is the single source of truth.
        imp["imputed_tv"] = new
        tvf = tv_fields(name, cur)
        # trade_value_upside is the "old" (chart upside-ON); keep it consistent.
        tvf["trade_value_upside"] = old
        row = {
            "name": name, "pos": info["pos"], "team": info["team"],
            "player_key": info["player_key"],
            "chart_value": old,
            "implied_tv_prev": old, "implied_tv_cur": new,
            "roster_pct": roster_pct(pid),
            "established": CHART_TV.get(pid, 0) >= 8,
            **tvf, **imp,
            "path": _pmm_why(why, short=True) if why else None,
            "trend": trend_card(name),
        }
        # _imputed carries a legacy dict-shaped monday_value; the board's
        # Monday value is the boundary integer.
        row["monday_value"] = new
        return row

    def _aggression_for_add(new):
        # Adds are newly rosterable; press harder for higher Monday values.
        if new >= 10:
            return {"level": "Aggressive", "note": AGGR_NOTES["Aggressive"]}
        if new >= 5:
            return {"level": "Moderate", "note": AGGR_NOTES["Moderate"]}
        return {"level": "Light", "note": AGGR_NOTES["Light"]}

    # Hand-curated copy, re-verified against the starter-model contract.
    # Allgeier is 5->5 (not a drop, decline, or downgrade): 59% snaps,
    # ~12 expected points, scored ~4 below expected - the workload supports
    # the existing value.
    CURATED = {
        "tyler allgeier": {
            "what_changed": ("What changed: essentially nothing - 5 to 5. The workload "
                             "supports the value: 59% of snaps, about 12 expected points "
                             "a game, and he scored roughly 4 below expected. Not a drop, "
                             "not a decline - the existing value held."),
            "verbal": ("5 to 5. 59% of snaps and about 12 expected points a game support "
                       "the value he already had; he scored roughly 4 below expected. "
                       "Hold - nothing changed."),
        },
        "cooper kupp": {
            # Career-veteran phrasing must not read as an established-role claim
            # (established flag is False: chart value < 8).
            "what_changed": ("What changed: his upside case firmed - about a 1-in-4 chance "
                             "over the next month that his role expands to a 10.6-point-a-game "
                             "player. He's a longtime veteran, not a stash: this is a depth "
                             "upgrade, not a lottery ticket."),
            "verbal": ("A longtime veteran, not a stash. Upside case firming: about a 1-in-4 "
                       "chance over the next month that his role expands to a "
                       "10.6-point-a-game player - a depth upgrade, not a lottery ticket."),
        },
    }

    def _what_changed(pid, old, new, kind):
        info = pool[pid]
        name = info["name"]
        key = norm_name(name)
        if key in CURATED and kind in ("hold", "drop"):
            return CURATED[key]["what_changed"], CURATED[key]["verbal"]
        t = trend_of(name)
        ev = ""
        if t:
            ev = trend_line(t) or ""
        if kind == "add":
            return (
                f"What changed: newly worth a roster spot - {old} to {new}. {ev}",
                f"{old} to {new}. Newly rosterable. {ev}".strip(),
            )
        if kind == "drop":
            return (
                f"What changed: no longer worth a roster spot - {old} to {new}. {ev}",
                f"{old} to {new}. The value is gone. {ev}".strip(),
            )
        # hold
        if old == new:
            # Unchanged value must never read as a decline (audit guards this).
            return (
                f"What changed: Monday value held at {new} - still above replacement "
                f"and worth a roster spot. Why he's still held: {ev}",
                f"Held at {new}. Still worth a roster spot. {ev}".strip(),
            )
        return (
            f"What changed: value declined but still rosterable - {old} to {new}. "
            f"Why he's still held: {ev}",
            f"{old} to {new}. Declined but still worth a roster spot. {ev}".strip(),
        )

    add_rows = []
    for i, pid in enumerate(adds, 1):
        old, new = values[pid]["old"], values[pid]["new"]
        row = _base_row(pid)
        wc, verbal = _what_changed(pid, old, new, "add")
        case = {"id": "newly_rosterable", "label": "Newly rosterable",
                "note": "Entered the rosterable set on the week's games."}
        row.update({
            "rank": i,
            "aggression": _aggression_for_add(new),
            "what_changed": wc, "verbal": verbal,
            "case": case,
        })
        add_rows.append(row)

    # ---------------- Hot pickups: the debate ----------------
    # (2026-09-16: the community's most-added since Sunday, each with our
    # verdict. ADD = entrant or real value (new>=4); PASS = fringe/zero.)
    hot_rows = []
    _entrants = set(bnd.get("entrants", []))
    _trending = bnd.get("trending", {})
    for i, pid in enumerate(bnd.get("hot_pickups", []), 1):
        old, new = values[pid]["old"], values[pid]["new"]
        row = _base_row(pid)
        if pid in _entrants or new >= 4:
            verdict = {"id": "add", "label": "ADD"}
            if pid in _entrants:
                wc = (f"Verdict: ADD. #{i} most-added since Sunday - newly rosterable "
                      f"(Monday value {new}) and the community is already on it.")
                verbal = f"ADD. #{i} most-added since Sunday. Newly rosterable."
            else:
                if old == new:
                    wc = (f"Verdict: ADD. #{i} most-added since Sunday. Monday value "
                          f"held at {new} - worth a roster spot, and the "
                          f"community agrees.")
                else:
                    wc = (f"Verdict: ADD. #{i} most-added since Sunday. Monday value "
                          f"moved from {old} to {new} - worth a roster spot, and the "
                          f"community agrees.")
                verbal = f"ADD. {old} to {new}. #{i} most-added since Sunday."
        else:
            verdict = {"id": "pass", "label": "PASS"}
            if new == 0:
                wc = (f"Verdict: PASS. #{i} most-added since Sunday, but chasing a box score "
                      f"the value layer prices at replacement level (Monday value 0). "
                      f"Don't spend a claim here.")
                verbal = f"PASS. #{i} most-added, but replacement-level value."
            else:
                wc = (f"Verdict: PASS. #{i} most-added since Sunday, but Monday value "
                      f"is only {new} - fringe. Not a priority add.")
                verbal = f"PASS. #{i} most-added, but only value {new}."
        row.update({
            "rank": i,
            # sleeper_adds intentionally omitted (2026-09-18): exact add counts
            # are internal-only and must never ship in public data.
            "verdict": verdict,
            "aggression": _aggression_for_add(new),
            "what_changed": wc, "verbal": verbal,
        })
        hot_rows.append(row)

    drop_rows = []
    for i, pid in enumerate(drops, 1):
        old, new = values[pid]["old"], values[pid]["new"]
        row = _base_row(pid)
        wc, verbal = _what_changed(pid, old, new, "drop")
        row.update({
            "rank": i,
            "value_lost": old - new,
            "conviction": {"level": "Drop", "note": CONV_NOTES["Drop"]},
            "what_changed": wc, "verbal": verbal,
        })
        drop_rows.append(row)

    hold_rows = []
    for i, pid in enumerate(holds, 1):
        old, new = values[pid]["old"], values[pid]["new"]
        row = _base_row(pid)
        wc, verbal = _what_changed(pid, old, new, "hold")
        if old == new:
            why = (f"Monday value held at {new} - still above replacement and worth "
                   f"a roster spot. The surface move is noise; the underlying role "
                   f"supports the value.")
        else:
            why = (f"Value dipped from {old} to {new} but remains above replacement - "
                   f"worth a roster spot. Hold your nerve; the underlying usage "
                   f"supports the value.")
        row.update({
            "rank": i,
            "conviction": {"level": "Hold", "note": CONV_NOTES["Hold"]},
            "what_changed": wc, "verbal": verbal,
            "why_hold": why,
        })
        hold_rows.append(row)

    # ---------------- Hold-steady: didn't move, but should be rostered ----------------
    # In-both, still positive, not a hold: already on the board. Available
    # players are wire-checks; big jumpers under 90% rostered are awareness.
    steady_rows = []
    for i, pid in enumerate(bnd["hold_steady"], 1):
        old, new = values[pid]["old"], values[pid]["new"]
        row = _base_row(pid)
        if new - old >= 5:
            wc = (f"What changed: Monday value jumped from {old} to {new} - "
                  f"but he was already on the board.")
            verbal = f"Value jumped {old} to {new}. Already on the board."
            case = {"id": "riser", "label": "Already rostered, value jumped",
                    "note": ("Was already on the board - his Monday value jumped "
                             "on the week's games. Awareness, not a wire-check.")}
        elif old == new:
            wc = (f"What changed: Monday value held at {new} - still above "
                  f"replacement and worth a roster spot.")
            verbal = f"Held at {new}. Still worth a roster spot."
            case = {"id": "hold_steady", "label": "Didn't change, still rosterable",
                    "note": "Already on the board. Check if he's free in your league."}
        else:
            wc = (f"What changed: value moved from {old} to {new} - still above "
                  f"replacement and worth a roster spot.")
            verbal = f"{old} to {new}. Still worth a roster spot."
            case = {"id": "hold_steady", "label": "Didn't move, still rosterable",
                    "note": "Already on the board. Check if he's free in your league."}
        row.update({
            "rank": i,
            "what_changed": wc, "verbal": verbal,
            "case": case,
        })
        steady_rows.append(row)


    # ---------------- corrections / headline / week read ----------------
    corrections = []
    for pid, e in correction_overrides().items():
        if pid not in values:
            continue
        info = pool[pid]
        corrections.append({
            "name": info["name"], "pos": info["pos"], "team": info["team"],
            "player_key": info["player_key"],
            "roster_pct": roster_pct(pid),
            "chart_value": values[pid]["old"],
            "monday_value": values[pid]["new"],
            **_imputed(info["name"], info["pos"]),
            "what_was_wrong": e.get("what_was_wrong", ""),
            "correction": e.get("correction", ""),
            "action": e.get("action", ""),
            "provenance": "MODEL CORRECTION - not a market move.",
            "trend": trend_card(info["name"]),
        })

    # Gated-out: available-gate exclusions, promotable via league overrides.
    gated_out = []
    for pid in bnd["gated_out"]:
        if values[pid]["new"] < 1:
            continue
        row = _base_row(pid)
        row["rank"] = len(gated_out) + 1
        gated_out.append(row)

    # Drop pool: full boundary drop ranking for client-side re-pairing.
    drop_pool = []
    for i, pid in enumerate(bnd["drops"], 1):
        row = _base_row(pid)
        row.update({"rank": i, "value_lost": values[pid]["old"] - values[pid]["new"]})
        drop_pool.append(row)

    # Browse: every player in the NEW rosterable set, so the board is
    # filterable beyond the five sections. Steady-section players keep
    # the "rostered" browse status (they were already on the board).
    _status = {}
    for pid in bnd["adds"]:
        _status[pid] = "add"
    for pid in bnd["drops"]:
        _status[pid] = "drop"
    for pid in bnd["holds"]:
        _status[pid] = "hold"
    browse = []
    for pid in bnd["M"]:
        if pid not in values:
            continue  # unpriced: skipped, never rendered as 0
        row = _base_row(pid)
        row["board_status"] = _status.get(pid, "rostered")
        browse.append(row)
    browse.sort(key=lambda r: (-(r.get("monday_value") or 0), r.get("name") or ""))

    out = {
        # as_of derives from the freshest Monday-leg label actually priced
        # (reassessed:<date> | current:<date> | monday) — never hardcoded
        # (stale-label class, fixed 2026-09-18).
        "as_of": _leg_as_of(),
        "board_week": board_week_label(),
        "monday_safe": True,
        "value_weeks": _value_weeks(),
        "monday_leg_source": {s: _proj_label(s) for s in SCORINGS},
        "sources": _sources_manifest(),
        "pool": _pool(),
        "week2": _week2_projections(),
        "boundary": {
            "capacity": bnd["capacity"], "teams": bnd["teams"],
            "bench": bnd["bench"], "slots": bnd["slots"],
            "scoring": bnd["scoring"],
            "adds": len(adds), "drops": len(drops), "holds": len(holds),
            "hold_steady": len(steady_rows),
            "raw_adds": len(bnd["adds"]), "raw_drops": len(bnd["drops"]),
            "entrants": len(bnd["entrants"]),
            "displaced": len(bnd["displaced"]),
        },
        "week_read": {
            "pmm_take": (f"{len(hot_rows)} hot pickups debated; "
                         f"{len(add_rows)} under-the-radar adds; "
                         f"{len(drop_rows)} fell out. {len(hold_rows)} declined but "
                         f"still belong on rosters. {len(steady_rows)} didn't move "
                         f"but are worth checking."),
        },
        "mechanics": ("How this board works: a finite-capacity boundary. For your league "
                      "settings, the complete player pool is ranked twice - once by chart "
                      "value (upside included), once by Monday value - and the top N available "
                      "players by each form the old and new rosterable sets (N = teams x "
                      "roster spots). Hot pickups are the most-added players since "
                      "Sunday with our verdict on each; other pickups are the "
                      "data's under-the-radar finds; "
                      "drops fell out and lost their "
                      "value; holds fell from high to low but are still worth rostering; "
                      "steady names were already on the board - check if they're free in "
                      "your league. Monday value is our "
                      "Monday estimate of what each player is worth right now, on the "
                      "chart's scale. Ranked by Monday value, highest first."),
        "corrections": corrections,
        "gated_out": gated_out,
        "drop_pool": drop_pool,
        "browse": browse,
        "sections": [
            {"id": "hot_pickups", "title": "Hot pickups",
             "rank_logic": ("The most-added players since Sunday, ranked by adds. "
                            "Our verdict on each: ADD means the value layer agrees "
                            "he's worth a roster spot; PASS means don't chase the hype."),
             "players": hot_rows},
            {"id": "add", "title": "Other pickups we like",
             "rank_logic": ("Under-the-radar adds the data likes that aren't on the "
                            "hot list - entered the rosterable set on the week's games. "
                            "Ranked by Monday value, highest first."),
             "players": add_rows},
            {"id": "hold", "title": "Hold",
             "rank_logic": ("Fell from 10-plus to below 10 but kept real value - "
                            "plus players displaced from the set who are still "
                            "worth a roster spot. Every card explains why. "
                            "Ranked by Monday value, highest first."),
             "players": hold_rows},
            {"id": "hold_steady", "title": "Didn't change, but should be rostered",
             "rank_logic": ("Already on the board - they didn't move on or off it. "
                            "Low-owned names are wire-checks; big value jumps under "
                            "90% rostered are flagged for awareness. "
                            "Ranked by Monday value, highest first."),
             "players": steady_rows},
            {"id": "drop", "title": "Players to drop",
             "rank_logic": ("Displaced from the rosterable set: no longer worth a roster "
                            "spot. Ranked by Monday value, highest first."),
             "players": drop_rows},
        ],
    }
    # Naming-table gate (2026-09-19): every player-facing name emitted by
    # this bake must equal the Supabase players-table full_name for its
    # player_key. The pool already resolves through the naming table; this
    # is the fail-closed backstop against any future path that stamps a
    # source spelling or derived string into a card.
    _eng = Path.home() / "workspace" / "football-signal" / "engine"
    if str(_eng) not in _sys.path:
        _sys.path.insert(0, str(_eng))
    from canonical_players import assert_canonical_names as _assert_names
    _name_pairs = []
    for _rows in (hot_rows, add_rows, drop_rows, hold_rows, steady_rows,
                  corrections, gated_out, drop_pool, browse):
        for _r in _rows:
            _name_pairs.append((_r["player_key"], _r["name"]))
    _assert_names(_name_pairs, context="waiver_dashboard_data.json")

    path = RES / "waiver_dashboard_data.json"
    path.write_text(json.dumps(out, indent=1))
    print("wrote", path, "| hot:", len(hot_rows), "| adds:", len(add_rows),
          "| holds:", len(hold_rows), "| steady:", len(steady_rows),
          "| drops:", len(drop_rows),
          "| raw:", len(bnd["adds"]), len(bnd["drops"]))


if __name__ == "__main__":
    main()
