"""v4 compute: Vegas-implied fantasy points WITH anytime-TD props vs ECR.

- Vegas: odds_history (latest row per player/market/book/selection).
  Line markets -> median line, odds from closest book (v3 fix);
  player_anytime_td -> de-vigged Yes/No per book -> median fair prob ->
  Poisson E[TDs] = -ln(1-p).
- Expert points: the ECR feed's weekly expert point projections
  (data/fantasypros/proj_{qb,rb,wr,te}_wk{N}.csv, TD-inclusive).
- ECR ranks: data/ecr_pos.json (rolling latest ECR).
- Position-aware deltas + post-worthiness gates from engine/disagreement.py.
- Writes results to data/signals_v4.json (+ week-stamped copy) and
  updates post_queue (singles + thread draft).

Usage: python3 v4/compute_v4.py [--week N] [--season 2026]
  --week defaults to engine.week.current_week().
"""
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_signals/pipeline root
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
import sbclient  # noqa: E402
from engine.vegas import (  # noqa: E402
    vegas_implied_points, devig, american_to_prob, fair_anytime_prob,
    poisson_expected_tds, vegas_provenance, completeness_gaps,
    DEFAULT_BOOK_HOLD, classify_anytime_td_outcome, consensus_pick_key,
)
from engine.fds_fallback import (  # noqa: E402
    load_payload as fds_load_payload, index_payload as fds_index_payload,
    validate_signal_rows, is_publishable,
)
from engine.source_priority import (  # noqa: E402
    VEGAS_SOURCE_PRIORITY, PROPLINE_BOOK_TITLES,
)
from engine.scoring import fantasy_points  # noqa: E402
from engine.disagreement import (rank_deltas_by_position, draft_post,  # noqa: E402
                                build_thread, practice_note,
                                news_injury_snippet)
from loaders.fantasypros import read_projections_dict  # noqa: E402  (ECR feed expert points)


def norm(name):
    return re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()


def _now_ct():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Chicago"))


def injury_vintage_cutoff(now_ct=None):
    """Earliest acceptable injuries-table sync time for a build at now_ct.

    Official game designations are released Friday afternoon. A build
    running Saturday or Sunday must see injury data synced after the
    Friday designations (Friday 18:00 CT); otherwise a ruled-Out player
    still reads as Questionable and can be flagged as a read — the
    2026-09-19 Nico Collins miss (table last synced Fri 07:05 CT,
    Collins ruled Out Fri ~4pm CT, Saturday build flagged him).
    Returns None on Mon-Fri: no designation-vintage requirement.
    """
    from zoneinfo import ZoneInfo
    now_ct = now_ct or _now_ct()
    if now_ct.tzinfo is None:
        now_ct = now_ct.replace(tzinfo=ZoneInfo("America/Chicago"))
    if now_ct.weekday() not in (5, 6):  # Saturday, Sunday
        return None
    days_back = (now_ct.weekday() - 4) % 7  # Sat -> 1, Sun -> 2
    friday = now_ct - timedelta(days=days_back)
    return friday.replace(hour=18, minute=0, second=0, microsecond=0)


def check_injury_vintage(sbclient_mod, now_ct=None):
    """Fail-closed freshness check on the injuries table.

    Returns (True, detail) when the build may flag post-worthy reads,
    (False, reason) when designation data is too stale to trust. A
    query failure also returns False — unverifiable freshness is
    treated as stale. Pull-time (fetched_at) is the right measure here:
    unlike ECR, the Sleeper feed is live, so a fresh pull IS fresh
    content — the failure mode is not pulling at all.
    """
    cutoff = injury_vintage_cutoff(now_ct)
    if cutoff is None:
        return True, "weekday build: no designation-vintage requirement"
    try:
        rows = sbclient_mod.get(
            "injuries",
            "?select=fetched_at&fetched_at=not.is.null"
            "&order=fetched_at.desc&limit=1")
    except Exception as e:
        return False, f"injury vintage gate: could not verify freshness ({e})"
    max_fetched = None
    if rows:
        try:
            max_fetched = datetime.fromisoformat(rows[0]["fetched_at"])
        except (KeyError, ValueError, TypeError):
            max_fetched = None
    if max_fetched is None or max_fetched < cutoff:
        return False, (
            f"injury vintage gate: newest injuries sync {max_fetched} "
            f"predates Friday designations cutoff {cutoff} — reads withheld "
            f"until the injuries refresh runs")
    return True, f"injuries vintage ok: {max_fetched} >= {cutoff}"


LINE_MARKETS = {"player_pass_yds", "player_rush_yds",
                "player_receptions", "player_reception_yds"}


# ------------------------------------------- expert points + ECR (files)
# Week-stamped files: data/fantasypros/proj_{qb,rb,wr,te}_wk{N}.csv
# (ECR feed expert projections, TD-inclusive), data/ecr_pos.json (rolling
# latest ECR ranks). 2026-09-12 framework: the ECR feed supplies BOTH the
# position-specific rank and the expert point projections; ESPN is out as
# a points source. ESPN's projections pipeline is retired as of 2026-09-12
# (load_espn_full removed; bin/load_espn_phone.py, bin/espn_browser_pull.py,
# bin/load_espn_sheet.py, bin/espn_sheet_pull.gs removed).
# DB migration (ranker_rankings / projection_snapshots) is parked until the
# FP loader's player-mapping gaps are closed: several rookies with valid
# ECR entries (Jeremiyah Love, Terrance Ferguson, …) have no players-table
# row, so the DB join silently drops them.
def load_ecr():
    ecr = json.load(open(os.path.join(BASE, "data", "ecr_pos.json")))
    by_pos, meta, off = defaultdict(dict), {}, {}
    for k, v in ecr.items():
        pos = v["pos"]
        if v.get("pos_rank") is None:
            continue
        by_pos[pos][k] = v["pos_rank"]
        meta[k] = {"name": v["name"], "team": v["team"], "pos": pos}
        off[k] = v["pos_rank_str"]
    return by_pos, meta, off


