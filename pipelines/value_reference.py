#!/usr/bin/env python3
"""Python reference for every value series the page shows (JEG-479).

Jeremy, 2026-10-08: the math lives in two places on purpose -- the browser
engine (app/trade-value-chart/assets/curve-widget.js + value-model.js) and this
Python reference -- so one can validate the other. pipelines/value_check.py
runs both on the same build and diffs them on every chain run.

What it computes, per league setting (scoring x teams x roster) and view
(indexed / vorp / adj), for every player the page lists:

  espn                  the ESPN two-tier leg (fixture), refit live through the
                        browser's OLS cells at the active bench share, then the
                        roster-shape factor
  cbsros, razzball      each source's own two-tier values (its own per-game
                        projections), one factor to the anchor's shared total
  usatoday, fantasycalc,
  fantasypros, cbs      Indexed: the saved 12-team values at the saved setup,
                        else the saved natives times ONE factor that matches
                        the anchor's total over the chart's players
                        (published_one_factor; JEG-482: the chart keeps its
                        own order, no per-position translation);
                        VORP vs waivers / Adjusted values: the saved vorp_views
                        at their own setup, else derived (one batch)
  *_adjusted            the raw chart through the live OLS cells (ESPN two-tier
                        target), then per-position peaks to the anchor's and one
                        factor to its shared total
  *_vorp                projection minus the waiver line, one factor to the
                        anchor's shared total
  ddf_value             the DDF Composite Value per the written rule
                        (docs/methodology.md "DDF Composite Value")
plus the display rules (ESPN-listed 0, below-the-leg 0).

Inputs are the build's own snapshot: data/fixtures/current/
comparison-sources-data.json, players.json and the served adjustment inputs.

Independence (audited in the JEG-479 PR): this module's composition -- which
series reads what, in what order, with which factor -- is written here from
the methodology, not from the JS. The arithmetic kernels it calls are
separate Python implementations: pipelines/vorp_translation/unified.py (the
server's own published-chart translation, which the JS ports), and the
Python ports pipelines/twotier_reference.py and
pipelines/parity/value_model_parity.py (written from the JS, each held to it
by its own vector parity check). No code is shared with the engine at run
time; a JS bug that a port copied verbatim would not be caught here.
"""
from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "parity"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))
sys.path.insert(0, str(REPO))

import twotier_reference as tt  # noqa: E402
import value_model_parity as vm  # noqa: E402
from pipelines.vorp_translation import unified  # noqa: E402

VERSION = "value-reference-001/1"
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = REPO / "data" / "fixtures" / "current" / "players.json"
ADJUSTMENT_INPUTS = REPO / "app" / "trade-value-chart" / "assets" / "adjustment-inputs.json"

POSITIONS = ("QB", "RB", "WR", "TE")
PUBLISHED = ("usatoday", "fantasycalc", "fantasypros", "cbs")
ADJUSTED = ("fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted", "cbs_adjusted")
PROJECTIONS = ("espn", "cbsros", "razzball")
SOURCE_KEYS = ("usatoday", "fantasycalc", "fantasypros", "cbs", "espn", "cbsros", "razzball",
               *ADJUSTED)
VORP_KEYS = {"espn_vorp": "espn_ppg", "cbsros_vorp": "cbsros_ppg", "razzball_vorp": "rz_ppg"}
SERIES_KEYS = (*SOURCE_KEYS, *VORP_KEYS)
COMPOSITE_KEY = "ddf_value"
COMPOSITE_INPUTS = ("espn", "cbsros", "razzball", *ADJUSTED)
WEEKLY_KEYS = frozenset((*PUBLISHED, *ADJUSTED))
VIEWS = ("indexed", "vorp", "adj")
VIEW_FIELD = {"vorp": "vorp", "adj": "adj_values"}
LEG_PPG = {"espn": "espn_ppg", "cbsros": "cbsros_ppg", "razzball": "rz_ppg"}
SCORINGS = ("standard", "half_ppr", "ppr")
TEAM_COUNTS = (8, 10, 12, 14)
COMBO_PREFIX = {"ppr": "full", "half_ppr": "half", "standard": "standard"}
QB_AWARE = frozenset({"fantasycalc", "fantasycalc_adjusted"})
DEFAULT_ROSTER = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "BENCH": 6,
                  "K": 0, "DST": 0}
SAVED_TEAMS = 12
SAVED_SHAPE = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 6}
BENCH_SHARE = tt.DEFAULT_BENCH_SHARE
# Inputs a DDF Value needs. The engine on main publishes a DDF Value from one
# input; Jeremy's 2026-10-08 rule (at least 2) lands with the engine change
# for JEG-479 item 4, and this constant moves to 2 in the same change, so the
# two implementations change together.
DDF_MIN_INPUTS = 1
VIEW_SCORING = {"ppr": "ppr", "full": "ppr", "half_ppr": "half_ppr", "half": "half_ppr",
                "standard": "standard"}


def roster(superflex: int = 0) -> dict:
    return {**DEFAULT_ROSTER, "SUPERFLEX": int(superflex)}


def settings(superflex_too: bool = True) -> list[dict]:
    """The settings every chain run compares: 3 scorings x 4 team counts on
    the default roster, plus the same with one superflex slot."""
    out = []
    for sf in ((0, 1) if superflex_too else (0,)):
        for scoring in SCORINGS:
            for teams in TEAM_COUNTS:
                out.append({"scoring": scoring, "teams": teams, "superflex": sf})
    return out


def setting_id(s: dict) -> str:
    return f"{s['scoring']}/{s['teams']}/sf{s['superflex']}"


# ---------------------------------------------------------------------------
# Inputs (the build's snapshot)
# ---------------------------------------------------------------------------

def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _clamp(v):
    """A served value: finite and >= 0, else missing."""
    f = _num(v) if v not in (None, "") else None
    return None if f is None else max(0.0, f)


def collation_key(name: str) -> tuple:
    """Approximates ICU root collation (String.localeCompare) for names:
    accents and case are secondary, so compare the stripped, casefolded form
    first, then the original."""
    base = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    return (base.casefold(), name)


def tiebreak_key(player: dict) -> tuple:
    return (collation_key(str(player.get("name") or "")), int(player.get("player_key") or 0))


