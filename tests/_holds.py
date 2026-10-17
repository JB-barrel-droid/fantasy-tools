"""Held sections in the published fixture, for tests that need an unheld baseline (JEG-569).

Jeremy (JEG-520): "hold a source, never take the whole site down".
Jeremy (JEG-569 part 2, 2026-10-12): "gray out the source, run no calcs on it,
gray out its derivatives. Where grayed out, remove their columns, values and
sections from the respective pages. No computation on old data."

A held source carries a validationHold flag but its combos are KEPT so the
engine includes the source in the pipeline (weights, pie, universe).
Tests that need an unheld baseline strip held sources from their own copy
of the fixture.

tests/test_seeded_hold_build.py seeds holds and runs these checks on the
held build, so a test that forgets to strip fails there.
"""
from __future__ import annotations

import copy

HOLD_FIELDS = ("validationHold", "promotionHold")


def held_source_roots(comparison: dict) -> set[str]:
    """Source roots whose section (or a derived section) carries a hold."""
    roots = set()
    for sec, section in ((comparison or {}).get("sources") or {}).items():
        if not isinstance(section, dict):
            continue
        hold = next((section[f] for f in HOLD_FIELDS if section.get(f)), None)
        if not hold:
            continue
        root = (hold.get("root") if isinstance(hold, dict) else None) or sec.removesuffix("_adjusted")
        roots.add(root)
    return roots


def without_held_sources(comparison: dict) -> dict:
    """A copy of the fixture without any held source sections."""
    out = copy.deepcopy(comparison)
    for root in held_source_roots(comparison):
        out["sources"].pop(root, None)
        out["sources"].pop(f"{root}_adjusted", None)
        # projection-derived vorp keys
        out["sources"].pop(f"{root}_vorp", None)
    return out


# Backward compat aliases (part 1 callers)
held_chart_roots = held_source_roots
without_held_charts = without_held_sources


# The fixed fixture (JEG-675, Jeremy 2026-10-16: "Give the tests a fixed, held-proof
# fixture"): the three current-week trade charts and the three projections are
# never held; CBS (a Week 5 chart in this fixture, one week behind) is always held.
# Pinned both ways, so a render test's premise (FantasyCalc, or 3+ compared charts)
# does not depend on which sources the fidelity pulse holds on a given day.
PINNED_OPEN = ("usatoday", "fantasypros", "fantasycalc", "espn", "cbsros", "razzball")
PINNED_HELD = ("cbs",)


def with_pinned_holds(comparison: dict) -> dict:
    """A copy of the fixture with PINNED_OPEN sources unheld and PINNED_HELD held; sections are kept."""
    out = copy.deepcopy(comparison)
    sources = out.get("sources") or {}
    for root in PINNED_OPEN:
        for sec in (root, f"{root}_adjusted", f"{root}_vorp"):
            section = sources.get(sec)
            if isinstance(section, dict):
                for field in HOLD_FIELDS:
                    section.pop(field, None)
    for root in PINNED_HELD:
        section = sources.get(root)
        if isinstance(section, dict):
            section["validationHold"] = {"reason": "chain hold: review hold", "root": root,
                                         "stage": "review", "week": (comparison.get("value_weeks") or {}).get("ecr")}
    return out


def pin_holds_in_dist(dist) -> None:
    """Rewrite a test's own copy of dist/assets/comparison-sources-data.json with the pinned holds."""
    import json
    from pathlib import Path
    path = Path(dist) / "assets" / "comparison-sources-data.json"
    path.write_text(json.dumps(with_pinned_holds(json.loads(path.read_text(encoding="utf-8"))),
                               separators=(",", ":")), encoding="utf-8")
