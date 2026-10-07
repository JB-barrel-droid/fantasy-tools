#!/usr/bin/env python3
"""
Usage watcher - polls lane quotas, enforces 20% dispatch floor.

- ChatGPT lane: per-account codex poll data (JEG-101, descoped from JSON-RPC polling)
- MiniMax lane: dispatch ledger (lanes/dispatch_ledger.jsonl) with rolling 5h window
- Claude lane: per-account ledger-based depletion markers; legacy flat get_claude_usage()
  remains for backward compat with the 11 existing tests.
- Writes lanes/usage.json with the new multi-account shape:
    {
      "chatgpt": {"jeremy": {...}, "wife": {...}},
      "claude":  {"jeremy": {...}, "wife": {...}},
      "minimax": {...flat...}
    }
- can_dispatch(lane, usage_data) returns 'jeremy' | 'wife' for multi-account lanes, or bool
  for legacy flat lanes, or False when the lane is unknown.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional, Any

# Base directory for lanes
LANES_DIR = Path(__file__).parent
DISPATCH_LEDGER = LANES_DIR / "dispatch_ledger.jsonl"
USAGE_JSON = LANES_DIR / "usage.json"
CODEX_API_URL = os.environ.get("CODEX_API_URL", "http://localhost:8080")
MINIMAX_QUOTA = 100  # 100 dispatches per window = 100%
CLAUDE_QUOTA = 100

# Module-level cache for codex poll data, keyed by account name.
# Populated by inject_codex_poll_data(account, data), drained by get_chatgpt_usage().
_codex_poll_data: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Codex poll-data injection (JEG-101)
# ---------------------------------------------------------------------------

def inject_codex_poll_data(account: str, data: Dict[str, Any]) -> None:
    """
    Inject codex rate-limit poll data for a given account ('jeremy' or 'wife').
    Consumed by get_chatgpt_usage(); clear_codex_poll_data() removes all injections.
    """
    _codex_poll_data[account] = data


def clear_codex_poll_data() -> None:
    """Remove all injected codex poll data (used between tests)."""
    _codex_poll_data.clear()


# ---------------------------------------------------------------------------
# ChatGPT lane
# ---------------------------------------------------------------------------

def get_chatgpt_usage() -> Dict[str, Dict[str, Any]]:
    """
    Get ChatGPT lane usage from injected codex poll data only (JEG-101).
    CodeX JSON-RPC polling remains descoped.

    Returns a dict mapping account name to usage data:
        {'jeremy': {...}, 'wife': {...}}

    Each value is the injected payload normalized into the standard
    {used_percent, remaining_percent, remaining, resets_at, source, updated_at}
    shape. Missing accounts fall back to a default with source='codex-uninjected'.
    """
    accounts = ("jeremy", "wife")
    out: Dict[str, Dict[str, Any]] = {}
    for account in accounts:
        payload = _codex_poll_data.get(account)
        if payload is None:
            # No injected poll data: unknown, NEVER dispatch (fail closed).
            # _default_usage would report 100% remaining, which would be a
            # fail-open lie for an account we have no data on.
            out[account] = {
                "account": account,
                "used_percent": None,
                "remaining_percent": None,
                "remaining": None,
                "resets_at": None,
                "source": "codex-uninjected",
                "status": "unknown",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            continue
        out[account] = _normalize_codex_payload(account, payload)
    return out


def _normalize_codex_payload(account: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a raw codex poll payload into the standard usage shape.
    Accepts either used_percent/remaining_percent directly, or limit/remaining.
    """
    if "used_percent" in payload:
        used_percent = float(payload.get("used_percent", 0.0))
    else:
        limit = float(payload.get("limit", 100))
        remaining = float(payload.get("remaining", limit))
        used_percent = ((limit - remaining) / limit * 100.0) if limit > 0 else 0.0

    used_percent = max(0.0, min(used_percent, 100.0))
    remaining_percent = 100.0 - used_percent

    resets_at = payload.get("resets_at")
    if isinstance(resets_at, str) and resets_at and not resets_at.endswith("Z") and "+" not in resets_at:
        resets_at = resets_at + "Z"

    return {
        "account": account,
        "used_percent": round(used_percent, 1),
        "remaining_percent": round(remaining_percent, 1),
        "remaining": payload.get("remaining"),
        "resets_at": resets_at,
        "source": payload.get("source", "codex-poll"),
        "status": payload.get("status"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Legacy / shared helpers
# ---------------------------------------------------------------------------

def _default_usage(lane: str, source: str) -> Dict[str, Any]:
    """Return default usage when API is unavailable."""
    return {
        "used_percent": 0.0,
        "remaining_percent": 100.0,
        "remaining": 100,
        "resets_at": None,
        "source": source,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }


def record_dispatch(issue_id: str) -> None:
    """
    Record a dispatch event to the ledger.
    Appends one line per dispatch with timestamp and issue id.

    Args:
        issue_id: The Linear issue id for this dispatch
    """
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "issue_id": issue_id
        }
        with open(DISPATCH_LEDGER, 'a') as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"Warning: failed to record dispatch: {e}")


