#!/usr/bin/env python3
"""Acquire all 24 native FantasyCalc scopes, independently of material drift.

Run daily with a durable --cache-dir and retain --observations-out for the
source-ledger adapter. This collector does not implement the ledger or publish
the chart. Each fantasycalc_<scoring>_<teams>_qb<qbs>.json is an atomically
replaced native input bundle, including its content clock and archive reference.
A failed scope leaves its prior bundle intact and emits a failed observation;
consumers must consult this run's observations before using a prior bundle.
One serialized collector must own a cache directory (no concurrent writers).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pull_fantasycalc_12team import SCORINGS, MIN_ROWS, fetch
from nfl_week import content_week

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

# `lib` lives in pipelines/; make it importable whatever the CWD, checkout path or
# import order (tests import this module as pipelines.X without pipelines/ on sys.path).
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from lib.timestamps import parse_iso_timestamp  # noqa: E402

NORMALIZER_VERSION = "fantasycalc-native-v1"
COMBOS = tuple((s, t, q) for s in SCORINGS for t in (8, 10, 12, 14) for q in (1, 2))


def stamp(now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("observation time must be timezone-aware")
    return now.astimezone(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The temporary and destination must share a filesystem for atomic replace.
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, suffix=".tmp", delete=False) as out:
        temporary = Path(out.name)
        try:
            json.dump(payload, out, sort_keys=True, allow_nan=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def normalize(payload) -> list[dict]:
    """Complete player/value feed, before indexing. Reject rather than drop rows.

    Value is the native API number (no rounding). IDs, names, positions and
    teams are semantic; ranks and acquisition metadata are not consumed here.
    Draft-pick/non-player rows cannot silently pass this redraft contract.
    """
    if not isinstance(payload, list) or len(payload) < MIN_ROWS:
        raise ValueError(f"incomplete_scope: expected at least {MIN_ROWS} native rows")
    rows, seen = [], set()
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("player"), dict):
            raise ValueError("schema_error: expected a player object")
        player = item["player"]
        identity, value = player.get("id"), item.get("value")
        valid_id = (type(identity) is int and identity >= 0) or (
            isinstance(identity, str) and bool(identity.strip()) and identity == identity.strip())
        if (not valid_id or not isinstance(player.get("name"), str)
                or not player["name"].strip() or not isinstance(player.get("position"), str)
                or player["position"] not in {"QB", "RB", "WR", "TE"} or isinstance(value, bool)
                or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
            raise ValueError("schema_error: invalid identity, position or native value")
        identity = str(identity)
        if identity in seen:
            raise ValueError("identity_error: duplicate source player ID")
        seen.add(identity)
        rows.append({"fantasycalc_id": identity, "name": player["name"],
                     "pos": player["position"], "team": player.get("maybeTeam") or player.get("team"),
                     "value": float(value)})
    return sorted(rows, key=lambda row: row["fantasycalc_id"])


def content_hash(rows: list[dict]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def content_state(last_change: str | None, now: datetime) -> tuple[float | None, bool, str | None]:
    if last_change is None:
        return None, False, "content_vintage_unknown"
    age = (now - parse_iso_timestamp(last_change)).total_seconds()
    if age < 0:
        return age, False, "future_timestamp"
    return age, age > 86400, "content_stale" if age > 86400 else None


def acquire(cache_dir: Path, *, week: int, season: int, fetch_fn=fetch,
            now: datetime | None = None) -> list[dict]:
    """Promote each complete scope as one bundle; return ledger-shaped observations.

    The first baseline and normalizer migration have unknown vintage. An
    unchanged re-pull never advances the numeric content clock. A hash names
    an immutable full raw API archive and its normalized native rows.
    """
    now = now or datetime.now(timezone.utc)
    attempted_at = stamp(now)
    observations = []
    for scoring, teams, qbs in COMBOS:
        stem = f"fantasycalc_{scoring}_{teams}_qb{qbs}"
        path = cache_dir / f"{stem}.json"
        prior_error = None
        try:
            previous = json.loads(path.read_text()) if path.exists() else {}
            if not isinstance(previous, dict):
                raise ValueError("invalid prior scope bundle")
            if path.exists():
                prior_observation = previous.get("observation")
                if not isinstance(prior_observation, dict) or not isinstance(previous.get("rows"), list):
                    raise ValueError("invalid prior observation or rows")
                for field in ("normalized_content_hash", "ingested_hash", "normalizer_version"):
                    if prior_observation.get(field) is not None and not isinstance(prior_observation[field], str):
                        raise ValueError(f"invalid prior {field}")
                for field in ("last_observed_change_at", "successful_fetch_at"):
                    timestamp = prior_observation.get(field)
                    if timestamp is not None:
                        if not isinstance(timestamp, str) or parse_iso_timestamp(timestamp).tzinfo is None:
                            raise ValueError(f"invalid prior {field}")
                content_state(prior_observation.get("last_observed_change_at"), now)
        except (OSError, ValueError, TypeError, OverflowError) as exc:
            previous, prior_error = {}, exc
        prior = previous.get("observation", {})
        age, stale, reason = content_state(prior.get("last_observed_change_at"), now)
        obs = {
            "source": "fantasycalc", "dataset": "trade_values", "season": season,
            "week": week, "scoring": scoring,
            "league_variant": {"league_teams": teams, "qb_slots": qbs},
            "attempted_at": attempted_at, "successful_fetch_at": prior.get("successful_fetch_at"),
            "result": "failed", "complete": False,
            "coverage": {"complete": 0, "expected": len(previous.get("rows", [])) or MIN_ROWS},
            "raw_snapshot_reference": None, "normalized_content_hash": None,
            "normalizer_version": NORMALIZER_VERSION,
            "previous_hash": prior.get("normalized_content_hash"),
            "last_observed_change_at": prior.get("last_observed_change_at"),
            "source_updated_at": None, "timestamp_reliability": "observed_change_only",
            "content_age_seconds": age, "stale": stale, "reason": reason,
            "consumers": ["chart_comparison"],
            "ingested_hash": prior.get("ingested_hash"), "served_hash": None,
        }
        url = ("https://api.fantasycalc.com/values/current?isDynasty=false"
               f"&numQbs={qbs}&numTeams={teams}&ppr={SCORINGS[scoring]}")
        try:
            raw = fetch_fn(url)
            rows = normalize(raw)
            # Acquire even when saved state is corrupt, but preserve that bundle
            # for inspection rather than silently resetting its content clock.
            if prior_error is not None:
                raise ValueError(f"prior_state_invalid: {prior_error}")
            if len(rows) < 0.9 * len(previous.get("rows", [])):
                raise ValueError("incomplete_scope: fewer than 90% of prior rows")
            digest = content_hash(rows)
            same_normalizer = prior.get("normalizer_version") == NORMALIZER_VERSION
            same_scope = previous.get("week") == week and previous.get("season") == season
            baseline = not prior.get("normalized_content_hash") or not same_normalizer or not same_scope
            changed = not baseline and digest != prior["normalized_content_hash"]
            last_change = attempted_at if changed else (None if baseline else prior.get("last_observed_change_at"))
            age, stale, reason = content_state(last_change, now)
            archive = cache_dir / "snapshots" / stem / f"{NORMALIZER_VERSION}-{digest}.json"
            if not archive.exists():
                atomic_json(archive, {"raw": raw, "rows": rows, "normalized_content_hash": digest,
                                      "normalizer_version": NORMALIZER_VERSION})
            obs.update(successful_fetch_at=attempted_at,
                       result="baseline" if baseline else ("changed" if changed else "unchanged"),
                       complete=True, coverage={"complete": len(rows), "expected": len(rows)},
                       raw_snapshot_reference=str(archive), normalized_content_hash=digest,
                       last_observed_change_at=last_change, content_age_seconds=age,
                       stale=stale, reason=reason, ingested_hash=digest)
            # Rows and their observation switch together. A new value in another
            # scope can never update this scope's last_observed_change_at.
            atomic_json(path, {"rows": rows, "observation": obs, "fetched_at": attempted_at,
                               "week": week, "season": season, "url": url})
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            # Includes urllib HTTP/URL errors (OSError). No automatic retries.
            obs.update(result="failed", complete=False, reason="acquisition_failed", error=str(exc))
            obs["ingested_hash"] = prior.get("ingested_hash")
            obs["last_observed_change_at"] = prior.get("last_observed_change_at")
            obs["successful_fetch_at"] = prior.get("successful_fetch_at")
            obs["content_age_seconds"], obs["stale"], _ = content_state(
                prior.get("last_observed_change_at"), now)
        observations.append(obs)
    return observations


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-dir", required=True, type=Path)
    ap.add_argument("--observations-out", required=True, type=Path)
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--season", type=int, required=True)
    args = ap.parse_args(argv)
    observations = acquire(args.cache_dir, week=args.week or content_week(), season=args.season)
    atomic_json(args.observations_out, observations)
    failed = sum(o["result"] == "failed" for o in observations)
    print(f"FantasyCalc: {len(observations) - failed}/24 scopes verified; {failed} failed")
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
