#!/usr/bin/env python3
"""
Unit tests for usage_watcher.py

Tests:
1. Stubbed 95%-used codex response => can_dispatch("codex") is False
2. 3 fake ledger dispatches within 5h => minimax reads 3% used
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add lanes directory to path
sys.path.insert(0, str(Path(__file__).parent))

import usage_watcher


def test_codex_95_percent_blocked():
    """
    Unit test: stubbed 95%-used codex response => can_dispatch("codex") is False
    """
    # Create stubbed usage data simulating 95% used
    usage_data = {
        "codex": {
            "used_percent": 95.0,
            "remaining_percent": 5.0,
            "resets_at": "2026-10-02T16:00:00Z",
            "source": "codex-api",
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        "minimax": {
            "used_percent": 0.0,
            "remaining_percent": 100.0,
            "resets_at": None,
            "source": "ledger",
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        "claude": {
            "used_percent": 0.0,
            "remaining_percent": 100.0,
            "resets_at": None,
            "source": "ledger",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    }

    result = usage_watcher.can_dispatch("codex", usage_data)
    assert result == False, f"Expected can_dispatch to be False for 95% used, got {result}"
    print("TEST 1 PASSED: 95% used codex returns can_dispatch=False")


def test_minimax_3_dispatches():
    """
    Unit test: 3 fake ledger dispatches within 5h => minimax reads 3% used
    """
    # Create a temporary ledger with 3 entries within 5h window
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        ledger_path = f.name
        now = datetime.now(timezone.utc)
        for i in range(3):
            entry = {
                "ts": now.isoformat(),
                "issue_id": f"TEST-{i}"
            }
            f.write(json.dumps(entry) + "\n")

    try:
        # Patch the DISPATCH_LEDGER path
        original_ledger = usage_watcher.DISPATCH_LEDGER
        usage_watcher.DISPATCH_LEDGER = Path(ledger_path)

        # Get usage
        minimax_usage = usage_watcher.get_minimax_usage()

        # Verify 3% used (3/100 * 100 = 3%)
        expected_percent = 3.0
        assert minimax_usage["used_percent"] == expected_percent, \
            f"Expected {expected_percent}% used, got {minimax_usage['used_percent']}%"

        # Verify remaining
        assert minimax_usage["remaining"] == 97, \
            f"Expected 97 remaining, got {minimax_usage['remaining']}"

        print(f"TEST 2 PASSED: 3 dispatches = {minimax_usage['used_percent']}% used")

        # Restore original
        usage_watcher.DISPATCH_LEDGER = original_ledger

    finally:
        os.unlink(ledger_path)


def test_can_dispatch_80_percent_remaining():
    """
    Test can_dispatch with exactly 80% remaining (should be True)
    """
    usage_data = {
        "codex": {
            "used_percent": 20.0,
            "remaining_percent": 80.0,
            "resets_at": None,
            "source": "codex-api",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    }

    result = usage_watcher.can_dispatch("codex", usage_data)
    assert result == True, f"Expected True for 80% remaining, got {result}"
    print("TEST 3 PASSED: 80% remaining returns can_dispatch=True")


def test_can_dispatch_19_percent_remaining():
    """
    Test can_dispatch with 19% remaining (should be False - below 20% floor)
    """
    usage_data = {
        "codex": {
            "used_percent": 81.0,
            "remaining_percent": 19.0,
            "resets_at": None,
            "source": "codex-api",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    }

    result = usage_watcher.can_dispatch("codex", usage_data)
    assert result == False, f"Expected False for 19% remaining, got {result}"
    print("TEST 4 PASSED: 19% remaining returns can_dispatch=False")


def main():
    print("=" * 60)
    print("Running usage_watcher unit tests")
    print("=" * 60)

    try:
        test_codex_95_percent_blocked()
        test_minimax_3_dispatches()
        test_can_dispatch_80_percent_remaining()
        test_can_dispatch_19_percent_remaining()

        print("=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
