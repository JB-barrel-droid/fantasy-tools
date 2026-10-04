"""Backend parity reference for the OLS refit logic in `refitLiveCells`.

JEG-364b (JEG-327 Phase E, part 2 of 3): computation parity. Exact, faithful
port of the OLS refit logic from
`app/trade-value-chart/assets/curve-widget.js:2031-2081` (function
`refitLiveCells`). Every function here must match the JS implementation to
floating-point tolerance; the parity script
(`pipelines/check_refit_parity.py`) loads both sides against the same fixed
JSON vectors and reports mismatches.

Algorithm (mirrors curve-widget.js:2049-2074, the inner cell loop):

  for source in SOURCES:
    ddf = ddf_for_source(source)               # may be None -> skip source
    if not ddf: continue
    published = published_for_source(source)   # Map[playerKey -> value]
    if not published.size: continue
    for pos in TwoTier.POSITIONS:               # ["QB","RB","WR","TE"]
      if ddf.calibration[pos]?.invalid: continue
      for tier in ["starter", "bench"]:
        xs, ys = [], []
        for (playerKey, pub) in published:
          if ddf.posOf.get(playerKey) != pos: continue
          in_tier = (tier == "starter") == ddf.starters.has(playerKey)
                    if tier == "starter" else ddf.bench.has(playerKey)
          if not in_tier: continue
          y = ddf.values.get(playerKey)
          if not finite(pub) or not finite(y): continue
          xs.append(pub); ys.append(y)
        if len(xs) < 2: continue
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        sxx = sum((x - mx)**2 for x in xs)
        sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        if not (sxx > 0): continue
        beta = sxy / sxx
        alpha = my - beta * mx
        if not finite(alpha) or not finite(beta): continue
        cells.append({source, position: pos, tier, alpha, beta, n})

The inputs and outputs are pure data — no DOM, no closure state. The parity
test harness passes the same dict-shapes the JS code consumes, so both
sides see identical numbers and produce identical cells.

Conventions
- POSITIONS mirrors TwoTier.POSITIONS (curve-widget.js:196).
- Player keys are strings (JSON transport); the JS code coerces via Map.get
  and Set.has, both of which are exact-equality lookups. Passing strings
  on both sides keeps parity exact.
- Published values are floats; non-finite values (NaN/Inf) are skipped
  exactly like JS Number.isFinite skips them.
- The "starter" tier corresponds to ddf.starters.has(playerKey); the
  "bench" tier corresponds to ddf.bench.has(playerKey). Players in neither
  set are excluded (waiver tier — not adjusted, same as JS).
- A cell is omitted (not emitted) if any of the early-exit conditions hold:
  n < 2, sxx <= 0, alpha or beta not finite.

Do NOT change the formulas here. Mirror them. A parity mismatch is a defect
in either side.
"""
from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Constants (mirror TwoTier.POSITIONS at curve-widget.js:196).
# ---------------------------------------------------------------------------
POSITIONS = ["QB", "RB", "WR", "TE"]
# Mirrors the SOURCES enumeration at curve-widget.js:2038-2044 (the union of
# the two groups the refit loop walks). Listed in the JS source order so
# parity output is stable.
SOURCES = ["fantasycalc", "usatoday", "fantasypros", "cbs", "espn",
           "cbsros", "razzball"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _is_finite(x: Any) -> bool:
    """Mirror JS Number.isFinite — true for finite numbers only."""
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _key_set(d: Any) -> set:
    """Normalize a JSON-encoded Set/dict to a set of keys (strings)."""
    if d is None:
        return set()
    if isinstance(d, list):
        return {str(x) for x in d}
    if isinstance(d, dict):
        return {str(k) for k in d.keys()}
    return set(d)


def _keyed_map(d: Any) -> dict:
    """Normalize a JSON-encoded Map/dict to {str(key): float(value)}."""
    if d is None:
        return {}
    out: dict = {}
    for k, v in dict(d).items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# refit_live_cells
# ---------------------------------------------------------------------------
def refit_live_cells(inputs: dict) -> list[dict]:
    """Mirror refitLiveCells (curve-widget.js:2031-2081).

    `inputs` shape (matches the JS closure state at call time):

      {
        # source -> DDF two-tier snapshot. Each is None when ddfTwoTierValues /
        # ddfTwoTierValuesFor returns null (skip the source entirely).
        "ddf_by_source": {
          "fantasycalc": {
            "pos_of":     {"123": "QB", ...},   # Map playerKey -> pos
            "starters":   ["123", ...],          # Set
            "bench":      ["456", ...],          # Set
            "values":     {"123": 41.2, ...},    # Map playerKey -> value
            "calibration": {"QB": {"invalid": False}, ...},
          },
          "cbsros": None,                       # source skipped
          ...
        },

        # source -> published Map<playerKey, value>
        "published_by_source": {
          "fantasycalc": {"123": 35.0, ...},
          "espn":        {"789": 22.0, ...},
          ...
        },
      }

    Returns the list of emitted cells in source/position/tier order — same
    emission order as the JS `cells.push(...)` calls inside the nested loops.
    Each cell is {source, position, tier, alpha, beta, n}. Cells whose early
    exits trigger are omitted.
    """
    ddf_by_source = inputs.get("ddf_by_source") or {}
    published_by_source = inputs.get("published_by_source") or {}

    cells: list[dict] = []
    for source in SOURCES:
        ddf = ddf_by_source.get(source)
        if ddf is None:
            continue
        published = published_by_source.get(source) or {}
        if not published:
            continue

        pos_of = _keyed_map_to_str_keys(ddf.get("pos_of") or {})
        starters = _key_set(ddf.get("starters"))
        bench = _key_set(ddf.get("bench"))
        values = _keyed_map(ddf.get("values") or {})
        calibration = ddf.get("calibration") or {}

        for pos in POSITIONS:
            cal = calibration.get(pos) if isinstance(calibration, dict) else None
            if isinstance(cal, dict) and cal.get("invalid"):
                continue
            for tier in ("starter", "bench"):
                xs: list[float] = []
                ys: list[float] = []
                target_set = starters if tier == "starter" else bench
                for player_key, pub_raw in published.items():
                    pk = str(player_key)
                    if pos_of.get(pk) != pos:
                        continue
                    if pk not in target_set:
                        continue
                    y = values.get(pk)
                    if y is None:
                        continue
                    try:
                        pub = float(pub_raw)
                    except (TypeError, ValueError):
                        continue
                    if not (_is_finite(pub) and _is_finite(y)):
                        continue
                    xs.append(pub)
                    ys.append(y)

                n = len(xs)
                if n < 2:
                    continue
                mx = sum(xs) / n
                my = sum(ys) / n
                sxx = 0.0
                sxy = 0.0
                for i in range(n):
                    dx = xs[i] - mx
                    sxx += dx * dx
                    sxy += dx * (ys[i] - my)
                if not (sxx > 0):
                    continue
                beta = sxy / sxx
                alpha = my - beta * mx
                if not (_is_finite(alpha) and _is_finite(beta)):
                    continue
                cells.append({
                    "source": source,
                    "position": pos,
                    "tier": tier,
                    "alpha": alpha,
                    "beta": beta,
                    "n": n,
                })
    return cells


def _keyed_map_to_str_keys(d: Any) -> dict:
    """pos_of values are categorical — just normalize keys to str."""
    if isinstance(d, dict):
        return {str(k): v for k, v in d.items()}
    return {}