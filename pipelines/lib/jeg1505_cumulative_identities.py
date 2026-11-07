"""Cumulative canonical evidence for the search-only JEG-1505 catalog.

The prior owned artifact is a required refresh input, not current roster truth.
Omission never deletes an identity or establishes retirement. Evidence is kept
by canonical key; names never join people. No prices or provider-only keys.
"""
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
import json
import re

from .searchable_identity_eligibility import _history, _id, _key

POSITIONS = {"QB", "RB", "WR", "TE"}
CANONICAL_PATH = "data/inputs/players_identity_snapshot.json"


def _digest(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("retention evidence requires a source SHA-256")
    return value


def _unique(rows):
    return [json.loads(text) for text in sorted({json.dumps(row, sort_keys=True) for row in rows})]


def canonical_lifecycle_events(events, known_keys):
    """Validate/normalize emitted event fields before comparing evidence.

    Keep distinct sources and kinds. The existing lifecycle validator rejects
    same-date contradictions, holding the refresh without choosing an event.
    """
    histories = _history(events, known_keys)
    return _unique([event for history in histories.values() for event in history])


def accumulate(canonical, previous, source_hashes):
    """Return retained evidence, sourced history/redirects and source catalog.

    Caller supplies validated source JSON and its exact hashes. A None prior is
    explicit bootstrap; normal refresh must never silently fall back to it.
    """
    current = {}
    for row in canonical:
        if not isinstance(row, dict):
            raise ValueError("canonical export rows must be objects")
        key = _key(row.get("player_key"))
        if key in current:
            raise ValueError("duplicate canonical export key")
        current[key] = row
    sources, records, events, redirects = {}, {}, [], []
    for path, digest in source_hashes.items():
        sources.setdefault(_digest(digest), set()).add(path)
    if previous is not None:
        if (not isinstance(previous, dict) or previous.get("schema") != "jeg1505-search-identities/1"
                or not isinstance(previous.get("identities"), list) or not previous["identities"]):
            raise ValueError("invalid prior search identity artifact")
        meta = previous.get("meta") or {}
        old_hashes = meta.get("source_sha256")
        if not isinstance(old_hashes, dict) or CANONICAL_PATH not in old_hashes:
            raise ValueError("prior identity artifact requires source provenance")
        for path, digest in old_hashes.items():
            sources.setdefault(_digest(digest), set()).add(path)
        prior_sources = meta.get("retention_sources", {})
        if not isinstance(prior_sources, dict):
            raise ValueError("invalid retained source catalog")
        for digest, paths in prior_sources.items():
            if not isinstance(paths, list) or not paths or any(not isinstance(p, str) or not p for p in paths):
                raise ValueError("invalid retained source provenance")
            sources.setdefault(_digest(digest), set()).update(paths)
        # Used only when migrating legacy rows that have no retained evidence.
        legacy_digest = sha256(json.dumps(previous, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        for row in previous["identities"]:
            if not isinstance(row, dict):
                raise ValueError("prior identity rows must be objects")
            key = _key(row.get("player_key"))
            if key in records:
                raise ValueError("duplicate prior canonical key")
            if (not isinstance(row.get("name"), str) or not row["name"].strip()
                    or row.get("pos") not in POSITIONS or type(row.get("selectable")) is not bool
                    or row.get("eligibility_status") not in {"unknown", "retired", "returned"}
                    or row.get("pricing_status") != "unknown"
                    or not isinstance(row.get("lifecycle_history"), list)
                    or {"values", "value", "espn_ros", "blend_ros"} & row.keys()):
                raise ValueError("invalid prior search-only identity")
            if row["eligibility_status"] != "unknown" and not row["lifecycle_history"]:
                raise ValueError("prior lifecycle status requires sourced history")
            retained = deepcopy(row.get("retention"))
            if retained is not None and meta.get("retention_version") not in {1, 2}:
                raise ValueError("unsupported cumulative retention version")
            if retained is not None and meta.get("retention_version") == 1:
                retained.setdefault("gsis_claims", [])
            if retained is None:
                sources.setdefault(legacy_digest, set()).add("legacy-search-artifact:canonical-json-sha256")
                retained = {"canonical_observations": [{"full_name": row["name"], "position": row["pos"],
                    "gsis_id": _id(row.get("gsis_id")), "source_sha256": old_hashes[CANONICAL_PATH]}],
                    "sleeper_claims": [], "gsis_claims": [], "holds": [], "label_source_sha256": old_hashes[CANONICAL_PATH],
                    "present_in_canonical_export": key in current}
                if row.get("sleeper_id"):
                    retained["sleeper_claims"].append({"id": _id(row["sleeper_id"]), "source_sha256": legacy_digest})
                # Suppressed IDs cannot be reconstructed from a legacy row.
                # A disappearing source is not evidence resolving its hold.
                reason = row.get("selection_reason") or "Unresolved prior identity mapping"
                if not row["selectable"] and reason != "sourced retirement":
                    retained["holds"].append({"reason": reason, "source_sha256": legacy_digest})
            if (not isinstance(retained, dict)
                    or set(retained) != {"canonical_observations", "sleeper_claims", "gsis_claims", "holds",
                                         "label_source_sha256", "present_in_canonical_export"}
                    or type(retained["present_in_canonical_export"]) is not bool):
                raise ValueError("invalid retained identity evidence")
            for field in ("canonical_observations", "sleeper_claims", "gsis_claims", "holds"):
                if not isinstance(retained.get(field), list):
                    raise ValueError("invalid retained identity evidence lists")
                for evidence in retained[field]:
                    if not isinstance(evidence, dict) or _digest(evidence.get("source_sha256")) not in sources:
                        raise ValueError("retained evidence has no registered source")
            if not retained["canonical_observations"]:
                raise ValueError("retained identity requires canonical evidence")
            for observation in retained["canonical_observations"]:
                if (set(observation) != {"full_name", "position", "gsis_id", "source_sha256"}
                        or not isinstance(observation.get("full_name"), str) or not observation["full_name"].strip()
                        or not isinstance(observation.get("position"), str) or not observation["position"]):
                    raise ValueError("invalid retained canonical observation")
                _id(observation.get("gsis_id"))
            for claim in [*retained["sleeper_claims"], *retained["gsis_claims"]]:
                if set(claim) != {"id", "source_sha256"} or _id(claim.get("id")) is None:
                    raise ValueError("invalid retained provider claim")
            if any(set(hold) != {"reason", "source_sha256"} or not isinstance(hold.get("reason"), str)
                   or not hold["reason"].strip() for hold in retained["holds"]):
                raise ValueError("invalid retained identity hold")
            if _digest(retained.get("label_source_sha256")) not in sources:
                raise ValueError("retained label has no registered source")
            # Preserve resolved IDs from prior adapter output even if an older
            # retention version did not record its GSIS-derived Sleeper claim.
            if row.get("sleeper_id") and not any(c["id"] == str(row["sleeper_id"]) for c in retained["sleeper_claims"]):
                retained["sleeper_claims"].append({"id": _id(row["sleeper_id"]),
                    "source_sha256": _digest(old_hashes["data/inputs/sleeper_identity_base.json"])})
            reason = row.get("selection_reason")
            if (not row["selectable"] and reason != "sourced retirement"
                    and not retained["holds"] and isinstance(reason, str) and reason):
                retained["holds"].append({"reason": reason,
                    "source_sha256": _digest(old_hashes["data/inputs/sleeper_identity_base.json"])})
            records[key] = {"full_name": row["name"], "position": row["pos"], "evidence": retained}
            events.extend(deepcopy(row["lifecycle_history"]))
        redirects = deepcopy(previous.get("redirect_claims", []))
        if not isinstance(redirects, list):
            raise ValueError("invalid prior redirect claims")
        for redirect in redirects:
            if (not isinstance(redirect, dict)
                    or set(redirect) != {"from_player_key", "to_player_key", "status", "source", "evidence"}
                    or not isinstance(redirect.get("source"), str) or not redirect["source"]
                    or not isinstance(redirect.get("evidence"), str) or not redirect["evidence"]
                    or _key(redirect.get("from_player_key")) not in records
                    or _key(redirect.get("to_player_key")) not in records
                    or redirect.get("status") != "pending_current_registry_confirmation"):
                raise ValueError("invalid prior pending redirect claim")
    digest = source_hashes[CANONICAL_PATH]
    for key, row in sorted(current.items()):
        if row.get("position") not in POSITIONS and key not in records:
            continue
        if not isinstance(row.get("full_name"), str) or not row["full_name"].strip():
            raise ValueError("canonical identity requires full_name")
        if not isinstance(row.get("position"), str) or not row["position"]:
            raise ValueError("canonical identity requires a position observation")
        record = records.setdefault(key, {"evidence": {"canonical_observations": [], "sleeper_claims": [], "gsis_claims": [], "holds": []}})
        evidence = record["evidence"]
        evidence["canonical_observations"].append({"full_name": row["full_name"], "position": row["position"],
            "gsis_id": _id(row.get("gsis_id")), "source_sha256": digest})
        if row["position"] in POSITIONS:
            record.update(full_name=row["full_name"], position=row["position"])
            evidence["label_source_sha256"] = digest
        else:
            evidence["holds"].append({"reason": "Canonical export no longer supplies a skill position", "source_sha256": digest})
    for key, record in records.items():
        record["evidence"]["present_in_canonical_export"] = key in current
    return records, canonical_lifecycle_events(events, records), _unique(redirects), sources


def selection_inputs(records):
    """Keep every historical claim in ambiguity detection, including held IDs."""
    owners = {field: defaultdict(set) for field in ("sleeper_id", "gsis_id")}
    rejected, inputs = defaultdict(set), []
    for key, record in sorted(records.items()):
        evidence = record["evidence"]
        for field in ("canonical_observations", "sleeper_claims", "gsis_claims", "holds"):
            evidence[field] = _unique(evidence[field])
        sids = {_id(c["id"]) for c in evidence["sleeper_claims"]}
        canonical_gsis = {_id(c.get("gsis_id")) for c in evidence["canonical_observations"]} - {None}
        gsis = canonical_gsis | {_id(c["id"]) for c in evidence["gsis_claims"]}
        positions = {c["position"] for c in evidence["canonical_observations"]}
        if len(sids) > 1:
            rejected[key].add("Conflicting source Sleeper IDs")
        if len(gsis) > 1:
            rejected[key].add("Conflicting historical GSIS claims")
        if len(positions) > 1:
            rejected[key].add("Conflicting historical canonical positions")
        rejected[key].update(hold["reason"] for hold in evidence["holds"])
        for sid in sids:
            owners["sleeper_id"][sid].add(key)
        for gid in gsis:
            owners["gsis_id"][gid].add(key)
        inputs.append({"player_key": key, "full_name": record["full_name"], "position": record["position"],
                       "metadata": {"sleeper_id": next(iter(sids)) if len(sids) == 1 else None,
                                    "gsis_id": next(iter(canonical_gsis)) if len(canonical_gsis) == 1 else None}})
    for field, values in owners.items():
        for keys in values.values():
            if len(keys) > 1:
                for key in keys:
                    rejected[key].add(f"Multiple canonical keys claim historical {field}")
    return inputs, rejected
