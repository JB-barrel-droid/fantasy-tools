"""JEG-1280: an offline ledger of how projection inputs reach chart DDF Value.

DDF Value, in Jeremy's words (2026-10-29 brief), is "the average of the
weight-adjusted indexed values". At the pinned engine SHA that is the blended
version: the equal-weight mean of the included, visible trade charts' Adjusted
values (value_reference.py DDF_FAMILY and _rows). No projection number is
averaged into it, but each chart's Adjusted values are priced with stages that
the projections feed. This tool holds every chart observation fixed, changes
only projection inputs, and splits each chart DDF Value move into the stages
that carry it:

  lineup           starters per position (dedicated + superflex + flex) that
                   allocate() derives from mean projected points; each chart
                   uses them as its starter count
  bench            bench seats per position from the same allocate() call;
                   each chart uses them for its rostered count
  fill_in          the VP-2.4 estimates for rosterable players a chart does not
                   list: which players (the mean-points fill set) and the
                   curve-path value (mean points)
  position_weight  the projection sources' own mixes inside the DDF weights
                   (ddf_weights averages every included source, hidden ones too)

The direct chart inputs (each chart's natives, the included and hidden sets)
are identical on both sides of every pair; check_projection_only() refuses a
pair otherwise. Attribution is the Shapley value over the four stage outputs
(16 hybrid runs per pair). What still moves with all four held at baseline is
the unattributed residual, reported separately and never folded into a stage.

Nothing here changes the engine. A hybrid run swaps stage outputs inside this
process only, by wrapping value_reference._source_lines (charts only) and
value_reference.ddf_weights for the length of one call.

Commands (offline; no network, Supabase or production data):
  python3 tools/research/projection-influence-ledger/ledger.py freeze
  python3 tools/research/projection-influence-ledger/ledger.py run [--jobs N]
  python3 tools/research/projection-influence-ledger/ledger.py check
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import itertools
import json
import math
import shutil
import statistics
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))

import value_reference as vr  # noqa: E402

HERE = Path(__file__).resolve().parent
FROZEN = REPO / "tests" / "fixtures" / "projection-influence-ledger" / "frozen_inputs.json"
LEDGER = REPO / "docs" / "research" / "projection-influence-ledger" / "ledger.json"
READOUT = REPO / "docs" / "research" / "projection-influence-ledger" / "ledger-readout.md"
JS_DRIVER = HERE / "js_engine.cjs"
JS_ENGINE = REPO / "app" / "trade-value-chart" / "assets" / "value-model.js"

ENGINE_SHA = "430791c41ca9578d878c14c3a37d37a0f3fe0670"
# Files whose content decides the numbers in a run. `run` refuses to write a
# ledger when any of them differs from the copy hashed at `freeze`.
ENGINE_FILES = (
    "pipelines/value_reference.py",
    "pipelines/lib/roster_convention.py",
    "config/market_bench.json",
    "app/trade-value-chart/assets/value-model.js",
)
# Read once at `freeze` (their output, the resolved lineup, is frozen).
FREEZE_FILES = (
    "data/fixtures/current/comparison-sources-data.json",
    "data/fixtures/current/players.json",
    "config/lineup_parameters.json",
    "pipelines/derive_lineup_parameters.py",
)
FREEZE_TODAY = date(2026, 10, 29)   # the fixture's build date; pins the content-week clock

CHANNELS = ("lineup", "bench", "fill_in", "position_weight")
SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)
DELTA_PPG = 1.0
# The JEG-1047 readout's page-rounding threshold, reused so counts compare
# with that readout. It is a reporting cut, not a tolerance.
MOVE_EPS = 0.05
# Float-noise floor for "any move" counts: a recomputed sum can differ in its
# last bits without any input changing.
NONZERO_EPS = 1e-9
TOP_MOVERS = 5
DIGITS = 6
JS_SETTINGS = (("ppr", 12), ("standard", 8))


class NotProjectionOnly(ValueError):
    """A pair changes something other than projection inputs."""


# ---------------------------------------------------------------------------
# Hashing and provenance
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(rel: str) -> str:
    return sha256_bytes((REPO / rel).read_bytes())


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def git_blob(rel: str, rev: str | None = None) -> str | None:
    spec = f"{rev}:{rel}" if rev else None
    cmd = ["git", "rev-parse", spec] if spec else ["git", "hash-object", rel]
    try:
        proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def engine_hashes() -> dict:
    return {rel: sha256_file(rel) for rel in ENGINE_FILES}


def engine_drift(frozen: dict) -> list[str]:
    """Engine files that differ from the copies hashed at freeze."""
    pinned = frozen["provenance"]["engine_files"]
    now = engine_hashes()
    return sorted(rel for rel in ENGINE_FILES if pinned.get(rel, {}).get("sha256") != now[rel])


# ---------------------------------------------------------------------------
# Freeze: the committed fixture at the pinned SHA -> the exact per-setting
# inputs the engine consumes
# ---------------------------------------------------------------------------

def league_for(teams: int, frozen: dict | None = None) -> vr.League:
    """The page's default league at `teams`, exactly as Setting builds it
    (freeze() asserts the two are equal). A frozen document may carry its own
    `league` (the small test fixture does)."""
    if frozen and frozen.get("league"):
        lg = frozen["league"]
        return vr.League(teams=int(teams), slots=dict(lg["slots"]), flex=lg["flex"], superflex=lg["superflex"],
                         bench=lg["bench"], bench_share=lg.get("bench_share", vr.DEFAULT_BENCH_SHARE))
    shape = {**vr.roster(0), "QB": 1}
    return vr.League(teams=int(teams), slots={p: shape[p] for p in vr.POSITIONS}, flex=shape["FLEX"],
                     superflex=shape["SUPERFLEX"], bench=shape["BENCH"],
                     bench_share=vr.DEFAULT_BENCH_SHARE, position_shares=None, bench_share_override=None)


def _captured(section: dict | None) -> dict:
    sec = section or {}
    keep = ("week_designated", "content_vintage", "vintage", "published", "fetched_at",
            "espn_snapshot", "snapshot_id", "update_cadence")
    return {k: sec[k] for k in keep if isinstance(sec.get(k), str)}


def freeze() -> dict:
    inp = vr.Inputs.load(today=FREEZE_TODAY)
    fixture = inp.fixture
    lineup = vr.resolve_lineup(vr.load_lineup_config())
    scorings, players = {}, {}
    for scoring in SCORINGS:
        states = {}
        for teams in TEAMS:
            setting = vr.Setting(inp, scoring, teams)
            if setting.league != league_for(teams):
                raise AssertionError(f"league_for({teams}) differs from Setting's league")
            st = setting.state()
            states[teams] = {"included": list(st["included"]), "hidden": sorted(st["hidden"]),
                             "excluded": dict(sorted(st["excluded"].items())),
                             "natives": {k: dict(sorted(v.items())) for k, v in st["current"].items() if v}}
        first = states[TEAMS[0]]
        for teams in TEAMS[1:]:
            if canonical(states[teams]) != canonical(first):
                raise AssertionError(f"{scoring}: the included set or natives differ by team count")
        for nat in first["natives"].values():
            for key in nat:
                players[key] = {"pos": inp.players[key]["pos"], "name": inp.players[key]["name"]}
        scorings[scoring] = {**first, "natives": {k: {str(i): x for i, x in v.items()}
                                                  for k, v in first["natives"].items()}}
    sources = {}
    for key in vr.SOURCES:
        sec = inp.section(key)
        sources[key] = {"family": vr.FAMILY[key], "horizon": (sec or {}).get("week_designated"),
                        "captured": _captured(sec), "hold": vr.section_hold(inp, key),
                        "hold_level": vr.section_hold_level(inp, key)}
    doc = {
        "schema": "projection-influence-frozen-inputs/1",
        "ticket": "JEG-1280",
        "source_order": list(vr.SOURCES),
        "provenance": {
            "engine_sha": ENGINE_SHA,
            "head_at_freeze": _git_head(),
            "today": FREEZE_TODAY.isoformat(),
            "fixture_built_at": fixture.get("built_at"),
            "engine_files": {rel: {"sha256": sha256_file(rel), "git_blob": git_blob(rel)} for rel in ENGINE_FILES},
            "freeze_files": {rel: {"sha256": sha256_file(rel), "git_blob": git_blob(rel)} for rel in FREEZE_FILES},
            "sources": sources,
            "setting_equivalence": None,
        },
        "lineup": lineup,
        "players": {str(k): players[k] for k in sorted(players)},
        "scorings": scorings,
    }
    doc["provenance"]["setting_equivalence"] = _setting_equivalence(inp, doc)
    doc["provenance"]["natives_sha256"] = sha256_bytes(canonical(doc["scorings"]))
    return doc


def _git_head() -> str | None:
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO), capture_output=True,
                              text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _setting_equivalence(inp, doc) -> dict:
    """Running the pipeline on the frozen inputs reproduces Setting.result()
    exactly (every DDF version of every row, all 12 settings)."""
    worst = 0.0
    for scoring in SCORINGS:
        for teams in TEAMS:
            own = vr.Setting(inp, scoring, teams).result()["rows"]
            case = base_case(doc, scoring)
            ours = run_case(doc, scoring, teams, case)["rows"]
            if set(own) != set(ours):
                raise AssertionError(f"{scoring}/{teams}: frozen rows differ from Setting rows")
            for i in own:
                for version in ("blended", "charts", "projections"):
                    a, b = own[i]["ddf"][version]["value"], ours[i]["ddf"][version]["value"]
                    if (a is None) != (b is None):
                        raise AssertionError(f"{scoring}/{teams}/{i}/{version}: None mismatch")
                    if a is not None:
                        worst = max(worst, abs(a - b))
    if worst != 0.0:
        raise AssertionError(f"frozen inputs do not reproduce Setting.result() (worst {worst})")
    return {"settings": len(SCORINGS) * len(TEAMS), "max_abs_difference": 0.0}


# ---------------------------------------------------------------------------
# Cases, the projection-only guard and one pipeline run
# ---------------------------------------------------------------------------

def base_case(frozen: dict, scoring: str) -> dict:
    """{natives: {src: {int key: value}}, included, hidden, horizon}."""
    s = frozen["scorings"][scoring]
    src_meta = frozen["provenance"]["sources"]
    return {"natives": {k: {int(i): float(x) for i, x in v.items()} for k, v in s["natives"].items()},
            "included": list(s["included"]), "hidden": sorted(s["hidden"]),
            "horizon": {k: src_meta[k]["horizon"] for k in s["natives"]}}


def with_condition(case: dict, excluded=(), hidden=()) -> dict:
    """The same case with projection sources taken out of I (`excluded`) or
    given held semantics (`hidden`: in I, out of the DDF blend). Applied to
    both sides of a pair, so it is part of what the pair holds fixed."""
    out = copy.deepcopy(case)
    out["included"] = [k for k in out["included"] if k not in set(excluded)]
    out["hidden"] = sorted(set(out["hidden"]) | set(hidden))
    return out


def edited(case: dict, edits: dict, horizon: dict | None = None) -> dict:
    """edits: {source: {player key: new native, or None = no longer listed}}."""
    out = copy.deepcopy(case)
    for src, changes in edits.items():
        nat = out["natives"].setdefault(src, {})
        for key, value in changes.items():
            key = int(key)
            if value is None:
                nat.pop(key, None)
            else:
                nat[key] = float(value)
    if horizon:
        out["horizon"].update(horizon)
    return out


def source_order(frozen: dict) -> list:
    """Source-key order of the run (VP-0): peers, mean points and the DDF
    lists follow it. JSON objects are written with sorted keys, so it is
    stored as a list."""
    return list(frozen.get("source_order") or vr.SOURCES)


def family_of(frozen: dict, src: str) -> str:
    return frozen["provenance"]["sources"][src]["family"]


def chart_inputs(frozen: dict, case: dict) -> dict:
    """Everything a chart observes directly: its natives and the I / hidden sets."""
    charts = {k: sorted(v.items()) for k, v in case["natives"].items() if family_of(frozen, k) == "chart"}
    return {"charts": charts, "included": case["included"], "hidden": case["hidden"]}


def projection_inputs(frozen: dict, case: dict) -> dict:
    return {k: sorted(v.items()) for k, v in case["natives"].items() if family_of(frozen, k) == "projection"}


def check_projection_only(frozen: dict, base: dict, pert: dict) -> None:
    """Refuse a pair unless only projection natives differ."""
    if set(base["natives"]) != set(pert["natives"]):
        raise NotProjectionOnly("the set of sources differs between the two runs")
    for src in base["natives"]:
        if family_of(frozen, src) == "chart" and base["natives"][src] != pert["natives"][src]:
            raise NotProjectionOnly(f"chart input changed: {src} natives differ")
    if base["included"] != pert["included"]:
        raise NotProjectionOnly("the included set I differs")
    if base["hidden"] != pert["hidden"]:
        raise NotProjectionOnly("the hidden (held) set differs")
    for src in base["natives"]:
        if base["horizon"].get(src) != pert["horizon"].get(src):
            # Jeremy (2026-10-29 brief): "do not blend weekly data with ROS data, ever."
            raise NotProjectionOnly(f"{src} horizon changed ({base['horizon'].get(src)!r} -> "
                                    f"{pert['horizon'].get(src)!r}): weekly and ROS data would be blended")
    if projection_inputs(frozen, base) == projection_inputs(frozen, pert):
        raise NotProjectionOnly("no projection input changed")


def run_case(frozen: dict, scoring: str, teams: int, case: dict) -> dict:
    """One run_pipeline call on a case, as Setting.result() makes it."""
    pos_of = {int(k): p["pos"] for k, p in frozen["players"].items()}
    sources = {k: vr.SourceInput(k, family_of(frozen, k), dict(case["natives"][k]))
               for k in source_order(frozen) if k in case["natives"]}
    return vr.run_pipeline(league_for(teams, frozen), sources, pos_of, case["included"], None,
                           lineup=copy.deepcopy(frozen["lineup"]), hidden=set(case["hidden"]))


def chart_ddf(result: dict) -> dict:
    """{player key: DDF Value} (the blended version: the chart average)."""
    return {i: r["ddf"]["blended"]["value"] for i, r in result["rows"].items()}


# ---------------------------------------------------------------------------
# Stage capture and hybrid runs
# ---------------------------------------------------------------------------

def _slim_mix(detail: dict) -> dict:
    """The fields ddf_weights reads from one source's detail."""
    return {"family": detail["family"], "weights": copy.deepcopy(detail["weights"]),
            "starter_mix": copy.deepcopy(detail["starter_mix"]),
            "bench_mix": copy.deepcopy(detail["bench_mix"]),
            "positions": {p: {"method": detail["positions"][p]["method"]} for p in vr.POSITIONS}}


