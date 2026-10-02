#!/usr/bin/env python3
"""
Usage watcher - polls lane quotas, enforces 20% dispatch floor.

- ChatGPT lane: JSON-RPC handshake with initialize + account/rateLimits/read (per JEG-99 spec)
- MiniMax lane: dispatch ledger (lanes/dispatch_ledger.jsonl) with rolling 5h window
- Claude lane: ledger-based for now with mark_depleted hook
- Writes lanes/usage.json with per-lane {used_percent, remaining_percent, resets_at, source, updated_at}
- can_dispatch(lane) returns False when remaining < 20%
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


def get_chatgpt_usage() -> Dict[str, Any]:
    """
    Poll ChatGPT (Codex) lane quota per JEG-99 spec:
    - spawn 'codex app-server'
    - send 'initialize' with clientInfo
    - send 'initialized' notification
    - send 'account/rateLimits/read' with NO jsonrpc:2.0 field
    - extract primary (5h) and secondary (weekly) usedPercent + resetsAt

    Returns usage data with used_percent, remaining_percent, resets_at, source.
    """
    try:
        import requests

        # Step 1: Send initialize with clientInfo (NOT jsonrpc:2.0 wrapper)
        resp = requests.post(
            CODEX_API_URL,
            json={
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "data-driven-football",
                        "version": "1.0.0"
                    }
                }
            },
            timeout=5
        )
        if resp.status_code != 200:
            return _default_usage("chatgpt", "codex-unreachable")

        # Step 2: Send initialized notification (no id, no jsonrpc wrapper)
        resp = requests.post(
            CODEX_API_URL,
            json={
                "method": "initialized",
                "params": {}
            },
            timeout=5
        )
        # Ignore response - this is a notification

        # Step 3: Send account/rateLimits/read with NO jsonrpc:2.0 field
        resp = requests.post(
            CODEX_API_URL,
            json={
                "id": 2,
                "method": "account/rateLimits/read",
                "params": {}
            },
            timeout=5
        )
        if resp.status_code != 200:
            return _default_usage("chatgpt", "codex-unreachable")

        data = resp.json()

        # Parse the Codex response - may have primary (5h) and secondary (weekly) limits
        if "result" in data:
            result = data.get("result", {})

            # Get primary limit (5-hour window)
            primary = result.get("primary", {})
            limit = primary.get("limit", 100)
            remaining = primary.get("remaining", 100)
            used = limit - remaining

            # Use usedPercent if provided, otherwise calculate
            if "usedPercent" in primary:
                used_percent = primary.get("usedPercent", 0)
            else:
                used_percent = (used / limit * 100) if limit > 0 else 0

            # Get resetsAt from primary
            resets_at = primary.get("resetsAt")
            if resets_at:
                # Handle ISO format
                if isinstance(resets_at, str):
                    if not resets_at.endswith("Z") and "+" not in resets_at:
                        resets_at = resets_at + "Z"
            else:
                # Fallback to secondary if primary has no reset
                secondary = result.get("secondary", {})
                resets_at = secondary.get("resetsAt")

            return {
                "used_percent": round(used_percent, 1),
                "remaining_percent": round(100 - used_percent, 1),
                "remaining": remaining,
                "resets_at": resets_at,
                "source": "codex-api",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

        return _default_usage("chatgpt", "codex-no-result")

    except Exception as e:
        # If Codex API fails, return short status string (no exception repr)
        return _default_usage("chatgpt", "codex-unreachable")


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
    """
    if not DISPATCH_LEDGER.exists():
        return _default_usage("minimax", "ledger-missing")

    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=5)
        dispatch_count = 0

        with open(DISPATCH_LEDGER, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
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
        return _default_usage("minimax", f"ledger-error: {e}")


def get_claude_usage() -> Dict[str, Any]:
    """
    Get Claude lane usage - ledger-based for now.
    Returns default available until mark_depleted hook is implemented.
    """
    # TODO: Implement Claude ledger tracking
    return _default_usage("claude", "ledger")


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
    Get usage for all lanes.
    Returns dict mapping lane name to usage data.
    """
    return {
        "chatgpt": get_chatgpt_usage(),
        "minimax": get_minimax_usage(),
        "claude": get_claude_usage()
    }


def can_dispatch(lane: str, usage_data: Optional[Dict[str, Dict[str, Any]]] = None) -> bool:
    """
    Check if a lane can accept new dispatches.
    Returns False when remaining < 20% (i.e., used >= 80%).

    Args:
        lane: Lane name ("chatgpt", "minimax", "claude")
        usage_data: Optional pre-fetched usage data. Can be:
            - None: fetches fresh data for all lanes
            - A per-lane dict (single lane data): uses directly
            - An all-lanes dict {"chatgpt": {...}, "minimax": {...}, ...}: looks up the lane internally

    Returns:
        True if lane can accept dispatch, False if below 20% remaining threshold.
    """
    if usage_data is None:
        all_usage = get_all_usage()
        usage_data = all_usage.get(lane)
    else:
        # Check if this is an all-lanes dict or a per-lane dict
        # If usage_data has keys that are lane names (chatgpt, minimax, claude),
        # it's an all-lanes dict and we need to look up the specific lane
        if lane in usage_data:
            # It's an all-lanes dict, extract the lane
            usage_data = usage_data.get(lane)
        # Otherwise, it's already a per-lane dict

    if usage_data is None:
        # Unknown lane - allow by default
        return True

    remaining_percent = usage_data.get("remaining_percent", 100.0)

    # Enforce 20% dispatch floor
    return remaining_percent >= 20.0


def write_usage_json() -> None:
    """
    Write current usage to lanes/usage.json.
    """
    usage = get_all_usage()
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
        print(f"  Used: {data['used_percent']}%")
        print(f"  Remaining: {data['remaining_percent']}% ({data.get('remaining', 'N/A')} dispatches)")
        print(f"  Resets: {data.get('resets_at', 'N/A')}")
        print(f"  Source: {data['source']}")
        print(f"  Can dispatch: {can_dispatch(lane, data)}")

    print("\n" + "=" * 60)
    print(f"Usage written to: {USAGE_JSON}")
    print("=" * 60)

    # Write the JSON file
    write_usage_json()

    return 0


if __name__ == "__main__":
    sys.exit(main())
