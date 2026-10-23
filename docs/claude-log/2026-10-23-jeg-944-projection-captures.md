## 2026-10-23 - Store forward projections for all sources, all weeks ahead (JEG-944, parent JEG-943)

Contract: Jeremy 2026-10-23, store CBS ROS and Razzball week-ahead projections every week, append-only, with capture timestamp and source week; widened to all weeks ahead. Branch `data/JEG-944-weekly-projections`. Design and source findings: `docs/projection-captures.md`.

### What changed
- New table `public.source_projection_captures` (migration `jeg944_source_projection_captures_20261023.sql`), unique key, horizon/week rule, append-only trigger, RLS on.
- Hooks: `save_espn_weekly.py` (every unplayed week), `pull_cbs_ros_projections.py` + `save_cbsros_references.py` (ROS + current + next week), `save_razzball_references.py` (ROS).
- `check_projection_captures.py` gate, `backfill_projection_captures.py`, `pipelines/lib/projection_capture.py`, `tests/test_projection_captures.py`.

### Verified (check named)
- `python3.12 -m unittest tests.test_projection_captures` 24 tests OK; plus 139 existing tests in the espn/cbs/razzball/workflow/naming modules OK (163 total in one run).
- Seven mutations each made the new tests fail and the restored code passes: ESPN next-week-only, validator blind, overwrite instead of ignore-duplicates, fallback CBS page accepted, trigger removed, stored week rewritten, short capture passes.
- Migration applied to a throwaway local Postgres 17 (scratch dir, not any shared DB): duplicate insert ignored, UPDATE and DELETE raise, ROS with target_week 8 refused.
- CBS pages fetched live (read-only GET): week 7 and 8 parse (354 and 357 players); week 9 returns the week 7 page, detected as not offered.
- Razzball week-ahead: six URL patterns 404; weekly-rankings and next-week links soft-404.
- No published value changes: no file under `dist/`, `app/`, `data/` modified; committed `dist/` tree hash identical before and after (cce93496...); no build script imports the changed `main` functions (the other savers import helper functions from `save_razzball_references.py`, unchanged). `make sync` was not run, so dist was not rebuilt.

### Claimed, not verified
- The savers' capture step against a real database and the Tuesday first-run timing (needs the migration applied and one scheduled run).
- Size figures in `docs/projection-captures.md` are estimates.
- Whether CBS extends the week pages beyond next week later in the season.

### Not done
- Migration not applied, backfill not run (both write to a live database; waiting on Jeremy).
