#!/usr/bin/env python3
"""Build source value lineage for the monitoring dashboard.

For each source, shows the top 25 players by native (scrape) value in
12-team Half PPR, with:
  - live_value: scraped directly from the human-readable source page
  - native: value stored in our pipeline snapshot
  - live_matches_native: whether live page matches our snapshot
  - indexed: after isotonic reindexing onto the 0-70 scale
  - index_mult: indexed / native (effective multiplier)
  - reweighted: from the adjusted curve (DDF reweighting)
  - reweight_mult: reweighted / indexed (effective multiplier)
  - chart_value: what the chart actually displays

The user requires that verification data comes from the live pages
a human would visit, not API endpoints or database snapshots.
FantasyPros, USA Today, and CBS are scraped live from their article pages.
FantasyCalc is via the API that powers its human-visible page (same numbers
a human sees). ESPN, CBS ROS, and Razzball have no published trade value
chart; their values are calculated from rest-of-season projections.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Live values come from dist/modules/live-page-scrape.json (written by
# pipelines/scrape_live_source_pages.py). This builder does not scrape.
# Use the canonical normalization rule from the maintained identity system.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from canonical_players import norm_player_name

# JEG-107: the VORP round-trip in the lineage card uses translate_source()
# from JEG-62 to compute the publisher's implied waiver line per position
# and the implied VORP per player. Pure read+pure compute; no I/O.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vorp_translation"))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(REPO, "dist/assets/comparison-sources-data.json")
OUT_PATH = os.path.join(REPO, "dist/modules/source-value-lineage.json")

LIVE_PAGE_SCRAPE_PATH = os.path.join(REPO, "dist/modules/live-page-scrape.json")

# Sources whose live values come from the dedicated live-page scrape artifact.
# The lineage builder MUST NOT re-scrape at build time: live pages sit behind
# intermittent bot mitigation (HTTP 402/429, dropped connections), and a
# failed build-time scrape used to silently degrade to empty (live_value: null
# for every row), which the monitor then counted as FAIL RED. Scrape once via
# pipelines/scrape_live_source_pages.py, reuse downstream.
LIVE_SCRAPE_SOURCES = ["fantasypros", "usatoday", "cbs", "fantasycalc"]


def load_live_page_values():
    """Load live-scraped values from the dedicated scrape artifact.

    Returns {source: {normalized_name: value}}. Fails loudly (raises) when the
    artifact is missing, stale (>48h), or a source has no usable rows -- a
    builder that cannot verify against live pages must not publish nulls.
    """
    if not os.path.exists(LIVE_PAGE_SCRAPE_PATH):
        raise FileNotFoundError(
            f"Live page scrape artifact missing: {LIVE_PAGE_SCRAPE_PATH}. "
            "Run pipelines/scrape_live_source_pages.py first."
        )
    doc = json.load(open(LIVE_PAGE_SCRAPE_PATH))
    scraped_at = doc.get("scraped_at", "")
    try:
        from datetime import datetime, timezone
        age_h = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
        ).total_seconds() / 3600
        if age_h > 48:
            raise ValueError(
                f"Live page scrape artifact is {age_h:.1f}h old (>48h): {LIVE_PAGE_SCRAPE_PATH}. "
                "Re-run pipelines/scrape_live_source_pages.py."
            )
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Cannot parse scraped_at {scraped_at!r}: {e}")

    live_data = {}
    live_stale = {}
    for src in LIVE_SCRAPE_SOURCES:
        entry = (doc.get("sources") or {}).get(src) or {}
        # Prefer the full player map (all_players) over top25: the chart's top 25
        # by reindexed value can include players ranked outside the source's top 25.
        all_players = entry.get("all_players") or {}
        if all_players:
            player_map = {norm_player_name(name): value for name, value in all_players.items()}
            n_live = len(player_map)
        else:
            top25 = entry.get("top25") or []
            if entry.get("status") == "error" or not top25:
                raise ValueError(
                    f"Live page scrape has no usable rows for {src} "
                    f"(status={entry.get('status')!r}): {LIVE_PAGE_SCRAPE_PATH}"
                )
            player_map = {norm_player_name(name): value for name, value in top25}
            n_live = len(player_map)
        live_data[src] = player_map
        if entry.get("stale"):
            live_stale[src] = {
                "stale_as_of": entry.get("stale_as_of"),
                "stale_error": entry.get("stale_error"),
            }
            print(f"  {src}: {n_live} live values from scrape artifact ({scraped_at}) [STALE]")
        else:
            print(f"  {src}: {n_live} live values from scrape artifact ({scraped_at})")
    live_data["_scraped_at"] = scraped_at
    live_data["_stale"] = live_stale
    return live_data

# Snapshot paths for native values (raw scraped values, not transformed)
SNAPSHOT_PATHS = {
    "fantasypros": os.path.join(REPO, "data/raw/sources/fantasypros/2026-09-29/snapshot.json"),
    "usatoday": os.path.join(REPO, "data/raw/sources/usatoday/2026-09-29/snapshot.json"),
    "fantasycalc": os.path.join(REPO, "data/raw/sources/fantasycalc/week-4/snapshot.json"),
}


ALL_SOURCES = ["espn", "cbs", "cbsros", "razzball", "fantasycalc", "fantasypros", "usatoday"]
# Sources with no human-readable trade-value page and no raw snapshot: their
# lineage comes from the fixture alone, so they can be merged into an existing
# artifact on a machine without data/raw (e.g. a Claude session, CI).
FIXTURE_ONLY_SOURCES = ("espn", "cbsros", "razzball")


def load_snapshot_natives(source):
    """Load native_value (raw scraped) from snapshot, keyed by player_key slug.
    
    The snapshot has both native_value (raw from source page) and value (transformed).
    We want the raw native_value for the lineage comparison.
    """
    path = SNAPSHOT_PATHS.get(source)
    if not path or not os.path.exists(path):
        return {}
    
    snap = json.load(open(path))
    rows = snap.get("rows", [])
    
    # Build mapping from player name slug to native_value for half_ppr/12 teams
    natives = {}
    for r in rows:
        if r.get("scoring") != "half_ppr" or r.get("teams") != 12:
            # Also check for half-ppr variants
            scoring = str(r.get("scoring", "")).lower()
            if "half" not in scoring:
                continue
            if r.get("teams") != 12:
                continue
        
        name = r.get("player_name", "")
        if not name:
            continue
        
        # Create slug matching the comparison data format (normalized, no punctuation)
        slug = norm_player_name(name)
        native_val = r.get("native_value")
        if native_val is not None:
            # Keep the first (or highest?) - snapshots should have one per player
            if slug not in natives:
                natives[slug] = float(native_val)
    
    return natives

# Human-readable source pages (what a human would visit)
SOURCE_URLS = {
    "espn": {
        "url": "https://fantasy.espn.com/football/players/projections",
        "note": "ESPN Fantasy Football player projections page (human-readable). Mike Clay ROS projections scraped LIVE from this page.",
        "header_check": "2026 Season Projections",
    },
    "cbs": {
        "url": "https://www.cbssports.com/fantasy/football/news/dave-richards-week-4-trade-chart-and-rest-of-season-fantasy-football-rankings-help-you-win-now/",
        "note": "CBS Sports Dave Richards Week 4 trade chart article. Values scraped LIVE from this page.",
        "header_check": "Week 4 Trade Chart",
    },
    "cbsros": {
        "url": "https://www.cbssports.com/fantasy/football/stats/QB/2026/restofseason/projections/nonppr/",
        "note": "CBS Sports rest-of-season projections (per position; nonppr slug). Not a trade chart -- raw ROS stat projections, computed into value-above-waivers the way the ESPN leg is. No live trade-value to scrape.",
        "header_check": "Rest of Season",
    },
    "razzball": {
        "url": "https://football.razzball.com/projections-qb-restofseason/",
        "note": "Razzball rest-of-season projections. Not a trade chart -- published per-game projections, computed into value-above-waivers the way the ESPN leg is. No live trade-value to scrape.",
        "header_check": "Rest of Season",
    },
    "fantasycalc": {
        "url": "https://fantasycalc.com/trade-value-chart",
        "note": "FantasyCalc trade value chart (human UI). Settings: Redraft, 12 teams, 0.5 PPR, TEP off, Superflex off. Values scraped LIVE from this page.",
        "header_check": "Trade Value Chart",
    },
    "fantasypros": {
        "url": "https://www.fantasypros.com/2026/09/fantasy-football-trade-value-chart-week-4-2026/",
        "note": "FantasyPros Week 4 trade value chart article. Values scraped LIVE from this page.",
        "header_check": "Week 4",
    },
    "usatoday": {
        "url": "https://www.usatoday.com/story/sports/fantasy/football/2026/09/29/fantasy-trade-value-chart-week-4-ros-rankings/92008742007/",
        "note": "USA Today Week 4 trade value chart. Half-PPR column scraped LIVE from this page.",
        "header_check": "Week 4",
    },
}

# Source types: published trade values vs calculated from stat projections.
# Published: we scrape their published trade value chart; live comparison is valid.
# Calculated: we compute values from ROS stat projections; no live trade chart exists.
SOURCE_TYPES = {
    "espn": "calculated_from_projections",
    "cbs": "published_trade_values",
    "cbsros": "calculated_from_projections",
    "razzball": "calculated_from_projections",
    "fantasycalc": "published_trade_values",
    "fantasypros": "published_trade_values",
    "usatoday": "published_trade_values",
}

# FantasyCalc updates continuously mid-day; exact match is impossible.
# Use tolerance: within 5% or 2.0 points (whichever is larger).
FANTASYCALC_TOLERANCE_PCT = 0.05
FANTASYCALC_TOLERANCE_ABS = 2.0

# Combo keys for 12-team Half PPR
COMBO_KEYS = {
    "espn": "half_12",
    "cbs": "half_12",
    "cbsros": "half_12",  # DDF methodology like ESPN
    "razzball": "half_12",  # DDF methodology like ESPN
    "fantasycalc": "half_12_qb1",  # 1QB is the standard
    "fantasypros": "half_12",
    "usatoday": "half_12",
}

ADJUSTED_SOURCES = {
    "espn": None,  # ESPN uses DDF methodology, no "adjusted" variant
    "cbs": "cbs_adjusted",
    "cbsros": None,  # CBS ROS uses DDF methodology; no fitted bias-correction cells exist
    "razzball": None,  # Razzball uses DDF methodology; no fitted bias-correction cells exist
    "fantasycalc": "fantasycalc_adjusted",
    "fantasypros": "fantasypros_adjusted",
    "usatoday": "usatoday_adjusted",
}

# Map adjusted leg -> parent source key. Adjusted legs render the
# VORP-translated values on the chart and inherit the parent's publisher
# native, indexed value, and live scrape (no own live page).
# JEG-98: each gets a standalone top-25 audit table.
ADJUSTED_LEG_PARENT = {
    "fantasypros_adjusted": "fantasypros",
    "usatoday_adjusted": "usatoday",
    "fantasycalc_adjusted": "fantasycalc",
    "cbs_adjusted": "cbs",
}
ALL_ADJUSTED_LEGS = list(ADJUSTED_LEG_PARENT.keys())


# JEG-107: VORP round-trip helpers ------------------------------------------
#
# Each source's top-25 lineage card must show the three steps:
#   1. native          — publisher's published value (publisher's domain)
#   2. implied_vorp    — native minus the publisher's inferred waiver line,
#                        computed by translate_source() under the JEG-62
#                        inferred roster assumptions (roster settings are not
#                        inputs the publisher exposes — we infer them).
#   3. ddf_rebuilt     — what DDF shows after running through our methodology,
#                        i.e. the chart value (reindexed for published
#                        sources, native-scale DDF value for DDF-native
#                        sources, adjusted reindexed for adjusted legs).
#
# Per-player the lineage also carries:
#   vorp_replacement_level — the inferred waiver-line value for the player's
#                        position (the implied read on the model's
#                        replacement tier, from translate_source()).
# Failure-closed — no data, no row; never a guessed placeholder.

# Sources where the "native" really is a publisher-published trade value that
# goes through JEG-62 VORP translation. For these, implied_vorp is computed
# directly from the publisher native via translate_source().
_PUBLISHED_VORP_SOURCES = {"fantasypros", "usatoday", "fantasycalc", "cbs"}

# Sources where the "native" is a stat projection (no publisher trade value at
# all), and the VORP comes from running our own inferred roster assumptions on
# the projection. For these, implied_vorp is computed via
# compute_vorp_via_roster() from vorp_via_roster.py.
_DDF_NATIVE_VORP_SOURCES = {"espn", "cbsros", "razzball"}

_LINEAGE_WEEK = 4  # documented at build time; lineage is a snapshot, not a feed


def _compute_vorp_chain_for_source(src, sources, scoring="half_ppr", teams=12):
    """Compute implied VORP + waiver lines for one source.

    Returns a dict with:
      positions: {pos: {waiver_line_value, n_rostered, n_dedicated, n_flex, n_bench}}
      player_vorp: {pkey: float}         implied VORP per player (>= 0)
      player_pos: {pkey: pos}            position per player
      player_native: {pkey: float}       publisher native used (for sanity)
      ddf_rebuilt: {pkey: float}         DDF-rebuilt value per player
      method: str                         "published" | "ddf_native"
      error: str | None
    """
    if src in _PUBLISHED_VORP_SOURCES:
        try:
            from unified import translate_source
            r = translate_source(src, scoring=scoring, teams=teams,
                                 week=_LINEAGE_WEEK, bench_per_team=6.0,
                                 write_supabase=False)
            # JEG-107: translate_source() keys `translated` by numeric player
            # id, but lineage rows join on the canonical normalized name
            # (the same norm_player_name join the rest of this builder
            # uses). Re-key by normalized name so _attach_vorp_fields
            # finds the players; fail-closed is preserved (missing name ->
            # no row match -> null, never a guess).
            translated = r["translated"]
            return {
                "positions": r["positions"],
                "player_vorp": {
                    norm_player_name(t["name"]): t["vorp"]
                    for t in translated.values()
                },
                "player_pos": {
                    norm_player_name(t["name"]): t["pos"]
                    for t in translated.values()
                },
                "player_native": {
                    norm_player_name(t["name"]): t["native"]
                    for t in translated.values()
                },
                "ddf_rebuilt": {
                    norm_player_name(t["name"]): t["translated"]
                    for t in translated.values()
                },
                "method": "published",
                "error": None,
            }
        except Exception as e:
            return {"positions": {}, "player_vorp": {}, "player_pos": {},
                    "player_native": {}, "ddf_rebuilt": {},
                    "method": "published", "error": str(e)}

    if src in _DDF_NATIVE_VORP_SOURCES:
        # DDF-native: native is a stat projection. Implied VORP comes from
        # running our own inferred roster (DDF's roster) on the projection.
        try:
            from vorp_via_roster import (
                load_ranked_values, rostered_for_teams,
            )
            prefix = {"half_ppr": "half", "ppr": "full"}.get(scoring, scoring)
            combo_key = f"{prefix}_{teams}"
            ranked = load_ranked_values(src, combo_key)
            roster = rostered_for_teams(teams, 6.0, ranked=ranked,
                                        use_vorp_weighting=True)
            positions = {}
            player_vorp = {}
            player_pos = {}
            player_native = {}
            for pos, players in ranked.items():
                if not players:
                    continue
                r = roster[pos]
                n_rost = r["rostered"]
                if len(players) > n_rost:
                    waiver = players[n_rost][1]
                    method = "roster_determined"
                elif players:
                    waiver = players[-1][1]
                    method = "insufficient_coverage"
                else:
                    waiver = 0.0
                    method = "no_players"
                positions[pos] = {
                    "waiver_line_value": round(waiver, 2),
                    "n_rostered": n_rost,
                    "n_dedicated": r["dedicated"],
                    "n_flex": r["flex"],
                    "n_bench": r["bench"],
                    "waiver_method": method,
                }
                for name, val in players:
                    # Fail closed on identity: skip names the canonical
                    # registry cannot resolve. Chain dicts are keyed by
                    # normalized name -- the same join _attach_vorp_fields
                    # (and the rest of this builder) uses for lineage rows.
                    from canonical_players import resolve as _resolve
                    if _resolve(name) is None:
                        continue
                    nkey = norm_player_name(name)
                    vorp = max(0.0, val - waiver)
                    player_vorp[nkey] = round(vorp, 2)
                    player_pos[nkey] = pos
                    player_native[nkey] = round(val, 2)
            return {
                "positions": positions,
                "player_vorp": player_vorp,
                "player_pos": player_pos,
                "player_native": player_native,
                "ddf_rebuilt": {},  # filled in by caller from chart values
                "method": "ddf_native",
                "error": None,
            }
        except Exception as e:
            return {"positions": {}, "player_vorp": {}, "player_pos": {},
                    "player_native": {}, "ddf_rebuilt": {},
                    "method": "ddf_native", "error": str(e)}

    return {"positions": {}, "player_vorp": {}, "player_pos": {},
            "player_native": {}, "ddf_rebuilt": {}, "method": "unknown",
            "error": f"unknown source {src!r}"}


def _vorp_chain_for_sources(srcs, sources):
    """Build the VORP round-trip chain for every source we render.

    Returns {src: chain_dict}. Computed once and reused across parent + adjusted
    legs so the parent chain is what an adjusted leg inherits.
    """
    out = {}
    for src in srcs:
        out[src] = _compute_vorp_chain_for_source(src, sources)
    return out


def require_snapshot_natives(snapshot_natives):
    """Fail-closed guard: refuse to build when a required source snapshot is
    missing or empty.

    The source snapshots live under gitignored data/raw, so they are absent
    in CI. Without them the builder silently falls back to the TRANSFORMED
    combo natives and every live-vs-native comparison fails (2026-10-01:
    served FantasyPros showed 0/25 matches after a Pages rebuild). Never
    write a degraded lineage file: raise, so the committed (locally built,
    correct) artifact survives the deploy.
    """
    required = [src for src in ("fantasypros", "usatoday", "fantasycalc")
                if src in SNAPSHOT_PATHS]
    missing = [src for src in required if not snapshot_natives.get(src)]
    if missing:
        raise SystemExit(
            "build_source_value_lineage: missing required source snapshots for "
            f"{missing} (data/raw is gitignored; build locally where snapshots exist)"
        )


def _attach_vorp_fields(player_row, pkey, vorp_chain, ddf_rebuilt_override=None):
    """Attach implied_vorp / vorp_replacement_level / ddf_rebuilt to a player row.

    ddf_rebuilt_override: for DDF-native sources we already have the chart
    value in the lineage row; we keep that as the DDF-rebuilt value rather
    than the unified.translate_value (which would re-scale to OUR_MAX,
    producing a value the chart doesn't display).
    """
    pkey_norm = norm_player_name(pkey)
    # Explicit None checks, not `or`: a legitimate 0.0 VORP (player exactly
    # at the replacement tier) must not fall through to the second lookup.
    pos = vorp_chain.get("player_pos", {}).get(pkey)
    if pos is None:
        pos = vorp_chain.get("player_pos", {}).get(pkey_norm)
    vorp = vorp_chain.get("player_vorp", {}).get(pkey)
    if vorp is None:
        vorp = vorp_chain.get("player_vorp", {}).get(pkey_norm)
    if pos is not None:
        positions = vorp_chain.get("positions", {})
        waiver = positions.get(pos, {}).get("waiver_line_value")
        n_rost = positions.get(pos, {}).get("n_rostered")
    else:
        waiver = None
        n_rost = None
    player_row["implied_vorp"] = round(vorp, 2) if vorp is not None else None
    player_row["vorp_replacement_level"] = round(waiver, 2) if waiver is not None else None
    player_row["vorp_inferred_position"] = pos
    player_row["vorp_inferred_n_rostered"] = n_rost
    if ddf_rebuilt_override is not None:
        player_row["ddf_rebuilt"] = round(ddf_rebuilt_override, 2)
    else:
        rebuilt = vorp_chain.get("ddf_rebuilt", {}).get(pkey)
        if rebuilt is None:
            rebuilt = vorp_chain.get("ddf_rebuilt", {}).get(pkey_norm)
        player_row["ddf_rebuilt"] = round(rebuilt, 2) if rebuilt is not None else None
    return player_row


def build_source_entry(src, sources, live_data, snapshot_natives, vorp_chain=None):
    """Build one source's lineage block (top 25 by chart value) from the fixture."""
    combo_key = COMBO_KEYS[src]
    combo = sources[src]["combos"].get(combo_key, {})

    native = combo.get("native", {})
    # Override with snapshot natives for accuracy (raw scraped values)
    if src in snapshot_natives and snapshot_natives[src]:
        native = snapshot_natives[src]
    
    reindexed = combo.get("reindexed", {})
    values = combo.get("values", {})  # ESPN DDF values

    # Top 25 by CHART VALUE (most valuable), not native.
    # For ESPN, native is ROS projected points (counting stat), not trade value.
    # Sorting by native would rank high-volume QBs above elite RBs.
    if src in ("espn", "cbsros", "razzball"):
        sort_vals = values
    else:
        sort_vals = reindexed

    # JEG-106: keep numeric zero (0.0) -- only None means missing.
    # `if v` would drop legitimate zero values.
    top25_keys = sorted(
        [k for k in sort_vals if sort_vals[k] is not None],
        key=lambda k: sort_vals[k],
        reverse=True
    )[:25]

    # Get adjusted curve data for reweighted values
    adj_src = ADJUSTED_SOURCES[src]
    adj_combo = {}
    if adj_src and adj_src in sources:
        adj_combo = sources[adj_src]["combos"].get(combo_key, {})
    adj_reindexed = adj_combo.get("reindexed", {})

    players = []
    for rank, pkey in enumerate(top25_keys, 1):
        # Native value: try normalized key first (for snapshot natives),
        # then original pkey (for combo natives in comparison format)
        nat_val = native.get(norm_player_name(pkey))
        if nat_val is None:
            nat_val = native.get(pkey)
        # For ESPN, the "indexed" value IS the DDF value (from values),
        # not from reindexed (ESPN uses DDF methodology, not isotonic reindexing)
        if src in ("espn", "cbsros", "razzball"):
            idx_val = values.get(pkey)
        else:
            idx_val = reindexed.get(pkey)
        # Live value scraped from the human-readable page
        # Normalize pkey to match the scraper's normalized keys (suffixes stripped)
        live_pkey = norm_player_name(pkey)
        live_val = live_data.get(src, {}).get(live_pkey)
        # Fallback: try original pkey in case scraper didn't normalize
        if live_val is None:
            live_val = live_data.get(src, {}).get(pkey)
        live_matches = None
        if live_val is not None and nat_val is not None:
            if src == "fantasycalc":
                # FantasyCalc updates continuously; use tolerance, not exact match
                tol = max(abs(nat_val) * FANTASYCALC_TOLERANCE_PCT, FANTASYCALC_TOLERANCE_ABS)
                live_matches = abs(live_val - nat_val) <= tol
            else:
                live_matches = abs(live_val - nat_val) < 0.01
        # For ESPN, the chart shows DDF values; for others, reindexed
        if src in ("espn", "cbsros", "razzball"):
            chart_val = values.get(pkey)
        else:
            chart_val = idx_val

        # JEG-106: Check if an adjusted leg exists for this parent source.
        # If so, the parent chart column is N/A because the chart actually
        # uses the adjusted leg's value, not the parent's indexed value.
        # Compare against adjusted value if available, otherwise compare against indexed.
        has_adjusted = bool(adj_src and adj_reindexed.get(pkey))
        if has_adjusted:
            # Chart uses adjusted value, so parent's chart column is N/A
            display_chart_val = None
            chart_matches = None
        else:
            display_chart_val = chart_val
            # Original comparison: chart matches indexed
            chart_matches = (
                abs(chart_val - idx_val) < 0.01
                if chart_val and idx_val else None
            )

        # Effective multipliers
        index_mult = (idx_val / nat_val) if idx_val and nat_val else None
        reweighted_val = adj_reindexed.get(pkey)
        reweight_mult = (reweighted_val / idx_val) if reweighted_val and idx_val else None

        players.append({
            "rank": rank,
            "player_key": pkey,
            "live_value": round(live_val, 2) if live_val is not None else None,
            "native": round(nat_val, 2) if nat_val else None,
            "live_matches_native": live_matches,
            "index_mult": round(index_mult, 4) if index_mult else None,
            "indexed": round(idx_val, 2) if idx_val else None,
            "reweight_mult": round(reweight_mult, 4) if reweight_mult else None,
            "reweighted": round(reweighted_val, 2) if reweighted_val else None,
            "chart_value": round(display_chart_val, 2) if display_chart_val is not None else None,
            "chart_matches_indexed": chart_matches,
            # JEG-106: Flag to indicate adjusted version is available
            "has_adjusted_leg": has_adjusted,
        })
        if vorp_chain is not None:
            # JEG-107: the chain shows three steps per player. For DDF-native
            # sources (espn/cbsros/razzball) the chart value IS the DDF-rebuilt
            # value -- the chart renders our methodology directly, so passing
            # the chart value as the override makes the chain consistent.
            _attach_vorp_fields(players[-1], pkey, vorp_chain,
                                ddf_rebuilt_override=chart_val)

    return {
        "source_url": SOURCE_URLS[src]["url"],
        "source_note": SOURCE_URLS[src]["note"],
        "source_type": SOURCE_TYPES[src],
        "combo_key": combo_key,
        "player_count": len(native),  # Use actual native count, not stale 'n' field
        "live_scraped": src in live_data and bool(live_data[src]),
        # JEG-53: per-source build time. The lineage artifact can only fully
        # rebuild where raw snapshots exist; one global "Generated" timestamp
        # hides source-by-source age differences. Each source shows its own
        # actual build/promotion time.
        "source_built_at": (
            sources[src].get("promoted_at")
            or sources[src].get("fetched_at")
            or "unknown"
        ),
        # JEG-106: When an adjusted leg exists for this parent source,
        # provide a pointer to it for the dashboard UI.
        "adjusted_leg_pointer": adj_src,
        # JEG-107: VORP round-trip. Inspectable per position so a reader can
        # see the publisher's inferred roster assumptions (waiver line per
        # position, number of rostered players, how flex was apportioned).
        # Only populated when translate_source / vorp_via_roster succeeded.
        "vorp_round_trip": (
            {
                "method": vorp_chain.get("method"),
                "positions": {
                    pos: {
                        "waiver_line_value": info.get("waiver_line_value"),
                        "n_rostered": info.get("n_rostered"),
                        "n_dedicated": info.get("n_dedicated"),
                        "n_flex": info.get("n_flex"),
                        "n_bench": info.get("n_bench"),
                        "waiver_method": info.get("waiver_method"),
                    }
                    for pos, info in (vorp_chain.get("positions") or {}).items()
                },
                "error": vorp_chain.get("error"),
            }
            if vorp_chain is not None else None
        ),
        "top25": players,
    }


def build_adjusted_leg_entry(adj_src, sources, live_data, snapshot_natives,
                             vorp_chain=None):
    """Build one adjusted leg's lineage block (top 25 by chart value).

    Adjusted legs render the VORP-translated values on the chart. They have
    no live page of their own, so live verification uses the parent source's
    scrape and the live-verification column fails red per the standing
    contract. The builder raises (fail-closed) when the adjusted combo
    cannot be built, so a partial artifact is never written.
    """
    if adj_src not in ADJUSTED_LEG_PARENT:
        raise ValueError(f"build_source_value_lineage: unknown adjusted leg {adj_src!r}")
    parent_src = ADJUSTED_LEG_PARENT[adj_src]
    combo_key = COMBO_KEYS[parent_src]
    if adj_src not in sources:
        raise ValueError(
            f"build_source_value_lineage: adjusted leg {adj_src!r} missing from fixture; "
            f"refusing to write partial output"
        )
    parent_combo = sources.get(parent_src, {}).get("combos", {}).get(combo_key, {})
    adj_combo = sources.get(adj_src, {}).get("combos", {}).get(combo_key, {})

    if not adj_combo or not adj_combo.get("reindexed"):
        raise ValueError(
            f"build_source_value_lineage: adjusted leg {adj_src!r} combo "
            f"{combo_key!r} has no reindexed rows; refusing to write partial output"
        )

    # Native: parent's publisher native (snapshot overrides combo)
    parent_native = parent_combo.get("native", {})
    if parent_src in snapshot_natives and snapshot_natives[parent_src]:
        parent_native = snapshot_natives[parent_src]

    parent_reindexed = parent_combo.get("reindexed", {})
    adj_reindexed = adj_combo.get("reindexed", {})

    # Top 25 by chart value (= adjusted reindexed for adjusted legs)
    top25_keys = sorted(
        [k for k in adj_reindexed if adj_reindexed[k]],
        key=lambda k: adj_reindexed[k],
        reverse=True,
    )[:25]

    if not top25_keys:
        raise ValueError(
            f"build_source_value_lineage: adjusted leg {adj_src!r} produced no "
            f"top-25 rows; refusing to write partial output"
        )

    players = []
    for rank, pkey in enumerate(top25_keys, 1):
        # Publisher native (parent's snapshot overrides combo)
        nat_val = parent_native.get(norm_player_name(pkey))
        if nat_val is None:
            nat_val = parent_native.get(pkey)
        # Indexed = parent combo's reindexed
        idx_val = parent_reindexed.get(pkey)
        # Chart value = adjusted reindexed (what renders on the chart)
        chart_val = adj_reindexed.get(pkey)
        # Live value: inherited from parent source's live scrape
        live_pkey = norm_player_name(pkey)
        live_val = live_data.get(parent_src, {}).get(live_pkey)
        if live_val is None:
            live_val = live_data.get(parent_src, {}).get(pkey)
        # Effective multipliers
        index_mult = (idx_val / nat_val) if idx_val and nat_val else None
        vorp_mult = (chart_val / idx_val) if chart_val and idx_val else None
        # No own live page: live_matches stays None; the dashboard renders
        # the live column FAIL RED via the !live_scraped contract.
        live_matches = None

        players.append({
            "rank": rank,
            "player_key": pkey,
            "live_value": round(live_val, 2) if live_val is not None else None,
            "native": round(nat_val, 2) if nat_val else None,
            "live_matches_native": live_matches,
            "index_mult": round(index_mult, 4) if index_mult else None,
            "indexed": round(idx_val, 2) if idx_val else None,
            "reweight_mult": round(vorp_mult, 4) if vorp_mult else None,
            "reweighted": round(chart_val, 2) if chart_val else None,
            "chart_value": round(chart_val, 2) if chart_val is not None else None,
            # JEG-106: For adjusted legs, compare chart value (adjusted) against
            # parent's indexed value. This shows the actual difference between
            # what the chart displays (adjusted) vs what the parent published (indexed).
            # A red X means the chart value differs from parent's indexed.
            "chart_matches_indexed": (
                abs(chart_val - idx_val) < 0.01
                if chart_val and idx_val else None
            ),
        })
        if vorp_chain is not None:
            # JEG-107: adjusted leg inherits the parent's implied VORP
            # (same publisher native, same inferred roster), but the
            # DDF-rebuilt value is the adjusted reindexed (what the chart
            # displays for the adjusted leg), not the parent's translated
            # value -- so we override ddf_rebuilt with chart_val here.
            _attach_vorp_fields(players[-1], pkey, vorp_chain,
                                ddf_rebuilt_override=chart_val)

    return {
        "source_url": SOURCE_URLS[parent_src]["url"],
        "source_note": (
            f"VORP-translated bias-adjusted variant of {parent_src}; inherits "
            f"{SOURCE_URLS[parent_src]['note']}"
        ),
        "source_type": SOURCE_TYPES[parent_src],
        "combo_key": combo_key,
        "parent_source": parent_src,
        "player_count": len(adj_reindexed),
        "live_scraped": False,
        "live_inherits_from": parent_src,
        "source_built_at": (
            sources[adj_src].get("promoted_at")
            or sources[adj_src].get("fetched_at")
            or "unknown"
        ),
        # JEG-107: VORP round-trip inherited from the parent source.
        # Same publisher assumptions, different final translated value.
        "vorp_round_trip": (
            {
                "method": (vorp_chain or {}).get("method"),
                "positions": {
                    pos: {
                        "waiver_line_value": info.get("waiver_line_value"),
                        "n_rostered": info.get("n_rostered"),
                        "n_dedicated": info.get("n_dedicated"),
                        "n_flex": info.get("n_flex"),
                        "n_bench": info.get("n_bench"),
                        "waiver_method": info.get("waiver_method"),
                    }
                    for pos, info in ((vorp_chain or {})
                                       .get("positions") or {}).items()
                },
                "error": (vorp_chain or {}).get("error"),
                "inherited_from": parent_src,
            }
            if vorp_chain is not None else None
        ),
        "top25": players,
    }


def merge_fixture_only(names):
    """Merge fixture-only sources into the existing lineage artifact.

    Rebuilds only the named sources (from the fixture) and leaves every other
    source block, the live-scrape fields and the top-level generated_at exactly
    as they were. Refuses anything that needs live pages or raw snapshots, and
    refuses to run without an existing artifact, so it can never publish a
    degraded file.
    """
    bad = [n for n in names if n not in FIXTURE_ONLY_SOURCES]
    if bad:
        raise SystemExit(f"--merge only supports {FIXTURE_ONLY_SOURCES}; got {bad}")
    if not os.path.exists(OUT_PATH):
        raise SystemExit(f"--merge needs an existing artifact: {OUT_PATH}")
    d = json.load(open(DATA_PATH))
    result = json.load(open(OUT_PATH))
    for src in names:
        entry = build_source_entry(src, d["sources"], {}, {})
        if not entry["top25"]:
            raise SystemExit(f"--merge: {src} produced no rows; refusing to write")
        entry["built_from_fixture_at"] = d.get("built_at") or d.get("generated_at") or "unknown"
        result["sources"][src] = entry
        print(f"  merged {src}: {len(entry['top25'])} players (fixture {entry['built_from_fixture_at']})")
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote {OUT_PATH}")


def main():
    if "--merge" in sys.argv:
        i = sys.argv.index("--merge")
        merge_fixture_only([n for n in sys.argv[i + 1].split(",") if n])
        return
    d = json.load(open(DATA_PATH))
    sources = d["sources"]

    # Live values come from the dedicated scrape artifact (scrape once, reuse).
    # This builder must NOT re-scrape at build time: intermittent bot blocks
    # used to silently degrade to empty and poison the monitor with FAIL RED.
    print("Loading live page values from scrape artifact...")
    live_data = load_live_page_values()

    result = {
        "generated_at": d.get("generated_at") or d.get("built_at") or "unknown",
        "live_scraped_at": live_data.get("_scraped_at", "unknown"),
        "live_stale_sources": live_data.get("_stale", {}),
        "scoring": "Half PPR",
        "teams": 12,
        "method": "Native values verified against LIVE human-readable source pages where a trade-value page exists. FantasyPros, USA Today, CBS scraped directly from article pages. FantasyCalc via the API powering its human-visible page (same numbers). ESPN, CBS ROS, and Razzball have no published trade value chart; their projection-derived values are traced but live trade-value verification is unavailable.",
        "sources": {},
    }

    # Load snapshot natives (raw scraped values) for sources with snapshots
    # The comparison data's "native" field contains transformed values, not raw.
    # We need the true native_value from the snapshot for accurate lineage.
    snapshot_natives = {}
    for src in ["fantasypros", "usatoday", "fantasycalc"]:
        snapshot_natives[src] = load_snapshot_natives(src)
        print(f"  {src}: loaded {len(snapshot_natives[src])} native values from snapshot")
    require_snapshot_natives(snapshot_natives)

    # JEG-107: compute the VORP round-trip (native -> implied publisher VORP
    # -> DDF-rebuilt) for every source that has a lineage card, including
    # parents (so adjusted legs can inherit). Failed chains degrade to empty
    # positions -- the lineage row keeps its native and chart columns, with
    # vorp_* fields null and a recorded error in vorp_round_trip.error.
    print("Computing VORP round-trip per source...")
    chain_for = _vorp_chain_for_sources(
        list(ALL_SOURCES) + list(ALL_ADJUSTED_LEGS), sources
    )
    for src in ALL_SOURCES:
        c = chain_for.get(src, {})
        if c.get("error"):
            print(f"  {src}: VORP chain failed ({c['error']}) -- "
                  "implied_vorp/vorp_replacement_level will be null")
        else:
            print(f"  {src}: VORP chain OK "
                  f"({len(c.get('positions', {}))} positions, "
                  f"{len(c.get('player_vorp', {}))} players)")

    for src in ALL_SOURCES:
        result["sources"][src] = build_source_entry(
            src, sources, live_data, snapshot_natives,
            vorp_chain=chain_for.get(src),
        )

    # JEG-98: build the 4 VORP-translated adjusted legs as standalone top-25
    # audit tables. Each inherits native + indexed + live from the parent
    # source and renders the adjusted reindexed as the chart value. The
    # builder raises if a leg cannot be built, so this loop is fail-closed.
    print("Building adjusted legs...")
    for adj_src in ALL_ADJUSTED_LEGS:
        # JEG-107: adjusted legs inherit the parent's VORP round-trip
        # because the publisher assumptions are the same; only the final
        # translated value differs (the bias-adjusted reindexed).
        parent = ADJUSTED_LEG_PARENT[adj_src]
        result["sources"][adj_src] = build_adjusted_leg_entry(
            adj_src, sources, live_data, snapshot_natives,
            vorp_chain=chain_for.get(parent),
        )
        print(f"  {adj_src}: {len(result['sources'][adj_src]['top25'])} players")

    # Write output
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote {OUT_PATH}")
    for src in result["sources"]:
        n = len(result["sources"][src]["top25"])
        print(f"  {src}: {n} players")


if __name__ == "__main__":
    main()
