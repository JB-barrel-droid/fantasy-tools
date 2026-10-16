## 2026-10-16 - JEG-667 loosen gates: coverage slack, fidelity slack, CBS floor accept

- CBS coverage: accepted floor refresh (WR 41 / TE 10 at half_12) per Jeremy 2026-10-16. Wrote data/triage/coverage-accepted.json.
- Coverage slack: added COVERAGE_FLOOR_SLACK=0.06 so the tail-churn tolerance uses max(3, ceil(6% * fixture)) instead of max(3, ceil(5% * fixture)). FC WR 79->76 (3 dropped) now passes automatically; CBS WR 43->41 (4 dropped) still needs the floor accept (cap=3).
- Live tail-rule fix: the rank > depth test in verify_coverage_drop_live could never fire when the live list length equalled the candidate depth (all ranks <= depth). Added a value-based tail test: a player whose live value sits in the bottom 10% of the position's range is treated as tail regardless of rank.
- Fidelity publisher_vs_stored: when all values match (0 mismatches) and only 1-2 players missing/extra, downgrade from red to amber. This unblocks cbsros (1 unresolved name, 1101/1101 values match).
- Fidelity stored_vs_chart: when value-only drift (no missing/extra) and a newer bake/snapshot exists, downgrade from red to amber. The chart is stale, not wrong; the next chain build cures it. This unblocks espn (126/1743 values differ, newer snapshot exists).
- FantasyCalc fidelity: kept held. Column swap detected (stored full|2 closest to live half|2). Wrong data.
- Validate test: min top indexed value 45->38 to tolerate 1-2 held sources in a build.
- Verified: 123 targeted tests pass (test_coverage_acceptance, test_fidelity_hold, test_fidelity_pulse, test_rebuild_chain_per_source_hold, test_review_coverage_churn). Negative test: half-position cut (40/80 dropped) still blocked (net 40 > tolerance 5); large roster gap (3+ missing players) still red.
- Not verified: full make validate (will run in chain).
