"""Offline search-only snapshot; never changes the priced players fixture.

Existing snapshots are dated identity evidence, not a claim of current registry
freshness. No lifecycle events are inferred. Duplicate-key redirect claims are
retained as pending evidence, never activated from migration text or names.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile

if __package__:
    from .lib.searchable_identity_eligibility import build_searchable_identities
else:
    from lib.searchable_identity_eligibility import build_searchable_identities

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "app/trade-value-chart/assets/jeg1505-search-identities.json"


def build(root=ROOT, lifecycle_events=()):
    sources = {}

    def read(path):
        content = (root / path).read_bytes()
        sources[path] = sha256(content).hexdigest()
        return json.loads(content)

    canonical = read("data/inputs/players_identity_snapshot.json")
    base = read("data/inputs/sleeper_identity_base.json")
    spellings = read("data/inputs/player_platform_spellings.json")
    fixture = read("data/fixtures/current/players.json")
    aliases = read("data/inputs/player_aliases.json")
    rows = {r["player_key"]: r for r in canonical if r["position"] in {"QB", "RB", "WR", "TE"}}
    if len({r["player_key"] for r in canonical}) != len(canonical):
        raise ValueError("duplicate canonical export key")
    claims = defaultdict(set)
    for p in fixture["players"]:
        if p["player_key"] in rows and p.get("sleeper_id"):
            claims[p["player_key"]].add(str(p["sleeper_id"]))
    for p in spellings["rows"]:
        target = rows.get(p["player_key"])
        if (p["source"] == "sleeper" and p.get("source_player_id") and target
                and p["canonical_full_name"] == target["full_name"]
                and p["position"] == target["position"]):
            claims[p["player_key"]].add(str(p["source_player_id"]))
    inputs = []
    for key, row in sorted(rows.items()):
        metadata = {"gsis_id": row.get("gsis_id")}
        if len(claims[key]) == 1:
            metadata["sleeper_id"] = next(iter(claims[key]))
        inputs.append({**row, "metadata": metadata})
    result = build_searchable_identities(inputs, base, lifecycle_events,
                                        as_of=date.fromisoformat(base["meta"]["pulled_at"][:10]))
    by_key = {r["player_key"]: r for r in result["identities"]}
    redirect_claims = []
    for alias in aliases["aliases"]:
        evidence = alias.get("verified", "")
        match = re.search(r"Row (\d+).*duplicate", evidence)
        if match and int(match[1]) in by_key and alias["player_key"] in by_key:
            old = int(match[1])
            redirect_claims.append({"from_player_key": old, "to_player_key": alias["player_key"],
                                    "source": "data/inputs/player_aliases.json", "evidence": evidence,
                                    "status": "pending_current_registry_confirmation"})
            by_key[old]["selectable"] = False
            by_key[old]["selection_reason"] = "Historical duplicate-key claim requires confirmation"
    for key, ids in claims.items():
        if len(ids) > 1:
            by_key[key]["selectable"] = False
            by_key[key]["sleeper_id"] = None
            by_key[key]["selection_reason"] = "Conflicting source Sleeper IDs"
    result["eligible_player_keys"] = [r["player_key"] for r in result["identities"] if r["selectable"]]
    result.update({"schema": "jeg1505-search-identities/1", "meta": {
        "coverage": "dated local canonical snapshot; historical completeness unverified",
        "registry_freshness": "unverified", "lifecycle_input": "supplied" if lifecycle_events else "absent; unknown",
        "identity_base_pulled_at": base["meta"]["pulled_at"], "source_sha256": sources,
        "pricing_membership": "not supplied; runtime getAllRows is authoritative for computed membership"},
        "redirect_claims": redirect_claims})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true", help="reject missing/stale output without writing")
    args = parser.parse_args()
    payload = write_snapshot(out=args.out, check=args.check)
    print(f"{'Checked' if args.check else 'Wrote'} search-only snapshot: {len(payload['identities'])} identities; lifecycle unknown; {args.out}")


def write_snapshot(root=ROOT, out=None, check=False):
    """Validate/serialize completely, then atomically replace this owned asset."""
    out = Path(out) if out is not None else root / "app/trade-value-chart/assets/jeg1505-search-identities.json"
    payload = build(root)
    identities = payload.get("identities")
    if payload.get("schema") != "jeg1505-search-identities/1" or not identities:
        raise ValueError("search identity snapshot must contain canonical identities")
    keys = set()
    for row in identities:
        key = row.get("player_key")
        if (type(key) is not int or key <= 0 or key in keys
                or not isinstance(row.get("name"), str) or not row["name"].strip()
                or row.get("pos") not in {"QB", "RB", "WR", "TE"}
                or type(row.get("selectable")) is not bool
                or row.get("eligibility_status") not in {"unknown", "retired", "returned"}
                or row.get("pricing_status") != "unknown"
                or not isinstance(row.get("lifecycle_history"), list)
                or {"values", "value", "espn_ros", "blend_ros"} & row.keys()):
            raise ValueError("invalid search-only identity row")
        keys.add(key)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
    if check:
        if not out.exists() or out.read_text(encoding="utf-8") != text:
            raise ValueError("search identity artifact is missing or stale")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=out.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(text)
            os.chmod(temporary, out.stat().st_mode & 0o777 if out.exists() else 0o644)
            os.replace(temporary, out)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return payload


if __name__ == "__main__":
    main()