def espn_projects_zero(p: dict) -> bool:
    if p.get("espn_status") == "ineligible":
        return True
    if p.get("espn_status") == "absent":
        return False
    ppg = p.get("espn_ppg")
    if not isinstance(ppg, dict) or not ppg:
        return False
    return all(_finite(v) and v == 0 for v in ppg.values())


@dataclass
class Inputs:
    fixture: dict
    players: dict          # player_key -> player dict (QB/RB/WR/TE, named)
    key_of: dict           # fixture slug -> player_key
    adjustment_inputs: dict | None
    today: date
    held: dict = field(default_factory=dict)  # series -> reason (validation holds)

    @classmethod
    def load(cls, fixture=FIXTURE, players=PLAYERS, adjustment_inputs=ADJUSTMENT_INPUTS,
             today: date | None = None):
        fx = json.loads(Path(fixture).read_text(encoding="utf-8"))
        pl = json.loads(Path(players).read_text(encoding="utf-8"))
        try:
            adj = json.loads(Path(adjustment_inputs).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            adj = None
        canon = {}
        for p in pl.get("players") or []:
            try:
                key = int(p.get("player_key"))
            except (TypeError, ValueError):
                continue
            if isinstance(p.get("player_key"), bool) or float(p.get("player_key")) != key:
                continue
            name = str(p.get("full_name") or p.get("name") or "").strip()
            if not name or p.get("pos") not in POSITIONS:
                continue
            canon[key] = {
                "player_key": key, "name": name, "pos": p["pos"],
                "espn_ppg": p.get("espn_ppg") or None, "rz_ppg": p.get("rz_ppg") or None,
                "cbsros_ppg": p.get("cbsros_ppg") or None,
                "espn_zero": espn_projects_zero(p),
            }
        key_of = {}
        for slug, k in (fx.get("player_keys") or {}).items():
            n = _num(k)
            if n is not None and n == int(n):
                key_of[slug] = int(n)
        held = {s: (sec.get("validationHold") or {}).get("reason") or "validation hold"
                for s, sec in (fx.get("sources") or {}).items()
                if isinstance(sec, dict) and sec.get("validationHold")}
        return cls(fx, canon, key_of, adj, today or datetime.now(timezone.utc).date(), held)

    # product-data getPlayerValues, restricted to the chart's players.
    def cell(self, source: str, scoring: str, teams: int, view: str = "combo_reindexed") -> dict | None:
        section = "cbs" if source == "cbs_adjusted" else source
        combo_key = f"{COMBO_PREFIX[scoring]}_{teams}" + ("_qb1" if section in QB_AWARE else "")
        combo = ((self.fixture.get("sources") or {}).get(section) or {}).get("combos", {}).get(combo_key)
        if not combo:
            return None
        if view == "combo_reindexed":
            raw = combo.get("values") or combo.get("reindexed")
        else:
            raw = combo.get(view)
        if not raw:
            return None
        out = {}
        for slug, value in raw.items():
            key = self.key_of.get(slug)
            v = _num(value)
            if key is None or v is None or key not in self.players:
                continue
            out[key] = v
        return {"values": out, "index_total": combo.get("index_total")}

    def combo_exists(self, source: str, scoring: str, teams: int) -> bool:
        section = "cbs" if source == "cbs_adjusted" else source
        combo_key = f"{COMBO_PREFIX[scoring]}_{teams}" + ("_qb1" if section in QB_AWARE else "")
        return bool(((self.fixture.get("sources") or {}).get(section) or {}).get("combos", {}).get(combo_key))

    def ppg(self, key: int, field_name: str, scoring: str):
        v = (self.players[key].get(field_name) or {}).get(scoring)
        return float(v) if _finite(v) else None


# ---------------------------------------------------------------------------
# Content weeks (docs/methodology.md "Week-Over-Week Snapshots"; the
# Tuesday-flip calendar of pipelines/nfl_week.py)
# ---------------------------------------------------------------------------

def section_week(section: dict | None, today: date) -> tuple[int | None, bool]:
    """(content week, weekly?) of a fixture section."""
    from nfl_week import current_nfl_week
    if not isinstance(section, dict):
        return None, False
    for f in ("week_designated", "content_vintage"):
        m = re.search(r"week\s*(\d+)|wk\s*(\d+)", str(section.get(f) or ""), re.I)
        if m:
            return int(m.group(1) or m.group(2)), True
    for f in ("content_vintage", "vintage", "published", "fetched_at"):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(section.get(f) or ""))
        if m:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return current_nfl_week(d), f == "content_vintage"
    return None, False


def freshness(inp: Inputs) -> dict:
    """{series: {"week", "older", "first_load_excluded"}} for the weekly series."""
    from nfl_week import current_nfl_week
    current = current_nfl_week(inp.today)
    sources = inp.fixture.get("sources") or {}
    rows = {}
    for key in SOURCE_KEYS:
        base = key
        if key in ADJUSTED:
            raw = "cbs" if key == "cbs_adjusted" else key[: -len("_adjusted")]
            base = raw if raw in sources else key
        week, weekly = section_week(sources.get(base), inp.today)
        rows[key] = {"week": week, "weekly": weekly,
                     "older": week is not None and week < current}
    weekly_weeks = [r["week"] for r in rows.values() if r["weekly"] and r["week"] is not None]
    ref = min(max(weekly_weeks), current) if weekly_weeks else None
    for r in rows.values():
        r["first_load_excluded"] = bool(r["weekly"] and ref is not None and r["week"] is not None
                                        and r["week"] < ref)
    return {"current_week": current, "reference_week": ref, "series": rows}


# ---------------------------------------------------------------------------
# The engine's building blocks, written from the methodology
# ---------------------------------------------------------------------------

MIN_SHARED_FOR_PIE = 40


