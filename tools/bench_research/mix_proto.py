#!/usr/bin/env python3
"""Bench research harness: shared helpers for forcing a bench mix into the
expected-starts model and measuring bench shares, pie shares, rank correlation
and inversions.

Reproduces: finding 2 (bench mix barely moves player values).

Source: 2026-10-10 bench research session (JEG-546 -> JEG-556 -> JEG-557).
Tiers are by blended value (the JEG-546 fix).

Usage:
    import mix_proto as mp
    ddf, met, inv = mp.evaluate(sources, teams=12, forced={"QB": 1, "RB": 9, "WR": 11, "TE": 3})
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO))

import expected_starts_model as es  # noqa: E402
import value_reference as ref  # noqa: E402
import derive_lineup_parameters as dl  # noqa: E402

POSITIONS = es.POSITIONS


def load_defaults():
    """Load the repo's current inputs and lineup parameters."""
    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    cfg = json.loads(dl.CONFIG.read_text())
    res = dl.resolve(cfg)
    params = {"bye": res["bye"], **{p: dict(res["positions"][p]) for p in POSITIONS}}
    return inp, params


# Monkeypatch dhondt to allow forcing a bench mix
ORIG_DHONDT = es.dhondt
FORCED = {}


def patched_dhondt(seats, weights, order=POSITIONS):
    if FORCED and set(weights) == set(POSITIONS) and weights == dict(es.BENCH_MIX_12):
        return dict(FORCED)
    return ORIG_DHONDT(seats, weights, order)


es.dhondt = patched_dhondt


def median_lists(sources):
    """Compute median projection lists across projection sources."""
    acc = {}
    for s in sources:
        if s.family != "projection":
            continue
        for p in POSITIONS:
            for k, v in s.lists[p]:
                acc.setdefault((p, k), []).append(v)
    return {
        p: sorted(
            (statistics.median(v) for (q, _), v in acc.items() if q == p),
            reverse=True,
        )
        for p in POSITIONS
    }


def retier(tiers, score, teams):
    """Re-tier players by blended score (the JEG-546 fix: tier on the list
    being valued, not on the mean of 3 projections while measuring 7 sources)."""
    lists = {
        p: sorted(
            (t["mean"] for t in tiers.values() if t["pos"] == p), reverse=True
        )
        for p in POSITIONS
    }
    counts = es.alloc(lists, teams)
    out = {}
    for p in POSITIONS:
        ks = sorted(
            (k for k, t in tiers.items() if t["pos"] == p),
            key=lambda k: (-(score.get(k) or 0), k),
        )
        for i, k in enumerate(ks):
            out[k] = {
                **tiers[k],
                "tier": (
                    "starter"
                    if i < counts[p]["starters"]
                    else ("bench" if i < counts[p]["rostered"] else "waiver")
                ),
            }
    return out


def evaluate(sources, teams, forced, params=None):
    """Force a bench mix and evaluate. Returns (ddf, metrics, inversions)."""
    if params is None:
        _, params = load_defaults()
    FORCED.clear()
    FORCED.update(forced or {})
    cs = es.chart_sigma_from(sources, teams)
    tiers = es.tiers_on_mean(sources, teams)
    run = es.run_setting(sources, teams, params, cs, "A")
    ddf = es.ddf_mean(run["adjusted"], sorted(tiers))
    met = es.shares_and_ratio(ddf, retier(tiers, ddf, teams), teams)
    inv = es.inversions(run["adjusted"], sources)
    FORCED.clear()
    return ddf, met, inv


def spearman(a, b, keys):
    """Spearman rank correlation between two score dicts over given keys."""
    ra = {k: i for i, k in enumerate(sorted(keys, key=lambda k: -a[k]))}
    rb = {k: i for i, k in enumerate(sorted(keys, key=lambda k: -b[k]))}
    n = len(keys)
    return 1 - 6 * sum((ra[k] - rb[k]) ** 2 for k in keys) / (n * (n * n - 1))
