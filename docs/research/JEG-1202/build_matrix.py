#!/usr/bin/env python3
"""JEG-1202 audit: ESPN, Sleeper and Yahoo spellings per player_key (read-only).

Offline and deterministic. Reads only committed files, writes only under
docs/research/JEG-1202/ and tests/fixtures/JEG-1202/. No network, no Supabase,
no change to any canonical table, alias list, resolver or parser.

    PLAYER_ALIASES_SOURCE=json python3 docs/research/JEG-1202/build_matrix.py          # rewrite outputs
    PLAYER_ALIASES_SOURCE=json python3 docs/research/JEG-1202/build_matrix.py --check  # fail on drift

Evidence used (see README.md for what was excluded and why):
  canonical  data/inputs/players_identity_snapshot.json   public.players SELECT (player_key, full_name, position, gsis_id)
  Sleeper    data/inputs/sleeper_identity_base.json       Sleeper /players/nfl, meta.pulled_at
             data/inputs/sleeper_projection_idmap.csv     sleeper_id -> gsis -> player_key (JEG-949, exact ids only)
  ESPN       tests/fixtures/roster_paste/espn-team.txt, espn-matchup.txt (scrubbed real page pastes)
             tests/fixtures/league_paste/espn-league-rosters*.txt (a real league's rosters, team names scrubbed)
  Yahoo      tests/fixtures/roster_paste/yahoo-team.txt, yahoo-matchup.txt (scrubbed real page pastes)

A platform spelling is tied to a player_key only by one of these grounds, never
by the resolver under test and never by similarity:
  sleeper_idmap        sleeper_projection_idmap.csv status=matched (gsis chain)
  sleeper_gsis         Sleeper's own gsis_id equals exactly one snapshot gsis_id
  exact_canonical      paste spelling == one snapshot full_name at the pasted position, byte for byte
  sleeper_exact        paste spelling == one id-linked Sleeper name at the same position and NFL team
  verified_alias       paste spelling == an alias text in data/inputs/player_aliases.json, same position
  dst_mascot           D/ST or DEF row: exactly one snapshot DST whose last word is the pasted mascot
Grounds that disagree make the observation `conflict`; no ground makes it `ungrounded`.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_DOC = ROOT / "docs" / "research" / "JEG-1202"
OUT_FX = ROOT / "tests" / "fixtures" / "JEG-1202"

os.environ["PLAYER_ALIASES_SOURCE"] = "json"  # never read Supabase
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import canonical_players  # noqa: E402 -- the shared resolver, used read-only
import player_aliases  # noqa: E402

SNAPSHOT = "data/inputs/players_identity_snapshot.json"
SLEEPER_BASE = "data/inputs/sleeper_identity_base.json"
SLEEPER_IDMAP = "data/inputs/sleeper_projection_idmap.csv"
ALIASES = "data/inputs/player_aliases.json"

ESPN_FILES = [
    "tests/fixtures/roster_paste/espn-team.txt",
    "tests/fixtures/roster_paste/espn-matchup.txt",
    "tests/fixtures/league_paste/espn-league-rosters.txt",
    "tests/fixtures/league_paste/espn-league-rosters-split-record.txt",
]
YAHOO_FILES = [
    "tests/fixtures/roster_paste/yahoo-team.txt",
    "tests/fixtures/roster_paste/yahoo-matchup.txt",
]
# Matrix scope: fantasy-relevant canonical positions (logged pick, picks-log.md).
MATRIX_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")

POS_MAP = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "K": "K", "D/ST": "DST", "DEF": "DST"}
# Platform team codes -> the Sleeper base's codes, for the sleeper_exact ground only.
TEAM_FIX = {"WSH": "WAS", "JAC": "JAX", "LAR": "LA"}
TEAM_RE = re.compile(r"^[A-Z]{2,3}$")
ESPN_ROSTER_RE = re.compile(r"^([A-Z]{2,3}) (QB|RB|WR|TE|K|D/ST)$")
YAHOO_TEAM_RE = re.compile(r"^([A-Za-z]{2,3}) - (QB|RB|WR|TE|K|DEF)$")
YAHOO_CHROME = ("No new player Notes", "New Player Note", "Player Note", "Video Forecast")
YAHOO_STATUS_RE = re.compile(r"(?<=[a-z.])(Q|O|D|IR|PUP|NA|SUSP|NFI)$")
SUFFIX_RE = re.compile(r"\b(Jr\.?|Sr\.?|II|III|IV|V)$")


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def load_canonical():
    rows = json.loads(_read(SNAPSHOT))
    return {int(r["player_key"]): r for r in rows}


def registry(canon):
    # The snapshot has no `active` column; Registry treats every row as
    # inactive, so resolve_with_reason falls back to all candidates. The live
    # registry reads `active` from public.players (evidence gap in README.md).
    return canonical_players.load_registry(rows=list(canon.values()))


def resolver_result(reg, spelling, pos):
    key, reason = canonical_players.resolve_with_reason(spelling, position=pos, registry=reg)
    return key, reason


# ---------------------------------------------------------------- Sleeper links

def sleeper_links(canon):
    base = json.loads(_read(SLEEPER_BASE))
    by_gsis = defaultdict(list)
    for k, r in canon.items():
        if r.get("gsis_id"):
            by_gsis[r["gsis_id"]].append(k)
    idmap = {}
    with (ROOT / SLEEPER_IDMAP).open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            idmap[r["sleeper_id"]] = r
    links = []  # one per sleeper_id that links to a key
    excluded = []  # id links refused, for the gap inventory
    ids = sorted(set(base["by_sleeper_id"]) | set(idmap), key=lambda s: (len(s), s))
    for sid in ids:
        b = base["by_sleeper_id"].get(sid) or {}
        m = idmap.get(sid) or {}
        k_map = int(m["player_key"]) if m.get("status") == "matched" and m.get("player_key") else None
        g = b.get("gsis_id")
        k_gsis = by_gsis[g][0] if g and len(by_gsis.get(g, [])) == 1 else None
        name = b.get("name") or m.get("name")
        if k_gsis is not None and k_map is None:
            # The idmap's own rules win: a sleeper_id it marked conflict or
            # name_review is not linked; a gsis-only link must keep the last
            # name (sleeper_projection_idmap.py's name_review rule).
            if m.get("status") in ("conflict", "name_review"):
                excluded.append({"sleeper_id": sid, "name": name, "gsis_key": k_gsis,
                                 "why": f"idmap status {m['status']}"})
                k_gsis = None
            elif _last(name) != _last(canon[k_gsis]["full_name"]):
                excluded.append({"sleeper_id": sid, "name": name, "gsis_key": k_gsis,
                                 "why": "gsis-only link, last name differs"})
                k_gsis = None
        if k_map is None and k_gsis is None:
            continue
        links.append({
            "sleeper_id": sid,
            "name": name,
            "idmap_name": m.get("name") or None,
            "pos": (b.get("pos") or m.get("pos") or "").upper(),
            "team": b.get("team"),
            "active": b.get("active"),
            "key_idmap": k_map,
            "key_gsis": k_gsis,
            "conflict": k_map is not None and k_gsis is not None and k_map != k_gsis,
            "via": "+".join(x for x, v in (("idmap", k_map), ("gsis", k_gsis)) if v is not None),
        })
    return base["meta"], links, excluded


def _last(name):
    toks = canonical_players.norm_player_name(name or "").split(" ")
    return toks[-1] if toks else ""


# ---------------------------------------------------------------- paste extraction

def extract_espn(rel):
    lines = _read(rel).split("\n")
    out = []
    n = len(lines)
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        # Team page and league rosters: the name printed twice on one line.
        h = len(s) // 2
        if len(s) % 2 == 0 and h >= 3 and s[:h] == s[h:]:
            name = s[:h]
            nxt = lines[i + 1].strip() if i + 1 < n else ""
            m = ESPN_ROSTER_RE.match(nxt)
            if m:
                out.append(_obs("espn", rel, i, ln, name, m.group(1), m.group(2), "doubled+roster_line"))
                continue
            for j in range(i + 1, min(i + 6, n - 1)):
                t, p = lines[j].strip(), lines[j + 1].strip()
                if TEAM_RE.match(t) and p in POS_MAP:
                    out.append(_obs("espn", rel, i, ln, name, t, p, "doubled+team+pos"))
                    break
            continue
        # Matchup page: name, team code, position on three lines.
        if i + 2 < n and not TEAM_RE.match(s) and s not in POS_MAP and re.search(r"[a-z]", s):
            t, p = lines[i + 1].strip(), lines[i + 2].strip()
            if TEAM_RE.match(t) and p in POS_MAP:
                out.append(_obs("espn", rel, i, ln, s, t, p, "name+team+pos"))
    return out


def extract_yahoo(rel):
    lines = _read(rel).split("\n")
    out = []
    for i in range(len(lines) - 1):
        m = YAHOO_TEAM_RE.match(lines[i + 1].strip())
        if not m:
            continue
        s = lines[i].strip()
        notes = []
        changed = True
        while changed:
            changed = False
            for tail in YAHOO_CHROME:
                if s.endswith(tail):
                    s = s[: -len(tail)]
                    changed = True
        st = YAHOO_STATUS_RE.search(s)
        if st:
            notes.append(f"status_stripped:{st.group(1)}")
            s = s[: st.start()]
        out.append(_obs("yahoo", rel, i, lines[i], s.strip(), m.group(1).upper(), m.group(2),
                        "name+team-pos" + ("|" + "|".join(notes) if notes else "")))
    return out


def _obs(platform, rel, i, raw, spelling, team, pos, how):
    return {"platform": platform, "file": rel, "line": i + 1, "raw": raw.rstrip("\r"),
            "spelling": spelling, "team": team, "pos": POS_MAP[pos], "extracted_by": how}


# ---------------------------------------------------------------- grounding

def ground(o, canon, links, alias_entries):
    sp, pos = o["spelling"], o["pos"]
    hits = {}
    if pos == "DST":
        mascot = re.sub(r"\s*D/ST$", "", sp).strip()
        c = [k for k, r in canon.items() if r["position"] == "DST" and r["full_name"].split(" ")[-1] == mascot]
        if len(c) == 1:
            hits["dst_mascot"] = c[0]
        return hits
    c = [k for k, r in canon.items() if r["full_name"] == sp and r["position"] == pos]
    if len(c) == 1:
        hits["exact_canonical"] = c[0]
    team = TEAM_FIX.get(o["team"], o["team"])
    sl = {(l["key_idmap"] or l["key_gsis"]) for l in links
          if l["name"] == sp and l["pos"] == pos and (l["team"] or "") == team and not l["conflict"]}
    if len(sl) == 1:
        hits["sleeper_exact"] = sl.pop()
    al = [e for e in alias_entries if e["alias"] == sp and (e.get("pos") or "").upper() == pos]
    if len(al) == 1:
        hits["verified_alias"] = int(al[0]["player_key"])
    return hits


def tags_for(spelling, canonical_name, canon_forms):
    t = []
    if re.search(r"[.'\u2019/-]", spelling):
        t.append("punctuation")
    if SUFFIX_RE.search(spelling) or (canonical_name and SUFFIX_RE.search(canonical_name)):
        t.append("suffix")
    first = spelling.lower().split(" ")[0].replace(".", "")
    if first in canonical_players.NICKNAMES or (
            canonical_name and canonical_name.lower().split(" ")[0] in canonical_players.NICKNAMES):
        t.append("nickname")
    if len(canon_forms.get(canonical_players.norm_player_name(spelling), ())) > 1:
        t.append("collision")
    return t


# ---------------------------------------------------------------- build

def build():
    canon = load_canonical()
    reg = registry(canon)
    alias_entries = player_aliases.json_entries()
    meta, links, excluded = sleeper_links(canon)
    canon_forms = defaultdict(set)
    for k, r in canon.items():
        canon_forms[canonical_players.norm_player_name(r["full_name"])].add(k)

    obs = []
    for f in ESPN_FILES:
        obs += extract_espn(f)
    for f in YAHOO_FILES:
        obs += extract_yahoo(f)
    for o in obs:
        g = ground(o, canon, links, alias_entries)
        keys = set(g.values())
        o["grounds"] = g
        o["ground_status"] = "grounded" if len(keys) == 1 else ("conflict" if keys else "ungrounded")
        o["player_key"] = keys.pop() if len(keys) == 1 else None
        rk, rr = resolver_result(reg, o["spelling"], o["pos"])
        o["resolver"] = {"player_key": rk, "reason": rr}

    # per-key platform evidence
    per = defaultdict(lambda: {"sleeper": [], "espn": [], "yahoo": []})
    for l in links:
        keys = {k for k in (l["key_idmap"], l["key_gsis"]) if k is not None}
        for k in keys:
            per[k]["sleeper"].append(l)
    for o in obs:
        if o["player_key"] is not None:
            per[o["player_key"]][o["platform"]].append(o)

    sleeper_src = f"{SLEEPER_BASE} pulled_at {meta['pulled_at']}; {SLEEPER_IDMAP}"
    rows = []
    for k in sorted(canon):
        r = canon[k]
        if r["position"] not in MATRIX_POSITIONS:
            continue
        row = {"player_key": k, "canonical_full_name": r["full_name"], "position": r["position"],
               "gsis_id": r.get("gsis_id") or ""}
        # Sleeper
        sl = per[k]["sleeper"]
        names = sorted({l["name"] for l in sl if l["name"]})
        conflict = any(l["conflict"] for l in sl)
        if not sl:
            st = "missing"
        elif conflict:
            st = "link_conflict"
        elif len(names) != 1:
            st = "multiple"
        else:
            st = "same" if names[0] == r["full_name"] else "differs"
        row.update({
            "sleeper_status": st,
            "sleeper_spelling": " | ".join(names),
            "sleeper_ids": " ".join(l["sleeper_id"] for l in sl),
            "sleeper_link": " ".join(sorted({l["via"] for l in sl})),
            "sleeper_source": sleeper_src if sl else "",
        })
        row["sleeper_resolver"] = _resolver_cell(reg, names, r["position"], k)
        # ESPN / Yahoo
        for plat in ("espn", "yahoo"):
            ob = per[k][plat]
            sp = sorted({o["spelling"] for o in ob})
            if not ob:
                st = "missing"
            elif len(sp) != 1:
                st = "multiple"
            else:
                st = "same" if sp[0] == r["full_name"] else "differs"
            row[f"{plat}_status"] = st
            row[f"{plat}_spelling"] = " | ".join(sp)
            row[f"{plat}_ground"] = " ".join(sorted({g for o in ob for g in o["grounds"]}))
            row[f"{plat}_evidence"] = " ".join(f"{o['file']}:{o['line']}" for o in ob)
            row[f"{plat}_resolver"] = _resolver_cell(reg, sp, r["position"], k)
        rows.append(row)

    summary = summarize(rows, obs, links, meta, excluded, canon)
    cases = resolver_cases(rows, obs, links, canon, canon_forms, reg)
    return rows, obs, summary, cases


def _resolver_cell(reg, spellings, pos, key):
    cells = []
    for sp in spellings:
        rk, rr = resolver_result(reg, sp, pos)
        if rk == key:
            cells.append("ok")
        elif rk is None:
            cells.append(rr)
        else:
            cells.append(f"other_key:{rk}")
    return " | ".join(cells)


def summarize(rows, obs, links, meta, excluded, canon):
    def count(col):
        c = defaultdict(int)
        for r in rows:
            c[r[col]] += 1
        return dict(sorted(c.items()))

    by_pos = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for r in rows:
        for plat in ("sleeper", "espn", "yahoo"):
            by_pos[r["position"]][plat][r[f"{plat}_status"]] += 1
    resolver = defaultdict(lambda: defaultdict(int))
    for r in rows:
        for plat in ("sleeper", "espn", "yahoo"):
            for cell in filter(None, r[f"{plat}_resolver"].split(" | ")):
                resolver[plat][cell.split(":")[0]] += 1
    obs_status = defaultdict(lambda: defaultdict(int))
    for o in obs:
        obs_status[o["platform"]][o["ground_status"]] += 1
    return {
        "schema": "jeg1202-coverage-summary-v1",
        "matrix_positions": list(MATRIX_POSITIONS),
        "matrix_rows": len(rows),
        "sleeper_base_meta": meta,
        "sleeper_links": len(links),
        "sleeper_link_conflicts": sum(1 for l in links if l["conflict"]),
        "status_counts": {p: count(f"{p}_status") for p in ("sleeper", "espn", "yahoo")},
        "status_by_position": {p: {plat: dict(sorted(v.items())) for plat, v in d.items()}
                               for p, d in sorted(by_pos.items())},
        "resolver_on_grounded_spellings": {p: dict(sorted(v.items())) for p, v in sorted(resolver.items())},
        "paste_observations": {p: dict(sorted(v.items())) for p, v in sorted(obs_status.items())},
        "ungrounded_observations": sorted({(o["platform"], o["spelling"], o["pos"], o["team"],
                                           o["ground_status"], o["resolver"]["reason"], o["resolver"]["player_key"])
                                          for o in obs if o["ground_status"] != "grounded"}, key=str),
        "sleeper_links_refused": excluded,
        "suspected_duplicate_canonical_rows": duplicate_rows(links, canon),
        "resolver_misses_on_grounded": sorted(
            {(o["platform"], o["spelling"], o["pos"], o["player_key"], o["resolver"]["reason"],
              o["resolver"]["player_key"]) for o in obs
             if o["ground_status"] == "grounded" and o["resolver"]["player_key"] != o["player_key"]},
            key=str),
    }


def duplicate_rows(links, canon):
    """Snapshot rows with no gsis_id whose full_name is, byte for byte, the
    Sleeper spelling of a different, id-linked player_key at the same position.
    Evidence of a possible second row for one person; not proof."""
    out = []
    by_name = defaultdict(list)
    for k, r in canon.items():
        by_name[(r["full_name"], r["position"])].append(k)
    for l in links:
        k = l["key_idmap"] or l["key_gsis"]
        for d in by_name.get((l["name"], l["pos"]), []):
            if d != k and not canon[d].get("gsis_id"):
                out.append({"linked_key": k, "linked_full_name": canon[k]["full_name"],
                            "gsis_less_key": d, "gsis_less_full_name": canon[d]["full_name"],
                            "position": l["pos"], "sleeper_id": l["sleeper_id"], "via": l["via"]})
    return sorted(out, key=lambda x: x["linked_key"])


def resolver_cases(rows, obs, links, canon, canon_forms, reg):
    """Fixture cases with an independently grounded expectation, by category."""
    cases = []
    seen = set()

    def add(c):
        sig = (c["platform"], c["spelling"], c["pos"] or "")
        if sig in seen:
            return
        seen.add(sig)
        cases.append(c)

    # Paste observations (ESPN, Yahoo) with a ground.
    for o in obs:
        if o["ground_status"] != "grounded":
            continue
        full = canon[o["player_key"]]["full_name"]
        tags = tags_for(o["spelling"], full, canon_forms)
        if o["spelling"] != full:
            tags.append("source_disagreement")
        add({"platform": o["platform"], "spelling": o["spelling"], "pos": o["pos"],
             "expect_key": o["player_key"], "expect_reason": "dst" if o["pos"] == "DST" else "ok",
             "ground": sorted(o["grounds"]), "evidence": f"{o['file']}:{o['line']}",
             "tags": sorted(set(tags)) or ["plain"]})

    # Sleeper spellings that differ from canonical (id-grounded), plus a
    # sample of punctuation / suffix rows that match canonical.
    for l in sorted(links, key=lambda x: int(x["sleeper_id"])):
        k = l["key_idmap"] or l["key_gsis"]
        if l["conflict"] or not l["name"] or l["pos"] != canon[k]["position"]:
            continue
        full = canon[k]["full_name"]
        tags = tags_for(l["name"], full, canon_forms)
        if l["name"] != full:
            tags.append("source_disagreement")
        if l["name"] == full and not ({"punctuation", "suffix", "nickname", "collision"} & set(tags)):
            continue
        add({"platform": "sleeper", "spelling": l["name"], "pos": l["pos"],
             "expect_key": k, "expect_reason": "ok",
             "ground": [f"sleeper_{v}" for v in l["via"].split("+")],
             "evidence": f"{SLEEPER_BASE} sleeper_id {l['sleeper_id']}",
             "tags": sorted(set(tags))})

    # Collisions: snapshot names that normalize together. Without a position
    # the resolver must refuse; with one, the single row at that position wins.
    for form, keys in sorted(canon_forms.items()):
        if len(keys) < 2 or not any(canon[k]["position"] in MATRIX_POSITIONS for k in keys):
            continue
        ks = sorted(keys)
        ev = f"{SNAPSHOT} player_keys {ks}"
        add({"platform": "canonical", "spelling": canon[ks[0]]["full_name"], "pos": None,
             "expect_key": None, "expect_reason": "ambiguous", "ground": ["snapshot_collision"],
             "evidence": ev, "tags": ["collision"]})
        bypos = defaultdict(list)
        for k in ks:
            bypos[canon[k]["position"]].append(k)
        for pos, pk in sorted(bypos.items()):
            if pos in MATRIX_POSITIONS:
                add({"platform": "canonical", "spelling": canon[pk[0]]["full_name"], "pos": pos,
                     "expect_key": pk[0] if len(pk) == 1 else None,
                     "expect_reason": "ok" if len(pk) == 1 else "ambiguous",
                     "ground": ["snapshot_collision_position"], "evidence": ev, "tags": ["collision"]})

    # Unknowns: Sleeper players whose gsis is not in public.players (idmap
    # status gsis_not_in_players) and whose name matches no snapshot row.
    with (ROOT / SLEEPER_IDMAP).open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["status"] != "gsis_not_in_players":
                continue
            if canonical_players.norm_player_name(r["name"]) in canon_forms:
                continue
            add({"platform": "sleeper", "spelling": r["name"], "pos": r["pos"].upper(),
                 "expect_key": None, "expect_reason": "unmatched", "ground": ["idmap_gsis_not_in_players"],
                 "evidence": f"{SLEEPER_IDMAP} sleeper_id {r['sleeper_id']}", "tags": ["unknown"]})

    # Pin what the shared resolver does today. A case whose result differs
    # from its grounded expectation is a known gap, never a rewritten
    # expectation: fail_closed (no key) or other_key (a different row).
    for c in cases:
        c.pop("observed_resolver", None)
        rk, rr = resolver_result(reg, c["spelling"], c["pos"])
        if rk == c["expect_key"] and (c["expect_key"] is not None or rr == c["expect_reason"]):
            c["status"] = "pass"
        else:
            c["status"] = "known_gap"
            c["gap"] = "fail_closed" if rk is None else "other_key"
            c["observed"] = {"player_key": rk, "reason": rr}
    return cases


def render(rows, obs, summary, cases):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return {
        OUT_DOC / "coverage_matrix.csv": buf.getvalue(),
        OUT_DOC / "summary.json": json.dumps(summary, indent=1, ensure_ascii=False) + "\n",
        OUT_FX / "platform_observations.json": json.dumps(
            {"schema": "jeg1202-platform-observations-v1", "observations": obs},
            indent=1, ensure_ascii=False) + "\n",
        OUT_FX / "resolver_cases.json": json.dumps(
            {"schema": "jeg1202-resolver-cases-v1", "cases": cases}, indent=1, ensure_ascii=False) + "\n",
    }


def main(argv):
    outputs = render(*build())
    if "--check" in argv:
        bad = [str(p.relative_to(ROOT)) for p, txt in outputs.items()
               if not p.exists() or p.read_text(encoding="utf-8") != txt]
        if bad:
            print("drift: " + ", ".join(bad), file=sys.stderr)
            return 1
        print("no drift")
        return 0
    for p, txt in outputs.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