@contextlib.contextmanager
def _hooks(capture: dict | None = None, base: dict | None = None, pert: dict | None = None,
           live: frozenset = frozenset(CHANNELS)):
    """capture: record the stage outputs this run hands the charts and the
    weights. base/pert/live: hand each chart, and the weights, the stage
    outputs of `pert` for channels in `live` and of `base` for the rest."""
    orig_lines, orig_weights = vr._source_lines, vr.ddf_weights

    def lines(src, pos_of, alloc, estimates, es=None, promotion=None):
        if src.family == "chart":
            if capture is not None:
                capture["alloc"][src.key] = copy.deepcopy(alloc)
                capture["estimates"][src.key] = copy.deepcopy(estimates)
            if base is not None:
                alloc = _hybrid_alloc(base["alloc"][src.key], pert["alloc"][src.key], live)
                estimates = (pert if "fill_in" in live else base)["estimates"][src.key]
        return orig_lines(src, pos_of, alloc, estimates, es, promotion)

    def weights(league, details, included, computed_share=False):
        if capture is not None:
            capture["mixes"] = {k: _slim_mix(d) for k, d in details.items() if d["family"] == "projection"}
        if base is not None and "position_weight" not in live:
            details = {**details, **base["mixes"]}
        return orig_weights(league, details, included, computed_share)

    vr._source_lines, vr.ddf_weights = lines, weights
    try:
        yield
    finally:
        vr._source_lines, vr.ddf_weights = orig_lines, orig_weights


