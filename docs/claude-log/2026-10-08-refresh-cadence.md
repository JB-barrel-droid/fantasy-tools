## 2026-10-08 - Refresh cadence: cheap change probes, ingest on change (feat/refresh-cadence)

Jeremy's ask: refresh by each source's update frequency; find low-effort ways to see that a page
changed before a full scrape; define the week-over-week snapshot per source.

### Deliverable

| Source | Change signal used | Probe cadence (UTC) | Full ingest when | W/W snapshot (weeks lane rule) |
| --- | --- | --- | --- | --- |
| FantasyCalc | hash of (player id, value) for the three 12-team 1-QB lists | hourly at :05 | changed and ≥ 6 h since the last save; or 24 h; or probe failed; plus fixed Tue + Fri 13:07 saves | first pull at or after Tue 12:00 UTC of week N (fixed Tue 13:07 save guarantees one) |
| USA Today | the article the ingest's discover_url finds + its sitemap `<lastmod>` | every 3 h Mon–Thu at :35; 00:35 + 12:35 Fri–Sun | changed; or 20 h; or probe failed | latest revision of the Week-N article saved before week N freezes |
| FantasyPros | discovered article: JSON-LD `dateModified` + row-sorted tables hash | as USA Today | as USA Today | as USA Today |
| CBS | discovered article on www.cbssports.com: `dateModified` + tables hash (ETag kept, not hashed) | as USA Today | as USA Today | as USA Today |
| ESPN | hash of (player, period, appliedTotal) of the 2026 weekly projection blocks | every 4 h, 03:25–23:25 | changed; or 20 h; or probe failed | newest snapshot dated in week N |
| CBS rest of season | four stats pages, rows sorted, rows tied at the 100-row cutoff dropped | as ESPN | as ESPN | as ESPN |
| Razzball | the four pages' "Updated:" stamps + tables hash | as ESPN | as ESPN | as ESPN |

Retries: an un-acknowledged ingest is re-dispatched at the next slot after 50 min, at most 4 times
per fingerprint, then once per max age. The chain runs when an acknowledged fingerprint is new,
when the hourly vintage check sees a new content date, and daily at 11:45 (bake run).

### Verified (check named)

- **What each source exposes**: live HEAD/GET probes, 2026-10-08 10:35 UTC
  (scratchpad `probe_raw.py`):
  - FantasyCalc: HEAD 404, no ETag or Last-Modified, `Cache-Control: max-age=1200`.
  - USA Today:
    - article: weak ETag, `no-store`, JSON-LD dateModified.
    - monthly sitemap: ETag + Last-Modified, per-URL `<lastmod>`.
  - FantasyPros: no ETag, JSON-LD dateModified (10-06T16:31:34, published 16:27:55).
  - CBS article (sportsfly): ETag; a conditional GET returns 304; `max-age=5184000`.
  - CBS ROS: weak ETag, `private, max-age=0`.
  - Razzball: no ETag; JSON-LD dateModified frozen at 2026-07-13 (useless); the page's own
    "Updated: 2026-10-07 11:07:17 PM EST" stamp is present.
  - ESPN API: HEAD 405; JSON only.
- **CBS mirror serves a stale revision**:
  - Fetched the same Week-4 URL with gzip and identity encodings on both hosts.
  - sportsfly's gzip variant had dateModified 2026-09-29T19:02 and different tables.
  - sportsfly identity and www (both encodings) had 2026-09-30T17:33.
  - Diff: Zay Flowers 26/27.5/29 → 27/28.5/30; Jameis Winston, Emeka Egbuka and Matthew Golden
    moved.
  - `pull_cbs.pull` on the www URL returns the same 4 tables (36/43/44/17) as the sportsfly
    identity variant.
- **Vintage check 404**:
  - Run log of source-vintage-check 2026-10-08T10:00Z: PGRST205 for all 7 sources, changed=True.
  - `gh run list` shows rebuild-chain dispatched every hour.
  - With bare names, a read-only run (publishable key, gh_sbclient) returned all 7 vintages
    equal to the fixture.
  - origin/main's module under the same client still 404s.
- **Mid-week revisions are real**:
  - Supabase `source_trade_values`: USA Today Week 4 bake 10-02 differs from 09-29; 10-07
    equals 10-02.
  - CBS Week 4 was revised 09-30 (above).
- **Watcher**: scratchpad `watch*.py`, every 10 min from 10:40 UTC; FantasyCalc hourly after
  10:55. Results are in the "Watcher" section below.
- **FantasyCalc terms**: Terms of Usage and API docs rendered with headless Chrome. API docs:
  `/values/current` "should be cached ... and refreshed at most once per hour". See risk row
  GAP-FANTASYCALC-TERMS.
- **Probe dry-runs** (`source_probe.py probe --dry-run`):
  - All 7 sources ok.
  - With the merged multi-path discovery: CBS → Week 5 (`dave-richards-2026-week-5-trade-chart`,
    dateModified 2026-10-07T17:44) and FantasyPros → Week 5.
