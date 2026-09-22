#!/usr/bin/env python3
"""Canonical home of the trade-value chart's baked data.

2026-09-22: the legacy chart pipeline directory
~/workspace/football-signal/trade-value/ was retired (trade-value work now
lives in the fantasy-tools GitHub repo). The chart's baked players.json and
the dated actuals snapshots banked by chart builds live under the repo's
fixture dir. Every pipeline script and test that reads chart data resolves
through CHART_PLAYERS_JSON / CHART_DIR here, so the next move is a one-line
change instead of a 19-failure morning.

Both are overridable via env (e.g. tests pointing at a fixture copy):
CHART_PLAYERS_JSON wins outright; CHART_DIR sets the directory that
CHART_PLAYERS_JSON defaults under.
"""
import os
from pathlib import Path

REPO = Path(os.environ.get("FANTASY_TOOLS_REPO",
                   str(Path(__file__).resolve().parent.parent.parent.parent)))
CHART_DIR = Path(os.environ.get("CHART_DIR",
                                str(REPO / "data" / "fixtures" / "current")))
CHART_PLAYERS_JSON = Path(
    os.environ.get("CHART_PLAYERS_JSON", str(CHART_DIR / "players.json")))