def _hybrid_alloc(base: dict, pert: dict, live: frozenset) -> dict:
    out = {}
    for p in vr.POSITIONS:
        s = pert[p] if "lineup" in live else base[p]
        b = pert[p] if "bench" in live else base[p]
        out[p] = {**s, "bench": b["bench"], "rostered": s["starters"] + b["bench"]}
    return out


def captured_run(frozen, scoring, teams, case):
    stage = {"alloc": {}, "estimates": {}, "mixes": {}}
    with _hooks(capture=stage):
        result = run_case(frozen, scoring, teams, case)
    return result, stage


def hybrid_values(frozen, scoring, teams, pert_case, base_stage, pert_stage) -> dict:
    """{frozenset of live channels: chart DDF Value by player} for all 16 subsets."""
    out = {}
    for n in range(len(CHANNELS) + 1):
        for live in itertools.combinations(CHANNELS, n):
            live = frozenset(live)
            with _hooks(base=base_stage, pert=pert_stage, live=live):
                out[live] = chart_ddf(run_case(frozen, scoring, teams, pert_case))
    return out


def shapley(values: dict, key) -> dict:
    """Shapley share of each channel in values[all][key] - values[none][key]."""
    n = len(CHANNELS)
    out = {}
    for c in CHANNELS:
        others = [x for x in CHANNELS if x != c]
        phi = 0.0
        for k in range(n):
            w = math.factorial(k) * math.factorial(n - k - 1) / math.factorial(n)
            for s in itertools.combinations(others, k):
                s = frozenset(s)
                phi += w * ((values[s | {c}].get(key) or 0.0) - (values[s].get(key) or 0.0))
        out[c] = phi
    return out


