## 2026-10-29 - JEG-621 Fantasy Sharks: CI block, relay transport, held weekly pull

Contract: bring Fantasy Sharks in as a source per the existing pattern, held
from DDF blends. The rest-of-year puller, saver, table, pulse reader and sync
workflow were already on main (#592, #610, #647), so this session checked why
the table is empty and added what was missing: a transport that can get past
the runner block, and the weekly projections the ticket lists, kept separate.

### Verified (check named)
- Old PRs: #592, #610 and #647 are on main; #608 and #616 were closed as
  superseded by #610 and #647 (GitHub PR reads). Nothing to close.
- `fantasysharks-supabase-sync.yml` failed 10 of 10 runs, 2026-10-19 to
  2026-10-29, each `FANTASYSHARKS PULL FAILED [SOURCE_BLOCKED] HTTP 403` on the
  `Segment=877` URL (Actions job logs of runs 39288115721 and 40819509048).
- `public.fantasysharks_projections` has 0 rows; the `source-probe-sharks`
  pg_cron job exists (read-only SQL, 2026-10-29).
- From this cloud session the site is out of reach by shell (proxy refuses the
  host). A web fetch of the bare `projections.php` returned an old default page;
  any query string got a client error.
- New tests: `tests/test_fantasysharks_relay_weekly.py` (18) pass; 15 of them
  error with the pipeline changes stashed. `tests.test_pull_fantasysharks`,
  `tests.test_sharks_savers`, `tests.test_fidelity_sharks`,
  `tests.test_source_probe` pass. Results of `make test-core` are in the PR.

### Claimed, not confirmed
- That Supabase egress gets past Fantasy Sharks' wall. The relay function
  (`supabase/functions/fantasysharks-fetch/index.ts`) is not deployed; deploying
  it is Jeremy's call.
- The weekly Period labels read "Week N" on the live page. The 2026-10-15 note
  says weekly segments 883 to 900 exist; this session could not see the page.
  The pull fails closed (SOURCE_LAYOUT) if no "Week N" option matches.
- Weekly row floors (QB 20, RB 35, WR 50, TE 30) are set below the rest-of-year
  floors without a live weekly count.
- Name mapping against live `public.players` is still unmeasured (no row has
  ever been saved).

Nothing reads the weekly snapshot; there is no weekly table or saver. No values,
blends or published output change.
