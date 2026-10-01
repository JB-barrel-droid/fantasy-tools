#!/usr/bin/env python3
"""Build the Scale Agreement section for the monitoring dashboard.

For each as-published comparison source x position group, compares three
scales:

  anchor scale      - ESPN's positional peak (the chart's anchor), full_12
  native scale      - the source's PUBLISHED (pre-indexed) positional peak
  reindexed scale   - the source's REINDEXED positional peak (what the chart draws)

and derives per-cell verdicts that separate genuine inter-source disagreement
from artifacts our own indexation introduced.

Output: dist/modules/scale-agreement.json

Thresholds (documented, not tuned):
  BAND_LOW  = 0.80
  BAND_HIGH = 1.25
  Taken directly from the chart's own Chart Health "source-scale-agreement"
  check: curve-widget.js scaleAgreementDiagnostics() -> value-model.js
  PEAK_AGREEMENT_LOW / PEAK_AGREEMENT_HIGH. The dashboard must judge sources
  by the same band the chart judges them by; inventing a second band here
  would let the two disagree about what "agreement" means.

"Scale" means positional peak (max value per position group), matching the
Chart Health check's positionalPeaks(). Peaks are robust to deep-bench
coverage differences between sources; means/medians are not.

Verdict logic per (source, position) cell. Pure function -- unit-tested.

  The raw native_vs_anchor ratio is confounded by units: FantasyCalc publishes
  in the thousands, FantasyPros in tens. A 163x "ratio" is not disagreement,
  it is a different ruler. The verdict therefore compares SHAPES, not absolute
  scales:

  - native_shape[pos]  = native_peak[pos]  / max(native peaks)
  - anchor_shape[pos]  = anchor_peak[pos]  / max(anchor peaks)
  - shape_ratio        = native_shape[pos] / anchor_shape[pos]

  If the source's published curve has the same shape as the anchor (each
  position worth the same FRACTION of the source's top position), the source
  agrees with the anchor regardless of units.

  - "genuine disagreement": shape_ratio outside [0.80, 1.25].
    The source's PUBLISHED shape already differs from the anchor before any
    of our indexation touches it. Nothing we did caused this; it needs
    Jeremy's accept-vs-fix call, not a pipeline fix.
  - "indexation artifact": shape_ratio inside the band BUT reindexed_vs_anchor
    (reindexed_peak / anchor_peak -- both on the 0-70 indexed scale, so this
    ratio IS meaningful) outside it. The source's published shape tracks the
    anchor, but our reindexing moved it off the anchor's scale. This is a
    pipeline defect class -- the multiplier flattened or stretched the curve.
  - "agreement": shape in band and reindexed in band.

  The JSON still carries the raw native_vs_anchor and reindexed_vs_native
  ratios for transparency; the verdict uses the shape ratio for the
  native leg and the direct reindexed-vs-anchor ratio for the reindex leg.

Section status (for the fleet headline):
  - "bad"  if any cell is an indexation artifact (our bug -- fix it)
  - "warn" if any cell is a genuine disagreement but no artifact
           (honest signal -- needs Jeremy's call, not a pipeline fix)
  - "ok"   if every cell agrees

Razzball is included automatically once it appears as a comparison source in
the fixture; until then it is simply absent (not faked).
"""

import json
import os
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_PATH = os.path.join(REPO, "data/fixtures/current/comparison-sources-data.json")
PLAYERS_PATH = os.path.join(REPO, "data/fixtures/current/players.json")
OUT_PATH = os.path.join(REPO, "dist/modules/scale-agreement.json")

# --- Thresholds: must match the chart's Chart Health band -------------------
# value-model.js: PEAK_AGREEMENT_LOW = 0.80, PEAK_AGREEMENT_HIGH = 1.25.
# curve-widget.js scaleAgreementDiagnostics() uses these defaults for the
# direct (as-published) chart keys.
BAND_LOW = 0.80
BAND_HIGH = 1.25
BAND_SOURCE = (
    "Chart Health source-scale-agreement check "
    "(curve-widget.js scaleAgreementDiagnostics -> "
    "value-model.js PEAK_AGREEMENT_LOW/HIGH)"
)

POSITIONS = ["QB", "RB", "WR", "TE"]

ANCHOR_SOURCE = "espn"
ANCHOR_COMBO = "full_12"

# source -> combo used on the chart's default view
SOURCE_COMBOS = {
    "fantasypros": "full_12",
    "usatoday": "full_12",
    "fantasycalc": "full_12_qb1",  # chart default is 1QB (comparison-dashboard.js)
    "cbs": "full_12",
    "cbsros": "full_12",
    "razzball": "full_12",  # picked up automatically once wired
}


def in_band(ratio):
    return BAND_LOW <= ratio <= BAND_HIGH


def verdict_for(shape_ratio, reindexed_vs_anchor):
    """Data-driven verdict per cell. Pure function -- unit-tested.

    shape_ratio: (native[pos]/max native) / (anchor[pos]/max anchor).
    reindexed_vs_anchor: reindexed[pos]/anchor[pos] (both on indexed scale).
    """
    if not in_band(shape_ratio):
        return (
            "genuine disagreement",
            f"published shape {shape_ratio:.2f}x of anchor's shape is outside "
            f"the {BAND_LOW}-{BAND_HIGH}x band before any indexation",
        )
    if not in_band(reindexed_vs_anchor):
        return (
            "indexation artifact",
            f"published shape tracks anchor ({shape_ratio:.2f}x) but reindexed "
            f"is {reindexed_vs_anchor:.2f}x of anchor -- the reindex moved it",
        )
    return (
        "agreement",
        f"published shape {shape_ratio:.2f}x and reindexed "
        f"{reindexed_vs_anchor:.2f}x of anchor, both in band",
    )