# ---------------------------------------------------------------------------
# One pair -> one ledger entry
# ---------------------------------------------------------------------------

def r6(x):
    return None if x is None else round(float(x), DIGITS) + 0.0


def attribute(frozen: dict, scoring: str, teams: int, base: dict, pert: dict, base_run=None) -> dict:
    """Both runs, their stage outputs and one row per player priced on both
    sides: {key, pos, base, perturbed, delta, <channel>..., residual}, where
    delta == sum of the channels + residual (Shapley efficiency)."""
    check_projection_only(frozen, base, pert)
    b_res, b_stage = base_run or captured_run(frozen, scoring, teams, base)
    p_res, p_stage = captured_run(frozen, scoring, teams, pert)
    if b_res["degenerate"] != p_res["degenerate"]:
        raise NotProjectionOnly("the pair flips the degenerate week (no projection in I)")
    b_val, p_val = chart_ddf(b_res), chart_ddf(p_res)
    values = hybrid_values(frozen, scoring, teams, pert, b_stage, p_stage)
    everything = frozenset(CHANNELS)
    if any(values[everything].get(i) != p_val.get(i) for i in set(p_val) | set(values[everything])):
        raise AssertionError("the hooks changed the unfrozen run")
    pos = {i: r["pos"] for i, r in p_res["rows"].items()}
    pos.update({i: r["pos"] for i, r in b_res["rows"].items()})
    rows = []
    for i in sorted(i for i in b_val if i in p_val and b_val[i] is not None and p_val[i] is not None):
        none = values[frozenset()].get(i)
        rows.append({"key": i, "pos": pos[i], "base": b_val[i], "perturbed": p_val[i], "delta": p_val[i] - b_val[i],
                     **shapley(values, i), "residual": (none - b_val[i]) if none is not None else 0.0})
    return {"base": (b_res, b_stage), "perturbed": (p_res, p_stage), "rows": rows,
            "added": sorted(set(p_val) - set(b_val)), "removed": sorted(set(b_val) - set(p_val)),
            "base_values": b_val, "perturbed_values": p_val}


def ledger_pair(frozen: dict, spec: dict, base: dict, pert: dict, base_run=None) -> dict:
    """spec: {id, experiment, scoring, teams, ...labels}. base/pert: cases."""
    got = attribute(frozen, spec["scoring"], spec["teams"], base, pert, base_run)
    (b_res, b_stage), (p_res, p_stage) = got["base"], got["perturbed"]
    b_val, p_val, entries = got["base_values"], got["perturbed_values"], got["rows"]
    names = frozen["players"]
    edited_keys = {int(k) for changes in spec.get("edits", {}).values() for k in changes}
    others = [e for e in entries if e["key"] not in edited_keys]

    def agg(rows, field):
        xs = [abs(e[field]) for e in rows]
        return {"max_abs": r6(max(xs, default=0.0)), "sum_abs": r6(sum(xs)),
                "moved": sum(1 for x in xs if x >= MOVE_EPS), "nonzero": sum(1 for x in xs if x > NONZERO_EPS)}

    by_pos = {}
    for p in vr.POSITIONS:
        xs = [abs(e["delta"]) for e in others if e["pos"] == p]
        by_pos[p] = {"max_abs": r6(max(xs, default=0.0)), "moved": sum(1 for x in xs if x >= MOVE_EPS)}
    top = sorted(others, key=lambda e: (-abs(e["delta"]), e["key"]))[:TOP_MOVERS]
    proj_b = {i: r["ddf"]["projections"]["value"] for i, r in b_res["rows"].items()}
    proj_p = {i: r["ddf"]["projections"]["value"] for i, r in p_res["rows"].items()}
    proj_moves = [abs(proj_p[i] - proj_b[i]) for i in proj_b
                  if i in proj_p and proj_b[i] is not None and proj_p[i] is not None and i not in edited_keys]
    added, removed = got["added"], got["removed"]
    return {
        **{k: spec[k] for k in sorted(spec) if k != "edits"},
        "edits": {src: {str(k): v for k, v in sorted(ch.items())} for src, ch in sorted(spec.get("edits", {}).items())},
        "edited_players": [{"key": k, "name": names[str(k)]["name"], "pos": names[str(k)]["pos"]}
                           for k in sorted(edited_keys) if str(k) in names],
        "condition": {"included": base["included"], "hidden": base["hidden"]},
        # Direct included chart inputs: identical on both sides (check_projection_only),
        # so the direct path contributes nothing by construction.
        "direct_chart_inputs": {"changed": False, "sha256": sha256_bytes(canonical(chart_inputs(frozen, base)))},
        "projection_inputs_sha256": {"base": sha256_bytes(canonical(projection_inputs(frozen, base))),
                                     "perturbed": sha256_bytes(canonical(projection_inputs(frozen, pert)))},
        "stages": _stage_changes(b_res, p_res, b_stage, p_stage),
        "chart_ddf_other_players": agg(others, "delta"),
        # Identical across pairs exactly when every player's move is (to 6 dp).
        "chart_ddf_delta_sha256": sha256_bytes(canonical([[e["key"], r6(e["delta"])] for e in entries])),
        "chart_ddf_by_position": by_pos,
        "chart_ddf_edited_players": [{"key": e["key"], "delta": r6(e["delta"])} for e in entries
                                     if e["key"] in edited_keys],
        "channels": {c: agg(others, c) for c in CHANNELS},
        "residual": agg(entries, "residual"),
        "projection_ddf_other_players_max_abs": r6(max(proj_moves, default=0.0)),
        "rows_added": [{"key": i, "chart_ddf": r6(p_val[i])} for i in added],
        "rows_removed": [{"key": i, "chart_ddf": r6(b_val[i])} for i in removed],
        "top_movers": [{"key": e["key"], "name": names[str(e["key"])]["name"], "pos": e["pos"],
                        "base": r6(e["base"]), "perturbed": r6(e["perturbed"]), "delta": r6(e["delta"]),
                        **{c: r6(e[c]) for c in CHANNELS}, "residual": r6(e["residual"])} for e in top],
    }


