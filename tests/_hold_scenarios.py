"""Isolated source-hold and one-week-lag inputs for the JEG-1204 matrix.

The browser and Python reference must see the same inputs. Charts read their
native combos; projections read the canonical players' PPG fields, not their
saved fixture combos. History snapshots stay untouched, so a served source
can still be checked against its own saved week.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pipelines import value_check as vc
from pipelines import value_reference as ref

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
FIXTURE_ASSET = "assets/comparison-sources-data.json"
INDEX_ASSET = "assets/history/index.json"
ROOTS = tuple(vc.SOURCE_DERIVED)
SCORINGS = ("standard", "half_ppr", "ppr")
PREFIXES = {"standard": "standard", "half_ppr": "half", "ppr": "full"}


@dataclass
class Scenario:
    root: str
    week: int
    source_week: int
    held: bool
    lagging: bool
    fixture: dict
    players: dict
    index: dict
    overrides: dict[str, str]
    normalized_roots: tuple[str, ...] = ()


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline_history(index):
    """Newest complete common week with a complete prior for every root.

    The live fixture can itself be mid-transition. Starting there directly
    could make a supposed current-week hold actually exercise a lagging
    source, or exclude an unrelated lagging source from the baseline.
    """
    latest = max(record["week"] for record in index["served"].values()
                 if isinstance(record.get("week"), int))
    weeks = index.get("weeks") or {}
    loaded = {}

    def complete(week):
        if str(week) not in weeks or not set(ROOTS) <= set(weeks[str(week)].get("sources") or {}):
            return False
        path = ROOT / f"data/history/week-{week}.json"
        if not path.exists():
            return False
        if week not in loaded:
            loaded[week] = _read(path)
        sources = loaded[week].get("sources") or {}
        return all((sources.get(root) or {}).get("complete") is True for root in ROOTS)

    for week in sorted((int(key) for key in weeks if int(key) <= latest), reverse=True):
        if complete(week) and complete(week - 1):
            return week, loaded
    raise AssertionError("hold matrix needs consecutive complete saved weeks for every source root")


def _replace_chart_natives(fixture, root, entry):
    slug_of = {}
    for slug, key in sorted(fixture["player_keys"].items()):
        slug_of.setdefault(int(key), slug)
    section = fixture["sources"][root]
    for scoring, prefix in PREFIXES.items():
        natives = {slug_of[int(key)]: value for key, value in entry["natives"][scoring].items()
                   if int(key) in slug_of}
        combos = [combo for name, combo in section["combos"].items()
                  if name == f"{prefix}_12" or name.startswith(f"{prefix}_12_")]
        if not combos or not natives:
            raise AssertionError(f"{root}: no saved {scoring} natives or 12-team combo")
        for combo in combos:
            combo["native"] = dict(natives)
            # History saves the one-QB list only. Never overlay the current
            # week's superflex values onto that prior week's replay.
            combo.pop("native_superflex", None)
            # Keep the saved combo's single positive scale, but apply it to
            # the replay's natives. Otherwise the fixture itself would have
            # mismatched native/Indexed order before a guard even runs.
            scale = combo["fit"]["order_preserving_rescale"]
            factor = scale["factor"]
            combo["reindexed"] = {key: value * factor for key, value in natives.items()}
            uncalibrated = set(combo.get("not_on_espn") or []) & set(natives)
            if "not_on_espn" in combo:
                combo["not_on_espn"] = sorted(uncalibrated)
            scale["native_total"] = sum(value for key, value in natives.items() if key not in uncalibrated)
            scale["anchor_total"] = scale["native_total"] * factor
            scale["n_priced"] = len(natives) - len(uncalibrated)
            scale["n_uncalibrated"] = len(uncalibrated)
            combo["n"] = len(natives)
            combo["index_total"] = sum(combo["reindexed"].values())


def _replace_projection_players(players, root, entry):
    field = ref.PPG_FIELD[root]
    if entry.get("field") != field:
        raise AssertionError(f"{root}: unexpected saved projection field {entry.get('field')}")
    saved = entry["ppg"]
    for player in players["players"]:
        triple = saved.get(str(player["player_key"]))
        player[field] = (dict(zip(SCORINGS, triple)) if triple is not None else None)
        if root == "espn":
            # Old status flags cannot manufacture zero values for a player
            # absent from the replayed ESPN list.
            player["espn_status"] = "eligible" if triple is not None else "absent"


def _projection_browser_override(players, roots):
    """Replace changed PPG fields before product-data builds canonical rows.

    The engine reads an inline player island, so overriding players.json
    would do nothing. This served-only script edit preserves the island's
    other fields and runs the same product-data conversion as the real page.
    """
    fields = [ref.PPG_FIELD[root] for root in ref.PROJECTIONS if root in roots]
    if "espn" in roots:
        fields.append("espn_status")
    patches = {str(player["player_key"]): {key: player.get(key) for key in fields}
               for player in players["players"]}
    script = (DIST / "assets/product-data.js").read_text(encoding="utf-8")
    anchor = "    const playersPayload = loadPlayersInline();"
    if script.count(anchor) != 1:
        raise AssertionError("product-data inline player loading anchor moved")
    injection = ("\n    const holdScenarioPlayers = " + json.dumps(patches, separators=(",", ":")) + ";\n"
                 "    (playersPayload.players || []).forEach(player => {\n"
                 "      const patch = holdScenarioPlayers[String(player.player_key)];\n"
                 "      if (patch) Object.assign(player, patch);\n"
                 "    });")
    return script.replace(anchor, anchor + injection)


def source_scenario(root, *, held=False, lagging=False, corrupt=False):
    """Return fresh mutable copies and HTTP overrides for exactly one root.

    Call after ensure_built(). A common complete saved week is the matrix's
    baseline, including when the real build is mid-transition. Roots already
    on that week retain their exact served data and index version; other
    roots are restored from the saved week. A lag replay then serves just
    the target root's saved prior week. A hold is the exact
    validationHold shape isolate_hold writes (no hold_level means red).
    `corrupt` changes a single player's served native/PPG while retaining the
    index fingerprint, so week-history checks must reject it.
    """
    if root not in ROOTS:
        raise ValueError(f"unknown source root {root!r}")
    fixture = _read(DIST / FIXTURE_ASSET)
    players = _read(ROOT / "data/fixtures/current/players.json")
    index = _read(DIST / INDEX_ASSET)
    week, snapshots = _baseline_history(index)
    source_week = week - 1 if lagging else week
    for section in fixture["sources"].values():
        if isinstance(section, dict):
            section.pop("validationHold", None)
            section.pop("promotionHold", None)
    changed_projections = set()

    def restore_saved(source, saved_week):
        saved = snapshots[saved_week]["sources"][source]
        index["served"][source] = {"week": saved_week, "version": "snapshot",
                                   "fingerprint": saved["fingerprint"], "label_week": saved_week}
        section = fixture["sources"][source]
        section["week_designated"] = section["content_vintage"] = f"Week {saved_week}"
        if source in ref.PUBLISHED:
            _replace_chart_natives(fixture, source, saved)
        else:
            _replace_projection_players(players, source, saved)
            changed_projections.add(source)

    normalized = tuple(source for source in ROOTS if (index["served"].get(source) or {}).get("week") != week)
    for source in normalized:
        restore_saved(source, week)
    if lagging:
        restore_saved(root, source_week)
    if held:
        hold = {"reason": "chain hold: review hold", "week": week, "root": root, "stage": "review"}
        for section in vc.SOURCE_DERIVED[root]["sections"]:
            for key in (section, f"{section}_adjusted"):
                if isinstance(fixture["sources"].get(key), dict):
                    fixture["sources"][key]["validationHold"] = dict(hold)
    if corrupt:
        if root in ref.PUBLISHED:
            combos = fixture["sources"][root]["combos"]
            ppr = next(combo for name, combo in combos.items() if name.startswith("full_12"))
            key = max(ppr["native"], key=ppr["native"].get)
            for combo in combos.values():
                values = combo["native"]
                if key in values:
                    values[key] *= 1.07
        else:
            field = ref.PPG_FIELD[root]
            player = max(players["players"], key=lambda row: (row.get(field) or {}).get("ppr") or 0)
            player[field] = {scoring: value * 1.07 if value is not None else None
                             for scoring, value in player[field].items()}
            changed_projections.add(root)
    overrides = {FIXTURE_ASSET: json.dumps(fixture, separators=(",", ":")),
                 INDEX_ASSET: json.dumps(index, separators=(",", ":"))}
    if changed_projections:
        overrides["assets/product-data.js"] = _projection_browser_override(players, changed_projections)
    return Scenario(root, week, source_week, held, lagging, fixture, players, index, overrides, normalized)