# ---------------------------------------------------------------- Vegas props
def load_props(game_ids=None):
    """Latest line per (player, market, book, selection).

    game_ids: optional set of games.id to scope to (the intended week).
    When given, odds rows for other games — or rows with no game_id — are
    skipped, so a later week's props can never leak into this week's card.
    """
    rows = sbclient.get_all(
        "odds_history",
        "?select=game_id,sportsbook_id,market,selection,line,odds,recorded_at,metadata&limit=100000",
    )
    # User decision 2026-09-12: the "Vegas" leg is DraftKings + FanDuel only.
    # Pinnacle rows stay in odds_history for the separate pinnacle_implied
    # source but are excluded here from both the blended numbers and the
    # hook's book list.
    try:
        _sb_rows = sbclient.get_all("sportsbooks", "?select=id,code")
        _allowed_books = {r["id"] for r in _sb_rows
                          if (r.get("code") or "").lower()
                          in ("draftkings", "fanduel")}
    except Exception:
        # Fallback to the known DK/FD ids so the filter stays active even
        # if the sportsbooks lookup fails.
        _allowed_books = {"dea15b3d-015b-4808-b8d8-4eb41dc61094",
                          "47bb50a7-0476-45ce-a7c2-2c170c754da0"}
    n_dropped_scope = 0
    n_dropped_book = 0
    latest = {}
    for r in rows:
        if game_ids is not None and r.get("game_id") not in game_ids:
            n_dropped_scope += 1
            continue
        if r.get("sportsbook_id") not in _allowed_books:
            n_dropped_book += 1
            continue
        m = r.get("metadata") or {}
        key = (m.get("player_name") or "", r["market"], r["sportsbook_id"], r["selection"])
        if key not in latest or r["recorded_at"] > latest[key]["recorded_at"]:
            latest[key] = r

    per_pm = defaultdict(dict)  # (player, market) -> {book: {...}}
    for (player, market, book, sel), r in latest.items():
        d = per_pm[(player, market)].setdefault(book, {})
        if market == "player_anytime_td":
            d["yes" if sel == "Yes" else "no"] = r["odds"]
        else:
            if sel == "Over":
                d["over"] = r["odds"]
                d["line"] = r["line"]
            else:
                d["under"] = r["odds"]
                d.setdefault("line", r["line"])

    player_props = defaultdict(dict)
    td_cover = {}
    # Book-level hold estimated from two-sided line markets: the No side of
    # the TD market is never posted, so fair_p = implied_yes - hold/2.
    hold_by_book = defaultdict(list)
    for (player, market), books in per_pm.items():
        if market == "player_anytime_td":
            continue
        for book, o in books.items():
            if o.get("over") is not None and o.get("under") is not None:
                try:
                    po = american_to_prob(o["over"])
                    pu = american_to_prob(o["under"])
                    hold_by_book[book].append(po + pu - 1.0)
                except ValueError:
                    pass
    book_hold = {b: median(h) for b, h in hold_by_book.items() if h}
    # Split-line tie-break needs display names, not sportsbook UUIDs, so
    # the pick matches driving_prop's QA recompute (same consensus
    # order). Best-effort: a UUID fallback keeps the pick deterministic
    # even when the lookup fails.
    _sb_id_to_name = {}
    try:
        _sb_rows = sbclient.get_all("sportsbooks", "?select=id,name,code")
        _display = {"draftkings": "DraftKings", "fanduel": "FanDuel"}
        _sb_id_to_name = {
            r["id"]: _display.get((r.get("code") or "").lower(),
                                  r.get("name") or r.get("code") or r["id"])
            for r in _sb_rows if r.get("id")
        }
    except Exception:
        _sb_id_to_name = {}
    _LOCAL_BOOK_ORDER = ("DraftKings", "FanDuel")
    for (player, market), books in per_pm.items():
        if market == "player_anytime_td":
            ps = []
            for book, o in books.items():
                if "yes" not in o:
                    continue
                try:
                    # No-vig the two sides when No is posted; otherwise
                    # subtract half the book's estimated hold (measured from
                    # its two-sided line markets, DEFAULT_BOOK_HOLD fallback).
                    p = fair_anytime_prob(
                        o["yes"], o.get("no"),
                        hold=book_hold.get(book, DEFAULT_BOOK_HOLD))
                except ValueError:
                    continue
                ps.append(p)
            if ps:
                p = median(ps)
                etd = poisson_expected_tds(p)  # Poisson E[TDs], capped
                player_props[player][market] = {"prob": etd, "_p_yes": round(p, 3)}
                td_cover[player] = round(p, 3)
        else:
            book_entries = [
                (_sb_id_to_name.get(book, book),
                 o["line"], o.get("over"), o.get("under"))
                for book, o in books.items() if o.get("line") is not None]
            if not book_entries:
                continue
            med = median(e[1] for e in book_entries)
            _bk, line, over, under = min(
                book_entries,
                key=lambda e: consensus_pick_key(
                    e[0], e[1], med, _LOCAL_BOOK_ORDER))
            entry = {"line": line}
            if over is not None and under is not None:
                entry["over_odds"], entry["under_odds"] = over, under
            player_props[player][market] = entry
    # Sourcing metadata for the thread hook (intellectual honesty: state the
    # Vegas source and as-of time). Books observed across all consumed rows;
    # latest_at = newest recorded_at actually used.
    book_ids = {b for (_pl, _mk), books in per_pm.items() for b in books}
    latest_at = max((r["recorded_at"] for r in latest.values()
                     if r.get("recorded_at")), default=None)
    book_names = []
    if book_ids:
        try:
            rows = sbclient.get_all("sportsbooks", "?select=id,name,code")
            # DB stores 'Draftkings'/'Fanduel'; display the real brand names.
            display = {"draftkings": "DraftKings", "fanduel": "FanDuel"}
            book_names = sorted({
                display.get((r.get("code") or "").lower(),
                            r.get("name") or r.get("code") or "")
                for r in rows if r["id"] in book_ids
            })
        except Exception:
            book_names = []
    prop_meta = {"books": book_names, "latest_at": latest_at,
                 "dropped_scope": n_dropped_scope,
                 "dropped_book": n_dropped_book}
    return player_props, td_cover, prop_meta


