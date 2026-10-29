## 2026-10-29 - JEG-1172 FantasyPros week 8 divergence (read-only diagnosis)

Contract: find out why FantasyPros was flagged investigate for week 8, freeze the evidence as offline fixtures with one test. Change no reporter, parser, resolutions file, live data or source feed.

### Verified (check named)
- The flagged report (`dist/modules/source-divergence.json` at `e2c191c`) reproduces exactly: `python3 pipelines/check_source_divergence.py --out <scratch>` in a worktree at `e2c191c`. Per-combo n, bias, outlier rate and examples match the committed report.
- In that run `content_week` was 8 but every chart was served week 7. The FantasyPros natives equal frozen `data/history/week-7.json`, 178 of 178 in all three scorings, with the same fingerprint. `tests/test_jeg1172_fantasypros_w8_trace.py` asserts the whole population (`test_whole_flagged_population_is_the_frozen_week7_chart`) and the fingerprint.
- On the real Week 8 article FantasyPros is ok: 42.4/44.1/44.7% at `e55755c`, 41.5/43.9/43.3% on main `b863069` (same command).
- native x one factor = shown value for five players in three scorings at both revisions. Negative mutations (2QB column, other combo factor, other week, missing read as a price) break it. `python3 -m unittest tests.test_jeg1172_fantasypros_w8_trace -v`: 13 tests OK.

### Claimed, not confirmed
- That the stored FantasyPros values match the published pages. The diagnosis covers the committed data only; a parse error at the source is not ruled out.
- Article dates come from fixture provenance. The raw captures are on the Actions runner only, and the live FantasyPros pages were not read.
- The stale `dist/modules/source-divergence.json` on main (still generated 2026-10-27) was not traced.

Details: `docs/research/JEG-1172/README.md`.