def positional_peaks(values, pos_by_name):
    peaks = {pos: 0.0 for pos in POSITIONS}
    for name, v in values.items():
        if not isinstance(v, (int, float)):
            continue
        pos = pos_by_name.get(name)
        if pos in peaks and v > peaks[pos]:
            peaks[pos] = v
    return peaks


def main():
    fx = json.load(open(FIXTURE_PATH))
    players = json.load(open(PLAYERS_PATH))
    pls = players["players"] if isinstance(players, dict) else players
    pos_by_name = {
        p["name"].lower(): p["pos"] for p in pls if p.get("name") and p.get("pos")
    }

    sources_fx = fx.get("sources", {})

    # Anchor: ESPN full_12 modeled values (what the chart draws as the anchor)
    anchor_combo = sources_fx[ANCHOR_SOURCE]["combos"][ANCHOR_COMBO]
    anchor_peaks = positional_peaks(anchor_combo.get("values", {}), pos_by_name)

    # Anchor shape: each position's peak as a fraction of the anchor's top peak.
    # Unit-invariant -- this is what "the anchor's shape" means.
    anchor_max = max(anchor_peaks.values())
    anchor_shape = {
        pos: (anchor_peaks[pos] / anchor_max if anchor_max > 0 else 0)
        for pos in POSITIONS
    }

    result_sources = {}
    for src, combo_key in SOURCE_COMBOS.items():
        sdata = sources_fx.get(src)
        if not sdata:
            continue  # e.g. razzball until it is wired -- absent, not faked
        combo = sdata.get("combos", {}).get(combo_key)
        if not combo:
            continue
        native = combo.get("native", {})
        # DDF-modeled sources (cbsros) carry `values` instead of `reindexed`;
        # both are "what the pipeline puts on the chart".
        reindexed = combo.get("reindexed") or combo.get("values", {})
        native_peaks = positional_peaks(native, pos_by_name)
        reindexed_peaks = positional_peaks(reindexed, pos_by_name)
        native_max = max(native_peaks.values())

        cells = {}
        for pos in POSITIONS:
            a = anchor_peaks[pos]
            n = native_peaks[pos]
            r = reindexed_peaks[pos]
            if a <= 0 or n <= 0 or r <= 0 or native_max <= 0:
                cells[pos] = {
                    "anchor_scale": round(a, 2),
                    "native_scale": round(n, 2),
                    "reindexed_scale": round(r, 2),
                    "native_vs_anchor": None,
                    "reindexed_vs_native": None,
                    "reindexed_vs_anchor": None,
                    "native_shape_vs_anchor_shape": None,
                    "verdict": "insufficient data",
                    "verdict_reason": "anchor, native, or reindexed has no priced players at this position",
                }
                continue
            nva = n / a
            rvn = r / n
            rva = r / a
            shape_ratio = (n / native_max) / anchor_shape[pos] if anchor_shape[pos] > 0 else 0
            verdict, reason = verdict_for(shape_ratio, rva)
            cells[pos] = {
                "anchor_scale": round(a, 2),
                "native_scale": round(n, 2),
                "reindexed_scale": round(r, 2),
                "native_vs_anchor": round(nva, 3),
                "reindexed_vs_native": round(rvn, 3),
                "reindexed_vs_anchor": round(rva, 3),
                "native_shape_vs_anchor_shape": round(shape_ratio, 3),
                "verdict": verdict,
                "verdict_reason": reason,
            }
        result_sources[src] = {"combo": combo_key, "cells": cells}

    # Section status for the fleet headline
    verdicts = [
        cell["verdict"]
        for s in result_sources.values()
        for cell in s["cells"].values()
    ]
    if any(v == "indexation artifact" for v in verdicts):
        status = "bad"
        status_reason = "at least one cell is an indexation artifact -- the reindex moved a source off the anchor's scale"
    elif any(v == "genuine disagreement" for v in verdicts):
        status = "warn"
        status_reason = "sources genuinely disagree with the anchor at the native level -- needs accept-vs-fix call, not a pipeline fix"
    elif any(v == "insufficient data" for v in verdicts):
        status = "warn"
        status_reason = "some cells have insufficient data"
    else:
        status = "ok"
        status_reason = "every as-published source tracks the anchor's scale at native and reindexed level"

    counts = {
        "agreement": sum(1 for v in verdicts if v == "agreement"),
        "genuine disagreement": sum(1 for v in verdicts if v == "genuine disagreement"),
        "indexation artifact": sum(1 for v in verdicts if v == "indexation artifact"),
        "insufficient data": sum(1 for v in verdicts if v == "insufficient data"),
    }

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anchor": ANCHOR_SOURCE,
        "anchor_combo": ANCHOR_COMBO,
        "band": [BAND_LOW, BAND_HIGH],
        "band_source": BAND_SOURCE,
        "positions": POSITIONS,
        "scale_definition": "positional peak (max value per position group), matching Chart Health positionalPeaks()",
        "status": status,
        "status_reason": status_reason,
        "verdict_counts": counts,
        "sources": result_sources,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote {OUT_PATH}")
    print(f"  status={status}: {status_reason}")
    print(f"  verdicts: {counts}")
    for src, sdata in result_sources.items():
        flags = [
            f"{pos}={cell['verdict']} (shape {cell['native_shape_vs_anchor_shape']}x, rei {cell['reindexed_vs_anchor']}x)"
            for pos, cell in sdata["cells"].items()
            if cell["verdict"] != "agreement"
        ]
        for fl in flags:
            print(f"  {src} {fl}")


if __name__ == "__main__":
    main()