def _stage_changes(b_res, p_res, b_stage, p_stage) -> dict:
    out = {"lineup": {}, "bench": {}, "fill_in": {}, "ddf_weights_max_abs": 0.0}
    ba, pa = b_res["allocation"], p_res["allocation"]
    if ba and pa:
        for p in vr.POSITIONS:
            if ba[p]["starters"] != pa[p]["starters"]:
                out["lineup"][p] = [ba[p]["starters"], pa[p]["starters"]]
            if ba[p]["bench"] != pa[p]["bench"]:
                out["bench"][p] = [ba[p]["bench"], pa[p]["bench"]]
    for chart in sorted(b_stage["estimates"]):
        be, pe = b_stage["estimates"][chart], p_stage["estimates"].get(chart, {})
        b_keys = {(p, i) for p in be for i in be[p]}
        p_keys = {(p, i) for p in pe for i in pe[p]}
        moved = [abs(pe[p][i]["value"] - be[p][i]["value"]) for p, i in b_keys & p_keys]
        changed = {"added": len(p_keys - b_keys), "removed": len(b_keys - p_keys),
                   "value_changed": sum(1 for x in moved if x > NONZERO_EPS),
                   "max_value_change": r6(max(moved, default=0.0))}
        if any(changed[k] for k in ("added", "removed", "value_changed")):
            out["fill_in"][chart] = changed
    bw, pw = b_res["ddf_weights"], p_res["ddf_weights"]
    out["ddf_weights_max_abs"] = r6(max(abs(pw[g] - bw[g]) for g in vr.GROUPS))
    return out


# ---------------------------------------------------------------------------
# Experiments on the frozen inputs (all paired, fixed chart inputs)
# ---------------------------------------------------------------------------

def _line_player(result: dict, src: str, pos: str, which: str):
    """The player on src's waiver line (rank rostered + 1) or at rank 1."""
    info = result["sources"][src]["positions"].get(pos) or {}
    if info.get("method") != "roster_determined":
        return None
    rank = info["rostered"] + 1 if which == "waiver_line" else 1
    for i, pl in result["sources"][src]["players"].items():
        if pl["pos"] == pos and pl["rank"] == rank and not pl["imputed"]:
            return i
    return None


def experiments_for(frozen: dict, scoring: str, teams: int):
    """Yields (spec, base case, perturbed case, base run or None)."""
    base = base_case(frozen, scoring)
    proj = [k for k in source_order(frozen) if family_of(frozen, k) == "projection"]
    runs = {}

    def run_of(case_id, case):
        if case_id not in runs:
            runs[case_id] = captured_run(frozen, scoring, teams, case)
        return runs[case_id]

    tag = f"{scoring}-{teams}"
    b_run = run_of("base", base)
    # E1/E2: one projection source moves one player by +-1 PPG.
    for which, deltas in (("waiver_line", (1.0, -1.0)), ("top_player", (1.0,))):
        for src in proj:
            if src not in base["included"]:
                continue
            for pos in vr.POSITIONS:
                i = _line_player(b_run[0], src, pos, which)
                if i is None:
                    continue
                for d in deltas:
                    new = max(0.0, base["natives"][src][i] + d * DELTA_PPG)
                    spec = {"id": f"{tag}/{which}/{src}/{pos}/{d:+.0f}", "experiment": which,
                            "scoring": scoring, "teams": teams, "source": src, "pos": pos, "delta_ppg": d,
                            "edits": {src: {i: new}}}
                    yield spec, base, edited(base, spec["edits"]), b_run
    # E3: absent versus zero. ESPN lists a player it projects at zero at 0.0
    # (JEG-496), so he counts in mean points as 0. The pair removes him.
    zero_listed = sorted(i for i, x in base["natives"].get("espn", {}).items() if x == 0.0)
    for pos in vr.POSITIONS:
        cands = []
        for i in zero_listed:
            if frozen["players"][str(i)]["pos"] != pos:
                continue
            others = [base["natives"][k][i] for k in proj if k != "espn" and k in base["included"]
                      and i in base["natives"].get(k, {})]
            if others:
                cands.append((-statistics.fmean(others), i))
        if cands:
            i = sorted(cands)[0][1]
            spec = {"id": f"{tag}/espn_zero_to_absent/espn/{pos}", "experiment": "espn_zero_to_absent",
                    "scoring": scoring, "teams": teams, "source": "espn", "pos": pos, "edits": {"espn": {i: None}}}
            yield spec, base, edited(base, spec["edits"]), b_run
    # E3b: a player no chart lists. Absent from every projection versus listed
    # (as shipped): his chart DDF row exists (0 or a fill-in estimate) only
    # because a projection lists him.
    chart_listed = set()
    for k, v in base["natives"].items():
        if family_of(frozen, k) == "chart":
            chart_listed |= set(v)
    m = b_run[0]["mean_ppg"]
    for pos in vr.POSITIONS:
        cands = sorted((-m[i], i) for i in m if frozen["players"][str(i)]["pos"] == pos and i not in chart_listed)
        if not cands:
            continue
        i = cands[0][1]
        edits = {k: {i: None} for k in proj if i in base["natives"].get(k, {})}
        spec = {"id": f"{tag}/projection_only_player_absent/all/{pos}", "experiment": "projection_only_player_absent",
                "scoring": scoring, "teams": teams, "source": "all", "pos": pos, "edits": edits}
        yield spec, base, edited(base, edits), b_run
    # E4/E5: the same +1 waiver-line move with the source excluded from I, or
    # held (in I, hidden from the DDF blend), on both sides.
    for cond in ("excluded", "hidden"):
        for src in proj:
            if src not in base["included"]:
                continue
            c_base = with_condition(base, **{cond: (src,)})
            c_run = run_of(f"{cond}:{src}", c_base)
            for pos in vr.POSITIONS:
                i = _line_player(c_run[0], src, pos, "waiver_line")
                if i is None:
                    continue
                new = c_base["natives"][src][i] + DELTA_PPG
                spec = {"id": f"{tag}/source_{cond}/{src}/{pos}/+1", "experiment": f"source_{cond}",
                        "scoring": scoring, "teams": teams, "source": src, "pos": pos, "delta_ppg": 1.0,
                        "edits": {src: {i: new}}}
                yield spec, c_base, edited(c_base, spec["edits"]), c_run


