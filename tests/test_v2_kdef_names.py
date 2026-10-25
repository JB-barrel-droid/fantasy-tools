"""Build-time K/DEF name list for Find a trade's typed search (JEG-995): pipelines/build_v2_page.kdef_names_js.

The list is derived from data already in the repo: the 32 defenses are fixed, the kickers are the Sleeper identity base's
position-K players with a current team. Checks: 32 distinct defenses whose team codes are the 32 codes roster-paste.js
accepts; every kicker has a name and a team code roster-paste.js accepts; no duplicate names; the kickers equal the base's
(a kicker without a team is never offered); a missing base gives defenses only; every defense name appears in
roster-paste.js's own city and mascot table, so a defense is never invented.

Discrimination: test_guard_fails_on_broken_inputs feeds a base with a team-less kicker, a duplicated kicker and a defense
list with one team missing/duplicated, and requires each to be caught.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

PASTE = (ROOT / "app" / "v2" / "roster-paste.js").read_text(encoding="utf-8")


def load(js: str) -> dict:
    return json.loads(js.split("=", 1)[1].strip().rstrip(";"))


def paste_team_codes() -> set[str]:
    block = PASTE.split("var TEAM_ALIASES", 1)[1].split("};", 1)[0]
    return set(re.findall(r':\s*"([A-Z]{2,3})"', block))


def problems(data: dict, base: dict | None) -> list[str]:
    found = []
    codes = paste_team_codes()
    defenses = data["defenses"]
    if len(defenses) != 32 or len({d["team"] for d in defenses}) != 32 or {d["team"] for d in defenses} != codes:
        found.append(f"defenses are not the 32 distinct teams roster-paste.js knows: {len(defenses)}")
    for d in defenses:
        known = {f"{city.strip()} {mascot.lower()}" for city, mascot in
                 re.findall(r'"?([a-z ]+)"?:\s*"([A-Za-z0-9]+)"', PASTE.split("var CITY_TO_MASCOT", 1)[1].split("};", 1)[0])}
        known |= {name.rsplit(" ", 1)[0] for name in known}   # "los angeles rams rams" is written "los angeles rams"
        if d["name"].lower() not in known:
            found.append(f"defense {d['name']} is not a city + mascot in roster-paste.js")
    seen = set()
    for k in data["kickers"]:
        if not k.get("name") or not k.get("team") or build_v2_team(k["team"]) not in codes:
            found.append(f"kicker without a name or a known team: {k}")
        if k["name"] in seen:
            found.append(f"duplicate kicker {k['name']}")
        seen.add(k["name"])
    if base is not None:
        want = {p["name"] for p in base["by_sleeper_id"].values() if p.get("pos") == "K" and p.get("team")}
        if seen != want:
            found.append(f"kickers differ from the base: {sorted(seen ^ want)[:5]}")
    return found


def build_v2_team(team: str) -> str:
    return {"JAX": "JAC"}.get(team, team)


class KdefNamesTest(unittest.TestCase):
    def test_list_from_the_real_base(self):
        base = json.loads(build_v2_page.SLEEPER_BASE.read_text(encoding="utf-8"))
        data = load(build_v2_page.kdef_names_js())
        self.assertEqual(problems(data, base), [])
        self.assertGreaterEqual(len(data["kickers"]), 25)

    def test_missing_base_gives_defenses_only(self):
        data = load(build_v2_page.kdef_names_js(Path(tempfile.gettempdir()) / "no-such-sleeper-base.json"))
        self.assertEqual((len(data["defenses"]), data["kickers"]), (32, []))

    def test_guard_fails_on_broken_inputs(self):
        base = json.loads(build_v2_page.SLEEPER_BASE.read_text(encoding="utf-8"))
        good = load(build_v2_page.kdef_names_js())
        teamless = json.loads(json.dumps(good))
        teamless["kickers"].append({"name": "Free Agent Kicker", "team": ""})
        duplicated = json.loads(json.dumps(good))
        duplicated["kickers"].append(dict(good["kickers"][0]))
        short = json.loads(json.dumps(good))
        short["defenses"].pop()
        twice = json.loads(json.dumps(good))
        twice["defenses"][1]["team"] = twice["defenses"][0]["team"]
        invented = json.loads(json.dumps(good))
        invented["defenses"][0]["name"] = "Arizona Wildcats"
        extra_base = json.loads(json.dumps(base))
        extra_base["by_sleeper_id"]["999999"] = {"name": "Newly Signed Kicker", "pos": "K", "team": "KC"}
        for name, (data, b) in {"team-less kicker": (teamless, None), "duplicate kicker": (duplicated, None), "31 defenses": (short, None),
                                "two defenses one team": (twice, None), "invented defense": (invented, None),
                                "kicker missing from the list": (good, extra_base)}.items():
            with self.subTest(name):
                self.assertTrue(problems(data, b), f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
