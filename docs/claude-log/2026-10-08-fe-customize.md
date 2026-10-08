# 2026-10-08 · Customize panel, league bar, root-source freshness (JEG-466 part 1, JEG-462, JEG-463)

Spec: JEG-474 (signed off on mock https://claude.ai/artifact/TYSXr7Wpg4SPiQpu2MTd56).

## Changes
- League bar: "Edit league" and "Weights & bench" are two equal secondary buttons; no ↗ on in-page dialogs (JEG-462).
- Methods bar replaced by one "Showing: …" line, a compact legend (symbol + name, prior-week badge) and one Customize button (JEG-466).
- Customize panel: series grouped by type (Projections, Trade charts adjusted, Trade charts as published, Advanced · Value above waivers collapsed), per-group Select all/none, Reset to default, draft until Done, empty selection blocked.
- Freshness panel shows one row per root source. Failures in the import or rebuild steps (`reference-freshness.json` `freshness_ok === false`) and paused series show as "Not updating since <date>", and the header chip warns (JEG-463).

## Verified
- `tests/test_v2_panels_render.py` checks the grouped checkbox picker, root-source freshness rows, and a routed `reference-freshness.json` with a failed FantasyPros import (row says "Not updating", "since 2026-10-06", chip says "1 source not updating"). New mutation "pipeline failure ignored" is caught.
- All 12 v2 render suites pass (before rebase). After rebase they were re-run (see commit).
- `make validate`: every suite passes except `tests.test_trade_chart_ingest_ci`, which fails locally on Windows because its harness runs bash with a POSIX `PATH` (`…:/usr/bin:/bin`) and a Windows temp dir. That's a back-end workflow test, not touched here; it runs in CI on Linux.

## Claimed (not verified by a test)
- Visual spacing of the two league buttons at 768–1023 px was checked by eye only.
- DDF section, the default "DDF Value + as-published charts", the shared per-tab picker and localStorage persistence (rest of JEG-466) wait on the back end's `ddf_value` series.