def ledger_setting(frozen: dict, scoring: str, teams: int) -> list[dict]:
    return [ledger_pair(frozen, spec, b, p, b_run) for spec, b, p, b_run in experiments_for(frozen, scoring, teams)]


def _ledger_setting_job(args) -> list[dict]:
    frozen_path, scoring, teams = args
    return ledger_setting(json.loads(Path(frozen_path).read_text(encoding="utf-8")), scoring, teams)


# ---------------------------------------------------------------------------
# JS engine cross-check (production value-model.js, totals only)
# ---------------------------------------------------------------------------

def js_setting(teams: int, frozen: dict | None = None) -> dict:
    lg = league_for(teams, frozen)
    return {"teams": lg.teams, "slots": dict(lg.slots), "flex": lg.flex, "superflex": lg.superflex,
            "bench_per_team": lg.bench, "bench_share": lg.bench_share,
            "bench_share_override": None, "position_shares": None}


def js_cross_check(frozen: dict, entries: list[dict], settings=JS_SETTINGS) -> dict:
    """Re-run both sides of every pair at JS_SETTINGS on the JS engine and
    compare each player's chart DDF Value move with the reference's."""
    node = shutil.which("node")
    if node is None:
        return {"status": "skipped: node not found"}
    cases, plan = {}, []
    for e in entries:
        if (e["scoring"], e["teams"]) not in settings:
            continue
        base = base_case(frozen, e["scoring"])
        if e["experiment"] in ("source_excluded", "source_hidden"):
            base = with_condition(base, **{e["experiment"].split("_")[1]: (e["source"],)})
        pert = edited(base, e["edits"])
        ids = []
        for case in (base, pert):
            cid = sha256_bytes(canonical([e["scoring"], e["teams"], projection_inputs(frozen, case),
                                          case["included"], case["hidden"]]))
            cases[cid] = {"setting": js_setting(e["teams"], frozen), "included": case["included"], "hidden": case["hidden"],
                          "lineup": frozen["lineup"],
                          "sources": {k: {"family": family_of(frozen, k),
                                          "values": {str(i): x for i, x in sorted(case["natives"][k].items())}}
                                      for k in source_order(frozen) if k in case["natives"]}}
            ids.append(cid)
        plan.append((e, base, pert, ids))
    players = {k: {"pos": v["pos"], "name": v["name"]} for k, v in frozen["players"].items()}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cases.json"
        path.write_text(json.dumps({"players": players, "cases": cases}), encoding="utf-8")
        proc = subprocess.run([node, str(JS_DRIVER), str(JS_ENGINE), str(path)], capture_output=True,
                              text=True, timeout=1200)
    if proc.returncode != 0:
        return {"status": "failed", "stderr": proc.stderr[-2000:]}
    js = json.loads(proc.stdout)
    worst_level = worst_delta = 0.0
    for e, base, pert, (bid, pid) in plan:
        py_b = chart_ddf(run_case(frozen, e["scoring"], e["teams"], base))
        py_p = chart_ddf(run_case(frozen, e["scoring"], e["teams"], pert))
        for i in py_b:
            jb, jp = js[bid].get(str(i)), js[pid].get(str(i))
            if py_b[i] is None or jb is None or i not in py_p or jp is None:
                continue
            worst_level = max(worst_level, abs(jb - py_b[i]), abs(jp - py_p[i]))
            worst_delta = max(worst_delta, abs((jp - jb) - (py_p[i] - py_b[i])))
    return {"status": "ran", "engine": "app/trade-value-chart/assets/value-model.js",
            "settings": [f"{s}-{t}" for s, t in settings], "pairs": len(plan),
            "max_abs_level_difference": float(f"{worst_level:.3g}"),
            "max_abs_delta_difference": float(f"{worst_delta:.3g}")}


# ---------------------------------------------------------------------------
# Ledger document and readout
# ---------------------------------------------------------------------------

def build_ledger(frozen: dict, frozen_path: Path = FROZEN, jobs: int = 1, js: bool = True) -> dict:
    if jobs > 1:
        tasks = [(str(frozen_path), s, t) for s in SCORINGS for t in TEAMS]
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            chunks = list(pool.map(_ledger_setting_job, tasks))
    else:
        chunks = [ledger_setting(frozen, s, t) for s in SCORINGS for t in TEAMS]
    entries = sorted((e for chunk in chunks for e in chunk), key=lambda e: e["id"])
    prov = frozen["provenance"]
    return {
        "schema": "projection-influence-ledger/1",
        "ticket": "JEG-1280",
        "engine_sha": prov["engine_sha"],
        "engine": "pipelines/value_reference.py (Python reference); totals cross-checked on value-model.js",
        "frozen_inputs": {"path": str(frozen_path.relative_to(REPO)),
                          "sha256": sha256_bytes(frozen_path.read_bytes()),
                          "natives_sha256": prov["natives_sha256"]},
        "provenance": {k: prov[k] for k in ("today", "fixture_built_at", "engine_files", "freeze_files",
                                             "sources", "setting_equivalence")},
        "definitions": {
            "chart_ddf": "rows[i].ddf.blended.value = equal-weight mean of the included, visible charts' "
                         "Adjusted values (value_reference.py DDF_FAMILY, _rows, _ddf)",
            "channels": list(CHANNELS),
            "attribution": "Shapley value over the four stage outputs; residual = chart DDF with all four "
                           "held at baseline minus baseline",
            "move_eps": MOVE_EPS,
            "delta_ppg": DELTA_PPG,
        },
        "limitations": LIMITATIONS,
        "js_cross_check": js_cross_check(frozen, entries) if js else {"status": "skipped: --no-js"},
        "summary": summarize(entries),
        "pairs": entries,
    }


