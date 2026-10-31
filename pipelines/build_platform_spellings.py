#!/usr/bin/env python3
"""JEG-1202: the ESPN, Sleeper and Yahoo spelling of each player, as name-table rows.

Offline and deterministic. Reads the committed JEG-1202 audit outputs
(docs/research/JEG-1202/coverage_matrix.csv and
tests/fixtures/JEG-1202/platform_observations.json) and writes

  data/inputs/player_platform_spellings.json            one row per (source, norm_name, position)
  supabase/migrations/jeg1202_platform_spellings.sql    the same rows for public.player_name_aliases

    python3 pipelines/build_platform_spellings.py          # rewrite both
    python3 pipelines/build_platform_spellings.py --check  # fail on drift

Only spellings the audit tied to a player_key by an independent ground are
written (Sleeper: its id through sleeper_projection_idmap.csv or its own
gsis_id; ESPN/Yahoo: exact canonical text, an id-linked Sleeper name, a
verified alias or the one DST with that mascot). The resolver under test never
picks the key, and no spelling is made up: a player with no committed platform
text gets no row. Platform names supplement canonical identity; they never
replace public.players.full_name.

The migration is NOT APPLIED. It writes production data, so Jeremy decides
when it runs. Nothing in the repo reads these rows yet: lib/player_aliases
reads only source '*' curated rows, and the saver queue and the nightly
reconcile touch only open rows (unmatched, review, provisional), so applying it
moves no value.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from canonical_players import norm_player_name  # noqa: E402 -- the single normalization rule

MATRIX = "docs/research/JEG-1202/coverage_matrix.csv"
OBSERVATIONS = "tests/fixtures/JEG-1202/platform_observations.json"
OUT_JSON = "data/inputs/player_platform_spellings.json"
OUT_SQL = "supabase/migrations/jeg1202_platform_spellings.sql"
SCHEMA = "player-platform-spellings-v1"
SOURCES = ("sleeper", "espn", "yahoo")
GROUNDED = ("same", "differs", "multiple")
METHOD = {"sleeper": "platform:sleeper_id", "espn": "platform:paste", "yahoo": "platform:paste"}
VERIFIED_BY = "jeg1202-platform-audit"


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _paste_evidence(observations):
    """(platform, player_key, spelling) -> {"teams", "evidence"} for grounded paste text."""
    out = defaultdict(lambda: {"teams": set(), "evidence": set(), "grounds": set()})
    for o in observations:
        if o.get("ground_status") != "grounded" or not isinstance(o.get("player_key"), int):
            continue
        e = out[(o["platform"], o["player_key"], o["spelling"])]
        if o.get("team"):
            e["teams"].add(o["team"])
        e["evidence"].add(f"{o['file']}:{o['line']}")
        e["grounds"].update(o.get("grounds") or {})
    return out


def build():
    matrix = list(csv.DictReader(_read(MATRIX).splitlines()))
    paste = _paste_evidence(json.loads(_read(OBSERVATIONS))["observations"])
    rows = []
    for m in matrix:
        key = int(m["player_key"])
        pos = m["position"]
        for src in SOURCES:
            if m[f"{src}_status"] not in GROUNDED:
                continue
            for spelling in m[f"{src}_spelling"].split(" | "):
                spelling = spelling.strip()
                if src == "sleeper":
                    ids = m["sleeper_ids"].split()
                    row = {"source_player_id": ids[0] if len(ids) == 1 else None, "team": None,
                           "ground": f"sleeper_{m['sleeper_link']}",
                           "evidence": m["sleeper_source"]}
                else:
                    e = paste.get((src, key, spelling))
                    if e is None:
                        raise SystemExit(f"{src} {spelling!r} -> {key} is in the matrix but has no "
                                         "grounded observation; rebuild the audit first")
                    teams = sorted(e["teams"])
                    row = {"source_player_id": None, "team": teams[0] if len(teams) == 1 else None,
                           "ground": " ".join(sorted(e["grounds"])),
                           "evidence": " ".join(sorted(e["evidence"]))}
                rows.append({"source": src, "source_player_name": spelling,
                             "norm_name": norm_player_name(spelling), "position": pos,
                             "player_key": key, "canonical_full_name": m["canonical_full_name"],
                             "same_as_canonical": spelling == m["canonical_full_name"], **row})
    rows.sort(key=lambda r: (SOURCES.index(r["source"]), r["norm_name"], r["position"], r["player_key"]))

    # The table's grain is (source, norm_name, position). Two players that
    # share it can't both be stored there, so neither is: a row that picked
    # one would be a guess.
    by_grain = defaultdict(list)
    for r in rows:
        by_grain[(r["source"], r["norm_name"], r["position"])].append(r)
    kept, held = [], []
    for grain_rows in by_grain.values():
        keys = {r["player_key"] for r in grain_rows}
        if len(keys) > 1:
            held.extend(grain_rows)
        else:
            kept.append(grain_rows[0])
    kept.sort(key=lambda r: (SOURCES.index(r["source"]), r["norm_name"], r["position"]))
    held.sort(key=lambda r: (SOURCES.index(r["source"]), r["norm_name"], r["position"], r["player_key"]))
    return kept, held


def render_json(rows, held):
    counts = {s: sum(1 for r in rows if r["source"] == s) for s in SOURCES}
    differs = {s: sum(1 for r in rows if r["source"] == s and not r["same_as_canonical"]) for s in SOURCES}
    doc = {
        "schema": SCHEMA,
        "about": ("Each player's ESPN, Sleeper and Yahoo spelling, keyed by public.players "
                  "player_key, from the JEG-1202 audit's grounded evidence. Generated by "
                  "pipelines/build_platform_spellings.py; do not edit by hand. Mirrors "
                  "supabase/migrations/jeg1202_platform_spellings.sql. A spelling that "
                  "two players share at one position is held, not stored."),
        "built_from": [MATRIX, OBSERVATIONS],
        "counts": counts,
        "differs_from_canonical": differs,
        "held_shared_spellings": [
            {k: r[k] for k in ("source", "source_player_name", "position", "player_key")} for r in held],
        "rows": rows,
    }
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def _q(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def render_sql(rows):
    values = ",\n".join(
        "    (" + ", ".join(_q(r[k]) for k in ("source", "source_player_name", "norm_name", "position",
                                                "source_player_id", "player_key", "team"))
        + ", " + _q(METHOD[r["source"]]) + ", " + _q(f"{r['ground']}; {r['evidence']}") + ")"
        for r in rows)
    return f"""-- JEG-1202: store each player's ESPN, Sleeper and Yahoo spelling in