def load_propline_props(cache_dir=None, game_ids=None):
    """PropLine primary-leg props loader.

    Reads the per-game PropLine cache files (data/propline_cache/) and
    returns the SAME (player_props, td_cover, prop_meta) shape as
    load_props(), so the engine.vegas translation runs unchanged.

    Consensus: DraftKings + FanDuel + BetMGM + Pinnacle (the four books
    the collector pulls). Median line across books; median de-vigged
    anytime-TD prob. Only two-sided quotes (over+under) feed the line
    markets — a one-sided quote can't be de-vigged.

    game_ids: optional set of PropLine event ids to scope to (the
    intended week). When given, other games are skipped.
    """
    import glob as _glob
    if cache_dir is None:
        cache_dir = os.path.join(BASE, "data", "propline_cache")
    # PropLine book keys -> display titles (matches the collector's BOOKS).
    _BOOKS = {"draftkings": "DraftKings", "fanduel": "FanDuel",
              "betmgm": "BetMGM", "pinnacle": "Pinnacle"}
    per_pm = defaultdict(dict)  # (norm_player, market) -> {book: {...}}
    # 2026-09-18: key by the NORMALIZED player name so spelling variants
    # across books ("Demario Douglas" vs "DeMario Douglas") merge into one
    # cross-book median instead of silently overwriting each other
    # last-wins in translate_props_to_vegas (which dropped the fuller
    # record and printed a degenerate 0.0 standard leg).
    display_names = defaultdict(lambda: defaultdict(int))
    n_files, n_outcomes, n_dropped_scope = 0, 0, 0
    latest_at = None
    for fp in sorted(_glob.glob(os.path.join(cache_dir, "props_*.json"))):
        try:
            game = json.load(open(fp))
        except Exception:
            continue
        if game_ids is not None and str(game.get("id")) not in {
                str(g) for g in game_ids}:
            n_dropped_scope += 1
            continue
        n_files += 1
        for bm in game.get("bookmakers", []):
            bkey = (bm.get("key") or "").lower()
            if bkey not in _BOOKS:
                continue
            book = _BOOKS[bkey]
            for m in bm.get("markets", []):
                mk = m.get("key")
                if m.get("last_update"):
                    try:
                        _lu = m["last_update"]
                        if latest_at is None or _lu > latest_at:
                            latest_at = _lu
                    except TypeError:
                        pass
                for o in m.get("outcomes", []):
                    player = o.get("description") or ""
                    if not player:
                        continue
                    n_outcomes += 1
                    pkey = norm(player)
                    display_names[pkey][player] += 1
                    d = per_pm[(pkey, mk)].setdefault(book, {})
                    sel = o.get("name")
                    if mk == "player_anytime_td":
                        # 2026-09-18: PropLine's anytime outcomes are NOT
                        # "Yes"/"No" — they are name=<player> (Yes-only) or
                        # Over/Under 0.5 (Pinnacle). Unknown shapes raise.
                        side = classify_anytime_td_outcome(
                            sel, o.get("point"), player,
                            book=book, source=fp)
                        price = o.get("price")
                        if price is None:
                            continue
                        asof = (o.get("last_seen_at")
                                or o.get("last_change_at")
                                or m.get("last_update"))
                        d[side] = price
                        d[side + "_asof"] = asof
                    else:
                        pt = o.get("point")
                        pr = o.get("price")
                        if pt is None or pr is None:
                            continue
                        # Group strictly by (book, line): alternate lines
                        # are separate rungs, never overwritten.
                        rung = d.setdefault(("line", float(pt)), {})
                        if sel == "Over":
                            rung["over"] = pr
                        elif sel == "Under":
                            rung["under"] = pr

    # Collapse alternate-line rungs per (player, market, book): keep the
    # rung closest to the cross-book median line (deterministic).
    collapsed = defaultdict(dict)
    for (player, mk), books in per_pm.items():
        if mk == "player_anytime_td":
            for book, o in books.items():
                if "yes" in o:
                    collapsed[(player, mk)][book] = o
            continue
        # Gather all two-sided rungs to find the median line.
        rungs = []
        for book, d in books.items():
            for k, rung in d.items():
                if not isinstance(k, tuple):
                    continue
                if rung.get("over") is not None and rung.get(
                        "under") is not None:
                    rungs.append((rung["over"], rung["under"], k[1], book))
        if not rungs:
            continue
        med = median([r[2] for r in rungs])
        # Per book, keep the rung closest to the median.
        best_by_book = {}
        for over, under, line, book in rungs:
            prev = best_by_book.get(book)
            if prev is None or abs(line - med) < abs(prev[2] - med):
                best_by_book[book] = (over, under, line)
        for book, (over, under, line) in best_by_book.items():
            collapsed[(player, mk)][book] = {
                "over": over, "under": under, "line": line}

    player_props = defaultdict(dict)
    td_cover = {}
    hold_by_book = defaultdict(list)
    for (player, market), books in collapsed.items():
        if market == "player_anytime_td":
            continue
        for book, o in books.items():
            try:
                po = american_to_prob(o["over"])
                pu = american_to_prob(o["under"])
                hold_by_book[book].append(po + pu - 1.0)
            except ValueError:
                pass
    book_hold = {b: median(h) for b, h in hold_by_book.items() if h}

    def _display(pkey):
        variants = display_names.get(pkey)
        if not variants:
            return pkey
        return max(variants, key=lambda n: variants[n])

    for (player, market), books in collapsed.items():
        disp = _display(player)
        if market == "player_anytime_td":
            ps = []
            asofs = []
            for book, o in books.items():
                if "yes" not in o:
                    continue
                try:
                    p = fair_anytime_prob(
                        o["yes"], o.get("no"),
                        hold=book_hold.get(book, DEFAULT_BOOK_HOLD))
                except ValueError:
                    continue
                ps.append(p)
                if o.get("yes_asof"):
                    asofs.append(o["yes_asof"])
            if ps:
                p = median(ps)
                etd = poisson_expected_tds(p)
                entry = {"prob": etd, "_p_yes": round(p, 3),
                         "_n_books": len(ps),
                         "_asof": max(asofs) if asofs else None}
                player_props[disp][market] = entry
                td_cover[disp] = round(p, 3)
        else:
            # Deterministic split-line tie-break shared with driving_prop's
            # QA recompute (engine.vegas.consensus_pick_key): distance ties
            # break by consensus book order, then book name — never by
            # dict/file order.
            book_entries = [(book, o["line"], o.get("over"), o.get("under"))
                            for book, o in books.items()
                            if o.get("line") is not None]
            if not book_entries:
                continue
            med = median(e[1] for e in book_entries)
            _bk, line, over, under = min(
                book_entries,
                key=lambda e: consensus_pick_key(
                    e[0], e[1], med, tuple(PROPLINE_BOOK_TITLES.values())))
            entry = {"line": line}
            if over is not None and under is not None:
                entry["over_odds"], entry["under_odds"] = over, under
            player_props[disp][market] = entry
    prop_meta = {"books": sorted(_BOOKS.values()), "latest_at": latest_at,
                 "dropped_scope": n_dropped_scope,
                 "files": n_files, "outcomes": n_outcomes,
                 "leg": "propline"}
    return player_props, td_cover, prop_meta


