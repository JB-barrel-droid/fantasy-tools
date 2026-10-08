#!/usr/bin/env python3
"""Sync finished fixture artifacts into the static dashboard and dist output."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from check_reference_freshness import build_report


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "trade-value-chart"
FIXTURES = ROOT / "data" / "fixtures" / "current"
MODULES = ROOT / "modules"
WEEKLY_VEGAS = ROOT / "weekly_vegas" / "dashboard"
WAIVER_WIRE = ROOT / "waiver_wire" / "dashboard"
DIST = ROOT / "dist"
REFERENCE_FRESHNESS = ROOT / "output" / "reference-freshness.json"
RUNTIME_IMPORT_HEALTH = ROOT / "output" / "source-import-health.json"
FIXTURE_IMPORT_HEALTH = FIXTURES / "source-import-health.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def replace_inline_players(index_html: str, players: dict) -> str:
    start_marker = '<script id="players-data" type="application/json">'
    end_marker = "</script>"
    start = index_html.index(start_marker) + len(start_marker)
    end = index_html.index(end_marker, start)
    payload = json.dumps(players, separators=(",", ":"), ensure_ascii=False)
    return index_html[:start] + payload + index_html[end:]


METHODOLOGY_SCORINGS = ["standard", "half", "full"]
METHODOLOGY_SCORING_LABELS = {
    "standard": "Standard",
    "half": "Half PPR",
    "full": "Full PPR",
}
METHODOLOGY_TEAMS = [8, 10, 12, 14]
METHODOLOGY_POSITION_SOURCES = [
    ("usatoday", "USA Today"),
    ("fantasycalc", "FantasyCalc"),
    ("fantasypros", "FantasyPros"),
    ("cbs", "CBS"),
    ("espn", "ESPN"),
]
METHODOLOGY_ADJUSTED_PAIRS = [
    ("usatoday", "usatoday_adjusted", "USA Today"),
    ("fantasycalc", "fantasycalc_adjusted", "FantasyCalc"),
    ("fantasypros", "fantasypros_adjusted", "FantasyPros"),
    ("cbs", "cbs_adjusted", "CBS"),
]
# The two-tier value model behind the adjusted view. Baked here so the
# methodology section can describe the actual bench/starter split.
METHODOLOGY_BENCH_SHARE = 0.15
METHODOLOGY_ROSTER = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 6}


def _methodology_combo(source: str, scoring: str, teams: int) -> str:
    # FantasyCalc variants take the _qb1 combo; every other source uses the
    # plain scoring_teams combo.
    suffix = "_qb1" if source.startswith("fantasycalc") else ""
    return f"{scoring}_{teams}{suffix}"


def build_methodology_payload(fixtures: Path, players_data: dict) -> dict:
    """Bake the numbers behind the 'How we make the charts comparable' section.

    Baked per (scoring x teams) combo so the section follows the chart's
    league settings instead of being pinned to Full PPR / 12 teams.

    combos[<scoring>_<teams>]:
      position_shares: per-position share of each source's fixed pie -- the
        'same pie, different slicing' visual. Sources without that combo
        (e.g. USA Today only ships 12-team) are omitted from that combo.
      adjustments: biggest as-published -> adjusted movers per adjusted
        series -- the 'correcting toward our view' visual.
    Derived from the same fixture the curves render, so the section can
    never drift from the chart.
    """
    comp = read_json(fixtures / "comparison-sources-data.json")
    name2key = comp.get("player_keys", {})
    by_key = {p["player_key"]: p for p in players_data.get("players", [])}

    def pos_of(name: str) -> str:
        return (by_key.get(name2key.get(name)) or {}).get("pos", "?")

    def display_name(name: str) -> str:
        return (by_key.get(name2key.get(name)) or {}).get("name") or name.title()

    def series_values(source: str, combo: str) -> dict:
        series = comp["sources"].get(source, {}).get("combos", {}).get(combo, {})
        # ESPN's DDF-methodology leg is stored under "values" (never reindexed);
        # as-published series use "reindexed".
        return series.get("reindexed") or series.get("values") or {}

    combos = {}
    for scoring in METHODOLOGY_SCORINGS:
        for teams in METHODOLOGY_TEAMS:
            combo_key = f"{scoring}_{teams}"
            position_shares = {}
            for src, label in METHODOLOGY_POSITION_SOURCES:
                vals = series_values(src, _methodology_combo(src, scoring, teams))
                if not vals:
                    continue
                total = sum(vals.values())
                shares = {"QB": 0.0, "RB": 0.0, "WR": 0.0, "TE": 0.0}
                for name, value in vals.items():
                    pos = pos_of(name)
                    if pos in shares:
                        shares[pos] += value
                position_shares[src] = {
                    "label": label,
                    "shares": (
                        {p: round(s / total * 100) for p, s in shares.items()}
                        if total
                        else shares
                    ),
                    "n": len(vals),
                }
            adjustments = {}
            for pub, adj, label in METHODOLOGY_ADJUSTED_PAIRS:
                pub_vals = series_values(pub, _methodology_combo(pub, scoring, teams))
                adj_vals = series_values(adj, _methodology_combo(adj, scoring, teams))
                if not pub_vals or not adj_vals:
                    continue
                # Build full player list with tier (starter/bench) for the
                # interactive recalibration lab. Tier is by rank within
                # position: top (teams x starters) are starters.
                by_pos = {}
                for name, after in adj_vals.items():
                    if name not in pub_vals:
                        continue
                    pos = pos_of(name)
                    if pos not in by_pos:
                        by_pos[pos] = []
                    by_pos[pos].append((after, name))
                tier_of = {}
                for pos, plist in by_pos.items():
                    plist.sort(key=lambda x: -x[0])
                    n_starters = teams * METHODOLOGY_ROSTER.get(pos, 0)
                    for i, (_, name) in enumerate(plist):
                        tier_of[name] = "starter" if i < n_starters else "bench"
                movers = []
                all_players = []
                for name, before in pub_vals.items():
                    if name not in adj_vals:
                        continue
                    after = adj_vals[name]
                    delta = after - before
                    pos = pos_of(name)
                    tier = tier_of.get(name, "bench")
                    entry = {
                        "name": display_name(name),
                        "pos": pos,
                        "tier": tier,
                        "before": round(before, 1),
                        "after": round(after, 1),
                        "delta": round(delta, 1),
                    }
                    all_players.append(entry)
                    if before > 8:
                        movers.append((delta, entry))
                movers.sort(key=lambda m: -abs(m[0]))
                # Default position weights from ESPN's shares at this combo
                # (the "pie" the recalibration targets).
                espn_vals = series_values("espn", _methodology_combo("espn", scoring, teams))
                default_weights = {"QB": 25.0, "RB": 25.0, "WR": 25.0, "TE": 25.0}
                if espn_vals:
                    tot = sum(espn_vals.values())
                    if tot > 0:
                        w = {"QB": 0.0, "RB": 0.0, "WR": 0.0, "TE": 0.0}
                        for n, v in espn_vals.items():
                            p = pos_of(n)
                            if p in w:
                                w[p] += v
                        default_weights = {p: round(s / tot * 100, 1) for p, s in w.items()}
                adjustments[pub] = {
                    "label": label,
                    "movers": [e for _, e in movers[:6]],
                    "players": sorted(all_players, key=lambda x: -x["after"]),
                    "default_weights": default_weights,
                    "n_players": len(all_players),
                }
            # Only keep combos that have at least one source; an empty combo
            # would render a blank methodology section.
            if position_shares:
                combos[combo_key] = {
                    "scoring": scoring,
                    "scoring_label": METHODOLOGY_SCORING_LABELS[scoring],
                    "teams": teams,
                    "position_shares": position_shares,
                    "adjustments": adjustments,
                }

    return {
        "combos": combos,
        "default_combo": "full_12",
        "bench_share": METHODOLOGY_BENCH_SHARE,
        "roster": METHODOLOGY_ROSTER,
    }


def replace_inline_methodology(index_html: str, payload: dict) -> str:
    start_marker = '<script id="methodology-data" type="application/json">'
    end_marker = "</script>"
    start = index_html.index(start_marker) + len(start_marker)
    end = index_html.index(end_marker, start)
    baked = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return index_html[:start] + baked + index_html[end:]


SITE_URL = "https://jb-barrel-droid.github.io/fantasy-tools/"
# Launch 2026-10-08 (Jeremy): the v2 page is the front door at the site root;
# the chart dashboard moves to /classic/. build_v2_page reads this page as its
# engine input and writes dist/index.html (root) and dist/v2/index.html.
CLASSIC_DIR = "classic"


def classic_page_html(index_html: str) -> str:
    """The chart dashboard as served from dist/classic/index.html.

    One directory down from the site root, so a <base href="../"> keeps every
    relative asset, fetch and data path pointing where it always has. A base
    also re-targets in-page "#x" links at the base URL (the root, now v2), so
    those are rewritten to "classic/#x", which is this same document.
    Canonical to itself; noindex so search results land on the front door
    rather than the secondary chart view.
    """
    if "<head>" not in index_html or "</title>" not in index_html:
        raise SystemExit("classic page: <head> or <title> missing from app/trade-value-chart/index.html")
    html = index_html.replace("<head>", '<head>\n  <base href="../">', 1)
    html = html.replace('href="#', f'href="{CLASSIC_DIR}/#')
    head_extra = (
        f'\n  <link rel="canonical" href="{SITE_URL}{CLASSIC_DIR}/">'
        '\n  <meta name="robots" content="noindex, follow">'
    )
    title_end = html.index("</title>") + len("</title>")
    return html[:title_end] + head_extra + html[title_end:]


def copy_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def build_tag() -> str | None:
    """Identity of the commit this build came from: tv-YYYYMMDD-HHMM-<sha>.

    Derived from HEAD's own commit time, not from now(), so re-running sync on
    the same commit produces the same tag. deploy.sh used to stamp this from
    the wall clock at deploy time; folding it in here keeps `make sync` the
    single publish path without making every sync dirty index.html.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "show", "-s", "--format=%cd-%h", "--date=format:%Y%m%d-%H%M", "HEAD"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    tag = out.stdout.strip()
    return f"tv-{tag}" if out.returncode == 0 and tag else None


