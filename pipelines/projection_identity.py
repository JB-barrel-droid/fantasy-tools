#!/usr/bin/env python3
"""Snapshot identity shared by players.json and the projection sections.

The browser prices ESPN, CBS ROS and Razzball from players.json (baked by
bake_players.py); the main table and the chart read the chain-built fixture
sections. Both must come from the very same snapshot. A date cannot tell two
snapshots apart: on 2026-10-08 CBS ROS was saved at 08:48 and again at 13:54
with the same cbs_snapshot_date and different numbers, the chain rebuilt the
section from the 13:54 save while players.json still held the 08:48 one, and
tests.test_cbsros_8t_qb failed in every combo (GAP-BAKE-ON-CHANGE).

The identity is a content hash of the exact input file:
  - ESPN: sha256 of data/inputs/espn_projections.csv (the file the bake and
    the 12 ESPN DDF legs both read; the legs already record it as
    inputs.espn_csv_sha256);
  - CBS ROS / Razzball: sha256 of the snapshot's vintage_date plus its rows
    in canonical form (sorted), so a re-import of the same Supabase rows in a
    different order is the same snapshot and any changed value is not.

bake_players.py writes it to players.json meta (``<prefix>_snapshot_id``);
the leg builders record it per leg and the section builders copy it to
``sources.<source>.snapshot_id``. The chain holds a source whose snapshot id
differs from players.json's (isolated: last good section kept).

CLI (rebuild-chain.yml, "Decide whether to bake players.json"):
  projection_identity.py decide --espn-csv F --cbsros-snapshot F --razzball-snapshot F
(CBS ROS / Razzball default to the chain's own latest imported snapshot)
prints one line per source, then ``bake=true|false`` and the input paths
(also to $GITHUB_OUTPUT, for the bake step).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"

# players.json meta key per projection source (the date keys are the older
# espn_snapshot / cbsros_snapshot / rz_snapshot; these sit beside them).
META_KEYS = {
    "espn": "espn_snapshot_id",
    "cbsros": "cbsros_snapshot_id",
    "razzball": "rz_snapshot_id",
}
SOURCES = tuple(META_KEYS)


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def csv_id(path) -> str:
    """Identity of a CSV input: its exact bytes (= the legs' espn_csv_sha256)."""
    return _sha(Path(path).read_bytes())


def snapshot_doc_id(doc: dict) -> str:
    """Identity of a parsed snapshot: vintage_date + rows, order-free."""
    rows = sorted(json.dumps(r, sort_keys=True, separators=(",", ":"))
                  for r in (doc.get("rows") or []))
    canon = json.dumps({"vintage_date": doc.get("vintage_date"), "rows": rows},
                       sort_keys=True, separators=(",", ":"))
    return _sha(canon.encode())


def file_id(path) -> str:
    """Identity of a projection input file (.csv or snapshot .json)."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return csv_id(path)
    return snapshot_doc_id(json.loads(path.read_text(encoding="utf-8")))


def espn_id_from_sha256(hexdigest: str | None) -> str | None:
    """A leg's inputs.espn_csv_sha256 as an identity (None stays None)."""
    return f"sha256:{hexdigest}" if hexdigest else None


def players_ids(players_path=PLAYERS) -> dict:
    """{source: snapshot id} from players.json meta (None when absent)."""
    try:
        meta = json.loads(Path(players_path).read_text(encoding="utf-8")).get("meta") or {}
    except (OSError, ValueError):
        meta = {}
    return {s: meta.get(k) for s, k in META_KEYS.items()}


def mismatch(source: str, snapshot_id: str | None, players_path=PLAYERS) -> str | None:
    """Why `source` built from `snapshot_id` would disagree with players.json, or None."""
    baked = players_ids(players_path).get(source)
    if not snapshot_id:
        return f"{source}: no snapshot id for the section's input"
    if not baked:
        return (f"{source}: players.json has no {META_KEYS[source]} (baked before "
                "snapshot ids); the section waits for a bake")
    if baked != snapshot_id:
        return (f"{source}: snapshot {snapshot_id[:19]} != players.json "
                f"{META_KEYS[source]} {baked[:19]}; the section waits for a bake "
                "from the same snapshot")
    return None


def decide(inputs: dict, force: bool, players_path=PLAYERS) -> tuple[bool, list[str]]:
    """Whether the chain must bake players.json before it builds sections.

    inputs: {source: input file path or None}. A source whose input differs
    from what players.json was baked from needs a bake; so does a forced run
    (the daily bake). A missing input cannot be compared and does not force a
    bake (that source's chain fails or holds on its own).
    """
    baked = players_ids(players_path)
    lines, drift = [], False
    for source in SOURCES:
        path = inputs.get(source)
        if not path:
            lines.append(f"{source}: no input to compare")
            continue
        current = file_id(path)
        same = current == baked.get(source)
        drift = drift or not same
        lines.append(f"{source}: input {current[:19]} players.json "
                     f"{(baked.get(source) or 'none')[:19]} -> "
                     f"{'same' if same else 'CHANGED'}")
    return (force or drift), lines


def latest_snapshot(source: str, repo=ROOT):
    """The snapshot the chain builds `source` from (its own lookup)."""
    import rebuild_comparison_chain  # noqa: PLC0415 - imports this module
    return rebuild_comparison_chain.find_latest_snapshot(Path(repo), source)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decide")
    d.add_argument("--espn-csv", default="")
    d.add_argument("--cbsros-snapshot", default="")
    d.add_argument("--razzball-snapshot", default="")
    d.add_argument("--force", default="false")
    d.add_argument("--players", default=str(PLAYERS))
    i = sub.add_parser("id")
    i.add_argument("path")
    args = ap.parse_args(argv)
    if args.cmd == "id":
        print(file_id(args.path))
        return 0
    inputs = {"espn": args.espn_csv or str(ROOT / "data" / "inputs" / "espn_projections.csv"),
              "cbsros": args.cbsros_snapshot or latest_snapshot("cbsros"),
              "razzball": args.razzball_snapshot or latest_snapshot("razzball")}
    inputs = {k: (str(v) if v else None) for k, v in inputs.items()}
    bake, lines = decide(inputs, force=args.force == "true", players_path=args.players)
    for line in lines:
        print(line)
    outputs = {"bake": "true" if bake else "false",
               "espn_csv": inputs["espn"] or "",
               "cbsros_snapshot": inputs["cbsros"] or "",
               "razzball_snapshot": inputs["razzball"] or ""}
    for k, v in outputs.items():
        print(f"{k}={v}")
    if args.force == "true":
        print("(forced: bake_players=true)")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.writelines(f"{k}={v}\n" for k, v in outputs.items())
    return 0


if __name__ == "__main__":
    sys.exit(main())