def _props_stat_keys(props: dict, position: str) -> set:
    """Stat keys priced by a market->entry props dict.

    Mirrors engine.vegas.vegas_implied_points' market->stat mapping
    (binary anytime-TD markets attribute to the position-appropriate TD
    bucket). Used to decide whether a scoring leg is computable from the
    priced markets at all.
    """
    from engine.vegas import PROP_MARKETS
    keys = set()
    for mk in props:
        spec = PROP_MARKETS.get(mk)
        if not spec:
            continue
        sk, is_bin = spec
        if is_bin:
            keys.add("rushing_tds" if position == "QB" else "receiving_tds")
        elif sk:
            keys.add(sk)
    return keys


def translate_props_to_vegas(player_props, td_cover, meta, leg):
    """Translate raw-book props to Vegas fantasy points via engine.vegas.

    Shared by the Odds-API audit leg and the PropLine primary leg.
    Returns (by_pos, extra, n_matched, unmatched).

    A scoring leg is null — never zero — when none of the priced markets
    can move it (fantasy_points_or_null rule; e.g. a receptions-only line
    leaves standard uncomputable). Name variants that normalize to the
    same key are merged by the loader before this runs, so no silent
    last-wins overwrite happens here.
    """
    from engine.scoring import SCORING
    by_pos = defaultdict(dict)
    extra = {}
    unmatched = []
    for player, props in player_props.items():
        k = norm(player)
        m = meta.get(k)
        if not m:
            unmatched.append(player)
            continue
        pos = m["pos"]
        try:
            full = {sc: vegas_implied_points(props, position=pos, scoring=sc)
                    for sc in ("standard", "half_ppr", "ppr")}
            stat_keys = _props_stat_keys(props, pos)
            pts = {}
            for leg_key, sc in (("std", "standard"), ("half", "half_ppr"),
                                ("ppr", "ppr")):
                table = SCORING[sc]
                if any(table.get(s, 0) != 0 for s in stat_keys):
                    pts[leg_key] = full[sc]["points"]
                else:
                    # No priced market carries weight in this scoring:
                    # uncomputable, not zero. Never zero-fill.
                    pts[leg_key] = None
            _ppr = full["ppr"]
        except Exception as e:
            print("vegas fail", player, str(e)[:80])
            continue
        by_pos[pos][k] = {"std": pts["std"], "half": pts["half"],
                          "ppr": pts["ppr"]}
        prov = vegas_provenance(_ppr["markets_used"], _ppr["td_source"], pos)
        extra[k] = {
            "name": player,
            "td_p": td_cover.get(player),
            "markets": sorted(_ppr["markets_used"]),
            "provenance": prov,
            "vegas_leg": leg,
            "prov_gaps": completeness_gaps(
                _ppr["markets_used"], _ppr["td_source"], pos),
        }
    n_v = sum(len(v) for v in by_pos.values())
    return by_pos, extra, n_v, unmatched


