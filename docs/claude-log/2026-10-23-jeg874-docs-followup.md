## 2026-10-23 - JEG-874 docs follow-up (docs only)

Contract: finish the JEG-874 sync after the day's later merges; cite the audit tickets JEG-875 to JEG-881; correct stale methodology status; index research posts; self-host doc banners. Docs only; base `origin/main` 35205b89.

### Changed
- `docs/risk-register.md`: GAP-GUARD-WEAKENING-AUDIT now cites JEG-875 to JEG-881; new rows GAP-TARGETS-FOLD-PIN-RAISED (JEG-877, needs Jeremy), GAP-CIRCULAR-BANNER-TEST-UNPROVEN (JEG-878), GAP-FINDER-HELD-GUARD-TAUTOLOGY (JEG-881), GAP-GUARD-LOOSENED-IN-804-852 (JEG-879, JEG-880); ticket index lines; JEG-916 and JEG-905 added to GAP-RENDER-MODULES-NO-TARGET evidence.
- `docs/methodology.md`: the "Pending, not live" block became "Live and pending": JEG-804 (#814) and JEG-787 (#815) are merged; JEG-861 naming note ("Value above waivers" is the user-facing label); JEG-930 (#848) listed as pending.
- `docs/research/README.md`: posts 8 (stale blend note), 9 (pending, on open #837, not indexed by file), 10 (merged #847), three unindexed pages, Writing-route link note (JEG-905, JEG-916).
- `docs/v2-design-notes.md`: tab list is seven including Find a trade (#809 merged).

### Verified (check named)
- Ticket states and text read in Linear on 2026-10-23: JEG-874, 875 to 881, 905, 916.
- PR states by `gh pr view`: #814, #815 merged; #837 open. `gh pr list --state all`: #809, #826, #827, #829, #830, #833, #842, #843, #847 merged; #845, #848 open.
- DDF Value projections-only: `pipelines/value_reference.py` `DDF_FAMILY` maps blended to projection. Held predicate: `heldReason` in `app/v2/v2.js`. Label: `SHORT_METHOD` in `app/v2/v2.js` and `grep` of `app/v2` copy.
- Guard state on main: `grep -n` on `tests/test_v2_targets_render.py` (1080), `test_value_pipeline_engine.py` (no skip, bands `== 2`), `test_ddf_composite_value.py` (lines 589-592, 795), `test_v2_phone_fallback_font_render.py`, `test_v2_circular_banner_render.py` (conditionals at 177, 239), `test_v2_finder.py` (line 113).
- Seven tabs: `grep -o 'data-view=...' app/v2/shell.html`.
- `python -m unittest tests.test_doc_staleness tests.test_source_link_urls`: 11 tests OK (before and after).

### Claimed, not verified
- JEG-879's fixes read as present on main by reading assertions; the three modules were not run, and the ticket is still Backlog.
- Post 8's projections-only column being unaffected by #814 was not re-checked. No contract mirror test exists under that name in `tests/`; none run.
- No self-host docs remain to banner: `docs/selfhost-*.md` and `selfhost/` were removed by JEG-792 (#813; `docs/decisions.md` "JEG-792"). `git ls-files | grep -i selfhost` is empty. Remaining mentions are historical (decisions, risk register, mobile-plan notes path).
- Post 9's text was not read or copied (unmerged).
