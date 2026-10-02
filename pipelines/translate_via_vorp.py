#!/usr/bin/env python3
"""JEG-64: substitute VORP-translated values from Supabase into as-published
comparison combos, replacing the quantile-mapped reindexed values.

Background: the quantile-mapping reindex (pipelines/reindex_comparison_section.py)
maps as-published trade charts onto the anchor scale, but it compresses real
published judgments (USA Today RB peak 48.58 against the 70.0 anchor -- JEG-32).
JEG-62/63 translated those sources through the VORP methodology and stored
per-player values in Supabase (publisher_translated_values, JEG-62 schema).

This stage substitutes translated values for the quantile-mapped ones, per
combo, on the as-published sources only (usatoday, fantasypros, fantasycalc,
cbs). It is FAIL-SAFE by design (acceptance #3):

* a Supabase grain (source, scoring, league_teams, week, season) with zero
  rows -> the combo keeps its reindexed values; provenance records
  "reindex-fallback".
* any Supabase transport error (network, auth, missing table) -> same
  fallback; never a crash. The comparison chain never halts on this stage.

Identity joins on the numeric player_key, never on raw slug strings.
Resolution order per slug: combo-level player_keys (if non-empty), then the
fixture-level player_keys map, then the players.json name map.

Operates on either:
  (a) the fixture (data/fixtures/current/comparison-sources-data.json;
      shape {sources: {<source>: {combos: {...}}}}), or
  (b) a reindexed section artifact (shape {source_key, combos: {...}}),
      e.g. the file reindex_comparison_section.py produces inside the
      comparison chain, before review.

Every touched combo gains a `translation` provenance block:
  {"method": "vorp-supabase" | "reindex-fallback",
   "grain": {"source","scoring","league_teams","week","season"},
   "n_translated": <int>, "n_fallback_reindex": <int>, "n_total": <int>}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

AS_PUBLISHED_SOURCES = ("usatoday", "fantasypros", "fantasycalc", "cbs")

# Fixture combo prefixes -> Supabase scoring names.
SCORING_PREFIX = {"half": "half_ppr", "full": "ppr", "standard": "standard"}
COMBO_RE = re.compile(r"^(half|full|standard)_(\d+)(?:_qb\d+)?$")


def parse_combo(combo_name):
    """Parse 'half_12' / 'half_12_qb1' -> ('half_ppr', 12). None if unknown."""
    m = COMBO_RE.match(combo_name)
    if not m:
        return None
    return SCORING_PREFIX[m.group(1)], int(m.group(2))


def _sb():
    """Supabase REST client via the stored credential (surrogate flow)."""
    bin_dir = Path.home() / "workspace" / "skills" / "supabase-football-signal" / "bin"
    if str(bin_dir) not in sys.path:
        sys.path.insert(0, str(bin_dir))
    import sbclient  # noqa: E402
    return sbclient


def fetch_translated(source, scoring, teams, week, season, sb=None):
    """Read the translated grain from Supabase.

    Returns {player_key (str): translated_value}. Raises on transport error --
    the caller decides the fail-safe policy (default: fall back to reindex).
    """
    sbclient = sb or _sb()
    params = (
        "publisher_translated_values"
        f"?source=eq.{source}&scoring=eq.{scoring}"
        f"&league_teams=eq.{teams}&week=eq.{week}&season=eq.{season}"
        "&select=player_key,translated_value"
    )
    rows = sbclient.get(params)
    out = {}
    for r in rows:
        key = str(r["player_key"])
        val = r["translated_value"]
        if val is None:
            continue
        out[key] = float(val)
    return out


def _key_maps(fixture_doc):
    """Build the two slug->key resolution maps from the fixture + players."""
    fixture_keys = fixture_doc.get("player_keys", {}) or {}
    players_path = REPO / "data" / "fixtures" / "current" / "players.json"
    name_keys = {}
    try:
        players = json.loads(players_path.read_text(encoding="utf-8"))
        for p in players.get("players", []):
            name = p.get("name")
            key = p.get("player_key")
            if name and key is not None:
                name_keys[name.strip().lower()] = str(key)
    except (OSError, ValueError):
        pass  # name map is a last-resort fallback; absence is fine
    return fixture_keys, name_keys


def resolve_key(slug, combo_keys, fixture_keys, name_keys):
    """Slug -> numeric player_key (str), fail-closed to None."""
    key = (combo_keys or {}).get(slug)
    if key is not None:
        return str(key)
    key = (fixture_keys or {}).get(slug)
    if key is not None:
        return str(key)
    return (name_keys or {}).get(slug.strip().lower())


def apply_combo(source, combo_name, combo, translated, fixture_keys, name_keys):
    """Substitute translated values into one combo. Returns a report dict."""
    grain = parse_combo(combo_name)
    report = {"source": source, "combo": combo_name, "method": None,
              "n_translated": 0, "n_fallback_reindex": 0, "n_total": 0}
    reindexed = combo.get("reindexed")
    if not isinstance(reindexed, dict) or not reindexed:
        report["method"] = "reindex-fallback"
        report["reason"] = "no reindexed values to translate"
        combo["translation"] = _provenance(report, grain)
        return report
    combo_keys = combo.get("player_keys", {}) or {}
    for slug, val in list(reindexed.items()):
        report["n_total"] += 1
        key = resolve_key(slug, combo_keys, fixture_keys, name_keys)
        tval = translated.get(key) if key is not None else None
        if tval is None:
            report["n_fallback_reindex"] += 1
            continue
        reindexed[slug] = tval
        report["n_translated"] += 1
    report["method"] = "vorp-supabase" if report["n_translated"] else "reindex-fallback"
    combo["translation"] = _provenance(report, grain)
    if report["method"] == "vorp-supabase":
        # Keep the superseded quantile fit record (history) and document the
        # substitution alongside it, so downstream readers don't mistake the
        # stored reindexed values for bucket-scaled ones.
        fit = combo.setdefault("fit", {})
        fit["vorp_translation"] = {
            "method": "vorp-supabase",
            "supersedes": "flex_aware_pie quantile mapping",
            "grain": combo["translation"]["grain"],
            "n_translated": report["n_translated"],
            "n_fallback_reindex": report["n_fallback_reindex"],
        }
    return report


def _qb_divergent_siblings(source, sdata):
    """Find qb-split combos whose natives diverge from the canonical one.

    Some sources publish per-QB-config variants (fantasycalc ..._qb1/_qb2).
    The JEG-62 Supabase grain (source, scoring, league_teams, week, season)
    has no qb dimension, and resolve_combo_key treats the first-sorted
    variant (qb1) as canonical. When a sibling's natives differ materially
    from the canonical variant's, a single grain must not serve both --
    the sibling falls back to the reindex. Data-driven: no per-source
    branching. Returns {combo_name: reason} for combos that must fall back.
    """
    by_base = {}
    for combo_name, combo in (sdata.get("combos") or {}).items():
        m = re.match(r"^((?:half|full|standard)_\d+)_qb\d+$", combo_name)
        if not m or not isinstance(combo, dict):
            continue
        by_base.setdefault(m.group(1), []).append(combo_name)
    must_fallback = {}
    for base, names in by_base.items():
        if len(names) < 2:
            continue
        names = sorted(names)
        canon = (sdata["combos"][names[0]].get("native") or {})
        for other in names[1:]:
            native = (sdata["combos"][other].get("native") or {})
            if set(native) != set(canon):
                must_fallback[other] = (
                    "qb-split natives cover different players than the "
                    "canonical variant; grain has no qb dimension")
                continue
            maxd = max((abs(float(native[k]) - float(canon[k]))
                        for k in canon), default=0.0)
            if maxd > 1e-9:
                must_fallback[other] = (
                    f"qb-split natives diverge from canonical {names[0]} "
                    f"(max|d|={maxd:.1f}); grain has no qb dimension")
    return must_fallback


def _provenance(report, grain):
    scoring, teams = grain if grain else (None, None)
    return {
        "method": report["method"],
        "grain": {"source": report["source"], "scoring": scoring,
                  "league_teams": teams, "week": report.get("week"),
                  "season": report.get("season")},
        "n_translated": report["n_translated"],
        "n_fallback_reindex": report["n_fallback_reindex"],
        "n_total": report["n_total"],
        "note": "Translated values from publisher_translated_values (JEG-62); "
                "reindexed quantile values kept as fail-safe fallback.",
    }


def translate_document(doc, week=4, season=2026, sb=None, strict=False):
    """Substitute translated values across every eligible combo in doc.

    doc is the parsed fixture or section artifact (mutated in place).
    Never raises in fail-safe mode (strict=False): any Supabase error keeps
    the reindexed values and records reindex-fallback provenance. Returns a
    summary dict.
    """
    fixture_keys, name_keys = _key_maps(doc if "sources" in doc else {})
    # For section artifacts the fixture-level map still helps identity.
    if not fixture_keys:
        try:
            fixture_keys = json.loads(
                (REPO / "data" / "fixtures" / "current"
                 / "comparison-sources-data.json").read_text(encoding="utf-8")
            ).get("player_keys", {}) or {}
        except (OSError, ValueError):
            fixture_keys = {}

    jobs = []  # (source, combo_name, combo, translated_or_error)
    reports = []
    sources = doc["sources"] if "sources" in doc else {doc.get("source_key"): doc}
    for source, sdata in (sources or {}).items():
        if source not in AS_PUBLISHED_SOURCES or not isinstance(sdata, dict):
            continue
        qb_guarded = _qb_divergent_siblings(source, sdata)
        for combo_name, combo in (sdata.get("combos") or {}).items():
            grain = parse_combo(combo_name)
            if grain is None or not isinstance(combo, dict):
                continue
            if combo_name in qb_guarded:
                # Fail-safe: a single non-qb-aware grain must not serve a
                # diverging qb variant. Record the fallback explicitly.
                report = {"source": source, "combo": combo_name,
                          "method": "reindex-fallback",
                          "n_translated": 0,
                          "n_fallback_reindex": len(combo.get("reindexed") or {}),
                          "n_total": len(combo.get("reindexed") or {}),
                          "week": week, "season": season,
                          "reason": qb_guarded[combo_name]}
                combo["translation"] = _provenance(report, grain)
                combo["translation"]["note"] = (
                    qb_guarded[combo_name] + ". Quantile reindex kept as "
                    "fail-safe fallback. See JEG-70.")
                # Strip any stale fit record from an earlier mis-application.
                (combo.get("fit") or {}).pop("vorp_translation", None)
                reports.append(report)
                continue
            scoring, teams = grain
            try:
                translated = fetch_translated(source, scoring, teams, week, season, sb=sb)
            except Exception as e:  # fail-safe: fall back, never halt
                if strict:
                    raise
                jobs.append((source, combo_name, combo, e))
                continue
            jobs.append((source, combo_name, combo, translated))

    for source, combo_name, combo, translated in jobs:
        if isinstance(translated, Exception):
            report = {"source": source, "combo": combo_name,
                      "method": "reindex-fallback",
                      "n_translated": 0, "n_fallback_reindex": 0, "n_total": 0,
                      "reason": f"supabase error: {translated}"}
            combo["translation"] = _provenance({**report, "week": week,
                                               "season": season},
                                              parse_combo(combo_name))
            reports.append(report)
            continue
        report = apply_combo(source, combo_name, combo, translated,
                             fixture_keys, name_keys)
        report["week"] = week
        report["season"] = season
        # Empty grain = same fail-safe path: keep reindexed, mark fallback.
        if not translated:
            combo["translation"] = _provenance({**report, "week": week,
                                               "season": season},
                                              parse_combo(combo_name))
        reports.append(report)
    translated_total = sum(r["n_translated"] for r in reports)
    combos_vorp = sum(1 for r in reports if r["method"] == "vorp-supabase")
    combos_fallback = sum(1 for r in reports if r["method"] == "reindex-fallback")
    return {"week": week, "season": season, "reports": reports,
            "values_translated": translated_total,
            "combos_vorp_supabase": combos_vorp,
            "combos_reindex_fallback": combos_fallback}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Substitute VORP-translated Supabase values into "
                    "as-published comparison combos (fail-safe fallback to reindex).")
    ap.add_argument("--fixture", default=None,
                    help="Fixture path (default: data/fixtures/current/comparison-sources-data.json). "
                         "Use --section for a reindexed section artifact instead.")
    ap.add_argument("--section", default=None,
                    help="Reindexed section artifact path (mutated in place).")
    ap.add_argument("--week", type=int, default=4)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--out", default=None, help="Output path (default: in place).")
    ap.add_argument("--strict", action="store_true",
                    help="Raise on Supabase errors instead of falling back.")
    args = ap.parse_args(argv)

    path = Path(args.section or args.fixture or
                REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    summary = translate_document(doc, week=args.week, season=args.season, strict=args.strict)
    out_path = Path(args.out) if args.out else path
    out_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "reports"}))
    for r in summary["reports"]:
        print(f"  {r['source']}/{r['combo']}: {r['method']} "
              f"translated={r['n_translated']} fallback={r['n_fallback_reindex']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