def _rotate_and_write_drafts(week, worthy, prop_meta, fds_keys=None,
                           fds_payload=None):
    """Live-queue mutation: reject existing drafts, write new single drafts
    and one thread draft. Never called in dry-run."""
    drafts = sbclient.get("post_queue", "?status=eq.draft&select=id")
    print("existing drafts to reject:", len(drafts), flush=True)
    for d in drafts:
        sbclient.patch("post_queue",
                       {"status": "rejected", "note": "superseded by regenerated batch"},
                       f"?id=eq.{d['id']}")
    written = 0
    for s in worthy:
        text = draft_post(s, "new", week=week)
        note = (f"v4 wk{week} | {s['name']} {s['team']} {s['pos']} | "
                f"V {s['vegas_ppr']:.1f} vs E {s['expert_ppr']:.1f} "
                f"(Δ{s['pts_delta_ppr']:+.1f} raw, Δadj{s['pts_delta_adj']:+.1f}) | "
                f"rank gap {s['abs_delta']} | "
                f"vegas_leg={s.get('vegas_leg')} prov={s.get('vegas_provenance')}")
        if s.get("injury_flag"):
            note += f" | ⚠ {s['injury_flag']}"
        sbclient.post("post_queue", {
            "post_type": "new",
            "post_text": text,
            "status": "draft",
            "note": note,
        })
        written += 1
    print("new v4 drafts written:", written, flush=True)

    # ---- weekly thread draft (one row, tweets joined by a separator)
    # Sourcing for the hook (intellectual honesty: Vegas source + as-of time,
    # ECR as the expert source). ECR time = newest of the 4 projections CSVs;
    # Vegas time = newest prop line actually consumed.
    try:
        ecr_mtime = max(
            os.path.getmtime(
                os.path.join(BASE, "data", "fantasypros",
                             f"proj_{p}_wk{week}.csv"))
            for p in ("qb", "rb", "wr", "te"))
    except OSError:
        ecr_mtime = None
    sourcing = {
        "books": prop_meta.get("books") or [],
        "vegas_at": prop_meta.get("latest_at"),
        "ecr_at": ecr_mtime,
        "fds_derived": len(fds_keys or ()),
        "fds_snapshot_at": (fds_payload or {}).get("snapshot_generated_at"),
    }
    thread = build_thread(worthy, week=week, sourcing=sourcing)
    sbclient.post("post_queue", {
        "post_type": "thread",
        "post_text": "\n---\n".join(thread),
        "status": "draft",
        "note": (f"v4 wk{week} thread | {len(thread)} tweets | {len(worthy)} signals | "
                 "points-only, grouped by position x direction"),
    })
    print("thread tweets:", len(thread), flush=True)


def _require_injury_vintage(sbclient_mod, now_ct=None):
    """Fail-closed vintage gate for main().

    Called at the top of main(), before any computation or output
    mutation. Raises SystemExit(1) unless the injury designations are
    fresh enough for a weekend build (Friday 18:00 CT cutoff). A stale or
    unverifiable vintage exits nonzero — never suppress-in-place.
    """
    _vintage_ok, _vintage_detail = check_injury_vintage(sbclient_mod, now_ct)
    if not _vintage_ok:
        print(f"FAIL: {_vintage_detail}", flush=True)
        raise SystemExit(1)
    print(_vintage_detail, flush=True)