def get_minimax_usage() -> Dict[str, Any]:
    """
    Get MiniMax lane usage from dispatch ledger.
    Rolling 5h window: count dispatches in last 5 hours, each dispatch = 1% of quota.
    Skips lines with event=="depleted" when counting dispatches.
    If any depletion marker exists, returns 100% used / 0% remaining.
    """
    if not DISPATCH_LEDGER.exists():
        return _default_usage("minimax", "ledger-missing")

    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=5)
        dispatch_count = 0
        has_depletion_marker = False

        with open(DISPATCH_LEDGER, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)

                    # Check for depletion marker first
                    if entry.get("event") == "depleted" and entry.get("lane") == "minimax":
                        has_depletion_marker = True

                    # Skip depletion markers when counting dispatches
                    if entry.get("event") == "depleted":
                        continue

                    ts_str = entry.get("ts")
                    if ts_str:
                        # Parse ISO timestamp
                        if "+" in ts_str or ts_str.endswith("Z"):
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        else:
                            ts = datetime.fromisoformat(ts_str)
                        # Make timezone-aware
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)

                        if ts >= cutoff:
                            dispatch_count += 1
                except (json.JSONDecodeError, ValueError):
                    continue

        # If depletion marker exists, return depleted state
        if has_depletion_marker:
            return {
                "used_percent": 100.0,
                "remaining_percent": 0.0,
                "remaining": 0,
                "resets_at": None,
                "source": "ledger",
                "status": "depleted",
                "updated_at": now.isoformat(),
                "dispatch_count": dispatch_count
            }

        # Each dispatch = 1% of quota
        used_percent = min(dispatch_count * 1.0, 100.0)
        remaining = max(100 - dispatch_count, 0)

        return {
            "used_percent": used_percent,
            "remaining_percent": 100.0 - used_percent,
            "remaining": remaining,
            "resets_at": None,
            "source": "ledger",
            "updated_at": now.isoformat(),
            "dispatch_count": dispatch_count
        }

    except Exception as e:
        return _default_usage("minimax", "ledger-error")


# ---------------------------------------------------------------------------
# Claude lane
# ---------------------------------------------------------------------------

