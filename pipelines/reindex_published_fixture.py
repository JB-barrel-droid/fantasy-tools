#!/usr/bin/env python3
"""Re-index every published chart in the fixture from its own natives (JEG-482).

Indexed (methodology.md, The Three Views #3) is each published chart's native
values times ONE factor per combo, so the chart keeps its own ranking:

    factor = anchor_total(priced) / native_total(priced)

(reindex_comparison_section.order_preserving_rescale; the anchor is the
fixture's ESPN leg for the same combo, QB-suffix stripped as in the reindex
stage). The comparison chain runs this after promotion so every saved value
is indexed against the ESPN leg the site will show; it replaced the
re-translation stage, which wrote value-above-waivers translations into the
saved Indexed values.

Per published combo it rewrites `reindexed`, `index_total`, `n` and
`fit.order_preserving_rescale`, and drops what the removed layers left
behind: `fit.flex_aware_pie`, `fit.vorp_translation` and `translation`.
Natives, `native_superflex`, player keys and every other source are untouched.

Usage: python3 pipelines/reindex_published_fixture.py [--fixture PATH] [--players PATH] [--check]
--check writes nothing and exits 1 when any saved Indexed value differs from
the re-index by more than 1e-9 (relative).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from reindex_comparison_section import (  # noqa: E402
    POSITIONS, RESCALE_FIT_KEY, order_preserving_rescale, published_priced, resolve_anchor_combo,
)

PUBLISHED_SOURCES = ("fantasycalc", "usatoday", "fantasypros", "cbs")
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = REPO / "data" / "fixtures" / "current" / "players.json"
REMOVED_FIT_RECORDS = ("flex_aware_pie", "vorp_translation", "per_position_pie", "global")


def reindex_fixture(doc: dict, players: dict) -> dict:
    """Re-index the published combos of `doc` in place. Returns a summary."""
    pos_by_key = {p["player_key"]: p["pos"] for p in players["players"]}
    not_on_espn = {p["player_key"] for p in players["players"] if p.get("espn_status") == "absent"}
    fixture_keys = doc.get("player_keys", {}) or {}
    espn_combos = ((doc.get("sources") or {}).get("espn") or {}).get("combos") or {}
    summary = {"combos": [], "review_rows": 0}
    for source in PUBLISHED_SOURCES:
        sdata = (doc.get("sources") or {}).get(source)
        if not isinstance(sdata, dict):
            continue
        for combo_name, combo in (sdata.get("combos") or {}).items():
            native = combo.get("native") or {}
            if not native:
                continue
            anchor_name, _ = resolve_anchor_combo(combo_name, espn_combos)
            anchor_by_key = {}
            for slug, val in (espn_combos[anchor_name].get("values") or {}).items():
                key = fixture_keys.get(slug)
                if key is not None:
                    anchor_by_key[key] = val
            combo_keys = combo.get("player_keys") or {}
            key_by_slug = {s: combo_keys.get(s, fixture_keys.get(s)) for s in native}
            pos_by_slug = {s: pos_by_key[k] for s, k in key_by_slug.items() if k in pos_by_key}
            priced, review, anchor_of, chart_only = published_priced(
                native, key_by_slug, anchor_by_key, combo_name, not_on_espn)
            rescaled = order_preserving_rescale(native, priced, anchor_of, pos_by_slug, chart_only)
            if rescaled is None:
                raise SystemExit(f"reindex-fixture: {source}/{combo_name} cannot be indexed "
                                 "(no positive native or anchor total)")
            before = combo.get("reindexed") or {}
            combo["reindexed"] = rescaled["reindexed"]
            combo["index_total"] = rescaled["index_total"]
            # The fixture stores the combo total (promote sums the section's per-position n).
            combo["n"] = sum(t["n_priced"] for t in rescaled["index_total"].values())
            fit = combo.setdefault("fit", {})
            for name in REMOVED_FIT_RECORDS + tuple(POSITIONS):
                fit.pop(name, None)
            fit[RESCALE_FIT_KEY] = rescaled["fit"]
            combo.pop("translation", None)
            if chart_only:
                combo["not_on_espn"] = chart_only
            else:
                combo.pop("not_on_espn", None)
            changed = sum(
                1 for s, v in rescaled["reindexed"].items()
                if s not in before or abs(float(before[s]) - v) > 1e-9 * max(1.0, abs(v)))
            changed += sum(1 for s in before if s not in rescaled["reindexed"])
            summary["combos"].append({"source": source, "combo": combo_name,
                                      "anchor_combo": anchor_name,
                                      "factor": rescaled["fit"]["factor"],
                                      "n": len(rescaled["reindexed"]), "changed": changed})
            summary["review_rows"] += len(review)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fixture", default=str(FIXTURE))
    ap.add_argument("--players", default=str(PLAYERS))
    ap.add_argument("--check", action="store_true",
                    help="write nothing; exit 1 if any saved Indexed value would change")
    args = ap.parse_args(argv)
    path = Path(args.fixture)
    doc = json.loads(path.read_text(encoding="utf-8"))
    players = json.loads(Path(args.players).read_text(encoding="utf-8"))
    summary = reindex_fixture(doc, players)
    for row in summary["combos"]:
        print(f"  {row['source']}/{row['combo']}: factor {row['factor']:.6g} "
              f"(anchor {row['anchor_combo']}), {row['n']} players, {row['changed']} changed")
    if args.check:
        drift = [r for r in summary["combos"] if r["changed"]]
        if drift:
            print(f"reindex-fixture --check: {len(drift)} combo(s) differ from the re-index")
            return 1
        print("reindex-fixture --check: every saved Indexed value matches the re-index")
        return 0
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"re-indexed {len(summary['combos'])} published combos -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
