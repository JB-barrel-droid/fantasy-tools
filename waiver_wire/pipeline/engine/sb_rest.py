"""sbclient-based replacements for mgmt.query.

The Supabase MANAGEMENT API (mgmt.py's SQL runner) is returning 400s; the
direct data API via sbclient works. Everything here is PostgREST REST.
"""
import os
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.expanduser("~"), "workspace", "skills", "supabase-football-signal", "bin"))
import sbclient  # noqa: E402


def eq(v):
    """URL-encode a value for an eq. filter (timestamps contain + and :)."""
    return quote(str(v), safe="")


def latest_as_of(table="lottery_valuations"):
    rows = sbclient.get(table, "?select=as_of&order=as_of.desc&limit=1")
    return rows[0]["as_of"] if rows else None


def valuations_at(as_of):
    """Latest-run lottery_valuations rows (exact as_of match)."""
    return sbclient.get_all(
        "lottery_valuations",
        f"?select=valuation_id,player_key,position,team,owned_option_ev,"
        f"base_option_ev,"
        f"lottery_score,primary_mechanism,availability_tier,component_json"
        f"&as_of=eq.{eq(as_of)}")


def board_at(as_of):
    """v_lottery_board rows for one run, score-ordered."""
    return sbclient.get_all(
        "v_lottery_board",
        f"?select=*&as_of=eq.{eq(as_of)}&order=lottery_score.desc")


def patch_rows(table, id_col, updates, retries=4):
    """Sequential per-row PATCH with retry on transient failures
    (504/502/429/connection resets). Idempotent: safe to re-run."""
    import time
    n = 0
    for rid, fields in updates:
        last = None
        for attempt in range(retries):
            try:
                sbclient.patch(table, fields, f"?{id_col}=eq.{eq(rid)}")
                last = None
                break
            except Exception as e:
                last = e
                time.sleep(2 * (attempt + 1))
        if last is not None:
            raise last
        n += 1
    return n