def get_claude_usage() -> Dict[str, Any]:
    """
    Get Claude lane usage - ledger-based.
    Returns unknown until a real data source is implemented.
    If a depletion marker exists in the ledger, returns 0% remaining with status "depleted".

    Backward compat: this is the FLAT single-lane accessor used by the 11 existing tests.
    Per-account data is served by get_claude_account_usage().
    """
    if not DISPATCH_LEDGER.exists():
        return {
            "used_percent": None,
            "remaining_percent": None,
            "remaining": None,
            "resets_at": None,
            "source": "none",
            "status": "unknown",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

    try:
        now = datetime.now(timezone.utc)

        # Check for depletion marker
        with open(DISPATCH_LEDGER, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Check for Claude depletion marker
                    if entry.get("event") == "depleted" and entry.get("lane") == "claude":
                        return {
                            "used_percent": 100.0,
                            "remaining_percent": 0.0,
                            "remaining": 0,
                            "resets_at": None,
                            "source": "ledger",
                            "status": "depleted",
                            "updated_at": now.isoformat()
                        }
                except json.JSONDecodeError:
                    continue

        # No depletion marker - return unknown
        return {
            "used_percent": None,
            "remaining_percent": None,
            "remaining": None,
            "resets_at": None,
            "source": "none",
            "status": "unknown",
            "updated_at": now.isoformat()
        }

    except Exception as e:
        return {
            "used_percent": None,
            "remaining_percent": None,
            "remaining": None,
            "resets_at": None,
            "source": "none",
            "status": "unknown",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }


def get_claude_account_usage(account: str, config_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Get Claude lane usage for a single account (JEG-101).

    Reads per-account depletion markers from <config_dir>/dispatch_ledger.jsonl.
    NEVER reads credential files - only the ledger.

    Args:
        account: 'jeremy' or 'wife'.
        config_dir: directory holding dispatch_ledger.jsonl for this account.
            If None, looks up:
              - CLAUDE_CONFIG_DIR        (jeremy's account)
              - CLAUDE_CONFIG_DIR_WIFE   (wife's account)
            If both are unset, returns 'unknown' WITHOUT touching the filesystem.

    Returns:
        Standard usage dict. status is 'depleted' if the ledger contains a
        depletion marker for this account; otherwise 'unknown'.
    """
    if config_dir is None:
        env_var = "CLAUDE_CONFIG_DIR_WIFE" if account == "wife" else "CLAUDE_CONFIG_DIR"
        config_dir = os.environ.get(env_var)
        if not config_dir:
            return {
                "account": account,
                "used_percent": None,
                "remaining_percent": None,
                "remaining": None,
                "resets_at": None,
                "source": "none",
                "status": "unknown",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

    ledger_path = Path(config_dir) / "dispatch_ledger.jsonl"
    if not ledger_path.exists():
        return {
            "account": account,
            "used_percent": None,
            "remaining_percent": None,
            "remaining": None,
            "resets_at": None,
            "source": "ledger-missing",
            "status": "unknown",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        now = datetime.now(timezone.utc)
        with open(ledger_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    entry.get("event") == "depleted"
                    and entry.get("lane") == "claude"
                    and entry.get("account") == account
                ):
                    return {
                        "account": account,
                        "used_percent": 100.0,
                        "remaining_percent": 0.0,
                        "remaining": 0,
                        "resets_at": None,
                        "source": "ledger",
                        "status": "depleted",
                        "updated_at": now.isoformat(),
                    }
        return {
            "account": account,
            "used_percent": None,
            "remaining_percent": None,
            "remaining": None,
            "resets_at": None,
            "source": "ledger",
            "status": "unknown",
            "updated_at": now.isoformat(),
        }
    except Exception:
        return {
            "account": account,
            "used_percent": None,
            "remaining_percent": None,
            "remaining": None,
            "resets_at": None,
            "source": "ledger-error",
            "status": "unknown",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


def mark_minimax_depleted() -> None:
    """
    Hook to mark MiniMax lane as depleted when quota is hit.
    Writes a depletion marker to the ledger for tracking.
    """
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "depleted",
            "lane": "minimax"
        }
        with open(DISPATCH_LEDGER, 'a') as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"Warning: failed to mark minimax depleted: {e}")


def mark_claude_depleted() -> None:
    """
    Hook to mark Claude lane as depleted when quota is hit.
    Writes a depletion marker to the ledger for tracking.
    """
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "depleted",
            "lane": "claude"
        }
        with open(DISPATCH_LEDGER, 'a') as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"Warning: failed to mark claude depleted: {e}")


def get_all_usage() -> Dict[str, Dict[str, Any]]:
    """
    Get usage for all lanes (JEG-101 multi-account shape).

    Returns:
        {
            "chatgpt": {"jeremy": {...}, "wife": {...}},
            "claude":  {"jeremy": {...}, "wife": {...}},
            "minimax": {...flat...},
        }
    """
    return {
        "chatgpt": get_chatgpt_usage(),
        "claude": {
            "jeremy": get_claude_account_usage("jeremy"),
            "wife": get_claude_account_usage("wife"),
        },
        "minimax": get_minimax_usage(),
    }


def can_dispatch(lane: str, usage_data: Optional[Dict[str, Dict[str, Any]]] = None) -> Any:
    """
    Check if a lane can accept new dispatches (JEG-101 multi-account aware).

    Behavior:
      - If the lane's data has 'jeremy'/'wife' sub-keys (multi-account), return
        the first account whose remaining >= 20% AND status is not 'depleted'.
        Order: 'jeremy', then 'wife'. False if neither qualifies.
      - Otherwise, fall through to the legacy flat path: return True iff
        remaining_percent >= 20% AND status is not 'unknown' / 'depleted'.
      - If the lane is unknown, return False (fail closed).

    Args:
        lane: Lane name ('chatgpt', 'claude', 'minimax').
        usage_data: Optional pre-fetched usage data, either an all-lanes dict
            (as returned by get_all_usage) or a per-lane dict.
    """
    _KNOWN_LANES = ("chatgpt", "claude", "minimax")

    if usage_data is None:
        usage_data = get_all_usage()

    # If we got an all-lanes dict, look up the lane.
    if isinstance(usage_data, dict) and lane in usage_data and isinstance(usage_data.get(lane), dict):
        lane_data = usage_data[lane]
    else:
        if isinstance(usage_data, dict) and any(k in _KNOWN_LANES for k in usage_data):
            # All-lanes dict that does not contain this lane: unknown lane,
            # fail closed (never treat the whole dict as a per-lane payload).
            return False
        lane_data = usage_data

    if not isinstance(lane_data, dict) or lane_data is None:
        return False

    # Multi-account path: dict with 'jeremy' / 'wife' sub-keys.
    if "jeremy" in lane_data or "wife" in lane_data:
        for account in ("jeremy", "wife"):
            account_data = lane_data.get(account)
            if not isinstance(account_data, dict):
                continue
            if account_data.get("status") in ("depleted", "unknown"):
                continue
            remaining = account_data.get("remaining_percent")
            if remaining is None:
                continue
            if remaining >= 20.0:
                return account
        return False

    # Legacy flat path.
    status = lane_data.get("status")
    if status in ("unknown", "depleted"):
        return False
    remaining_percent = lane_data.get("remaining_percent", 100.0)
    return remaining_percent >= 20.0


def write_usage_json() -> None:
    """
    Write current usage to lanes/usage.json (JEG-101 multi-account shape).
    """
    usage = get_all_usage()
    # Per-entry fresh updated_at (already set by the leaf functions, but refresh
    # once more at the top level so the file stamp is monotonic on every write).
    now = datetime.now(timezone.utc).isoformat()
    for lane_data in usage.values():
        if isinstance(lane_data, dict):
            # Could be {"jeremy": {...}, "wife": {...}} or flat.
            for sub in lane_data.values():
                if isinstance(sub, dict) and "updated_at" in sub:
                    sub["updated_at"] = now
    with open(USAGE_JSON, 'w') as f:
        json.dump(usage, f, indent=2)
    print(f"Wrote usage to {USAGE_JSON}")


def main():
    """Main entry point - poll and report usage."""
    print("=" * 60)
    print("Lane Usage Report")
    print("=" * 60)

    usage = get_all_usage()

    for lane, data in usage.items():
        print(f"\n{lane.upper()}:")
        if isinstance(data, dict) and ("jeremy" in data or "wife" in data):
            for account, sub in data.items():
                print(f"  [{account}]")
                print(f"    Used:      {sub.get('used_percent')}%")
                print(f"    Remaining: {sub.get('remaining_percent')}% ({sub.get('remaining', 'N/A')})")
                print(f"    Resets:    {sub.get('resets_at', 'N/A')}")
                print(f"    Source:    {sub.get('source')}")
                print(f"    Status:    {sub.get('status', 'ok')}")
                print(f"    Pick:      {can_dispatch(lane, {lane: {account: sub}})}")
        else:
            print(f"  Used: {data.get('used_percent')}%")
            print(f"  Remaining: {data.get('remaining_percent')}% ({data.get('remaining', 'N/A')} dispatches)")
            print(f"  Resets: {data.get('resets_at', 'N/A')}")
            print(f"  Source: {data.get('source')}")
            print(f"  Can dispatch: {can_dispatch(lane, data)}")

    print("\n" + "=" * 60)
    print(f"Usage written to: {USAGE_JSON}")
    print("=" * 60)

    # Write the JSON file
    write_usage_json()

    return 0


if __name__ == "__main__":
    sys.exit(main())
