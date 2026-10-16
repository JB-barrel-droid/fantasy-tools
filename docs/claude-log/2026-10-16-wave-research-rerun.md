# Wave research re-run on settled convention (2026-10-16)

## What

Re-ran bench research scripts and updated docs/posts after JEG-562 (expected
starts on convention), JEG-563 (default roster 2 WR / 7 bench / K / DEF), and
JEG-630 (JS engine parity) all merged.

## Verified

- `tools/bench_research/bench_share_bounds.py` ran on all 12 settings (config params).
  ppr/12: fill-in floor 9.3%, recommended 9.7%, VORP ceiling 20.2%.
- `tools/bench_research/bench_share_decomposition.py` ran on ppr/12.
  Displacement absorbs 82% of gross start-worthy gain (was 83% pre-convention).
  Pie = 2352 units (was 2688 with 8 starting slots; now 7 with 2 WR default).
- Bench share readout ppr/12: QB 6.4%, RB 7.7%, WR 13.0%, TE 2.5%, overall 10.0%.
  QB artifact (22.6%) resolved by convention tiers.
- ES-7 sensitivity ppr/12: m 0.5x-1.5x gives 9.3%-10.7%; sigma 0x-1.5x gives 9.1%-10.7%.
- Scorecard, draft_composition, depth_round_starts, insurance_upside, waiver_rule
  all run (script fixes for schedule JSON format and CSV column renames applied).
- Chart-ready JSON emitted to `output/bench-research/`.

## Updated

- `docs/research/bench-share-bounds.md`: added final convention table.
- `docs/research/bench-share-decomposition.md`: replaced with convention numbers.
- `docs/methodology.md` ES-7: bounds updated to 9.3%/20.2% at ppr/12.
- `docs/methodology.md` ES-14: readout updated to QB 6.4%, overall 10.0%.
- `docs/research/posts/01-bench-player-value.md`: replaced pending numbers.
- `docs/research/posts/02-how-many-backups.md`: updated evidence links, removed pending notes.
- `tools/bench_research/` scripts: fixed schedule JSON format, CSV column names,
  STARTERS_PER_TEAM -> _starters_per_team() API change.
- `tools/bench_research/README.md`: marked JEG-566 complete.

## Not changed

- Posts 03-06 (gated on JEG-505, not on this re-run).
- Insurance/upside and depth_round_starts numbers in the post body (the
  historical-data findings are from game logs, not from the convention change;
  the convention only changes the model-based numbers).