LIMITATIONS = [
    "Pinned engine SHA 430791c4: each projection source's waiver line is one player (work[n_rost]). "
    "The seven-player waiver-line average Jeremy approved (pick A, JEG-1244 / #1077) is not on main at "
    "this SHA; nothing here measures or implements it.",
    "Week view and prior week are off (no history): every source is priced on its current fixture "
    "values, as Setting.result() does without a History.",
    "Default league only (1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 7 bench, no superflex), default lineup "
    "parameters, default value basis and no DDF input selection.",
    "Attribution runs on the Python reference; the JS engine reproduces totals (js_cross_check), not "
    "the stage split, because it has no hook.",
    "Perturbations are synthetic (+-1 PPG to one player, a zero-listed player made absent, a "
    "projection-only player removed). They show where coupling exists and how large it is per PPG; they "
    "are not a forecast of weekly movement.",
]


def summarize(entries: list[dict]) -> dict:
    out = {}
    by_id = {e["id"]: e for e in entries}
    for exp in sorted({e["experiment"] for e in entries}):
        rows = [e for e in entries if e["experiment"] == exp]
        mx = [e["chart_ddf_other_players"]["max_abs"] for e in rows]
        totals = {c: sum(e["channels"][c]["sum_abs"] for e in rows) for c in CHANNELS}
        grand = sum(totals.values())
        same = [e["chart_ddf_by_position"][e["pos"]]["max_abs"] for e in rows if e.get("pos") in vr.POSITIONS]
        cross = [max(v["max_abs"] for p, v in e["chart_ddf_by_position"].items() if p != e["pos"])
                 for e in rows if e.get("pos") in vr.POSITIONS]
        out[exp] = {
            "pairs": len(rows),
            "same_position_max_abs": r6(max(same, default=0.0)),
            "other_positions_max_abs": r6(max(cross, default=0.0)),
            "pairs_any_move": sum(1 for x in mx if x > NONZERO_EPS),
            "pairs_move_ge_eps": sum(1 for e in rows if e["chart_ddf_other_players"]["moved"]),
            "median_max_abs": r6(statistics.median(mx)) if mx else None,
            "max_abs": r6(max(mx, default=0.0)),
            "worst_pair": max(rows, key=lambda e: (e["chart_ddf_other_players"]["max_abs"], e["id"]))["id"] if rows else None,
            "channel_share_of_abs_attribution": {c: r6(totals[c] / grand) if grand > 0 else None for c in CHANNELS},
            "pairs_where_channel_moved": {c: sum(1 for e in rows if e["channels"][c]["nonzero"]) for c in CHANNELS},
            "residual_max_abs": r6(max(e["residual"]["max_abs"] for e in rows)),
            "rows_added": sum(len(e["rows_added"]) for e in rows),
            "rows_removed": sum(len(e["rows_removed"]) for e in rows),
            "projection_ddf_median_max_abs": r6(statistics.median(
                [e["projection_ddf_other_players_max_abs"] for e in rows])) if rows else None,
        }
        if exp == "source_hidden":
            # The same +1 move with the source visible is the waiver_line pair.
            twins = [(e, by_id.get(e["id"].replace(f"/{exp}/", "/waiver_line/"))) for e in rows]
            twins = [(e, t) for e, t in twins if t is not None and t["edits"] == e["edits"]]
            out[exp]["same_as_waiver_line_pair"] = {
                "compared": len(twins),
                "identical_moves": sum(1 for e, t in twins if e["chart_ddf_delta_sha256"] == t["chart_ddf_delta_sha256"])}
    return out


EXPERIMENT_TEXT = {
    "waiver_line": "One projection source moves its waiver-line player by +-1 PPG",
    "top_player": "One projection source moves its top player at the position by +1 PPG",
    "espn_zero_to_absent": "A player ESPN lists at 0.0 (JEG-496) is made absent from ESPN",
    "projection_only_player_absent": "The best player no chart lists is removed from every projection",
    "source_excluded": "Waiver-line +1 PPG with that source excluded from I on both sides",
    "source_hidden": "Waiver-line +1 PPG with that source held (in I, hidden) on both sides",
}


