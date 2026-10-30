#!/usr/bin/env python3
"""JEG-1388 (part of JEG-1202): one name-alias list for the page's roster paste and the chat.

The roster paste (app/v2/roster-paste.js) and the chat connector's name match
(supabase/functions/mcp/names.ts) can't read pipelines/lib/player_aliases.py,
so a platform spelling that isn't the canonical name ("Zonovan Knight" for Bam
Knight, "Kenny Gainwell" for Kenneth Gainwell) reaches no player there. This
writes one list, from

  * the verified aliases (data/inputs/player_aliases.json, through lib/player_aliases), and
  * the JEG-1202 platform spellings (data/inputs/player_platform_spellings.json)
    that differ from the canonical name,

into a generated block in each of those two files, so both read the same rows:

    python3 pipelines/build_name_aliases.py          # rewrite both blocks
    python3 pipelines/build_name_aliases.py --check  # fail on drift

An alias is kept only when it names one player and no other player's own
name. Defences are left out (the paste matches them by city and mascot).
Offline; no value moves: an alias only lets a name reach the player it
already belongs to.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import player_aliases  # noqa: E402
from canonical_players import norm_player_name  # noqa: E402

SPELLINGS = "data/inputs/player_platform_spellings.json"
SNAPSHOT = "data/inputs/players_identity_snapshot.json"
TARGETS = {
    "app/v2/roster-paste.js": "  var NAME_ALIASES = [\n{rows}\n  ];",
    "supabase/functions/mcp/names.ts": "const NAME_ALIASES: ReadonlyArray<readonly [string, number]> = [\n{rows}\n];",
}
BEGIN = "// BEGIN GENERATED name aliases: python3 pipelines/build_name_aliases.py (JEG-1388). Do not edit."
END = "// END GENERATED name aliases"
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
DEFENCE = {"DST", "DEF", "D/ST"}


def plain(name):
    """The chat's names.ts tokens(): accents and punctuation off, a trailing suffix dropped."""
    text = unicodedata.normalize("NFD", str(name or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[.'’‘`´]", "", text)
    words = re.sub(r"[^a-z0-9]+", " ", text).split()
    kept = [w for w in words if w not in SUFFIXES]
    return " ".join(kept or words)


def _forms(name):
    return {plain(name), norm_player_name(name)}


def build():
    snapshot = json.loads((ROOT / SNAPSHOT).read_text(encoding="utf-8"))
    owner = defaultdict(set)  # name form -> player_keys whose own name has it
    for r in snapshot:
        for f in _forms(r["full_name"]):
            owner[f].add(int(r["player_key"]))
    canonical = {int(r["player_key"]): r for r in snapshot}

    candidates = []  # (alias, player_key, where)
    for e in player_aliases.json_entries():
        candidates.append((e["alias"], int(e["player_key"]), "verified alias"))
    for r in json.loads((ROOT / SPELLINGS).read_text(encoding="utf-8"))["rows"]:
        if not r["same_as_canonical"] and r["position"] not in DEFENCE:
            candidates.append((r["source_player_name"], int(r["player_key"]), r["source"]))

    by_form = defaultdict(set)
    for alias, key, _ in candidates:
        by_form[plain(alias)].add(key)
    kept, dropped = {}, []
    for alias, key, where in candidates:
        snap = canonical.get(key)
        if snap is None or snap["position"] in DEFENCE:
            dropped.append((alias, key, "not a priced-player row"))
            continue
        if plain(alias) == plain(snap["full_name"]):
            continue  # both matchers already reach it by the canonical name
        others = set().union(*(owner.get(f, set()) for f in _forms(alias))) - {key}
        if others:
            dropped.append((alias, key, f"another player's name ({sorted(others)})"))
        elif len(by_form[plain(alias)]) > 1:
            dropped.append((alias, key, f"names {sorted(by_form[plain(alias)])}"))
        else:
            kept.setdefault((plain(alias), key), alias)
    rows = sorted(((alias, key) for (_, key), alias in kept.items()), key=lambda r: (plain(r[0]), r[1]))
    return rows, dropped


def render(template, rows):
    lines = ",\n".join(f"  [{json.dumps(alias, ensure_ascii=False)}, {key}]" for alias, key in rows)
    if template.startswith("  "):
        lines = "\n".join("  " + ln for ln in lines.split("\n"))
    indent = "  " if template.startswith("  ") else ""
    return f"{indent}{BEGIN}\n{template.format(rows=lines)}\n{indent}{END}"


def rewrite(text, block):
    start = text.index(BEGIN)
    start = text.rindex("\n", 0, start) + 1
    end = text.index(END, start) + len(END)
    return text[:start] + block + text[end:]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail when a generated block drifts")
    args = ap.parse_args(argv)
    rows, dropped = build()
    drift = []
    for rel, template in TARGETS.items():
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        new = rewrite(text, render(template, rows))
        if new != text:
            if args.check:
                drift.append(rel)
            else:
                path.write_text(new, encoding="utf-8")
    if drift:
        print("drift (run python3 pipelines/build_name_aliases.py): " + ", ".join(drift))
        return 1
    print(f"{len(rows)} aliases, {len(dropped)} left out" + (" (no drift)" if args.check else ""))
    for alias, key, why in dropped:
        print(f"  left out {alias!r} -> {key}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
