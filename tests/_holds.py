"""Held sections in the published fixture, for tests that need an unheld baseline (JEG-569).

Jeremy (JEG-520): "hold a source, never take the whole site down". A held
published chart (USA Today, FantasyCalc, FantasyPros, CBS) is served from the
section of the last build the fidelity pulse or the value check did not hold
it on (pipelines/fidelity_hold.py, pipelines/value_check.py). Its Indexed
values tie to THAT build's anchor and its _adjusted section to THAT build's
fit cells, so a check that ties a chart to this build's anchor or cells reads
the fixture without its held charts: those were checked by the gate of the
build that made them. A held projection keeps this build's section
(players.json bakes it) and is never stripped.

tests/test_seeded_hold_build.py seeds holds and runs these checks on the
held build, so a test that forgets to strip fails there.
"""
from __future__ import annotations

import copy

PUBLISHED_CHARTS = ("usatoday", "fantasycalc", "fantasypros", "cbs")
HOLD_FIELDS = ("validationHold", "promotionHold")


def held_chart_roots(comparison: dict) -> set[str]:
    """Published charts whose section, or _adjusted section, carries a hold."""
    roots = set()
    for sec, section in ((comparison or {}).get("sources") or {}).items():
        if not isinstance(section, dict):
            continue
        hold = next((section[f] for f in HOLD_FIELDS if section.get(f)), None)
        if not hold:
            continue
        root = (hold.get("root") if isinstance(hold, dict) else None) or sec.removesuffix("_adjusted")
        if root in PUBLISHED_CHARTS:
            roots.add(root)
    return roots


def without_held_charts(comparison: dict) -> dict:
    """A copy of the fixture without held charts and their _adjusted sections."""
    out = copy.deepcopy(comparison)
    for root in held_chart_roots(comparison):
        out["sources"].pop(root, None)
        out["sources"].pop(f"{root}_adjusted", None)
    return out