def readout(ledger: dict) -> str:
    s = ledger["summary"]
    lines = [
        "# Projection influence ledger: readout",
        "",
        "Generated by `tools/research/projection-influence-ledger/ledger.py run` (JEG-1280). Do not edit;",
        "rerun the command. The memo that interprets these numbers is [README.md](README.md).",
        "",
        f"- Engine SHA: `{ledger['engine_sha']}` (read only)",
        f"- Frozen inputs: `{ledger['frozen_inputs']['path']}` `{ledger['frozen_inputs']['sha256']}`",
        f"- Fixture built at: {ledger['provenance']['fixture_built_at']}; content-week clock pinned to "
        f"{ledger['provenance']['today']}",
        f"- Pairs: {len(ledger['pairs'])} over 3 scorings x 4 team counts",
        "",
        "## Chart DDF Value moves of players other than the edited one",
        "",
        "| Experiment | Pairs | Pairs with any move | Pairs with a move >= 0.05 | Median worst move | Worst move | "
        "Worst, same position | Worst, other positions | Worst pair | DDF Projections median worst move |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for exp in EXPERIMENT_TEXT:
        if exp not in s:
            continue
        x = s[exp]
        lines.append(f"| {EXPERIMENT_TEXT[exp]} | {x['pairs']} | {x['pairs_any_move']} | {x['pairs_move_ge_eps']} | "
                     f"{x['median_max_abs']:.3f} | {x['max_abs']:.3f} | {x['same_position_max_abs']:.3f} | "
                     f"{x['other_positions_max_abs']:.3f} | `{x['worst_pair']}` | "
                     f"{x['projection_ddf_median_max_abs']:.3f} |")
    lines += ["", "## Which stage carries it (share of absolute Shapley attribution)", "",
              "| Experiment | " + " | ".join(CHANNELS) + " | Residual (max abs) | Rows added / removed |",
              "|---|" + "---|" * len(CHANNELS) + "---|---|"]
    for exp in EXPERIMENT_TEXT:
        if exp not in s:
            continue
        x = s[exp]
        shares = [("n/a" if x["channel_share_of_abs_attribution"][c] is None
                   else f"{100 * x['channel_share_of_abs_attribution'][c]:.1f}% ({x['pairs_where_channel_moved'][c]})")
                  for c in CHANNELS]
        lines.append(f"| {EXPERIMENT_TEXT[exp]} | " + " | ".join(shares) +
                     f" | {x['residual_max_abs']:.6f} | {x['rows_added']} / {x['rows_removed']} |")
    lines += ["", "In brackets: pairs in which that stage moved at least one player.", ""]
    if "same_as_waiver_line_pair" in s.get("source_hidden", {}):
        t = s["source_hidden"]["same_as_waiver_line_pair"]
        lines += ["## Held sources against the same edit with the source visible", "",
                  f"{t['identical_moves']} of {t['compared']} held-source pairs move every player's chart DDF Value "
                  "exactly (to 6 dp) as the same edit does with the source visible.", ""]
    js = ledger["js_cross_check"]
    lines += ["## JS engine cross-check", ""]
    if js.get("status") == "ran":
        lines.append(f"Both sides of the {js['pairs']} pairs at {', '.join(js['settings'])} re-run on "
                     f"`{js['engine']}`: largest level difference {js['max_abs_level_difference']}, largest "
                     f"move difference {js['max_abs_delta_difference']} (DDF Value points).")
    else:
        lines.append(f"Not run: {js.get('status')}.")
    lines += ["", "## Worst pair per experiment", ""]
    by_id = {e["id"]: e for e in ledger["pairs"]}
    for exp in EXPERIMENT_TEXT:
        if exp not in s or s[exp]["worst_pair"] is None:
            continue
        e = by_id[s[exp]["worst_pair"]]
        who = ", ".join(f"{p['name']} ({p['pos']})" for p in e["edited_players"]) or "none"
        lines += [f"### `{e['id']}`", "",
                  f"Edited: {who}. Stage changes: lineup {e['stages']['lineup'] or 'none'}, bench "
                  f"{e['stages']['bench'] or 'none'}, fill-in {sorted(e['stages']['fill_in']) or 'none'}, "
                  f"largest DDF weight change {e['stages']['ddf_weights_max_abs']}.", "",
                  "| Player | Pos | Base | Perturbed | Move | " + " | ".join(CHANNELS) + " | Residual |",
                  "|---|---|---|---|---|" + "---|" * len(CHANNELS) + "---|"]
        for t in e["top_movers"]:
            lines.append(f"| {t['name']} | {t['pos']} | {t['base']:.3f} | {t['perturbed']:.3f} | {t['delta']:+.3f} | "
                         + " | ".join(f"{t[c]:+.3f}" for c in CHANNELS) + f" | {t['residual']:+.6f} |")
        lines.append("")
    lines += ["## Limitations", ""] + [f"- {x}" for x in ledger["limitations"]] + [""]
    return "\n".join(lines)


def dump(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def dump_ledger(ledger: dict) -> str:
    """The header indented, then one pair per line (sorted by id)."""
    head = dump({k: v for k, v in ledger.items() if k != "pairs"}).rstrip()[:-1].rstrip()
    pairs = ",\n".join("  " + json.dumps(e, sort_keys=True, separators=(",", ":")) for e in ledger["pairs"])
    return head + ',\n "pairs": [\n' + pairs + "\n ]\n}\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze", help="freeze the committed fixture's per-setting inputs")
    for name in ("run", "check"):
        p = sub.add_parser(name)
        p.add_argument("--jobs", type=int, default=1)
        p.add_argument("--no-js", action="store_true", help="skip the JS engine cross-check")
    args = ap.parse_args(argv)
    if args.cmd == "freeze":
        FROZEN.parent.mkdir(parents=True, exist_ok=True)
        FROZEN.write_text(dump(freeze()), encoding="utf-8")
        print(f"wrote {FROZEN.relative_to(REPO)}")
        return 0
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    drift = engine_drift(frozen)
    if drift:
        print("engine files differ from the frozen copies; the ledger would not be the pinned SHA's:\n  "
              + "\n  ".join(drift), file=sys.stderr)
        return 2
    ledger = build_ledger(frozen, FROZEN, jobs=args.jobs, js=not args.no_js)
    text, md = dump_ledger(ledger), readout(ledger)
    if args.cmd == "check":
        if args.no_js:
            old = json.loads(LEDGER.read_text(encoding="utf-8"))
            old["js_cross_check"] = ledger["js_cross_check"]
            same = dump_ledger(old) == text
        else:
            same = LEDGER.read_text(encoding="utf-8") == text
        print("ledger reproduces" if same else "ledger differs from the committed copy")
        return 0 if same else 1
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(text, encoding="utf-8")
    READOUT.write_text(md, encoding="utf-8")
    print(f"wrote {LEDGER.relative_to(REPO)} ({len(ledger['pairs'])} pairs) and {READOUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
