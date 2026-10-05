"""Heartbeat evaluator driver (JEG-339 / JEG-357).

Single-pass CLI: read check configs + NDJSON observation rows produced by
``pipelines/heartbeat_producer``, call the pure-Python heartbeat evaluator,
and write a Heartbeat snapshot JSON. Intended to run every 60s right after
the producer.

Standing rule: no credentials, no network, no DB. Hermetic local files only.

Verdict → Observation mapping (Jeremy 2026-10-04):
    ok               -> (ok=True,  content_ok=None, error_code=None)
    content_mismatch -> (ok=True,  content_ok=False, error_code=None)
    timeout          -> (ok=False, content_ok=None, error_code='timeout')
    dns_error        -> (ok=False, content_ok=None, error_code='dns')
    tls_error        -> (ok=False, content_ok=None, error_code='tls')
    connect_error    -> (ok=False, content_ok=None, error_code='connect')
    http_error       -> (ok=False, content_ok=None, error_code='http')

Row fields map 1:1:
    checked_at  -> run_at
    status_code -> http_status
    response_ms -> latency_ms
    verdict     -> (ok, content_ok, error_code)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional

from pipelines.heartbeat_evaluator import (
    CheckConfig,
    CheckType,
    Heartbeat,
    HeartbeatState,
    Observation,
    SchedulerHeartbeat,
    compute_state,
)


# ---- Verdict → Observation projection ----------------------------------


VERDICT_TO_OBSERVATION: Dict[str, tuple] = {
    "ok":               (True,  None, None),
    "content_mismatch": (True,  False, None),
    "timeout":          (False, None, "timeout"),
    "dns_error":        (False, None, "dns"),
    "tls_error":        (False, None, "tls"),
    "connect_error":    (False, None, "connect"),
    "http_error":       (False, None, "http"),
}


# ---- Parsing helpers ----------------------------------------------------


def _parse_checked_at(value: str) -> datetime:
    """Parse the producer's 'YYYY-MM-DDTHH:MM:SS.ffffffZ' timestamp.

    ``datetime.fromisoformat`` only accepted 'Z' from 3.11+; normalize to an
    explicit UTC offset so older interpreters work too.
    """
    if not isinstance(value, str):
        raise ValueError(f"checked_at must be a string, got {type(value).__name__}")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _now_utc_z() -> str:
    """Current UTC as ISO-8601 with a trailing 'Z' (matches producer format)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---- Public row → Observation -------------------------------------------


def build_observation(row: dict) -> Observation:
    """Map one producer NDJSON row dict into an evaluator Observation.

    Unknown verdict → raise ValueError (fail closed; never fabricate green).
    """
    verdict = row["verdict"]
    if verdict not in VERDICT_TO_OBSERVATION:
        raise ValueError(f"unknown verdict: {verdict!r}")
    ok, content_ok, error_code = VERDICT_TO_OBSERVATION[verdict]
    return Observation(
        run_at=_parse_checked_at(row["checked_at"]),
        ok=ok,
        latency_ms=row.get("response_ms"),
        http_status=row.get("status_code"),
        content_ok=content_ok,
        error_code=error_code,
    )


# ---- CheckConfig construction -------------------------------------------


def _coerce_check_type(value) -> CheckType:
    if isinstance(value, CheckType):
        return value
    if value is None:
        return CheckType.HTTP_STATUS
    try:
        return CheckType(value)
    except ValueError:
        return CheckType.HTTP_STATUS


def _build_check_config(check: dict) -> CheckConfig:
    """Project a checks-list entry into a CheckConfig per the JEG-339 brief.

    cadence_seconds=60: the producer+driver run every 60s under the scheduler,
    so the evaluator can resolve the expected schedule. A check with no
    observations still yields UNKNOWN via the evaluator's "no observations yet"
    path (expected_next_run handles the empty case), not the "no schedule"
    path.
    """
    return CheckConfig(
        check_id=check["check_id"],
        cadence_seconds=60,
        grace_override_seconds=120,
        latency_budget_ms=check.get("latency_budget_ms"),
        check_type=_coerce_check_type(check.get("check_type", "http_status")),
    )


# ---- Snapshot serialisation ---------------------------------------------


def _iso_or_none(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def _heartbeat_to_dict(h: Heartbeat) -> dict:
    """Mirror the monitoring.check_heartbeats row shape (subset)."""
    return {
        "check_id": h.check_id,
        "state": h.state.value,
        "ownership_status": h.ownership_status.value,
        "scheduler_down": h.scheduler_down,
        "state_reason": h.state_reason,
        "expected_next_run_at": _iso_or_none(h.expected_next_run_at),
        "last_run_at": _iso_or_none(h.last_run_at),
        "last_ok_at": _iso_or_none(h.last_ok_at),
        "last_error_at": _iso_or_none(h.last_error_at),
        "latest_details": dict(h.latest_details),
    }


# ---- IO helpers ---------------------------------------------------------


def _load_checks(path: str) -> list:
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    return list(cfg.get("checks", []))


def _load_observations(path: str) -> Iterable[dict]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


# ---- Driver loop --------------------------------------------------------


def run_once(checks_path: str, observations_path: str, out_path: str) -> dict:
    """One pass: read inputs, call compute_state per check, write snapshot.

    Returns: {"checks": n, "states": {state_name: count, ...}}.
    A check with zero observations → state 'unknown' (delegated to
    compute_state with empty history; the evaluator emits UNKNOWN for
    "no schedule resolvable" / "no observations yet").
    """
    checks = _load_checks(checks_path)
    url_to_check = {c["url"]: c for c in checks if c.get("url")}

    observations_by_check: Dict[str, list] = {c["check_id"]: [] for c in checks}
    for row in _load_observations(observations_path):
        url = row.get("url")
        check = url_to_check.get(url) if url else None
        if check is None:
            # url not in checks config (removed check, stale row). Skip.
            continue
        observations_by_check[check["check_id"]].append(build_observation(row))

    now = datetime.now(timezone.utc)
    heartbeats: list = []
    for check in checks:
        cfg_obj = _build_check_config(check)
        obs_list = observations_by_check.get(check["check_id"], [])
        h = compute_state(
            cfg_obj,
            obs_list,
            scheduler_heartbeats=[],
            now=now,
            first_activation_at=None,
        )
        heartbeats.append(h)

    snapshot = {
        "generated_at": _now_utc_z(),
        "heartbeats": [_heartbeat_to_dict(h) for h in heartbeats],
    }

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    tmp_path = f"{out_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, sort_keys=True)
    os.replace(tmp_path, out_path)

    state_counts = Counter(h.state.value for h in heartbeats)
    return {"checks": len(checks), "states": dict(state_counts)}


# ---- CLI ----------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipelines.heartbeat_driver")
    p.add_argument("--checks", required=True,
                   help="Path to checks config JSON (e.g. config/heartbeat_checks.json).")
    p.add_argument("--observations", required=True,
                   help="Path to NDJSON observations file (one row per line).")
    p.add_argument("--out", required=True,
                   help="Path to write the Heartbeat snapshot JSON.")
    return p


def main(argv: Optional[list] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    summary = run_once(args.checks, args.observations, args.out)
    json.dump(summary, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())