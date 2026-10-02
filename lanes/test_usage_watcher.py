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


def test_chatgpt_95_percent_blocked():
    """
    Unit test: stubbed 95%-used chatgpt response => can_dispatch("chatgpt") is False
    """
    # Create stubbed usage data simulating 95% used
    usage_data = {
        "chatgpt": {
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

    result = usage_watcher.can_dispatch("chatgpt", usage_data)
    assert result == False, f"Expected can_dispatch to be False for 95% used, got {result}"
    print("TEST 1 PASSED: 95% used chatgpt returns can_dispatch=False")


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
        "chatgpt": {
            "used_percent": 20.0,
            "remaining_percent": 80.0,
            "resets_at": None,
            "source": "codex-api",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    }

    result = usage_watcher.can_dispatch("chatgpt", usage_data)
    assert result == True, f"Expected True for 80% remaining, got {result}"
    print("TEST 3 PASSED: 80% remaining returns can_dispatch=True")


def test_can_dispatch_19_percent_remaining():
    """
    Test can_dispatch with 19% remaining (should be False - below 20% floor)
    """
    usage_data = {
        "chatgpt": {
            "used_percent": 81.0,
            "remaining_percent": 19.0,
            "resets_at": None,
            "source": "codex-api",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    }

    result = usage_watcher.can_dispatch("chatgpt", usage_data)
    assert result == False, f"Expected False for 19% remaining, got {result}"
    print("TEST 4 PASSED: 19% remaining returns can_dispatch=False")


def test_unknown_lane_returns_false():
    """
    Test can_dispatch returns False for unknown lane name (fail closed).
    """
    # Test with completely unknown lane
    result = usage_watcher.can_dispatch("foo")
    assert result == False, f"Expected False for unknown lane 'foo', got {result}"
    print("TEST 5 PASSED: unknown lane 'foo' returns can_dispatch=False")


def test_claude_unknown_status_returns_false():
    """
    Test can_dispatch returns False for claude lane (status="unknown").
    Claude has no real data source yet, so it should fail closed.
    """
    # Test claude with unknown status
    usage_data = {
        "claude": {
            "used_percent": None,
            "remaining_percent": None,
            "remaining": None,
            "resets_at": None,
            "source": "none",
            "status": "unknown",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    }

    result = usage_watcher.can_dispatch("claude", usage_data)
    assert result == False, f"Expected False for unknown status, got {result}"
    print("TEST 6 PASSED: claude unknown status returns can_dispatch=False")


def test_minimax_depletion_marker_returns_zero_remaining():
    """
    Test get_minimax_usage returns 0% remaining when depletion marker exists.
    """
    # Create a temporary ledger with a depletion marker
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        ledger_path = f.name
        now = datetime.now(timezone.utc)
        # Add a depletion marker
        entry = {
            "ts": now.isoformat(),
            "event": "depleted",
            "lane": "minimax"
        }
        f.write(json.dumps(entry) + "\n")

    try:
        original_ledger = usage_watcher.DISPATCH_LEDGER
        usage_watcher.DISPATCH_LEDGER = Path(ledger_path)

        minimax_usage = usage_watcher.get_minimax_usage()

        assert minimax_usage["remaining_percent"] == 0.0, \
            f"Expected 0.0% remaining with depletion marker, got {minimax_usage['remaining_percent']}"
        assert minimax_usage["used_percent"] == 100.0, \
            f"Expected 100.0% used with depletion marker, got {minimax_usage['used_percent']}"
        assert minimax_usage.get("status") == "depleted", \
            f"Expected status='depleted', got {minimax_usage.get('status')}"

        print("TEST 7 PASSED: depletion marker returns 0% remaining, status=depleted")

        usage_watcher.DISPATCH_LEDGER = original_ledger
    finally:
        os.unlink(ledger_path)


def test_minimax_depletion_marker_not_counted_as_dispatch():
    """
    Test get_minimax_usage does NOT count event==depleted lines as dispatches.
    1 dispatch + 1 marker should = 1%, not 2%.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        ledger_path = f.name
        now = datetime.now(timezone.utc)
        # Add 1 dispatch
        dispatch_entry = {
            "ts": now.isoformat(),
            "issue_id": "TEST-1"
        }
        f.write(json.dumps(dispatch_entry) + "\n")
        # Add 1 depletion marker (should NOT count as dispatch)
        marker_entry = {
            "ts": now.isoformat(),
            "event": "depleted",
            "lane": "minimax"
        }
        f.write(json.dumps(marker_entry) + "\n")

    try:
        original_ledger = usage_watcher.DISPATCH_LEDGER
        usage_watcher.DISPATCH_LEDGER = Path(ledger_path)

        minimax_usage = usage_watcher.get_minimax_usage()

        # Should be 1% (1 dispatch), not 2%
        assert minimax_usage["used_percent"] == 1.0, \
            f"Expected 1% used (1 dispatch), got {minimax_usage['used_percent']}"
        assert minimax_usage["remaining"] == 99, \
            f"Expected 99 remaining, got {minimax_usage['remaining']}"

        print("TEST 8 PASSED: depletion marker NOT counted as dispatch (1% = 1 dispatch)")

        usage_watcher.DISPATCH_LEDGER = original_ledger
    finally:
        os.unlink(ledger_path)


def test_claude_depletion_marker_returns_zero_remaining():
    """
    Test get_claude_usage returns 0% remaining when depletion marker exists.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        ledger_path = f.name
        now = datetime.now(timezone.utc)
        # Add a depletion marker for claude
        entry = {
            "ts": now.isoformat(),
            "event": "depleted",
            "lane": "claude"
        }
        f.write(json.dumps(entry) + "\n")

    try:
        original_ledger = usage_watcher.DISPATCH_LEDGER
        usage_watcher.DISPATCH_LEDGER = Path(ledger_path)

        claude_usage = usage_watcher.get_claude_usage()

        assert claude_usage["remaining_percent"] == 0.0, \
            f"Expected 0.0% remaining with depletion marker, got {claude_usage['remaining_percent']}"
        assert claude_usage["used_percent"] == 100.0, \
            f"Expected 100.0% used with depletion marker, got {claude_usage['used_percent']}"
        assert claude_usage.get("status") == "depleted", \
            f"Expected status='depleted', got {claude_usage.get('status')}"

        print("TEST 9 PASSED: claude depletion marker returns 0% remaining, status=depleted")

        usage_watcher.DISPATCH_LEDGER = original_ledger
    finally:
        os.unlink(ledger_path)


def test_claude_no_ledger_returns_unknown():
    """
    Test get_claude_usage returns unknown when no ledger exists.
    """
    # Remove the ledger temporarily
    original_ledger = usage_watcher.DISPATCH_LEDGER
    usage_watcher.DISPATCH_LEDGER = Path("/tmp/nonexistent_ledger_xyz.jsonl")

    claude_usage = usage_watcher.get_claude_usage()

    assert claude_usage["used_percent"] is None, \
        f"Expected None used_percent, got {claude_usage['used_percent']}"
    assert claude_usage["remaining_percent"] is None, \
        f"Expected None remaining_percent, got {claude_usage['remaining_percent']}"
    assert claude_usage.get("status") == "unknown", \
        f"Expected status='unknown', got {claude_usage.get('status')}"
    assert claude_usage["source"] == "none", \
        f"Expected source='none', got {claude_usage['source']}"

    print("TEST 10 PASSED: claude no ledger returns unknown")

    usage_watcher.DISPATCH_LEDGER = original_ledger


def test_error_status_string_no_exception_repr():
    """
    Test that error status strings do NOT contain exception repr.
    We can't easily trigger the exception path, but we verify the source field
    doesn't have interpolation by checking the code doesn't use f-string with {e}.
    """
    # This is a code inspection test - verify the source string is short
    # We test by checking that ledger-error is a bare string
    # Create a scenario that would trigger an error - e.g., invalid ledger
    import io
    import contextlib

    # Patch the ledger to cause an exception during read
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        ledger_path = f.name
        # Write invalid JSON
        f.write("not valid json\n")

    try:
        original_ledger = usage_watcher.DISPATCH_LEDGER
        usage_watcher.DISPATCH_LEDGER = Path(ledger_path)

        result = usage_watcher.get_minimax_usage()

        # The source should be "ledger-error" (bare string), not "ledger-error: Exception(...)"
        assert result["source"] == "ledger-error", \
            f"Expected source='ledger-error', got '{result['source']}'"
        # Verify no exception repr in source
        assert "Exception" not in result["source"], \
            f"Source should not contain Exception repr: {result['source']}"
        assert "{" not in result["source"], \
            f"Source should not contain format braces: {result['source']}"

        print("TEST 11 PASSED: error status string is bare 'ledger-error', no exception repr")

        usage_watcher.DISPATCH_LEDGER = original_ledger
    finally:
        os.unlink(ledger_path)


def main():
    print("=" * 60)
    print("Running usage_watcher unit tests")
    print("=" * 60)

    try:
        test_chatgpt_95_percent_blocked()
        test_minimax_3_dispatches()
        test_can_dispatch_80_percent_remaining()
        test_can_dispatch_19_percent_remaining()
        test_unknown_lane_returns_false()
        test_claude_unknown_status_returns_false()
        test_minimax_depletion_marker_returns_zero_remaining()
        test_minimax_depletion_marker_not_counted_as_dispatch()
        test_claude_depletion_marker_returns_zero_remaining()
        test_claude_no_ledger_returns_unknown()
        test_error_status_string_no_exception_repr()

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
