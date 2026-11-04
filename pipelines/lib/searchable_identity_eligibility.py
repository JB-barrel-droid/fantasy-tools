"""JEG-1505: pure, opt-in eligibility for canonical searchable identities.

This is NOT nfl_universe.active_universe and must not drive players.active,
pricing, curves or production sync. No caller is activated in this change.
Known canonical QB/RB/WR/TE identities remain selectable unless explicitly
retired or their provider mapping is ambiguous. Team, news, active flags and
pricing coverage never establish retirement. Provider-only rows cannot mint
canonical keys. Names are labels, never a fallback identity join here.

Inputs are caller-supplied canonical rows (player_key, full_name, position,
metadata.sleeper_id/gsis_id), a Sleeper identity base and optional sourced
lifecycle events. Events use player_key, kind (retired/returned), ISO date,
and a source URL. No lifecycle dataset is supplied or inferred. Dates are
effective dates; as_of is explicit so replay is deterministic. A later return
restores the same key. All history, including future evidence, is preserved.
Source URLs receive syntax checks only; provenance is the caller's responsibility.

priced_player_keys=None means pricing coverage is unknown; an explicit key
set distinguishes available/unavailable coverage. This adapter computes no
prices or projections and returns no value fields. Callers must retain the
existing priced outputs and materialize unavailable identities separately.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
from typing import Iterable
from urllib.parse import urlsplit

_POSITIONS = {"QB", "RB", "WR", "TE"}


def _key(value) -> int:
    # Do not truncate floats, coerce booleans or invent synthetic keys.
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("player_key must be a positive canonical integer")
    if isinstance(value, str) and (not value.isascii() or not value.isdigit()):
        raise ValueError("player_key must be a positive canonical integer")
    key = int(value)
    if key <= 0:
        raise ValueError("player_key must be a positive canonical integer")
    return key


def _id(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("provider id must be a non-empty string or integer")
    result = str(value).strip()
    if not result:
        raise ValueError("provider id must be a non-empty string or integer")
    return result


def _history(events, known_keys):
    histories = defaultdict(list)
    day_kinds = defaultdict(set)
    for event in events:
        key = _key(event.get("player_key"))
        if key not in known_keys:
            raise ValueError(f"lifecycle evidence references unknown player_key {key}")
        kind = event.get("kind")
        if kind not in {"retired", "returned"}:
            raise ValueError("lifecycle kind must be retired or returned")
        on, source = event.get("date"), event.get("source")
        if not isinstance(on, str) or len(on) != 10:
            raise ValueError("lifecycle date must be YYYY-MM-DD")
        if date.fromisoformat(on).isoformat() != on:
            raise ValueError("lifecycle date must be YYYY-MM-DD")
        # urlsplit silently removes some raw controls, so reject them first.
        if not isinstance(source, str) or any(
            char.isspace() or ord(char) < 32 or ord(char) == 127 for char in source
        ):
            raise ValueError("lifecycle evidence requires a source URL")
        url = urlsplit(source)
        if url.scheme not in {"http", "https"} or not url.hostname:
            raise ValueError("lifecycle evidence requires a source URL")
        _ = url.port  # Validate explicit port syntax/range without fetching.
        day_kinds[key, on].add(kind)
        if len(day_kinds[key, on]) > 1:
            raise ValueError(f"conflicting lifecycle evidence for player_key {key} on {on}")
        histories[key].append({"player_key": key, "kind": kind, "date": on, "source": source})
    for history in histories.values():
        history.sort(key=lambda e: (e["date"], e["kind"], e["source"]))
    return histories


def build_searchable_identities(
    canonical_rows: Iterable[dict],
    sleeper_base: dict,
    lifecycle_events: Iterable[dict] = (),
    *,
    as_of: date,
    priced_player_keys: Iterable[int] | None = None,
) -> dict:
    """Return identities, eligible_player_keys and mapping issues; never write.

    Duplicate canonical keys or malformed evidence raise ValueError. Ambiguous
    provider claims preserve the canonical identity in identities, but omit its
    provider IDs and exclude it from eligible_player_keys pending resolution.
    Missing provider records alone do not make an identity ineligible.
    """
    if type(as_of) is not date:
        raise ValueError("as_of must be a date")
    canonical, canonical_ids = {}, {}
    owners = {field: defaultdict(set) for field in ("sleeper_id", "gsis_id")}
    for row in canonical_rows:
        key = _key(row.get("player_key"))
        if key in canonical:
            raise ValueError(f"duplicate player_key {key}")
        if not isinstance(row.get("full_name"), str) or not row["full_name"].strip():
            raise ValueError(f"player_key {key} requires full_name")
        canonical[key] = row
        metadata = row.get("metadata") or {}
        ids = {field: _id(metadata.get(field)) for field in owners}
        canonical_ids[key] = ids
        for field, value in ids.items():
            if value is not None:
                owners[field][value].add(key)

    histories = _history(lifecycle_events, canonical)
    priced = None if priced_player_keys is None else {_key(k) for k in priced_player_keys}
    provider = {}
    by_gsis = defaultdict(set)
    for raw_sid, record in (sleeper_base.get("by_sleeper_id") or {}).items():
        sid = _id(raw_sid)
        if sid is None or sid in provider:
            raise ValueError("duplicate or missing Sleeper id in identity base")
        provider[sid] = record
        gsis = _id(record.get("gsis_id"))
        if gsis is not None:
            by_gsis[gsis].add(sid)

    candidates, rejected = {}, {}
    claims = defaultdict(set)
    for key, row in canonical.items():
        ids = canonical_ids[key]
        sid, gsis = ids["sleeper_id"], ids["gsis_id"]
        matches = set(by_gsis.get(gsis, ()))
        if sid is not None:
            matches.add(sid)
        if any(value is not None and len(owners[field][value]) > 1
               for field, value in ids.items()):
            rejected[key] = "ambiguous canonical provider id"
        if len(matches) > 1:
            rejected[key] = "multiple Sleeper ids claim one canonical identity"
        for match in matches:
            claims[match].add(key)
        matched = next(iter(matches)) if len(matches) == 1 else None
        candidates[key] = matched
        record = provider.get(matched)
        if record is not None:
            provider_gsis = _id(record.get("gsis_id"))
            if provider_gsis and len(by_gsis[provider_gsis]) > 1:
                rejected[key] = "multiple Sleeper ids share one GSIS id"
            if gsis and provider_gsis and gsis != provider_gsis:
                rejected[key] = "canonical and Sleeper GSIS ids disagree"
            if (record.get("pos") or "").upper() != (row.get("position") or "").upper():
                rejected[key] = "canonical and Sleeper positions disagree"
    for sid, keys in claims.items():
        if len(keys) > 1:
            for key in keys:
                rejected[key] = "multiple canonical keys claim one Sleeper id"

    identities, eligible, issues = [], [], []
    for key, row in sorted(canonical.items()):
        if (row.get("position") or "").upper() not in _POSITIONS:
            continue
        history = histories.get(key, [])
        effective = [e for e in history if e["date"] <= as_of.isoformat()]
        status = effective[-1]["kind"] if effective else "unknown"
        issue = rejected.get(key)
        sid = None if issue else candidates[key]
        record = provider.get(sid) or {}
        pricing = "unknown" if priced is None else "available" if key in priced else "unavailable"
        selectable = issue is None and status != "retired"
        identities.append({
            "player_key": key,
            "name": row["full_name"],
            "pos": row["position"].upper(),
            "sleeper_id": sid,
            "gsis_id": None if issue else canonical_ids[key]["gsis_id"],
            "team": deepcopy(record.get("team")),
            "roster_status": deepcopy(record.get("status")),
            "injury_status": deepcopy(record.get("injury_status")),
            "eligibility_status": status,
            "selectable": selectable,
            "selection_reason": issue or ("sourced retirement" if status == "retired"
                                          else "no sourced retirement in effect"),
            "lifecycle_history": deepcopy(history),
            "pricing_status": pricing,
            "unpriced_reason": ("No chart or projection prices this player."
                                if pricing == "unavailable" else None),
        })
        if selectable:
            eligible.append(key)
        if issue:
            issues.append({"player_key": key, "reason": issue})
    return {"identities": identities, "eligible_player_keys": eligible, "issues": issues}
