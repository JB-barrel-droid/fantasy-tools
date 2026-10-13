# Bench Research Scripts

Analysis scripts from the 2026-10-10 bench research session (JEG-546, JEG-556,
JEG-557). Each script reproduces one or more findings from JEG-557 "How many
backups should a fantasy roster hold?"

## Scripts and findings

| Script | Finding | What it measures |
|--------|---------|------------------|
| `mix_proto.py` | 2 | Harness: force a bench mix, measure shares, rank correlation, inversions |
| `qb_diag.py` | 1 | QB 22.6% diagnosis: per-source waiver lines, Razzball data-bug detection |
| `depth_round_starts.py` | 5 | Starts per week by depth round from 2015-2025 game logs |
| `insurance_upside.py` | 6 (gross) | Insurance vs upside points, compared to hindsight-optimal bench |
| `waiver_rule.py` | 6 (net) | Net-of-waivers bench value, compared to best available pickup |
| `streaming_coverage.py` | 7 | Streaming coverage (circular, kept as cautionary example) |
| `draft_composition.py` | 9, 2 | FFC 2016-2024 draft composition, backups-per-starter ratios |
| `scorecard.py` | 10 | Five bench rules scored on fit, held-out fit, stability |

## Prerequisites

Run from the repo root with the Python 3.12 venv active. Scripts import from
`pipelines/` and read data from `data/inputs/` and `data/fixtures/current/`.

## Usage

```sh
# Standalone scripts
python3 tools/bench_research/scorecard.py
python3 tools/bench_research/draft_composition.py
python3 tools/bench_research/depth_round_starts.py --teams 12
python3 tools/bench_research/waiver_rule.py --teams 12 --scoring ppr

# The harness (mix_proto.py) is imported by other scripts
import tools.bench_research.mix_proto as mp
```

## Data sources

- `data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz`: nflverse weekly stats
- `data/inputs/nfl_schedule_2015_2025.json`: NFL schedule by team and week
- `data/fixtures/current/players.json`: current projections
- Fantasy Football Calculator ADP archives (2016, 2018, 2020, 2024)

## Status

Step 1 of JEG-566 (commit scripts). Steps 2-3 (re-run on merged convention
and new default roster, emit chart-ready CSV/JSON) are gated on JEG-562 and
JEG-563.