def stamp_build_tag(index_html: str, tag: str) -> str:
    stamped = re.sub(
        r'(<meta name="trade-chart-build" content=")[^"]*(">)',
        lambda m: m.group(1) + tag + m.group(2),
        index_html,
    )
    stamped = re.sub(
        r'(<span id="buildStamp">)Build [^<]*(</span>)',
        lambda m: m.group(1) + "Build " + tag + m.group(2),
        stamped,
    )
    # Cache-bust every local asset with the SAME build tag.
    #
    # These ?v= tokens used to be hand-written strings ("20260920-curve-all-
    # scale"). They were never bumped, so the asset URL stayed byte-identical
    # across deploys and returning browsers kept serving the cached file. A
    # deploy that fixed a blank chart therefore left the chart blank for
    # anyone who had loaded the page before -- the server had the fix and the
    # browser would not ask for it. Tying the token to the build tag means a
    # new commit always produces a new URL.
    return re.sub(
        r'(<script src="assets/[A-Za-z0-9._-]+\.js)(\?v=[^"]*)?(")',
        lambda m: m.group(1) + "?v=" + tag + m.group(3),
        stamped,
    )


def import_health_source(root: Path = ROOT) -> Path:
    """Use the freshest valid import-health file.

    The 30-min cron pushes a fresh dist/modules/source-import-health.json with
    every health run, but the gitignored output/ runtime file never exists in
    CI (Pages deploy). A fixture-only fallback silently overwrote the fresh
    pushed dist copy with the stale committed fixture -- on 2026-10-01 the
    served health JSON read 08:37Z while main held 10:07Z. Picking the
    freshest valid candidate keeps the deployed file honest.
    """
    runtime = root / "output" / "source-import-health.json"
    dist_copy = root / "dist" / "modules" / "source-import-health.json"
    fixture = root / "data" / "fixtures" / "current" / "source-import-health.json"
    best, best_ts = fixture, None
    for cand in (runtime, dist_copy, fixture):
        ts = _health_checked_at(cand)
        if ts and (best_ts is None or ts > best_ts):
            best, best_ts = cand, ts
    return best


