"""Offline search-only snapshot; never changes the priced players fixture.

Existing snapshots are dated identity evidence, not a claim of current registry
freshness. No lifecycle events are inferred. Duplicate-key redirect claims are
retained as pending evidence, never activated from migration text or names.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile

if __package__:
    from .lib.searchable_identity_eligibility import build_searchable_identities, _id
    from .lib.jeg1505_cumulative_identities import accumulate, canonical_lifecycle_events, selection_inputs, _unique
else:
    from lib.searchable_identity_eligibility import build_searchable_identities, _id
    from lib.jeg1505_cumulative_identities import accumulate, canonical_lifecycle_events, selection_inputs, _unique

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "app/trade-value-chart/assets/jeg1505-search-identities.json"
_AUTO_PRIOR = object()


def build(root=ROOT, lifecycle_events=(), *, prior_snapshot=_AUTO_PRIOR, as_of=None):
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
    if len({r["player_key"] for r in canonical}) != len(canonical):
        raise ValueError("duplicate canonical export key")
    if prior_snapshot is _AUTO_PRIOR:
        prior_snapshot = root / "app/trade-value-chart/assets/jeg1505-search-identities.json"
    if isinstance(prior_snapshot, Path):
        if not prior_snapshot.is_file():
            raise ValueError("prior search identity artifact is required; bootstrap must be explicit")
        prior_snapshot = json.loads(prior_snapshot.read_text(encoding="utf-8"))
    records, prior_events, redirect_claims, retained_sources = accumulate(canonical, prior_snapshot, sources)
    previous_meta = (prior_snapshot or {}).get("meta", {})
    provider_day = date.fromisoformat(base["meta"]["pulled_at"][:10])
    prior_day = date.fromisoformat(previous_meta.get("lifecycle_as_of")
        or previous_meta.get("identity_base_pulled_at", provider_day.isoformat())[:10])
    if as_of is None:
        as_of = max(provider_day, prior_day)
    if type(as_of) is not date or as_of < prior_day:
        raise ValueError("cumulative lifecycle replay date cannot move backwards")
    if not isinstance(lifecycle_events, (list, tuple)):
        raise ValueError("lifecycle events must be an array")
    events = canonical_lifecycle_events([*prior_events, *lifecycle_events], records)

    def claim(key, sid, path):
        sid = _id(sid)
        if sid is None:
            raise ValueError("verified Sleeper claim requires an ID")
        records[key]["evidence"]["sleeper_claims"].append({"id": sid, "source_sha256": sources[path]})

    for p in fixture["players"]:
        if p["player_key"] in records and p.get("sleeper_id"):
            claim(p["player_key"], p["sleeper_id"], "data/fixtures/current/players.json")
    for p in spellings["rows"]:
        target = records.get(p["player_key"])
        if (p["source"] == "sleeper" and p.get("source_player_id") and target
                and p["canonical_full_name"] == target["full_name"]
                and p["position"] == target["position"]):
            claim(p["player_key"], p["source_player_id"], "data/inputs/player_platform_spellings.json")
    # Record candidate IDs even when ambiguity prevents a resolved output ID.
    # A later provider refresh must not erase the claims that caused a hold.
    provider = base.get("by_sleeper_id") or {}
    provider_by_gsis = {}
    for sid, record in provider.items():
        gid = _id(record.get("gsis_id"))
        if gid is not None:
            provider_by_gsis.setdefault(gid, set()).add(_id(sid))
    for key, record in records.items():
        evidence = record["evidence"]
        gsis = {_id(c.get("gsis_id")) for c in evidence["canonical_observations"]} - {None}
        gsis.update(c["id"] for c in evidence["gsis_claims"])
        for sid in {c["id"] for c in evidence["sleeper_claims"]}:
            gid = _id((provider.get(sid) or {}).get("gsis_id"))
            if gid is not None:
                gsis.add(gid)
        for gid in sorted(gsis):
            if gid in provider_by_gsis:
                evidence["gsis_claims"].append({"id": gid, "source_sha256": sources["data/inputs/sleeper_identity_base.json"]})
                for sid in sorted(provider_by_gsis[gid]):
                    claim(key, sid, "data/inputs/sleeper_identity_base.json")
    for alias in aliases["aliases"]:
        evidence = alias.get("verified", "")
        match = re.search(r"Row (\d+).*duplicate", evidence)
        if match and int(match[1]) in records and alias["player_key"] in records:
            old = int(match[1])
            redirect_claims.append({"from_player_key": old, "to_player_key": alias["player_key"],
                                    "source": "data/inputs/player_aliases.json", "evidence": evidence,
                                    "status": "pending_current_registry_confirmation"})
            records[old]["evidence"]["holds"].append({"reason": "Historical duplicate-key claim requires confirmation",
                "source_sha256": sources["data/inputs/player_aliases.json"]})
    inputs, rejected = selection_inputs(records)
    result = build_searchable_identities(inputs, base, events, as_of=as_of)
    for issue in result["issues"]:
        records[issue["player_key"]]["evidence"]["holds"].append({"reason": issue["reason"],
            "source_sha256": sources["data/inputs/sleeper_identity_base.json"]})
    for row in result["identities"]:
        claims = records[row["player_key"]]["evidence"]["sleeper_claims"]
        if row["sleeper_id"] is not None and not any(c["id"] == row["sleeper_id"] for c in claims):
            claims.append({"id": row["sleeper_id"], "source_sha256": sources["data/inputs/sleeper_identity_base.json"]})
    # New resolved IDs and source holds participate in this same refresh.
    _, rejected = selection_inputs(records)
    for row in result["identities"]:
        key = row["player_key"]
        row["retention"] = deepcopy(records[key]["evidence"])
        if rejected[key]:
            row.update(selectable=False, sleeper_id=None, gsis_id=None,
                       team=None, roster_status=None, injury_status=None,
                       selection_reason="; ".join(sorted(rejected[key])))
            for reason in sorted(rejected[key]):
                result["issues"].append({"player_key": key, "reason": reason})
    result["issues"] = _unique(result["issues"])
    result["eligible_player_keys"] = [r["player_key"] for r in result["identities"] if r["selectable"]]
    result.update({"schema": "jeg1505-search-identities/1", "meta": {
        "coverage": "cumulative observed canonical identities; historical completeness unverified",
        "registry_freshness": "unverified", "lifecycle_input": "sourced history supplied or retained" if events else "absent; unknown",
        "lifecycle_as_of": as_of.isoformat(), "retention_version": 2,
        "retention_sources": {digest: sorted(paths) for digest, paths in sorted(retained_sources.items())},
        "identity_base_pulled_at": base["meta"]["pulled_at"], "source_sha256": sources,
        "pricing_membership": "not supplied; runtime getAllRows is authoritative for computed membership"},
        "redirect_claims": _unique(redirect_claims)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true", help="reject missing/stale output without writing")
    prior = parser.add_mutually_exclusive_group()
    prior.add_argument("--prior", type=Path, help="explicit prior owned search artifact")
    prior.add_argument("--bootstrap", action="store_true", help="explicitly start a new catalog without prior history")
    parser.add_argument("--lifecycle-events", type=Path, help="caller-verified sourced retirement/return JSON array")
    parser.add_argument("--as-of", type=date.fromisoformat, help="explicit lifecycle replay day; cannot regress")
    args = parser.parse_args()
    events = json.loads(args.lifecycle_events.read_text(encoding="utf-8")) if args.lifecycle_events else ()
    payload = write_snapshot(out=args.out, check=args.check, lifecycle_events=events, as_of=args.as_of,
        prior_snapshot=None if args.bootstrap else args.prior if args.prior else _AUTO_PRIOR)
    print(f"{'Checked' if args.check else 'Wrote'} search-only snapshot: {len(payload['identities'])} identities; {args.out}")


def write_snapshot(root=ROOT, out=None, check=False, *, lifecycle_events=(), as_of=None, prior_snapshot=_AUTO_PRIOR):
    """Validate/serialize completely, then atomically replace this owned asset."""
    out = Path(out) if out is not None else root / "app/trade-value-chart/assets/jeg1505-search-identities.json"
    if (out.exists() and prior_snapshot is not _AUTO_PRIOR
            and (not isinstance(prior_snapshot, Path) or prior_snapshot.resolve() != out.resolve())):
        raise ValueError("existing cumulative history cannot be replaced by bootstrap or another prior")
    if prior_snapshot is _AUTO_PRIOR and out.exists():
        prior_snapshot = out
    try:
        payload = build(root, lifecycle_events, prior_snapshot=prior_snapshot, as_of=as_of)
    except ValueError as error:
        if check:
            raise ValueError("search identity artifact is missing or stale: invalid cumulative input") from error
        raise
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