- **Tests**: `tests/test_source_probe.py` (46 tests), each guard paired with a broken variant.
  Broken variants covered:
  - a rule that ignores max age;
  - a rule that skips on probe failure;
  - a rule with no retry, and one with unbounded retries;
  - a whole-page hash, an order-sensitive hash, and a cutoff-tie-sensitive hash;
  - slug-guessing discovery;
  - schema-qualified vintage table names;
  - a chain dispatch that ignores a waiting run (the burst test queues exactly one extra run);
  - comparing a FantasyPros pull against an older bake.
- **Gate**:
  - Final branch state 35d8651 (merged origin/main with weeks-tidy, superflex and CBS
    versioning): `make sync` exited 0.
  - `make validate` with playwright unimportable
    (PYTHONPATH=scratchpad/noplaywright) exited 0.
  - Normal `make validate` fails only on `test_week_history.DeltaRecomputeTest`. It fails the
    same way on clean origin/main 59999c6: CBS Week 5 was promoted without a history entry. The
    integrator marked it known-red and it skips in CI.
  - `make test-unit`: `test_source_probe` passed 46/46. The run then stops at
    `test_adjustment_inputs` with "versioned adjustment-inputs missing:
    data/adjustment-inputs/ddf-20261008-..." — a main data artifact, not touched here.
  - No sweep: no change moves chart numbers. Probes, schedules and acks only. The CBS host change
    returns identical tables, and bake-id formats are not read by the importer, which selects by
    created_at.

### Claimed, not confirmed

- The source-probe workflow, ingest acks and chain dispatch have not run in Actions: no
  production dispatch before merge. First check after merge and SQL apply:
  `gh workflow run source-probe.yml -f dry=true`, and read the annotations.
- PostgREST upsert of `source_probe_state` with `on_conflict=source` and merge-duplicates, and
  the 60-day prune, are written but not executed: the lane has no write key.
- Weekly cadence numbers (3 h / 4 h / hourly) are reasoned from one day of watching, not from a
  week. `public.source_probe_log` will hold the real rhythm after a week.

### Watcher (2026-10-08, 10:40–13:10 UTC, Thursday)

Probed every source every 10 minutes and FantasyCalc hourly. One round, at 11:39, failed on a
local DNS blip and is excluded.

- **FantasyCalc** (5 pulls):
  - No value moved from 10:40 to 12:03.
  - Between 12:03 and 13:04, 192 of 197 players moved in all three scorings (e.g. Dak Prescott
    1663 → 1816, Josh Allen 6011 → 6123).
  - So the values recompute in batches (at least daily), not continuously. Against the
    2026-10-06 saved bake they had moved a lot (Saquon Barkley 4491 → 3337).
  - An hourly probe sees each batch within the hour; the 6-hour minimum between saves bounds
    the number of bakes.
- **USA Today, FantasyPros, CBS article, ESPN, Razzball**: 11–12 probes each, one fingerprint
  each. Nothing changed on a Thursday morning.
- **CBS rest of season**:
  - The first table hash changed 9 times in 2 hours, but no projection changed.
  - The pages list the top 100 players per position. Players tied on points reorder between
    requests, and players tied at the 100th row swap in and out (Corey Kiner / Andrew Beck at
    8.8, Justin Joly / Ja'Tavion Sanders at 4.1).
  - With rows sorted and cutoff ties dropped (`cbsros_stable_rows`), 10 probes from 12:24 to
    13:10 gave one fingerprint.
  - Consequence for the full pull (not changed here): which tied player fills the 100th row of
    a saved CBS ROS snapshot is chance. Those are fringe players near zero value.
- **Supabase history** (`source_trade_values` bakes; `cbs_ros_projections` / `razzball_projections`
  snapshot hashes):
  - Razzball changed on each of 10-01, 10-06 and 10-07; its page stamp reads
    "2026-10-07 11:07:17 PM EST", so it updates late evening US time.
  - CBS ROS changed on 09-30, 10-02 and 10-08.
  - USA Today revised Week 4 once mid-week.

### Follow-up: probe output fix (fix/probe-output)

- Verified, run 37784191326 (main, dry): all 7 probes ran, then the summary step failed with json
  "Expecting value". The CBS discovery line "[cbs] discovered week 5 chart: ..." was on stdout
  between the JSON lines.
- Fix:
  - `run_probe` redirects anything a probe prints to stderr.
  - `probe --out` writes the JSON lines to a file, and the workflow reads that file.
  - Pinned by `ProbeOutputTest`. Removing the redirect makes it fail; checked.
- Verified, run 37784444647 (`fix/probe-output`, dry=true): green, 7/7 "ingest (first)".
  - Fingerprints in CI equal the local ones (CBS ROS 767985420fcf…, ESPN 0090bb9fd7bd…, USA Today
    59561ffbb85e…). Probes give the same result from CI and from this machine.
- Migration split:
  - `source_probe_tables_20261008.sql`, part 1, already applied.
  - `source_probe_schedules_20261008.sql`, parts 2–4, not applied yet.