def _health_checked_at(path: Path):
    """checked_at of a valid health payload, or None (fail-closed skip)."""
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("schema") != "trade-value-import-health-v1":
        return None
    ts = payload.get("checked_at")
    return ts if isinstance(ts, str) and ts else None


def sync_monitor_fixture(fixtures_dir, modules_dir):
    """Copy the comparison fixture into dist/modules/ (JEG-8).

    The module monitor serves its fixture copy from dist/modules/; make sync
    maintains it from the canonical fixture on every run, like the app copy,
    so a red (fail-closed) rebuild-chain run can't leave it stale. A missing
    fixture fails loudly instead of leaving a stale copy behind.
    """
    from pathlib import Path
    fixtures_dir = Path(fixtures_dir)
    modules_dir = Path(modules_dir)
    src = fixtures_dir / "comparison-sources-data.json"
    if not src.exists():
        raise FileNotFoundError(f"comparison fixture missing: {src}")
    modules_dir.mkdir(parents=True, exist_ok=True)
    dst = modules_dir / "comparison-sources-data.json"
    dst.write_bytes(src.read_bytes())
    return dst


def write_consolidated_export(fixture_path: Path, out_path: Path) -> dict:
    """Write the consolidation watcher's JSON (JEG-424). Fails closed."""
    import hashlib
    from build_consolidated_values import build_rows, reconcile
    from export_consolidated_json import build_export_doc
    raw = fixture_path.read_bytes()
    detail = json.loads(raw)
    rows, diagnostics = build_rows(detail)
    # Cells whose player has no fixture player_key are left out (review), the
    # same rule as the Supabase write (JEG-324 / JEG-380).
    errors = reconcile(rows, detail, diagnostics.get("review_no_player_key", ()))
    if errors:
        raise SystemExit(f"consolidated export: reconciliation failed ({len(errors)} errors), "
                         f"e.g. {errors[:3]}; not publishing")
    doc = build_export_doc(rows, hashlib.sha256(raw).hexdigest())
    out_path.write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote consolidation export -> {out_path} ({len(rows)} rows, "
          f"{out_path.stat().st_size} bytes)")
    return doc


