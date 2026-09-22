"""Monday-imputed waiver values, projection-space contract (2026-09-15).

What changed and why: the trade value chart retired its full-roster VORP
scale for the expected-lineup (starter-weighted) model. The old contract
chained integer trade values on the dead 0.2884 scale, so the waiver board's
"Monday value" no longer matched the chart it claimed to sit on (Juwan
Johnson: waiver 14 vs chart 1). This contract chains per-game ROS
projections in points - scale-free - and prices them through the chart's
own starter model (bin/starter_model.py, a verified port of the chart's
client-side math). The waiver board is now literally "the trade value
chart, one day smarter": same model, Monday-updated projections.

Per scoring leg (standard/half/full), the carried state per player is
(proj_pg, mult):
  proj_pg - chained Monday-updated per-game projection, healthy rate, in
            the leg's scoring points. First run: the chart's frozen
            ESPN-first per-game projection (blend_ppg).
  mult    - persistent ROS multiplier from the dated news/injury layer
            (1.0 = healthy). An injury entry multiplies by
            playable/games_left once; the discount then lives in the
            carried state until new evidence moves it.

Monday step (one market step per scoring, run ONCE - see DOUBLE-RUN HAZARD
in AGENTS.md):
  surprise_pg = form_pg - prior_pg            (form = xFP + 0.10*FPOE, the
  new_pg      = prior_pg + surprise_pg / 9     TD-stickiness share; 1 game
                                               of form vs 8 of prior)
  news injury: skip_form carries the per-game prior (a partial game on a
  bad ankle is not a role signal); missed games scale mult, never the rate.
  beneficiary bumps are ROS points -> converted to per-game.

Pricing happens downstream (dashboard builder / client) via starter_model:
  tv = model_display_value(updated_pg) * mult + lottery_edge
The lottery edge is the board's lottery_edge_tv, unchanged - the same edge
the chart's own upside toggle adds to its starter base, so the waiver
board's include-upside total matches the chart's by construction.

Monday-safe: frozen chart + project-observed form only. No fresh ECR, no
new ESPN projections. Wednesday remains the formal chart repricing event.

Identity contract (2026-09-15): every feed spells names differently
("Michael Pittman" vs "Michael Pittman Jr.", "Cam Ward" vs "Cameron Ward").
The leg universe is keyed by CANONICAL identity (bin/identity.py, backed by
the Supabase player_identities registry via data/player_identity_map.json):
chart players first, then feed variants merged onto their canonical record,
so one human is exactly one leg record. The frozen-chart prior is looked up
by canonical key - a variant spelling must never fall back to carrying its
own one-week form as the prior (that bug priced Pittman at 4.06 instead of
the honest 7.56 blend and manufactured a phantom 20->0 drop; it hit all six
known alias pairs in both directions). A fail-closed audit at the end of
each leg raises if any chart player with Week-N form fell back to a form
prior - that means a new variant needs to be added to the registry.

Run:  bin/impute_monday_tv.py [--scoring half] [--prior PATH] [--week N]
                               [--games-left N]
      bin/impute_monday_tv.py --report [--scoring half]
One invocation runs all three scoring legs (the single market step). The
prior defaults to the leg's own previous file; a missing file or a file
pre-dating this contract falls back to the frozen chart base (first run).
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chart_paths import CHART_PLAYERS_JSON  # noqa: E402

LOT = Path(__file__).resolve().parent.parent
RES = LOT / "results"
DATA = LOT / "data"
TRENDS = json.loads((LOT.parent / "waiver-trends" / "results"
                     / "trends_latest.json").read_text())
CHART = json.load(open(CHART_PLAYERS_JSON))

PRIOR_W = 8          # games of prior weight against one game of new form
EFF_SHARE = 0.10     # form = xFP + EFF_SHARE * FPOE (opportunity full, efficiency
                     # one-tenth). Data-driven 2026-09-14 (results/td_stickiness.md):
                     # week-to-week FPOE autocorrelation is 0.011 - essentially zero -
                     # while xFP persists at 0.674; the residual partial coefficient
                     # predicting next-week points is 0.09 pooled. TD value does not
                     # imply future TDs; the 0.5 credit was ~5x what the data supports.

SCORINGS = ("standard", "half", "full")
BKEY = {"standard": "standard", "half": "half_ppr", "full": "ppr"}
# receptions adjustment restating half-PPR xFP to the leg's scoring
REC_C = {"standard": -0.5, "half": 0.0, "full": 0.5}


def norm_name(n):
    return re.sub(r"[^a-z ]", "", n.lower()).strip()


# Whole-market universe: every chart player, plus any trends-panel player
# outside the chart (priced from observed form; unobserved and unprojected
# players are excluded from the model). key -> (display name, pos, team)
# Chart players seed the universe; trends-panel variants merge onto their
# canonical identity below (after IDENT is built).
UNIVERSE = {}
for p in CHART["players"]:
    UNIVERSE[norm_name(p["name"])] = (p["name"], p["pos"], p.get("team"))


def frozen_blend_pg(scoring):
    """Frozen ESPN-first per-game projection per player (the chart's own
    blend_ppg). {norm_name: pg or None}."""
    bkey = BKEY[scoring]
    out = {}
    for p in CHART["players"]:
        b = (p.get("blend_ppg") or {}).get(bkey)
        out[norm_name(p["name"])] = float(b) if b is not None else None
    return out


def frozen_ecr_pg(scoring):
    """Frozen expert per-game projection per player (the chart's ECR mode)."""
    bkey = BKEY[scoring]
    out = {}
    for p in CHART["players"]:
        b = (p.get("ecr_ppg") or {}).get(bkey)
        out[norm_name(p["name"])] = float(b) if b is not None else None
    return out


FROZEN_BLEND = {s: frozen_blend_pg(s) for s in SCORINGS}
FROZEN_ECR = {s: frozen_ecr_pg(s) for s in SCORINGS}

# Canonical identity map (Supabase player_identities registry snapshot).
# Chart keys are the canonical key space by construction.
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from identity import IdentityMap  # noqa: E402
from board_week import board_stem  # noqa: E402
IDENT = IdentityMap(chart_keys=set(FROZEN_BLEND["half"]))


def edge_map():
    board = json.loads((RES / (board_stem() + ".json")).read_text())
    d = {}
    for sec in ("lottery_tickets", "upside_stashes", "on_the_radar"):
        for p in board[sec]:
            d.setdefault(IDENT.canon(norm_name(p["player"])),
                         p.get("lottery_edge_tv") or 0)
    return d


EDGE = edge_map()


# Merge trends-panel players onto the canonical universe: a feed variant
# whose identity resolves to a chart player does NOT get its own leg record
# (that duplicate is what mispriced Pittman et al). FORM holds the Week-N
# on-field evidence by canonical identity - whichever variant carried the
# read contributes it, preferring the variant with an actual xFP read.
for tkey in sorted(TRENDS):
    t = TRENDS[tkey]
    ck = IDENT.canon(tkey)
    if ck not in UNIVERSE:
        UNIVERSE[ck] = (t.get("name") or tkey, t.get("pos"), t.get("team"))
FORM = {}
for tkey in sorted(TRENDS):
    t = TRENDS[tkey]
    ck = IDENT.canon(tkey)
    cur = FORM.get(ck)
    if cur is None or (cur.get("xfp") is None and t.get("xfp") is not None):
        FORM[ck] = t


def load_news():
    """Dated injury/news entries not yet consumed by a run.

    Returns (pending, consumed): pending entries are those whose id is not
    in results/news_consumed.json. Each entry applies ONCE - after a run
    consumes it, the adjustment lives in the carried state and the entry is
    never applied again (change-not-level)."""
    pending, consumed = [], {}
    fp = DATA / "news_adjustments.json"
    if fp.exists():
        pending = json.loads(fp.read_text()).get("entries", [])
    cp = RES / "news_consumed.json"
    if cp.exists():
        consumed = json.loads(cp.read_text())
    return [e for e in pending if e.get("id") not in consumed], consumed


def observed_week_players(week):
    """Normed names with a logged stat row for the observed week.

    Explicit timing gate (user directive 2026-09-14): a player whose game
    has not occurred is carried at the prior, never treated as observed.
    Returns None when the cache is unreadable - the trends panel's own
    xfp/snap checks still apply as a backstop.

    Reads via pyarrow, not polars: polars is not installable in the
    scheduled runtime (PEP 668 externally-managed env). 2026-09-17.
    """
    try:
        import pyarrow.parquet as pq
        import pyarrow.compute as pc
    except ImportError:
        return None
    files = sorted(DATA.glob("player_stats_*.parquet"))
    if not files:
        return None
    try:
        tbl = pq.read_table(files[-1],
                            columns=["player_display_name", "week"])
    except Exception:
        return None
    w = tbl.filter(pc.field("week") == week)
    return {norm_name(n) for n in w.column("player_display_name").to_pylist() if n}


def load_receptions(week):
    """Actual receptions per player for the observed week, from the nflverse
    cache (Monday-safe: observed, not projected). Used to restate half-PPR
    xFP to full-PPR (+0.5/rec) or standard (-0.5/rec). Missing file or player
    -> 0 receptions (documented fallback).

    Reads via pyarrow, not polars: polars is not installable in the
    scheduled runtime, and the silent {} fallback was biasing the std/full
    legs' form reads (2026-09-17: 144 players/leg off by >=0.1 ppg).
    """
    try:
        import pyarrow.parquet as pq
        import pyarrow.compute as pc
    except ImportError:
        print("  WARNING: pyarrow unavailable - receptions fall back to 0")
        return {}
    files = sorted(DATA.glob("player_stats_*.parquet"))
    if not files:
        print("  WARNING: no player_stats parquet - receptions fall back to 0")
        return {}
    tbl = pq.read_table(files[-1],
                        columns=["player_display_name", "week", "receptions"])
    w = tbl.filter(pc.field("week") == week)
    out = {}
    for nm, r in zip(w.column("player_display_name").to_pylist(),
                     w.column("receptions").to_pylist()):
        if nm:
            out[norm_name(nm)] = r or 0
    return out


def prior_path(scoring):
    return RES / ("imputed_proj_%s.json" % scoring)


def load_prior(path):
    """{norm_name: (proj_pg, mult)} from a previous run under this contract.
    Returns None when the file is missing or pre-dates the contract (no
    "proj_pg" leg) - the run then starts from the frozen chart base."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        prev = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    out = {}
    for key, rec in prev.items():
        if "proj_pg" not in (rec or {}):
            return None
        # Prior files pre-dating canonical keys resolve through the identity
        # map so a rename never orphans carried state.
        out[IDENT.canon(key)] = (rec.get("proj_pg"), rec.get("mult") or 1.0)
    return out


def build_note(name, t, prior_pg, new_pg, mult, edge, week, first_run,
               form_pg=None, surprise_pg=None, played=False,
               news_note="", snap_txt=""):
    """One-line plain-words note. Pure function of the run's inputs."""
    if form_pg is None:
        anchor_noun = ("the preseason baseline" if first_run
                       else "last week's projection")
        if played:
            note = (f"Week {week} played but no expected-points read - "
                    f"carries {anchor_noun}.")
        else:
            note = f"No Week {week} line yet - carries {anchor_noun}."
    elif surprise_pg is not None and surprise_pg >= 1.0:
        note = (f"Week {week} role ({snap_txt}{form_pg:.1f} expected points) "
                f"beat his projection ({prior_pg:.1f} a game) - projection "
                f"nudged up.")
    elif surprise_pg is not None and surprise_pg <= -1.0:
        note = (f"Week {week} role ({snap_txt}{form_pg:.1f} expected points) "
                f"fell short of his projection ({prior_pg:.1f} a game) - "
                f"projection nudged down.")
    else:
        note = (f"Week {week} usage matched his projection "
                f"({prior_pg:.1f} expected points a game).")
    if news_note:
        note += news_note
    if edge > 0:
        note += f" Includes +{edge} of upside the model prices in."
    return note


def impute_player(name, pos, prev_pg, prev_mult, first_run, week,
                  games_left, scoring, rec_map, observed=None, news=None,
                  beneficiaries=()):
    """One step of a scoring leg's whole-market run. Chains the per-game
    projection (scale-free points); pricing happens downstream through the
    chart's starter model. Returns (proj_pg, mult, note, debug, news_id)."""
    key = norm_name(name)
    ck = IDENT.canon(key)
    t = FORM.get(ck)
    frozen = FROZEN_BLEND[scoring].get(ck)

    played = observed is None or ck in observed
    form_pg, fpoe, xfp_disp, snap_txt = None, 0.0, None, ""
    # On-field evidence: snap share is the direct read, but the 2026
    # participation cache has gaps - a real xFP or nonzero FPOE also proves
    # the player took the field (an all-zero placeholder row proves nothing).
    if (t and t.get("xfp") is not None and pos and played
            and ((t.get("snap_share") or 0) > 0
                 or (t["xfp"] or 0) > 0 or (t.get("fpoe") or 0) != 0)):
        fpoe = t.get("fpoe") or 0.0
        rec = (rec_map or {}).get(ck, 0) or 0
        xfp_s = t["xfp"] + REC_C[scoring] * rec
        xfp_disp = xfp_s
        form_pg = xfp_s + EFF_SHARE * fpoe
        if (t.get("snap_share") or 0) > 0:
            snap_txt = f"{t['snap_share']:.0f}% of snaps, "

    # Prior: chained, else frozen chart, else (non-chart player with form)
    # the form itself, else unpriceable. The frozen lookup is by canonical
    # identity - a variant spelling must resolve to the chart key, never fall
    # back to carrying its own one-week form as the prior.
    if prev_pg is not None:
        prior_pg, prior_source = prev_pg, "chained"
    elif frozen is not None:
        prior_pg, prior_source = frozen, "chart"
    else:
        prior_pg, prior_source = form_pg, "form"
    mult = prev_mult or 1.0
    if prior_pg is None:
        note = ("No chart projection and no Week %d line - off the board."
                % week)
        return None, mult, note, {"unpriced": True}, None

    surprise_pg = (form_pg - prior_pg) if form_pg is not None else 0.0
    new_pg = prior_pg + surprise_pg / (PRIOR_W + 1)

    # Dated news layer, on top of the prior + performance adjustment. The
    # base chart stays pure median; this layer lives only in the Monday
    # projections, on top of the priors. Missed games scale the ROS
    # multiplier, never the per-game rate.
    news_id, news_note = None, ""
    if news and news.get("kind") in ("injury", "suspension"):
        news_id = news.get("id")
        wks = news.get("weeks_out") or 0
        if news.get("skip_form") and t:
            # The injury explains the week: a partial game on a bad ankle
            # is not a role signal. Carry the per-game prior; the priced
            # adjustment is for missed games, applied below.
            surprise_pg, new_pg = 0.0, prior_pg
        if wks and games_left:
            playable = max(0, games_left - wks)
            mult = mult * playable / games_left
            news_note = (f" Injury adjustment ({news.get('date')}): "
                         f"{news.get('injury')}, {news.get('status')} - "
                         f"expected out ~{wks} weeks, so this prices "
                         f"{playable} of {games_left} remaining games.")
            if news.get("skip_form"):
                news_note += (f" The Week {week} line was injury-affected, "
                              f"not a role signal.")
    for b in beneficiaries:
        # Bump units: ROS points (none currently defined; kept for the
        # mechanism). A permanent bump to the per-game rate.
        bump_ros = b.get("bump_ros") or 0
        if bump_ros and games_left:
            new_pg += bump_ros / games_left
            news_note += f" {b.get('reason', 'Beneficiary bump')}: +{bump_ros}."
            news_id = news_id or b.get("news_id")

    new_pg = max(0.0, new_pg)
    edge = EDGE.get(ck) or 0
    note = build_note(name, t, prior_pg, new_pg, mult, edge, week, first_run,
                      form_pg=form_pg, surprise_pg=surprise_pg,
                      played=played, news_note=news_note, snap_txt=snap_txt)
    # FPOE color: role vs points honesty (PMM glossary).
    if form_pg is not None and fpoe >= 5:
        note += (f" Caution: {abs(fpoe):.1f} of his Week {week} points were "
                 f"scoring over expected - the role underneath is thinner "
                 f"than the points.")
    elif form_pg is not None and fpoe <= -3:
        note += (f" Note: he scored {abs(fpoe):.1f} under expected - the "
                 f"points are lagging the role, not the other way round.")
    debug = {"prior_pg": round(prior_pg, 2),
             "form_pg": round(form_pg, 2) if form_pg is not None else None,
             "surprise_pg": round(surprise_pg, 2),
             "new_pg": round(new_pg, 2), "mult": round(mult, 4),
             "edge": edge, "news_id": news_id,
             "prior_source": prior_source, "canonical_key": ck}
    return new_pg, mult, note, debug, news_id


def run_leg(scoring, week, games_left, prior_arg, rec_map,
            news_pending, observed):
    """Run one scoring leg end to end; write its carried state file.
    Returns (scoring, full, applied_news_ids)."""
    default_prior = str(prior_path(scoring))
    prior = load_prior(prior_arg or default_prior)
    first_run = prior is None
    # All name-keyed inputs canonicalize through the identity map: a feed
    # variant must land on the same record as its chart spelling.
    if rec_map:
        rec_map = {IDENT.canon(k): v for k, v in rec_map.items()}
    if observed is not None:
        observed = {IDENT.canon(k) for k in observed}
    news_map, ben_map = {}, {}
    for e in news_pending:
        k = norm_name(e.get("player") or "")
        if k and e.get("kind") in ("injury", "suspension"):
            news_map[IDENT.canon(k)] = e
        for b in e.get("beneficiaries", []):
            bk = norm_name(b.get("player") or "")
            if bk:
                bb = dict(b)
                bb["news_id"] = e.get("id")
                ben_map.setdefault(IDENT.canon(bk), []).append(bb)
    full = {}
    applied = set()
    for key, (name, pos, team) in UNIVERSE.items():
        if prior is not None:
            prev_pg, prev_mult = prior.get(key, (None, 1.0))
        else:
            prev_pg, prev_mult = None, 1.0
        new_pg, mult, note, dbg, nid = impute_player(
            name, pos, prev_pg, prev_mult, first_run, week, games_left,
            scoring, rec_map, observed=observed, news=news_map.get(key),
            beneficiaries=ben_map.get(key, ()))
        if nid:
            applied.add(nid)
        full[key] = {"name": name, "pos": pos, "team": team,
                     "proj_pg": new_pg, "mult": mult, "note": note,
                     "debug": dbg}
    out = prior_path(scoring)
    out.write_text(json.dumps(full, indent=1))
    # Fail-closed identity audit: a chart player with Week-N form must never
    # carry a form-fallback prior. If this fires, a new name variant appeared
    # that neither the registry snapshot nor the heuristic resolves - add it
    # to player_identities, do not weaken this check.
    regressed = sorted(
        k for k, r in full.items()
        if (r.get("debug") or {}).get("prior_source") == "form"
        and FROZEN_BLEND[scoring].get(k) is not None)
    if regressed:
        raise AssertionError(
            "identity regression: form-fallback prior for chart players: %s"
            % regressed)
    nfl = sum(1 for r in full.values()
              if (r.get("debug") or {}).get("prior_source") == "form")
    spot = full.get("juwan johnson", {}).get("debug", {})
    print("wrote %s for %d players (%d form-fallback, all non-chart) | prior: %s | week: %d | games_left: %d | "
          "johnson pg %s" % (out.name, len(full), nfl,
             "frozen chart base (first run)" if first_run else (prior_arg or default_prior),
             week, games_left, spot.get("new_pg")))
    return scoring, full, applied


METHOD_BLURB = (
    "**Method.** The legs chain per-game ROS projections in points - "
    "scale-free. Pricing happens through the trade value chart's own "
    "expected-lineup (starter-weighted) model, so the waiver board's Monday "
    "value is the chart's number recomputed on Monday's information. "
    "Monday step: surprise = this week's form (xFP + 0.10 x scoring "
    "over/under expected, the TD-stickiness share) minus the prior per-game "
    "projection, blended one game against eight of prior. The dated "
    "news/injury layer scales the ROS multiplier for missed games, never "
    "the per-game rate; the base chart stays pure median. The lottery edge "
    "is the board's lottery_edge_tv, unchanged - the same edge the chart's "
    "own upside toggle adds, so include-upside totals match the chart by "
    "construction. "
    "Approximation carried: the reception restatement (std/full legs) uses "
    "actual rather than expected receptions, so ~0.25x the reception "
    "surprise leaks into the opportunity leg - second order against one "
    "week of evidence. "
    "Contract history: the 2026-09-14/15 integer-TV contract (0.2884 scale, "
    "imputed_pg_*.json) is retired to results/retired_tv_contract_2026-09-15/ "
    "- it chained values on the chart's retired full-roster VORP scale and "
    "disagreed with the chart's starter-weighted display."
)


def write_report(week, scoring="half"):
    path = prior_path(scoring)
    if not path.exists():
        print("no leg file for %s - run the market step first" % scoring)
        return
    full = json.loads(path.read_text())
    movers = []
    for key, r in full.items():
        d = r.get("debug") or {}
        if d.get("surprise_pg") is not None and not d.get("unpriced"):
            movers.append((abs(d["surprise_pg"]), r["name"],
                           d["surprise_pg"], d["prior_pg"], d["new_pg"]))
    movers.sort(reverse=True)
    lines = ["# Monday projection pass - week %d (%s leg)" % (week, scoring),
             "", METHOD_BLURB, "",
             "## Largest projection moves (per-game points)",
             "| player | surprise | prior pg | new pg |",
             "|---|---|---|---|"]
    for _, name, s, p, n in movers[:15]:
        lines.append("| %s | %+.2f | %.2f | %.2f |" % (name, s, p, n))
    out = RES / ("monday_projection_report_week%d_%s.md" % (week, scoring))
    out.write_text(json.dumps("\n".join(lines) + "\n"))
    print("wrote %s" % out.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=1)
    ap.add_argument("--games-left", type=int, default=None)
    ap.add_argument("--scoring", choices=list(SCORINGS) + [None],
                    default=None, nargs="?")
    ap.add_argument("--prior", default=None)
    ap.add_argument("--report", action="store_true",
                    help="write the method/movers report only")
    args = ap.parse_args()

    if args.report:
        write_report(args.week, args.scoring or "half")
        return

    games_left = args.games_left if args.games_left is not None else 17 - args.week
    rec_map = load_receptions(args.week)
    news_pending, news_consumed = load_news()
    observed = observed_week_players(args.week)
    if observed is not None:
        print("timing gate: %d players with a logged Week %d stat row"
              % (len(observed), args.week))
    if observed is not None and not observed:
        # Fail closed (flaw-035, 2026-09-17): the stat cache is readable but
        # the requested week has zero logged rows — the week hasn't been
        # played yet or --week is wrong. Running would silently carry every
        # player at their prior and consume news as if a market step had
        # happened. Refuse instead; the caller must pass the latest
        # COMPLETED week (bin/board_week.py observed_week_arg()).
        print("ERROR: no logged stat rows for Week %d - week not yet played "
              "or wrong --week; refusing to run the market step" % args.week)
        raise SystemExit(2)

    legs = [args.scoring] if args.scoring else list(SCORINGS)
    applied_all = set()
    for scoring in legs:
        _, _, applied = run_leg(scoring, args.week, games_left, args.prior,
                                rec_map, news_pending, observed)
        applied_all |= applied
    if applied_all:
        from datetime import date
        today = date.today().isoformat()
        for nid in sorted(applied_all):
            news_consumed[nid] = today
        (RES / "news_consumed.json").write_text(
            json.dumps(news_consumed, indent=1))
        print("consumed news entries:", sorted(applied_all))

    # Carried-run metadata the dashboard bakes (one file, all legs).
    (RES / "imputed_proj_meta.json").write_text(json.dumps({
        "week": args.week,
        "games_left": games_left,
        "prior_weight": PRIOR_W,
        "eff_share": EFF_SHARE,
        "model": "starter expected-lineup (chart port v1)",
        "news_applied": sorted(applied_all),
        "scorings": list(legs if args.scoring else SCORINGS),
    }, indent=1))


if __name__ == "__main__":
    main()