def published_one_factor(native: dict, keys, anchor: dict, saved: dict | None = None) -> dict:
    """A published chart's Indexed values off the saved setup (methodology,
    The Three Views #3; JEG-482): native x one factor, where the factor is the
    anchor's total over the chart's players it prices / the chart's native
    total over them. With fewer than MIN_SHARED_FOR_PIE shared players the
    factor is the saved one (saved total / native total over the chart's
    players). Players with no native value are left out (missing, not 0)."""
    keys = [k for k in keys if k in native]
    shared = [k for k in keys if k in anchor and _finite(anchor[k])]
    a_total = sum(max(0.0, float(anchor[k])) for k in shared)
    n_total = sum(max(0.0, float(native[k])) for k in shared)
    if len(shared) < MIN_SHARED_FOR_PIE or a_total <= 0 or n_total <= 0:
        base = saved if saved is not None else native
        a_total = sum(max(0.0, float(base[k])) for k in keys if k in base)
        n_total = sum(max(0.0, float(native[k])) for k in keys if k in base)
    factor = a_total / n_total if a_total > 0 and n_total > 0 else 0.0
    return {k: max(0.0, float(native[k])) * factor for k in keys}


class Setting:
    """Everything the page computes at one (scoring, teams, roster)."""

    def __init__(self, inp: Inputs, scoring: str, teams: int, superflex: int = 0):
        self.inp, self.scoring, self.teams = inp, scoring, int(teams)
        self.shape = roster(superflex)
        self.saved_setup = (self.teams == SAVED_TEAMS and not superflex)
        self.player_of = inp.players.get
        self._published = {}
        self._natives = {}
        self._ddf = {}
        self._cells = None

    # -- published charts ------------------------------------------------
    def native(self, src: str) -> dict:
        """Saved 12-team natives; the publisher's superflex values replace
        them where saved when the roster has a superflex slot."""
        if src not in self._natives:
            cell = self.inp.cell(src, self.scoring, SAVED_TEAMS, "native")
            out = dict(cell["values"]) if cell else {}
            if out and self.shape["SUPERFLEX"]:
                sf = self.inp.cell(src, self.scoring, SAVED_TEAMS, "native_superflex")
                if sf:
                    out.update(sf["values"])
            self._natives[src] = out
        return self._natives[src]

    def saved_values(self, src: str) -> dict:
        cell = self.inp.cell(src, self.scoring, SAVED_TEAMS)
        if not cell:
            return {}
        return {k: c for k, v in cell["values"].items() if (c := _clamp(v)) is not None}

    def _ranked(self, native: dict) -> dict:
        ranked = {p: [] for p in POSITIONS}
        for key, value in native.items():
            ranked[self.player_of(key)["pos"]].append((str(key), str(key), float(value)))
        for p in POSITIONS:
            ranked[p].sort(key=lambda r: -r[2])
        return ranked

    def _peers(self, src: str) -> dict:
        out = {}
        for other in PUBLISHED:
            if other == src:
                continue
            nat = self.native(other)
            if nat:
                by_pos = {p: [] for p in POSITIONS}
                for key, value in nat.items():
                    by_pos[self.player_of(key)["pos"]].append((str(key), float(value)))
                out[other] = by_pos
        return out

    def our_max(self) -> dict:
        proj = {p: [] for p in POSITIONS}
        for key, p in self.inp.players.items():
            v = self.inp.ppg(key, "espn_ppg", self.scoring)
            if v is not None:
                proj[p["pos"]].append((str(key), str(key), v))
        for rows in proj.values():
            rows.sort(key=lambda r: -r[2])
        return unified.positional_max_for_setup(
            proj, self.teams, self.shape["BENCH"], self.shape["FLEX"],
            slots={p: self.shape[p] for p in POSITIONS}, superflex_count=self.shape["SUPERFLEX"])

    def published_indexed(self, src: str) -> dict:
        """Indexed values: saved at the saved setup, derived elsewhere."""
        if src in self._published:
            return self._published[src]
        saved = self.saved_values(src)
        if self.saved_setup:
            out = saved
        else:
            native = self.native(src)
            out = {}
            if saved and native:
                out = published_one_factor(native, list(saved), self.anchor(), saved)
        self._published[src] = out
        return out

    def raw_map(self, src: str) -> dict:
        """The source's served (as-published / leg) values at this setting."""
        if src in PUBLISHED:
            return self.published_indexed(src)
        cell = self.inp.cell(src, self.scoring, self.teams)
        if not cell:
            return {}
        return {k: c for k, v in cell["values"].items() if (c := _clamp(v)) is not None}

    # -- two-tier ------------------------------------------------------
    def two_tier(self, src: str = "espn", ppg_override: dict | None = None) -> dict | None:
        """Live two-tier values on src's own per-game projections (ESPN for
        espn and the published charts), the pipeline's legacy bench mix, the
        default bench share, top player at 70."""
        if ppg_override is None and src in self._ddf:
            return self._ddf[src]
        ppg_field = LEG_PPG.get(src, "espn_ppg")
        lists = {p: [] for p in POSITIONS}
        for key, p in self.inp.players.items():
            v = (ppg_override.get(key) if ppg_override is not None
                 else self.inp.ppg(key, ppg_field, self.scoring))
            if v is not None:
                # Zero-padded ids: the port breaks ties on str(id), the engine on
                # the numeric id; padding makes the two orders the same.
                lists[p["pos"]].append({"id": f"{key:012d}", "x": v})
        try:
            pool = tt.build_position_tiers(lists, {
                "teams": self.teams, "slots": dict(tt.REF_SLOTS), "flexCount": tt.REF_FLEX_COUNT,
                "flexEligible": list(tt.REF_FLEX_ELIGIBLE),
                "benchMix": tt.legacy_bench_mix_for(self.teams)})
        except ValueError:
            pool = None
        if pool is None:
            if ppg_override is None:
                self._ddf[src] = None
            return None
        shares = tt.skill_bench_shares(BENCH_SHARE)
        cal, invalid = {}, set()
        for pos in POSITIONS:
            tier = pool["tiers"].get(pos)
            pie = float(tier["surplus"]) if tier else float("nan")
            try:
                c = tt.calibrate_position_feasible(tier, pie, tt.skill_bench_share(shares, pos), pos)
            except Exception:  # noqa: BLE001 - mirrors the engine's withheld position
                c = None
            if src in ("cbsros", "razzball") and (not c or c.get("invalid")):
                invalid.add(pos)
                continue
            cal[pos] = c
        raw, pos_of = {}, {}
        for pos in POSITIONS:
            if pos in invalid:
                continue
            for d in lists[pos]:
                pos_of[int(d["id"])] = pos
                raw[int(d["id"])] = tt.price_for_projection(d["x"], cal.get(pos))
        mx = max(raw.values(), default=0.0)
        scale = 70.0 / mx if mx > 0 else 1.0
        out = {"values": {k: v * scale for k, v in raw.items()}, "pos_of": pos_of,
               "starters": {int(i) for i in pool["starters"]}, "bench": {int(i) for i in pool["bench"]},
               "cal": cal}
        if ppg_override is None:
            self._ddf[src] = out
        return out

    CELL_KEYS = ("fantasycalc", "usatoday", "fantasypros", "cbs", "espn", "cbsros", "razzball")

    def cells(self) -> list[dict]:
        """OLS cells per (source, position, tier): the source's served values
        against the live two-tier values on the same players."""
        if self._cells is None:
            self._cells = [c for raw_key in self.CELL_KEYS for c in self._fit_cells(raw_key)]
        return self._cells

    def _fit_cells(self, raw_key: str) -> list[dict]:
        """One source's cells, fitted on demand: a published chart's Indexed
        values are scaled against the anchor (JEG-482), and the anchor needs
        only ESPN's own cells, so ESPN's are fitted without the others."""
        if not hasattr(self, "_cells_by_key"):
            self._cells_by_key = {}
        if raw_key in self._cells_by_key:
            return self._cells_by_key[raw_key]
        cells = []
        espn = self.two_tier("espn")
        ddf = (self.two_tier(raw_key) if raw_key in ("cbsros", "razzball") else espn) if espn else None
        published = self.raw_map(raw_key) if ddf else None
        if ddf and published:
            for pos in POSITIONS:
                c = ddf["cal"].get(pos)
                if c and c.get("invalid"):
                    continue
                for tier in ("starter", "bench"):
                    members = ddf["starters"] if tier == "starter" else ddf["bench"]
                    xs, ys = [], []
                    for key, x in published.items():
                        if ddf["pos_of"].get(key) != pos or key not in members:
                            continue
                        y = ddf["values"].get(key)
                        if y is None or not math.isfinite(x) or not math.isfinite(y):
                            continue
                        xs.append(x)
                        ys.append(y)
                    if len(xs) < 2:
                        continue
                    n = len(xs)
                    mx, my = sum(xs) / n, sum(ys) / n
                    sxx = sum((x - mx) ** 2 for x in xs)
                    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
                    if not sxx > 0:
                        continue
                    beta = sxy / sxx
                    cells.append({"source": raw_key, "position": pos, "tier": tier,
                                  "alpha": my - beta * mx, "beta": beta, "n": n})
        self._cells_by_key[raw_key] = cells
        return cells

    def cells_for(self, raw_key: str) -> list[dict] | None:
        live = list(self._fit_cells(raw_key)) if raw_key in self.CELL_KEYS else []
        if live:
            return live
        entry = ((self.inp.adjustment_inputs or {}).get("sources") or {}).get(raw_key)
        return entry["cells"] if cell_set_complete(entry) else None

    def live_adjusted(self, raw_key: str, cells: list[dict], raw: dict | None = None) -> dict:
        """The served values through the OLS cells, on the two-tier tiers the
        cells were fitted on."""
        raw = self.raw_map(raw_key) if raw is None else raw
        ddf = self.two_tier(raw_key) if raw_key in ("cbsros", "razzball") else self.two_tier("espn")
        by_cell = {}
        for c in cells:
            pos, tier = str(c.get("position", "")).upper(), str(c.get("tier", "")).lower()
            a, b = _num(c.get("alpha")), _num(c.get("beta"))
            if pos in POSITIONS and tier in ("starter", "bench") and a is not None and b is not None:
                by_cell[(pos, tier)] = (a, b)
        native = raw_key in PROJECTIONS
        out, sums, cell_of = {}, {}, {}
        for key, value in raw.items():
            if ddf:
                tier = "starter" if key in ddf["starters"] else "bench" if key in ddf["bench"] else None
                pos = ddf["pos_of"].get(key)
            else:  # the engine's fallback: value-ordered roles on the served values
                tier = vm.role_map(raw, self.player_of, self.teams, self.shape).get(key)
                pos = self.player_of(key)["pos"]
            cell = by_cell.get((pos, tier)) if tier and pos else None
            if native and not cell:
                continue
            if not native and not cell and tier in ("starter", "bench"):
                continue
            safe = max(0.0, value) if math.isfinite(value) else 0.0
            fitted = cell[0] + cell[1] * safe if cell else safe
            out[key] = max(0.0, fitted)
            if native and cell:
                s = sums.setdefault((pos, tier), [0.0, 0.0])
                s[0] += fitted
                s[1] += max(0.0, fitted)
                cell_of[key] = (pos, tier)
        for ck, (fitted, kept) in sums.items():
            if kept > fitted and fitted > 0:
                f = fitted / kept
                for key, k2 in cell_of.items():
                    if k2 == ck:
                        out[key] *= f
        return out

    # -- roster shape ------------------------------------------------------
    def roster_is_default(self) -> bool:
        return all(self.shape[k] == DEFAULT_ROSTER[k] for k in DEFAULT_ROSTER)

    def _allocation(self, shape: dict) -> dict:
        pool = [p for k, p in self.inp.players.items()
                if self.inp.ppg(k, "espn_ppg", self.scoring) is not None]
        rank = {k: self.inp.ppg(k, "espn_ppg", self.scoring) for k in self.inp.players}
        return allocation_counts(pool, self.teams, shape, lambda p: rank[p["player_key"]])

    def roster_shaped(self, values: dict, key: str) -> dict:
        """Roster-shape factor for the non-published series off the default
        roster: per position the top-N average at the custom roster over the
        default one (clamped 0.25-1.8), then one factor keeps the skill total."""
        if key in PUBLISHED or key in VORP_KEYS or self.roster_is_default():
            return values
        default = self._allocation(DEFAULT_ROSTER)["rostered"]
        custom = self._allocation(self.shape)["rostered"]
        shaped = dict(values)
        before = sum(v for v in values.values())
        for pos in POSITIONS:
            rows = sorted(((k, v) for k, v in values.items() if self.player_of(k)["pos"] == pos),
                          key=lambda r: -r[1])
            if not rows:
                continue
            d = max(1, min(len(rows), default.get(pos) or 1))
            c = max(1, min(len(rows), custom.get(pos) or 1))
            avg_d = sum(v for _, v in rows[:d]) / d
            avg_c = sum(v for _, v in rows[:c]) / c
            factor = max(0.25, min(1.8, avg_c / avg_d)) if avg_d > 0 else 1.0
            for k, v in rows:
                shaped[k] = v * factor
        after = sum(shaped.values())
        f = before / after if before > 0 and after > 0 else 1.0
        return {k: v * f for k, v in shaped.items()}

    # -- the anchor and every other series -------------------------------
    def anchor(self) -> dict:
        if not hasattr(self, "_anchor"):
            cells = self.cells_for("espn")
            if not cells:
                raise RuntimeError("no ESPN cells: the engine would fall back to the browser-derived leg")
            self._anchor = self.roster_shaped(self.live_adjusted("espn", cells), "espn")
        return self._anchor

    def adjusted_map(self, key: str) -> dict:
        raw_key = "cbs" if key == "cbs_adjusted" else key[: -len("_adjusted")] if key.endswith("_adjusted") else key
        if raw_key in ("cbsros", "razzball"):
            ddf = self.two_tier(raw_key)
            return dict(ddf["values"]) if ddf else {}
        cells = self.cells_for(raw_key)
        return self.live_adjusted(raw_key, cells) if cells else {}

    def normalized(self, key: str) -> dict:
        values = self.roster_shaped(self.adjusted_map(key), key)
        anchor = self.anchor()
        if key in ("cbsros", "razzball"):
            return vm.scale_to_shared_total(values, anchor, self.player_of)
        raw_key = "cbs" if key == "cbs_adjusted" else key[: -len("_adjusted")]
        if self.cells_for(raw_key):
            return vm.shape_to_anchor_peaks_then_shared_total(values, anchor, self.player_of)
        raise RuntimeError(f"{key}: no cells (fixed-pie fallback not modelled)")

    def vorp_map(self, key: str, ppg_override: dict | None = None) -> dict:
        """Projection minus each position's waiver line, roles by projected
        points at this roster; one factor to the anchor's shared total."""
        ppg_field = VORP_KEYS[key]
        priced = [(p, v) for k, p in self.inp.players.items()
                  if (v := (ppg_override.get(k) if ppg_override is not None
                            else self.inp.ppg(k, ppg_field, self.scoring))) is not None]
        priced.sort(key=lambda r: (-r[1], tiebreak_key(r[0])))
        ppg = {p["player_key"]: v for p, v in priced}
        roles = projection_roles([p for p, _ in priced], self.teams, self.shape,
                                 lambda p: ppg[p["player_key"]])
        baseline = {}
        for pos in POSITIONS:
            rows = [(p, v) for p, v in priced if p["pos"] == pos]
            waiver = next(((p, v) for p, v in rows if roles.get(p["player_key"], "waiver") == "waiver"), None)
            baseline[pos] = waiver[1] if waiver else (rows[-1][1] if rows else 0.0)
        raw = {}
        for p, v in priced:
            role = roles.get(p["player_key"], "waiver")
            raw[p["player_key"]] = 0.0 if role == "waiver" else max(0.0, v - baseline[p["pos"]])
        return vm.scale_to_shared_total(raw, self.anchor(), self.player_of)

    def published_view(self, src: str, view: str) -> dict:
        """VORP vs waivers / Adjusted values for a published chart."""
        vv = ((self.inp.fixture.get("sources") or {}).get(src) or {}).get("vorp_views")
        if (vv and self.saved_setup
                and VIEW_SCORING.get(str(vv.get("scoring") or "").lower()) == self.scoring
                and _num(vv.get("teams")) == self.teams):
            saved = self._saved_view(vv, VIEW_FIELD[view])
            if saved:
                return saved
        batch = self.view_batch()
        return dict((batch.get(src) or {}).get(view) or {})

    def _saved_view(self, vv: dict, field_name: str) -> dict:
        data = (vv.get("views") or {}).get(field_name)
        if not isinstance(data, dict):
            return {}
        name_to_key = {}
        for slug, key in self.inp.key_of.items():
            norm = str(slug).strip().lower()
            if key in self.inp.players and norm and norm not in name_to_key:
                name_to_key[norm] = key
        out = {}
        for name, value in data.items():
            key = name_to_key.get(str(name).strip().lower())
            v = _clamp(value)
            if key is not None and v is not None:
                out[key] = v
        return out

    def view_batch(self) -> dict:
        """Every published chart derived into both views as one batch (the
        Adjusted 70 anchor is shared): value above the setting's waiver line,
        VORP scaled to the anchor's group-budget total, Adjusted shares each
        anchor group total in proportion to value above waivers."""
        if hasattr(self, "_batch"):
            return self._batch
        anchor = self.anchor()
        roles = vm.role_map(anchor, self.player_of, self.teams, self.shape)
        inputs = {}
        for src in PUBLISHED:
            native = self.native(src)
            keys = list(self.saved_values(src))
            if native and keys:
                budgets = {p: {"starter": 0.0, "bench": 0.0} for p in POSITIONS}
                kset = set(keys)
                for key, value in anchor.items():
                    role = roles.get(key)
                    if key in kset and role in ("starter", "bench") and math.isfinite(value):
                        budgets[self.player_of(key)["pos"]][role] += max(0.0, value)
                inputs[src] = (native, keys, budgets)
        natives = {src: self.native(src) for src in PUBLISHED if self.native(src)}
        self._batch = derive_views(inputs, natives, lambda k: self.player_of(k)["pos"],
                                   self.teams, self.shape)
        return self._batch

    # -- the page's series maps and rows ----------------------------------
    def series_maps(self, view: str = "indexed") -> dict:
        maps = {"espn": self.anchor()}
        for key in SOURCE_KEYS:
            if key == "espn":
                continue
            if key in ADJUSTED or key in ("cbsros", "razzball"):
                maps[key] = self.normalized(key)
            elif view != "indexed":
                maps[key] = self.published_view(key, view)
            else:
                maps[key] = self.published_indexed(key)
        for key in VORP_KEYS:
            maps[key] = self.vorp_map(key)
        return maps

    def available(self, key: str) -> bool:
        """The series has values at this setting and is not paused/missing."""
        sources = self.inp.fixture.get("sources") or {}
        section = "cbs" if key == "cbs_adjusted" else key
        if key not in VORP_KEYS and section not in sources:
            return False
        if key in ("cbsros", "razzball"):
            ok = any(self.inp.ppg(k, LEG_PPG[key], self.scoring) is not None for k in self.inp.players)
        elif key in PUBLISHED or key in ADJUSTED:
            ok = self.inp.combo_exists(key if key in PUBLISHED or key == "cbs_adjusted" else key,
                                       self.scoring, SAVED_TEAMS)
        else:
            ok = self.inp.combo_exists(key, self.scoring, self.teams)
        if key in ADJUSTED:
            raw = "cbs" if key == "cbs_adjusted" else key[: -len("_adjusted")]
            entry = ((self.inp.adjustment_inputs or {}).get("sources") or {}).get(raw)
            ok = ok and cell_set_complete(entry)
        return ok

    def rows(self, view: str = "indexed") -> dict:
        """{player_key: {series: value or None}} -- the page's rows."""
        maps = self.series_maps(view)
        floors = {}
        for key, ppg_field in LEG_PPG.items():
            by_pos = {}
            for k in maps.get(key, {}):
                v = self.inp.ppg(k, ppg_field, self.scoring)
                if v is not None:
                    pos = self.player_of(k)["pos"]
                    by_pos[pos] = min(by_pos.get(pos, math.inf), v)
            floors[key] = by_pos
        universe = set()
        for m in maps.values():
            universe.update(m)
        out = {}
        for k in universe:
            p = self.player_of(k)
            if p is None:
                continue
            values = {}
            for key in SERIES_KEYS:
                m = maps.get(key) or {}
                if k in m:
                    values[key] = m[k]
                elif not m:
                    values[key] = None
                elif key in ("espn", "espn_vorp") and p["espn_zero"]:
                    values[key] = 0.0
                elif key in LEG_PPG:
                    v = self.inp.ppg(k, LEG_PPG[key], self.scoring)
                    fl = floors[key].get(p["pos"])
                    values[key] = 0.0 if v is not None and fl is not None and v <= fl else None
                else:
                    values[key] = None
            out[k] = values
        return out