def main(week=None, season=2026, dry_run=False, no_queue=False):
    """Compute Week N signals and draft post_queue rows.

    dry_run=True: compute everything, print the report, write signals to
    signals_wk{week}_v4_test.json — but make NO post_queue changes
    (no draft rotation, no new drafts, no thread row). Verification-only.
    no_queue=True: full build (production signals files + NMR flags
    persisted) but the post_queue rotation is skipped — regenerates the
    canonical signals without touching draft state.
    """
    from engine.week import current_week
    week = week or current_week(season)
    print(f"week: {week} | season: {season}", flush=True)
    # ---- designation-vintage gate (2026-09-19, Nico Collins miss): the
    # per-player injury gate below is only as fresh as the injuries table.
    # Friday designations release Friday PM; a Sat/Sun build on pre-
    # Friday-PM data exits nonzero HERE — before any signal is computed and
    # before any file or database mutation (signals, NMR flags, audit
    # sidecar, post_queue). The old suppress-in-place behavior wrote "reads
    # withheld" rows; exiting is the only fail-closed behavior. Weekday
    # builds carry no requirement.
    _require_injury_vintage(sbclient)
    # ECR feed expert projections (the expert leg). Fail-closed: the
    # weekly ECR refresh cron keeps these CSVs current; a missing file
    # raises instead of silently producing a Vegas-only card.
    ecr_proj = read_projections_dict(week)
    print("ECR expert projections:", len(ecr_proj), flush=True)
    ecr_by_pos, meta, official = load_ecr()
    print("ECR players:", sum(len(v) for v in ecr_by_pos.values()), flush=True)
    # week/game scoping: only this week's games' props may feed the card.
    # Clock rule (2026-09-13): game-status fields lag — SF@LA still read
    # "scheduled" two days after kickoff, which let a played game leak a
    # McCaffrey signal into the queue. Signals are pre-game only: a kicked-off
    # game is unbettable, so scope to games not yet started, using starts_at
    # against the clock (same objective rule as started_teams_for_week),
    # never the status field.
    from datetime import datetime, timezone
    from engine.snapshot import load_week_games
    _games_by_id, _ = load_week_games(season, week)
    _now = datetime.now(timezone.utc)
    _upcoming = set()
    for _gid, _g in _games_by_id.items():
        try:
            _sa = datetime.fromisoformat(str(_g.get("starts_at")))
        except (ValueError, TypeError):
            continue
        if _sa.tzinfo is None:
            _sa = _sa.replace(tzinfo=timezone.utc)
        if _sa > _now:
            _upcoming.add(_gid)
    print(f"game scoping: {len(_games_by_id)} week-{week} games, "
          f"{len(_upcoming)} not yet kicked off", flush=True)
    player_props, td_cover, prop_meta = load_props(game_ids=_upcoming)
    print("prop players:", len(player_props), "| with TD props:", len(td_cover),
          "| books:", prop_meta["books"],
          "| dropped (other weeks):", prop_meta.get("dropped_scope", 0),
          flush=True)

    # Local raw-book leg (The Odds API -> engine.vegas). Under the
    # PropLine-primary design (2026-09-18) these numbers are the AUDIT
    # leg: selective raw-book pulls to verify PropLine moves.
    local_by_pos, local_extra, n_v, unmatched = translate_props_to_vegas(
        player_props, td_cover, meta, "local")
    print(f"matched to ECR: {n_v} | unmatched: {len(unmatched)}", flush=True)

    # ---- PropLine primary leg (2026-09-18): the full-slate raw-price
    # backbone. Translated LOCALLY via engine.vegas from the PropLine
    # cache (never a vendor's blended number).
    propline_by_pos, propline_extra, n_pl, pl_unmatched = {}, {}, 0, []
    try:
        _pl_props, _pl_td, _pl_meta = load_propline_props()
        propline_by_pos, propline_extra, n_pl, pl_unmatched = \
            translate_props_to_vegas(_pl_props, _pl_td, meta, "propline")
        print(f"PropLine primary: {n_pl} matched | "
              f"unmatched: {len(pl_unmatched)} | books: {_pl_meta['books']} | "
              f"as of: {_pl_meta.get('latest_at')}", flush=True)
    except Exception as e:
        print(f"PropLine leg FAILED: {e} — build continues on FDS fallback "
              f"only", flush=True)

    # ---- PropLine-primary + FDS fallback + Odds-API audit
    # (2026-09-18): PropLine is the primary raw-price leg; FDS fills
    # ONLY players PropLine missed (fantasy-only, Sunday, per-stat
    # attribution); the Odds-API numbers audit the primary and
    # disagreements are QA findings. FDS numbers never touch
    # odds_history or engine.vegas.
    fds_index, fds_keys, local_keys = {}, set(), set()
    audit = {"disagreements": [], "counts": {}, "fds_counts": {}}
    try:
        _fds_payload = fds_load_payload(week)
    except ValueError as e:
        # Corrupt payload fails the build loudly — never silently degrade.
        raise SystemExit(f"FDS fallback BLOCKED: {e}")
    if _fds_payload is not None:
        fds_index = fds_index_payload(_fds_payload)
        from engine.propline_primary import build_propline_primary
        (vegas_by_pos, extra, propline_keys, fds_keys, local_keys,
         audit) = build_propline_primary(
            propline_by_pos, propline_extra, fds_index,
            local_by_pos, local_extra,
            pos_of=lambda k: (meta.get(k) or {}).get("pos"),
            priority=VEGAS_SOURCE_PRIORITY)
        _fc, _ac = audit["fds_counts"], audit["counts"]
        print(f"PropLine primary: {len(propline_keys)} players | "
              f"FDS fallback: payload {len(fds_index)} skill players "
              f"(snapshot {str(_fds_payload.get('snapshot_generated_at'))[:16]}); "
              f"added={_fc['added']} "
              f"(derived={_fc['added_derived']}, "
              f"partial={_fc['added_partial']}) {_fc['by_pos']} | "
              f"no_match={_fc['no_match']} | "
              f"pos_mismatch={_fc['pos_mismatch']} | "
              f"skipped_not_sunday={_fc['skipped_not_sunday']} | "
              f"local audit: only={_ac['local_only']} "
              f"agree={_ac['agreements']} override={_ac['overrides']} "
              f"partial_xcheck={_ac['partial_crosschecks']}",
              flush=True)
        for _d in audit["disagreements"]:
            print(f"  AUDIT DISAGREEMENT: {_d['name']} ({_d['pos']}): "
                  f"deltas={_d['deltas']} -> local wins", flush=True)
    else:
        # No FDS payload: the audit leg is the only leg — local-only build.
        vegas_by_pos, extra = local_by_pos, local_extra
        local_keys = {k for d in local_by_pos.values() for k in d}
        print("FDS primary: no payload file — local-only build", flush=True)

    expert_pts = {k: {"std": v["std"], "half": v["half"], "ppr": v["ppr"]}
                  for k, v in ecr_proj.items()}

    signals = rank_deltas_by_position(vegas_by_pos, ecr_by_pos,
                                      expert_pts=expert_pts,
                                      official_pos_rank=official, meta=meta)
    n_points_gate = sum(1 for s in signals if s["post_worthy"])
    for s in signals:
        k = s["player_key"]
        s["td_p_yes"] = extra.get(k, {}).get("td_p")
        s["expert_td_exp"] = ecr_proj.get(k, {}).get("td_exp")
        # Completeness gate (user-approved 2026-09-12): ONLY 'complete' and
        # 'td-filled' Vegas rows are publishable. 'partial' rows are computed
        # and stored but informational only — never post-worthy. (This
        # subsumes the old TD-only coverage gate: TD-only players are partial
        # because they lack the required yardage/reception markets.)
        # FDS fallback (2026-09-17): 'fds-derived' rows ARE publishable —
        # the fallback exists so Sunday's chain runs with broad coverage —
        # but they are always labeled and never presented as locally
        # calculated from raw sportsbook odds.
        prov = extra.get(k, {}).get("provenance", "partial")
        s["vegas_provenance"] = prov
        s["vegas_leg"] = extra.get(k, {}).get("vegas_leg")
        # Per-stat provenance rides the row: which translated stats fed the
        # Vegas leg (vegas-attributed only) vs FDS projection output shown
        # separately. Local rows carry None here.
        s["vegas_stats_used"] = extra.get(k, {}).get("vegas_stats_used")
        s["fds_projection_stats"] = extra.get(k, {}).get(
            "fds_projection_stats")
        s["fds_stat_sources"] = extra.get(k, {}).get("fds_stat_sources")
        s["coverage_ok"] = is_publishable(prov)
        if not s["coverage_ok"] and s["post_worthy"]:
            gaps = extra.get(k, {}).get("prov_gaps", [])
            s["post_worthy"] = False
            s["worthy_reason"] = (
                "Only partial market data — shown for context, never flagged"
                + (f" (missing {', '.join(gaps)})" if gaps else ""))
    # Fail-closed provenance audit: missing label or any never-blend
    # violation raises and fails the build — it never ships quietly.
    validate_signal_rows(signals, fds_index, local_keys, fds_keys,
                         audit=audit, priority=VEGAS_SOURCE_PRIORITY)
    print("provenance audit: all Vegas-leg rows labeled, never-blend holds",
          flush=True)
    from collections import Counter as _Counter
    _partial_by_pos = _Counter(
        s["pos"] for s in signals
        if not s.get("coverage_ok")
        and "partial Vegas markets" in s.get("worthy_reason", ""))
    n_partial_excluded = sum(_partial_by_pos.values())
    worthy = [s for s in signals if s["post_worthy"]]
    _gaps = {s["pos"]: s["pos_level_gap"] for s in signals
             if s.get("pos_level_gap") is not None}
    print(f"signals (full intersection universe): {len(signals)} | "
          f"points gate (|Δadj|≥2.0 + floor): {n_points_gate} | "
          f"pos level gaps (Vegas−ECR): "
          + ", ".join(f"{p}={_gaps[p]:+.2f}" for p in sorted(_gaps))
          + f" | excluded as partial: {n_partial_excluded} "
          f"{dict(_partial_by_pos)} | publishable pre-injury-gate: {len(worthy)}",
          flush=True)

    # ---- injury gate: Out/IR/Doubtful players are news-driven, not signal.
    # (Questionable stays — ~70% play — but gets flagged in the draft note.)
    # Thread tweets also get an injury sub-line: injury_note comes from the
    # nflverse practice rows first, then recent injury news (see helpers in
    # engine/disagreement.py). No pipeline refactor — same queries, one block.
    try:
        inj_rows = sbclient.get_all(
            "injuries", "?select=player_name,status,body_part")
        by_player = defaultdict(list)
        for r in inj_rows:
            if r.get("player_name"):
                by_player[norm(r["player_name"])].append(r)
        for s in signals:
            rows = by_player.get(s["player_key"], [])
            statuses = [(r.get("status") or "") for r in rows]
            gate = next((st for st in statuses
                         if st in ("Out", "IR", "Doubtful", "PUP")), None)
            if gate:
                if s["post_worthy"]:
                    s["post_worthy"] = False
                    bp = next((r.get("body_part") for r in rows
                               if (r.get("status") or "") == gate
                               and r.get("body_part")), None)
                    s["worthy_reason"] = (
                        f"{gate}{f' ({bp})' if bp else ''} — "
                        f"injury news, not a market signal")
                continue
            q = next((r for r in rows
                      if (r.get("status") or "") == "Questionable"), None)
            if q:
                s["injury_flag"] = (
                    f"Questionable"
                    + (f" ({q['body_part']})" if q.get("body_part") else ""))
                s["injury_note"] = practice_note(statuses)
        worthy = [s for s in signals if s["post_worthy"]]
        # News fallback: a recent injury/practice headline enriches the note
        # for flagged players, or makes a healthy-status player notable when
        # the headline is genuinely about that player's injury concern.
        try:
            import datetime as _dt
            from urllib.parse import quote as _quote
            cut = (_dt.datetime.now(_dt.timezone.utc)
                   - _dt.timedelta(hours=72)).isoformat()
            names = [s["name"] for s in worthy]
            if names:
                q = (f"?select=player_name,title,published_at"
                     f"&player_name=in.({_quote(','.join(names))})"
                     f"&published_at=gte.{_quote(cut)}&limit=200")
                news_by = defaultdict(list)
                for r in sbclient.get_all("news_items", q):
                    news_by[norm(r.get("player_name") or "")].append(r)
                for s in worthy:
                    if s.get("injury_note"):
                        continue
                    bp = None
                    if s.get("injury_flag"):
                        m = re.search(r"\(([^)]+)\)", s["injury_flag"])
                        bp = m.group(1) if m else None
                    for r in news_by.get(s["player_key"], []):
                        snip = news_injury_snippet(r.get("title"),
                                                   s.get("name") or "", bp)
                        if snip:
                            s["injury_note"] = snip
                            break
        except Exception as e:
            print(f"WARNING: injury news lookup skipped: {e}", flush=True)
        n_gated = sum(1 for s in signals
                      if s.get("worthy_reason", "").startswith("injury gate"))
        print(f"injury gate: {n_gated} excluded | post-worthy now: {len(worthy)}",
              flush=True)
    except Exception as e:
        print(f"WARNING: injury gate skipped: {e}", flush=True)
        worthy = [s for s in signals if s["post_worthy"]]
    # (designation-vintage gate runs at the top of main(): a stale vintage
    # exits nonzero before any output mutation — never suppress-in-place.)
    # ---- no-market-read flags (user-approved 2026-09-12): ECR-relevant
    # players (full-PPR >= positional floor) with zero non-TD prop markets
    # in the week-scoped pull. New signal category — informational only,
    # never post-worthy (no approved post format exists). Persisted per
    # week for the Tuesday scorecard's variance validation.
    from engine import no_market_read as _nmr
    nmr_flags = _nmr.compute_flags(
        ecr_proj, meta, official, ecr_by_pos, player_props,
        prop_meta.get("latest_at"),
        started_teams=_nmr.started_teams_for_week(season, week))
    print(f"no-market-read flags: {len(nmr_flags)}", flush=True)
    for f in nmr_flags[:12]:
        print(f"  NMR {f['name']} ({f['team']} {f['pos']}): "
              f"ECR {f['expert_ppr']:.1f} PPR, {f['ecr_official']}",
              flush=True)
    signals.extend(nmr_flags)
    if dry_run:
        print("DRY RUN: no-market-read flags computed but not persisted.",
              flush=True)
    else:
        _nmr.persist_flags(nmr_flags, season, week)
        print(f"no-market-read flags persisted for wk{week}: {len(nmr_flags)}",
              flush=True)

    sig_name = (f"signals_wk{week}_v4_test.json" if dry_run
                else f"signals_wk{week}_v4.json")
    if not dry_run:
        json.dump(signals, open(os.path.join(BASE, "data", "signals_v4.json"), "w"), indent=1)
    json.dump(signals, open(os.path.join(BASE, "data", sig_name), "w"), indent=1)
    # Audit-leg sidecar (2026-09-17): local-vs-FDS disagreements for the QA
    # bundle builder. Written on every non-dry run, even when empty.
    if not dry_run:
        json.dump({"week": week, "season": season,
                   "built_at": datetime.now(timezone.utc).isoformat(),
                   "priority": list(VEGAS_SOURCE_PRIORITY),
                   "disagreements": audit["disagreements"],
                   "counts": audit["counts"],
                   "fds_counts": audit["fds_counts"]},
                  open(os.path.join(BASE, "data", f"audit_wk{week}_v4.json"),
                       "w"), indent=1)

    # ---- post_queue rotation (skipped in dry-run and no-queue modes)
    if dry_run or no_queue:
        mode = "DRY RUN" if dry_run else "NO-QUEUE"
        print(f"\n{mode}: would reject existing drafts and write "
              f"{len(worthy)} single drafts + 1 thread draft. "
              f"No post_queue changes made.", flush=True)
    else:
        _rotate_and_write_drafts(week, worthy, prop_meta,
                                fds_keys=fds_keys, fds_payload=_fds_payload)

    print("\n=== TOP POST-WORTHY (v4, TD-inclusive) ===")
    for s in worthy[:8]:
        print(f"{s['name']} ({s['team']} {s['pos']}): "
              f"V {s['vegas_ppr']:.1f} vs E {s['expert_ppr']:.1f} "
              f"(Δ{s['pts_delta_ppr']:+.1f} raw, Δadj{s['pts_delta_adj']:+.1f}) | "
              f"Vegas #{s['vegas_pos_rank']} {s['pos']} "
              f"| ECR {s['ecr_official']} (gap {s['abs_delta']}) | td_p={s['td_p_yes']} "
              f"| prov={s.get('vegas_provenance')}")
    from collections import Counter as _C2
    print("provenance mix among publishable:",
          dict(_C2(s.get("vegas_provenance") for s in worthy)), flush=True)

    # ---- FDS calibration cross-check (informational): our
    # locally-recomputed Vegas numbers vs FDS's own derived points over the
    # FDS-primary players. Not a gate.
    _fds_added = (audit.get("fds_counts") or {}).get("added", 0)
    if _fds_payload is not None and _fds_added:
        diffs = []
        for s in signals:
            if s.get("vegas_leg") != "fds":
                continue
            rec = fds_index.get(s["player_key"])
            if not rec:
                continue
            fds_ppr = (rec.get("fantasy_points") or {}).get("ppr")
            if fds_ppr is None:
                continue
            diffs.append(abs(s["vegas_ppr"] - fds_ppr))
        if diffs:
            diffs.sort()
            med = diffs[len(diffs) // 2]
            p90 = diffs[int(len(diffs) * 0.9)]
            print(f"FDS calibration: n={len(diffs)} FDS-added players; "
                  f"|ours - FDS derived ppr| median={med:.2f} p90={p90:.2f} "
                  "(informational — audit-leg calibration for the flip)",
                  flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--dry-run", action="store_true",
                    help="verification-only: no post_queue changes")
    ap.add_argument("--no-queue", action="store_true",
                    help="full build (signals files + NMR flags) but skip "
                         "the post_queue rotation")
    a = ap.parse_args()
    main(week=a.week, season=a.season, dry_run=a.dry_run,
         no_queue=a.no_queue)