def sync_week_history(target: Path) -> None:
    """Per-week source history (pipelines/build_week_history.py): save the
    projection inputs players.json serves (append-only; no Supabase), rebuild
    the index against the fixture being published (which saved week each
    source serves) and copy the week files beside the page. Every week file
    is validated (no-relabel guard); a bad file stops the sync."""
    from build_week_history import HISTORY_DIR, PLAYERS, load_weeks, main as build_history, write_espn_legs
    if not HISTORY_DIR.exists():
        return
    build_history(["--served-only"])
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for path in sorted(HISTORY_DIR.glob("*.json")):
        shutil.copy2(path, target / path.name)
    # Prior ESPN legs, rebuilt from the saved projections with today's
    # pipeline code (HISTORY-ESPN-PRIOR); derived, so served but not stored.
    write_espn_legs(load_weeks(HISTORY_DIR), json.loads(PLAYERS.read_text()), target / "espn-legs.json")


def main() -> int:
    players = read_json(FIXTURES / "players.json")
    import_health = import_health_source()
    # UTC, like every timestamp the report reads: a local date ran a day
    # behind them each evening in Chicago, so fresh inputs read as -1 days
    # old ("unknown") on a locally built monitor.
    freshness = build_report(FIXTURES, REFERENCE_FRESHNESS, datetime.now(timezone.utc).date(),
                             import_health_path=import_health)
    REFERENCE_FRESHNESS.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE_FRESHNESS.write_text(json.dumps(freshness, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    (APP / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURES / "comparison-sources-data.json", APP / "assets" / "comparison-sources-data.json")
    shutil.copy2(REFERENCE_FRESHNESS, APP / "assets" / "reference-freshness.json")
    # JEG-137 R10: the per-source dataset cards read assets/deadline-checker.json
    # for the slip measurement behind the Grace/Slip rows. Only copied when a
    # checker run has produced it -- the page falls back to the 6h default
    # (unmeasured) when the asset is absent.
    sync_week_history(APP / "assets" / "history")
    deadline_checker = ROOT / "output" / "deadline-checker.json"
    if deadline_checker.exists():
        shutil.copy2(deadline_checker, APP / "assets" / "deadline-checker.json")

    index_path = APP / "index.html"
    index_html = replace_inline_players(index_path.read_text(encoding="utf-8"), players)
    methodology = build_methodology_payload(FIXTURES, players)
    index_html = replace_inline_methodology(index_html, methodology)
    tag = build_tag()
    if tag:
        index_html = stamp_build_tag(index_html, tag)
    index_path.write_text(index_html, encoding="utf-8")

    # dist/ is exactly what GitHub Pages publishes -- nothing else.
    #
    # This used to also write dist/static/ (a byte-identical second copy of
    # the whole site, which doubled the deployed payload for nothing) and
    # dist/server/index.js (a Cloudflare-style worker stub that Pages never
    # executes). Both were Muse hosting leftovers, as was space.json.
    DIST.mkdir(parents=True, exist_ok=True)
    for name in ("icon.jpg", "404.html"):
        shutil.copy2(APP / name, DIST / name)
    (DIST / CLASSIC_DIR).mkdir(parents=True, exist_ok=True)
    (DIST / CLASSIC_DIR / "index.html").write_text(classic_page_html(index_html), encoding="utf-8")
    copy_tree(APP / "assets", DIST / "assets")

    # The module monitor and the health artifact it reads. Previously both
    # were hand-copied into dist/, so dist/modules/ silently drifted from
    # modules/; generating them here is what keeps the monitor honest.
    dist_modules = DIST / "modules"
    dist_modules.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MODULES / "dashboard.html", dist_modules / "dashboard.html")
    # The consolidation watcher is a modules/ page too — copy it on every sync
    # (JEG-328, 2026-10-03: dist/modules/consolidation.html silently served a
    # stale copy because only dashboard.html was synced here).
    shutil.copy2(MODULES / "consolidation.html", dist_modules / "consolidation.html")
    # JEG-424: live status page for every backend -> frontend surface, and the
    # spec it (and tests/test_published_surfaces.py) reads.
    shutil.copy2(MODULES / "status.html", dist_modules / "status.html")
    shutil.copy2(MODULES / "surfaces.json", dist_modules / "surfaces.json")
    # import_health_source() may resolve to the checked-in dist copy itself
    # (CI picks the freshest valid candidate, which is usually the pushed dist
    # file) -- never copy a file onto itself.
    if import_health.resolve() != (dist_modules / "source-import-health.json").resolve():
        shutil.copy2(import_health, dist_modules / "source-import-health.json")
    # The monitor's fixture copy: kept equal to the canonical fixture on every
    # sync (JEG-8), so it can never silently go stale behind the app copy.
    sync_monitor_fixture(FIXTURES, dist_modules)

    # JEG-424: the consolidation watcher's data. Built here, from the same
    # fixture `make validate` checks, so the page only ever shows validated
    # values (public.consolidated_values holds every bake, including ones
    # that never published, and anon cannot read it). Gitignored: Pages runs
    # `make sync` before deploying, so it is regenerated on every deploy.
    # Fail closed: a reconciliation error stops the sync, and so the deploy.
    write_consolidated_export(FIXTURES / "comparison-sources-data.json",
                              DIST / "consolidated-values.json")

    # JEG-206: 8-group VORP totals (position x starter/bench) rewritten on every
    # sync from the freshest DDF two-tier leg. Fails closed (SystemExit) if the
    # leg is missing or the 8 groups do not sum to the overall VORP pie. The
    # bake's existing sync step drives this -- no standalone cron.
    from build_ddf_groups import build_groups_from_leg, find_latest_leg
    try:
        groups_artifact = build_groups_from_leg(
            find_latest_leg(), dist_modules / "ddf-group-vorps.json")
        print(f"Wrote 8-group VORP totals -> {dist_modules / 'ddf-group-vorps.json'} "
              f"(total_vorp={groups_artifact['totals']['total_vorp']})")
    except SystemExit as e:
        # No leg yet (CI may run sync before a bake has happened). Skip with a
        # warning rather than failing the entire sync -- the leg artifact is
        # optional from the dashboard's perspective and the sync step is shared
        # by every deploy. The module is regenerated on the next sync that has
        # a leg to read.
        print(f"WARNING: skipping ddf-group-vorps.json rebuild: {e}", file=sys.stderr)


    # Each dashboard publishes from its own segmented source tree:
    # weekly_vegas/ (Vegas-vs-ECR signals) and waiver_wire/ (waiver board).
    # The published dist/ slugs are unchanged.
    for slug, source_dir in (("weekly-signals", WEEKLY_VEGAS), ("waiver-dashboard", WAIVER_WIRE)):
        source = source_dir / "index.html"
        target = DIST / slug
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target / "index.html")

    # v2 front end: the new layout over the same engine and data (app/v2/).
    # It is the site's front door: written to dist/index.html (root) and
    # dist/v2/index.html (old links), both from dist/classic/index.html.
    from build_v2_page import build as build_v2_page
    build_v2_page(DIST)

    # Internal math inspector (noindex, linked from no public page): the same
    # engine off-screen, every input and intermediate of the value math shown.
    from build_inspector_page import build as build_inspector_page
    build_inspector_page(DIST)

    print(f"Dashboard artifacts synced to app/trade-value-chart and dist{f' (build {tag})' if tag else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