# ---------------------------------------------------------------------------
# Prior week (docs/v2-design-notes.md "Back-end contract: history"): a saved
# week's own inputs priced at the CURRENT league, roster, bench share, anchor,
# fit cells and peers. Only the source's own inputs come from the saved week.
# The saved weeks are the build's history files (dist/assets/history, written
# by pipelines/build_week_history.py during `make sync`).
# ---------------------------------------------------------------------------
HISTORY = REPO / "dist" / "assets" / "history"
HISTORY_SCORING_INDEX = {"standard": 0, "half_ppr": 1, "ppr": 2}


class History:
    def __init__(self, root: Path = HISTORY):
        self.root = Path(root)
        self.index = self._load("index.json") or {}
        self.espn_legs = self._load("espn-legs.json") or {}
        self.served_versions = self._load("served.json") or {}
        self._weeks = {}

    def _load(self, name):
        try:
            return json.loads((self.root / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def week_doc(self, week: int):
        if week not in self._weeks:
            rec = (self.index.get("weeks") or {}).get(str(week)) or {}
            name = Path(str(rec.get("file") or "")).name
            doc = self._load(name) if name else None
            self._weeks[week] = doc if doc and doc.get("week") == week else None
        return self._weeks[week]

    def served(self, base: str):
        return (self.index.get("served") or {}).get(base)


def history_base(series: str) -> str:
    if series.endswith("_vorp"):
        return series[: -len("_vorp")]
    if series.endswith("_adjusted"):
        return "cbs" if series == "cbs_adjusted" else series[: -len("_adjusted")]
    return series


def _saved_ppg(setting: "Setting", entry: dict) -> dict:
    idx = HISTORY_SCORING_INDEX[setting.scoring]
    out = {}
    for key, triple in (entry.get("ppg") or {}).items():
        k = int(key)
        v = triple[idx] if isinstance(triple, list) and len(triple) > idx else None
        if k in setting.inp.players and _finite(v):
            out[k] = float(v)
    return out


def _display(setting: "Setting", series: str, values: dict, entry: dict, ppg: dict) -> dict:
    """The page's display rules on a saved week (ESPN-listed 0, below the leg)."""
    out = dict(values)
    floors = {}
    if series in LEG_PPG:
        for k in values:
            if k in ppg:
                pos = setting.player_of(k)["pos"]
                floors[pos] = min(floors.get(pos, math.inf), ppg[k])
    for key, triple in (entry.get("ppg") or {}).items():
        k = int(key)
        if k in out or k not in setting.inp.players or not values:
            continue
        if series in ("espn", "espn_vorp") and isinstance(triple, list) and triple \
                and all(v == 0 for v in triple):
            out[k] = 0.0
            continue
        v, fl = ppg.get(k), floors.get(setting.player_of(k)["pos"])
        if series in LEG_PPG and v is not None and fl is not None and v <= fl:
            out[k] = 0.0
    return out


def week_values(setting: "Setting", series: str, week: int, hist: History, view: str = "indexed"):
    """(values or None, reason) for one series at a saved week."""
    base = history_base(series)
    doc = hist.week_doc(week)
    entry = ((doc or {}).get("sources") or {}).get(base)
    served = hist.served(base) or {}
    if served.get("week") == week and served.get("version") == "superseded":
        version = (hist.served_versions.get("sources") or {}).get(base)
        if not version or version.get("fingerprint") != served.get("entry_fingerprint"):
            return None, "the served version is not saved"
        entry = version
    if not entry:
        return None, f"no Week {week} content saved"
    if entry.get("week") != week:
        return None, f"saved entry is labelled week {entry.get('week')}"
    if base in PUBLISHED and view != "indexed":
        return None, "earlier weeks are recomputed in the Indexed view only"
    anchor = setting.anchor()
    if series in ADJUSTED or base in PUBLISHED:
        native = {}
        for key, v in ((entry.get("natives") or {}).get(setting.scoring) or {}).items():
            k, f = int(key), _num(v)
            if k in setting.inp.players and f is not None:
                native[k] = f
        if not native:
            return None, "no values saved for that week"
        # JEG-482: a saved week's Indexed values are its natives times one
        # factor against today's anchor (the browser's historyPublishedValues).
        raw = published_one_factor(native, list(native), anchor)
        if series in PUBLISHED:
            values = raw
        else:
            if not cell_set_complete(((setting.inp.adjustment_inputs or {}).get("sources") or {}).get(base)):
                return None, "the Adjusted series is paused at this setting"
            cells = setting.cells_for(base)
            if not cells:
                return None, "no fit cells at this setting"
            adjusted = setting.roster_shaped(setting.live_adjusted(base, cells, raw=raw), series)
            values = vm.shape_to_anchor_peaks_then_shared_total(adjusted, anchor, setting.player_of)
    elif series in VORP_KEYS:
        ppg = _saved_ppg(setting, entry)
        if not ppg:
            return None, "no projections saved for that week"
        values = _display(setting, series, setting.vorp_map(series, ppg), entry, ppg)
    elif series == "espn":
        leg = (((hist.espn_legs.get("weeks") or {}).get(str(week)) or {}).get("legs") or {}).get(setting.scoring)
        if not leg:
            return None, f"no ESPN leg was built for Week {week}"
        raw = {}
        for key, v in leg.items():
            k, f = int(key), _num(v)
            if k in setting.inp.players and f is not None:
                raw[k] = f
        if len(raw) < vm.MIN_SHARED_FOR_PIE:
            return None, "the ESPN leg prices too few players"
        cells = setting.cells_for("espn")
        mapped = setting.live_adjusted("espn", cells, raw=raw) if cells else raw
        values = _display(setting, "espn", setting.roster_shaped(mapped, "espn"), entry,
                          _saved_ppg(setting, entry))
    else:  # cbsros, razzball
        ppg = _saved_ppg(setting, entry)
        if not ppg:
            return None, "no projections saved for that week"
        ddf = setting.two_tier(series, ppg)
        shaped = setting.roster_shaped(dict(ddf["values"]) if ddf else {}, series)
        values = vm.scale_to_shared_total(shaped, anchor, setting.player_of)
        if not values:
            return None, "that week's projections price no players at this setting"
        values = _display(setting, series, values, entry, ppg)
    out = {k: c for k, v in values.items() if (c := _clamp(v)) is not None}
    return out, None


def prior_values(setting: "Setting", series: str, hist: History, view: str = "indexed"):
    """(served week, prior week, values or None, reason)."""
    built = hist.index.get("fixture_built_at")
    if built and setting.inp.fixture.get("built_at") and built != setting.inp.fixture["built_at"]:
        return None, None, None, "the history index belongs to a different build of the values"
    served = hist.served(history_base(series))
    if not served or not isinstance(served.get("week"), int):
        return None, None, None, (served or {}).get("reason") or "no saved week matches the served values"
    week = served["week"]
    values, reason = week_values(setting, series, week - 1, hist, view)
    return week, week - 1, values, reason


def _ranked_by_pos(native: dict, pos_of) -> dict:
    ranked = {p: [] for p in POSITIONS}
    for key, value in native.items():
        ranked[pos_of(key)].append((str(key), str(key), float(value)))
    for p in POSITIONS:
        ranked[p].sort(key=lambda r: -r[2])
    return ranked


def derive_views(inputs: dict, natives: dict, pos_of, teams: int, shape: dict) -> dict:
    """VORP vs waivers and Adjusted values for a batch of published charts at
    one setting (docs/methodology.md "Other chart views").

    inputs: {src: (native {key: value}, keys [key], budgets {pos: {starter, bench}})}
    natives: {src: native} of every chart (each chart's peers are the others).
    Returns {src: {"vorp": {key: v}, "adj": {key: v}}}.
    """
    slots = {p: int(shape[p]) for p in POSITIONS}
    sf = int(shape.get("SUPERFLEX") or 0)
    vorp_out, weighted, batch_max = {}, {}, 0.0
    for src, (native, keys, budgets) in inputs.items():
        total = sum(b for g in budgets.values() for b in g.values() if b > 0)
        ranked = _ranked_by_pos(native, pos_of)
        peers = {}
        for other, nat in natives.items():
            if other != src and nat:
                by_pos = {p: [] for p in POSITIONS}
                for key, value in nat.items():
                    by_pos[pos_of(key)].append((str(key), float(value)))
                peers[other] = by_pos
        at = unified.translate_ranked(ranked, teams, shape["BENCH"], shape["FLEX"], slots=slots,
                                      peers=peers, superflex_count=sf)
        info, groups, vsum = {}, {p: {"starter": 0.0, "bench": 0.0} for p in POSITIONS}, 0.0
        for p in POSITIONS:
            pinfo = at["positions"].get(p)
            if not pinfo:
                continue
            n_start = pinfo["n_dedicated"] + pinfo.get("n_superflex", 0) + pinfo["n_flex"]
            for i, (pkey, _n, _v) in enumerate(ranked[p]):
                t = at["translated"].get(pkey)
                if t is None:
                    continue
                role = "starter" if i < n_start else "bench"
                info[pkey] = (p, role, t["vorp"])
                groups[p][role] += t["vorp"]
                vsum += t["vorp"]
        scale = total / vsum if vsum > 0 else 0.0
        v_map, w_map = {}, {}
        for key in keys:
            row = info.get(str(key))
            v = w = 0.0
            if row:
                p, role, vorp = row
                v = vorp * scale
                gt, b = groups[p][role], budgets[p][role]
                w = b * vorp / gt if gt > 0 and b > 0 else 0.0
            v_map[key], w_map[key] = v, w
            batch_max = max(batch_max, w)
        vorp_out[src], weighted[src] = v_map, w_map
    adj_scale = 70.0 / batch_max if batch_max > 0 else 0.0
    return {src: {"vorp": vorp_out[src], "adj": {k: w * adj_scale for k, w in weighted[src].items()}}
            for src in vorp_out}


def cell_set_complete(entry) -> bool:
    if not isinstance(entry, dict) or entry.get("status") != "live" or not isinstance(entry.get("cells"), list):
        return False
    present = set()
    for c in entry["cells"]:
        pos, tier = str(c.get("position", "")).upper(), str(c.get("tier", "")).lower()
        if pos in POSITIONS and tier in ("starter", "bench") and _num(c.get("alpha")) is not None \
                and _num(c.get("beta")) is not None:
            present.add((pos, tier))
    return len(present) == 8


def projection_roles(pool: list[dict], teams: int, shape: dict, rank_of) -> dict:
    """Roles by projected points: dedicated slots, superflex (any position),
    flex (RB/WR/TE), then bench by surplus over each position's last
    dedicated starter."""
    by_pos, direct = {}, {}
    for pos in POSITIONS:
        direct[pos] = teams * int(shape.get(pos) or 0)
        rows = [p for p in pool if p["pos"] == pos and math.isfinite(rank_of(p))]
        rows.sort(key=lambda p: (-rank_of(p), tiebreak_key(p)))
        by_pos[pos] = rows
    baseline = {}
    for pos in POSITIONS:
        rows = by_pos[pos]
        baseline[pos] = rank_of(rows[min(max(direct[pos] - 1, 0), len(rows) - 1)]) if rows else 0.0
    roles = {}
    for pos in POSITIONS:
        for p in by_pos[pos][:direct[pos]]:
            roles[p["player_key"]] = "starter"

    def remaining(positions, score):
        rest = [p for pos in positions for p in by_pos[pos] if p["player_key"] not in roles]
        rest.sort(key=lambda p: (-score(p), tiebreak_key(p)))
        return rest
    for p in remaining(POSITIONS, rank_of)[: teams * int(shape.get("SUPERFLEX") or 0)]:
        roles[p["player_key"]] = "starter"
    for p in remaining(("RB", "WR", "TE"), rank_of)[: teams * int(shape.get("FLEX") or 0)]:
        roles[p["player_key"]] = "starter"
    for p in remaining(POSITIONS, lambda p: rank_of(p) - baseline[p["pos"]])[: teams * int(shape.get("BENCH") or 0)]:
        roles[p["player_key"]] = "bench"
    return roles


def allocation_counts(pool: list[dict], teams: int, shape: dict, rank_of) -> dict:
    """Rostered counts per position from projection_roles."""
    roles = projection_roles(pool, teams, shape, rank_of)
    rostered = {p: 0 for p in POSITIONS}
    for key, role in roles.items():
        pos = next(p["pos"] for p in pool if p["player_key"] == key)
        if role in ("starter", "bench"):
            rostered[pos] += 1
    return {"rostered": rostered}


# ---------------------------------------------------------------------------
# DDF Composite Value (docs/methodology.md "DDF Composite Value")
# ---------------------------------------------------------------------------

def composite_inputs(setting: Setting, fresh: dict) -> tuple[list[str], dict]:
    """(default inputs, {excluded key: reason}) at a setting."""
    inputs, excluded = [], {}
    for key in COMPOSITE_INPUTS:
        row = fresh["series"].get(key) or {}
        if key in setting.inp.held or ("cbs" if key == "cbs_adjusted" else key) in setting.inp.held:
            excluded[key] = "held"
        elif not setting.available(key):
            excluded[key] = "not available"
        elif row.get("older") or row.get("first_load_excluded"):
            excluded[key] = "older week"
        else:
            inputs.append(key)
    return inputs, excluded


def composite(values: dict, keys: list[str], min_inputs: int = DDF_MIN_INPUTS) -> tuple:
    used = [k for k in keys if _finite(values.get(k))]
    if not used:
        return None, 0, "no input prices this player"
    if len(used) < min_inputs:
        return None, len(used), f"only {len(used)} input prices this player"
    return sum(values[k] for k in used) / len(used), len(used), None


def composite_prior(s: Setting, rows: dict, keys: list[str], hist: History, view: str) -> dict:
    """The DDF Value's week-over-week pair: the newest served week among the
    inputs and the week before it, over the SAME inputs on both sides; an
    input without that prior week (or serving another week) is dropped from
    both."""
    results = {}
    for key in keys:
        week, prior, values, reason = prior_values(s, key, hist, view)
        results[key] = {"week": week, "values": values, "reason": reason}
    weeks = [r["week"] for r in results.values() if isinstance(r["week"], int)]
    if not weeks:
        return {"available": False, "reason": "no DDF Value input matches a saved week", "sources": []}
    current = max(weeks)
    sources = [k for k in keys if results[k]["values"] is not None and results[k]["week"] == current]
    dropped = {k: (results[k]["reason"] if results[k]["values"] is None
                   else f"serves Week {results[k]['week']}, not Week {current}")
               for k in keys if k not in sources}
    if not sources:
        return {"available": False, "reason": f"no DDF Value input has Week {current - 1}",
                "sources": [], "dropped": dropped, "currentWeek": current, "priorWeek": current - 1}
    prior_vals, current_vals = {}, {}
    players = set()
    for k in sources:
        players.update(results[k]["values"])
    for pk in players:
        v, _n, _r = composite({k: results[k]["values"].get(pk) for k in sources}, sources)
        if v is not None:
            prior_vals[pk] = v
    for pk, values in rows.items():
        v, _n, _r = composite(values, sources)
        if v is not None:
            current_vals[pk] = v
    return {"available": True, "sources": sources, "dropped": dropped, "currentWeek": current,
            "priorWeek": current - 1, "values": prior_vals, "currentValues": current_vals}


def compute(inp: Inputs, setting_spec: dict, views=VIEWS, hist: History | None = None) -> dict:
    """One setting: {view: {player_key: {series: value}}} with ddf_value, and
    the DDF Value's prior-week pair per view."""
    s = Setting(inp, setting_spec["scoring"], setting_spec["teams"], setting_spec.get("superflex", 0))
    fresh = freshness(inp)
    keys, excluded = composite_inputs(s, fresh)
    out = {"setting": setting_spec, "composite_inputs": keys, "composite_excluded": excluded,
           "views": {}, "prior": {}}
    for view in views:
        rows = s.rows(view)
        for values in rows.values():
            values[COMPOSITE_KEY], values["ddf_count"], _reason = composite(values, keys)
        out["views"][view] = rows
        if hist is not None:
            out["prior"][view] = composite_prior(s, rows, keys, hist, view)
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=REPO / "output" / "value-reference.json")
    ap.add_argument("--fixture", type=Path, default=FIXTURE)
    ap.add_argument("--players", type=Path, default=PLAYERS)
    args = ap.parse_args(argv)
    inp = Inputs.load(args.fixture, args.players)
    result = {"version": VERSION, "settings": [compute(inp, s) for s in settings()]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, separators=(",", ":"), default=str), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
