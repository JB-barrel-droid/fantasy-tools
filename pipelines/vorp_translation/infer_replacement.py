#!/usr/bin/env python3
"""Infer a publisher's implicit replacement level from their value curve.

Jeremy 2026-10-01: Publishers may not show a list that gets down to replacement
level, or they may go beyond but still assign positive values. We need to
consider this early and adjust before going further into the math.

Fluid: re-infer every bake from what they give us. Nothing static.
Supabase: read from source_trade_values, write inferred params back.
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "pipelines"))

# Position-specific starter counts for 12-team (our framework)
# Used to sanity-check inferred replacement levels
OUR_STARTERS_12T = {"QB": 12, "RB": 24, "WR": 36, "TE": 12}


def infer_replacement_level(values: list[float], pos: str) -> dict:
    """Infer the publisher's implicit replacement level for a position.
    
    Args:
        values: Sorted descending list of publisher's values for the position
        pos: Position string (QB, RB, WR, TE)
    
    Returns:
        {
            "replacement_level": float (the inferred value at replacement),
            "method": str (how we inferred it),
            "n_players": int,
            "min_value": float,
            "max_value": float,
            "is_truncated": bool (True if curve flattens at bottom = they stopped early),
            "confidence": str ("high"/"medium"/"low")
        }
    
    Logic:
    - If values hit 0 or near-0: replacement is 0 (they show it)
    - If values flatten at bottom (many tied at min): min is their effective
      replacement (they're saying "everyone below this is replacement")
    - If values are still declining at min: they stopped before replacement;
      extrapolate or flag low confidence
    """
    if not values:
        return {
            "replacement_level": 0.0,
            "method": "empty",
            "n_players": 0,
            "confidence": "low",
        }
    
    sorted_vals = sorted(values, reverse=True)
    n = len(sorted_vals)
    max_v = sorted_vals[0]
    min_v = sorted_vals[-1]
    
    # Count how many are tied at the minimum (flattening = truncation)
    n_at_min = sum(1 for v in sorted_vals if v == min_v)
    is_truncated = n_at_min >= 3  # 3+ tied at bottom suggests they stopped
    
    # Check if they're still declining (didn't reach replacement)
    # Look at the slope of the bottom 10%
    bottom_n = max(5, n // 10)
    bottom_vals = sorted_vals[-bottom_n:]
    # If bottom values are strictly decreasing, they didn't hit replacement
    still_declining = all(
        bottom_vals[i] > bottom_vals[i + 1] 
        for i in range(len(bottom_vals) - 1)
    )
    
    if min_v <= 0.1:
        # They show replacement (or near-zero)
        method = "explicit_zero"
        replacement = 0.0
        confidence = "high"
    elif is_truncated:
        # Flat bottom = their effective replacement level
        # They're saying "everyone at this value is replacement"
        method = "truncated_floor"
        replacement = min_v
        confidence = "high"
    elif still_declining:
        # They stopped before replacement; low confidence
        # We use min as a conservative proxy, but flag it
        method = "stopped_early"
        replacement = min_v
        confidence = "low"
    else:
        # Gradual flattening, use min
        method = "inferred_floor"
        replacement = min_v
        confidence = "medium"
    
    return {
        "replacement_level": replacement,
        "method": method,
        "n_players": n,
        "min_value": min_v,
        "max_value": max_v,
        "is_truncated": is_truncated,
        "still_declining": still_declining,
        "confidence": confidence,
    }


def value_over_replacement(value: float, replacement_level: float) -> float:
    """Convert publisher value to value-over-their-replacement."""
    return max(0.0, value - replacement_level)