-- public.player_name_aliases, keyed by player_key, with where it came from.
--
-- NOT APPLIED. Production write: Jeremy decides when it runs on
-- iskiybsimubiujwuchsl. Generated by pipelines/build_platform_spellings.py from
-- the JEG-1202 audit (docs/research/JEG-1202/); do not edit by hand. The same
-- rows are in data/inputs/player_platform_spellings.json.
--
-- {len(rows)} rows: source 'sleeper' (method platform:sleeper_id, the Sleeper id
-- in source_player_id), 'espn' and 'yahoo' (method platform:paste, from scrubbed
-- page pastes). status 'verified', confidence 1. notes holds the ground and the
-- evidence (file:line, or the Sleeper pull and id map).
--
-- No value moves: lib/player_aliases reads only source '*' curated rows, and
-- the saver queue and nightly reconcile change only open rows. An existing
-- row at the same (source, norm_name, position) is left as it is when it names
-- the same player_key; when it names another player the whole migration stops,
-- because that is a disagreement to look at, not to overwrite.
-- Written for after JEG-1351: no row points at 4653, 4655 or 4660.

begin;

create temporary table jeg1202_platform_rows (
    source text, source_player_name text, norm_name text, position text,
    source_player_id text, player_key bigint, team text, method text, notes text
) on commit drop;

insert into jeg1202_platform_rows values
{values};

do $$
declare
    missing text;
    clash text;
begin
    select string_agg(r.player_key::text, ', ') into missing
    from jeg1202_platform_rows r
    left join public.players p on p.player_key = r.player_key
    where p.player_key is null;
    if missing is not null then
        raise exception 'jeg1202: player_key not in public.players: %', missing;
    end if;

    select string_agg(format('%s %s %s: table %s, audit %s', a.source, a.norm_name, a.position,
                             coalesce(a.player_key::text, 'null'), r.player_key), '; ') into clash
    from jeg1202_platform_rows r
    join public.player_name_aliases a
      on a.source = r.source and a.norm_name = r.norm_name and a.position = r.position
    where a.player_key is distinct from r.player_key;
    if clash is not null then
        raise exception 'jeg1202: existing rows name another player: %', clash;
    end if;
end $$;

insert into public.player_name_aliases
    (source, source_player_name, norm_name, position, source_player_id, player_key,
     status, method, confidence, team, verified_at, verified_by, notes)
select r.source, r.source_player_name, r.norm_name, r.position, r.source_player_id, r.player_key,
       'verified', r.method, 1, r.team, now(), {_q(VERIFIED_BY)}, r.notes
from jeg1202_platform_rows r
on conflict (source, norm_name, position) do nothing;

commit;
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail when the committed files drift")
    args = ap.parse_args(argv)
    rows, held = build()
    outputs = {OUT_JSON: render_json(rows, held), OUT_SQL: render_sql(rows)}
    drift = []
    for rel, text in outputs.items():
        path = ROOT / rel
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                drift.append(rel)
        else:
            path.write_text(text, encoding="utf-8")
    if drift:
        print("drift (run python3 pipelines/build_platform_spellings.py): " + ", ".join(drift))
        return 1
    print(f"{len(rows)} rows, {len(held)} held" + (" (no drift)" if args.check else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
