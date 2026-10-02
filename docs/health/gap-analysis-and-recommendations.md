# Gap analysis and recommendations

JEG-83 (step 3 of the health program, JEG-78). Audits the project against `docs/health/best-practices.md` (the standard, JEG-82). Measured 2026-10-02 against `main` at `2dc857b`, between 17:10 and 17:30 UTC. Docs only: nothing was changed, and **nothing here is approved to build**. Jeremy decides which recommendations proceed (step 4, JEG-84, turns approved ones into tickets).

The two non-negotiables apply throughout: **never show stale data or stale computes**, and **keep input flexibility**.

## How to read this

Basis tags: **[V]** I ran the check today and it is named in the row; **[L]** taken from a lane document (Claude, Muse or Codex) and not re-run by me; **[U]** unverified. "Established practice" tags in the standard are still from general knowledge (no sources were fetched).

## 1. Summary

**What I found when I measured the live system instead of reading the docs** (all [V]):

1. **The ESPN daily CI scrape crashes on every run I checked and the job reports success.** The log of run 37036078925 shows `ModuleNotFoundError: No module named 'identity'`, then `Scraper failed, using existing data`, then `No fresh ESPN data, skipping Supabase save`. `public.espn_season_projections` has not been written since 2026-10-01 02:22 UTC (latest vintage 2026-09-30). Defect ticket: **JEG-102**.
2. **The dashboard cannot say a source is stale, and some of its dates are wrong.** Every per-source card carries a constant "Live" badge; the top "As of" and the "Source snapshot" labels both show the fixture-wide `built_at` (last promotion). The card's "content" date comes from a fallback chain over four different field names, and for three sources it shows a date **older than the content**: CBS, FantasyPros and USA Today show `content 2026-09-15` (the `published` field), while their content vintage is Week 4 / 2026-09-29. FantasyCalc shows its pull time (`2026-09-30`). There is no single vintage field (section 3.1).
3. **The monitor does not show that it is itself stale.** Six of the monitor's committed artifacts are 25 to 45 hours old (section 4).
4. **A derived compute is behind its input and nothing would show it.** The CBS ROS table's latest vintage is 2026-10-02 (last write 12:57 UTC); the promoted fixture section is vintage 2026-09-30. The lag is about four hours (inside one chain cycle, so not a failure today), but no check or label detects it.
5. **A ticket marked Done was never run in production.** JEG-71 (automate the CBS ROS pull) is Done; its workflow `cbsros-supabase-sync.yml` has **zero runs on record**.
6. **The bench-share slider leaves a stale caption.** The Weights readout keeps saying `Bench 15.0%` after the slider moves while the table changes. Defect ticket: **JEG-103**.
7. **The scheduled workflows start late.** ESPN's `11:30` cron started at 17:26 and 16:45 UTC (5 to 6 hours late); FantasyCalc's `11:45` at 17:29 and 16:50. Any freshness limit must allow for that slip.

**The inputs themselves hold up.** Scoring, league size, bench share, roster shape, a source toggle, lock mode and position weights all change the table, and each returns to byte-identical values when set back (section 5).

**Ranking** (full list in section 6): fix the broken ESPN path, alert a person, make the monitor show its own age, show per-source freshness honestly on the page, record input lineage, close the deploy-gate hole, and make "Done" mean "ran in production".

**Decisions only Jeremy can make** (from the standard, still open): (1) a source past its limit is shown **labelled and toggleable** or **hidden by default**; (2) a stale input **blocks a deploy** or only labels; (3) the named **recipient and hours** for red alerts. New in this document: (4) the freshness **limits for CBS, CBS ROS, FantasyCalc and FantasyPros**, which have no rule today and need an owner.

## 2. Method and limits

- Read the repo at `2dc857b`; ran headless Chromium (`/opt/pw-browsers/chromium`) against the built `dist/`; ran read-only SQL on the production Supabase project; read GitHub Actions run lists and one job log; computed artifact ages from committed files.
- **Could not check:** the live production page (egress blocked); who receives GitHub failure emails; branch protection on `main`; whether a live copy of the monitor files is fresher than the committed copy; the curve (canvas) values (my sweep fingerprints the player table, not the canvas).
- The input sweep ran at the default 12-team Full PPR shape for bench, roster, toggle, lock and weight changes; scoring and league size ran across all 12 shapes. **Mouse dragging of the bench slider was not tested** (my drag attempt did not move it).
- Two uncaught page errors appeared in my first sweep (`NotFoundError ... replaceChildren ... blur`). They did **not** recur when I used real typing and key presses, so I attribute them to my synthetic events and do not report a defect; whether a user could trigger it is [U].

## 3. Practice-by-practice audit

**Verdict:** Yes / Partly / No / Unknown. Row IDs match `docs/health/best-practices.md`.

### 3.1 Data

| ID | Verdict | Check and result |
|---|---|---|
| DH-1 content-vintage clocks | **Partly** | [V] Read all 11 fixture sections. Vintage is carried by different fields per source: `content_vintage` (CBS `Week 4`, USA Today and FantasyPros `2026-09-29`, FantasyCalc `Week 4`), `vintage` (Razzball 2026-10-01, CBS ROS 2026-09-30), `espn_snapshot` (ESPN 2026-09-30), `fetched_at` (pull time; the only date on the adjusted sections), and `published` (CBS, FantasyPros and USA Today: `2026-09-15`). The page shows the first present of `published`, `espn_snapshot`, `fetched_at`, `vintage` (`index.html` ~2252), so **CBS, FantasyPros and USA Today display `content 2026-09-15`, 14 days older than their content vintage; FantasyCalc displays its pull date**; only ESPN, Razzball and CBS ROS display a content date. |
| DH-2 per-source budgets | **Partly** | [V] `publication_windows.py`: rules only for USA Today (Tuesday + 1 day) and ESPN (2 days). CBS, CBS ROS, FantasyCalc, FantasyPros: "unverified". Freshness report: a uniform 2 days, one item enforced. |
| DH-3 staleness computed | **No** | [V] CBS ROS table latest vintage 2026-10-02 (last write 12:57 UTC) vs promoted section vintage 2026-09-30; adjusted sections carry no input hash or vintage. Nothing compares them. `comparison.built_at` is one fixture-wide stamp reset on any promotion. |
| DH-4 contract checks | Partly | [L] Lane documents; unique indexes and saver tests exist. Not re-audited. |
| DH-5 identity integrity | Yes, with a gap | [V earlier today] Razzball saver sent 9 of 701 rows to review instead of guessing; those 9 are still unresolved (8 alias names plus the Audric Estime duplicate). |
| DH-6 anomaly and drift checks | Partly | [V] `fantasycalc-drift.yml` has 2 scheduled runs on record, both "success", about 12 to 14 seconds each; I did not read their logs, so whether they did real work is [U]. No drift check exists for the other sources [L]. |
| DH-7 order invariants | Yes | [L] JEG-73's 16 pairs; not re-run. |
| DH-8 durable shared inputs | **Partly, with two broken paths** | [V] ESPN CI path crashes (finding 1). CBS ROS workflow has zero runs (finding 5); its table row for 2026-10-02 came from a non-CI run. Razzball puller is still not in the repo [V earlier]. |
| DH-9 provenance and writer audit | Yes | [V earlier] Razzball rows carry `_run_id` and `_writer_identity`; payload hash on the snapshot. |

### 3.2 Pipeline

| ID | Verdict | Check and result |
|---|---|---|
| PH-1 fail closed, atomic publish | Partly | [V] Workflow read: an import or health-check failure ends `rebuild-chain.yml` before the status-publish steps (GAP-040). |
| PH-2 alert a person; missed-run detection | **No** | [V] Scheduled chain runs 3 to 9 failed (seven in a row, latest 12:43 UTC); no notification step in any workflow. |
| PH-3 no fail-open steps | **No** | [V] `espn-supabase-sync.yml` line 41 swallowed a real crash today (finding 1). |
| PH-4 idempotent, content-keyed runs | Partly | [L]. [V] Scheduled starts drift by up to ~6 hours from the cron time (finding 7). |
| PH-5 one canonical runner | **No** | [V] The current green fixture came from `runner: local` while the scheduled CI chain was red; the CBS ROS row came from a non-CI run. |
| PH-6 deploy gate that cannot be bypassed | Partly | [V] Workflow logic read: a `dist/modules/`-only last commit skips the validate block; `pages.yml` has no rendered gate. **Not exercised.** |
| PH-7 preview with a blocking rendered gate | Yes, with gaps | [V] On every PR; the gate rejects zero shapes but not fewer than 12; only the pie is blocking. |
| PH-8 discrimination proof per guard | Partly | [L] Reactive: each guard gained its negative test only after failing (JEG-51, 67, 68). |
| PH-9 reproducible builds, one credential path | **Partly** | [V] The CI scraper cannot import `identity`, a module the local environment has: an environment-parity failure. Two credential paths remain [L]. |
| PH-10 rehearsed rollback | Unknown | [L] No drill found. Would be settled by running one. |
| PH-11 docs checked against code | **No** | [V earlier] `docs/import-health-schema.md` says five sources. |

### 3.3 Dashboard

| ID | Verdict | Check and result |
|---|---|---|
| BH-1 rendered gate on every path | Partly | [V] PR previews only (PH-6, PH-7). |
| BH-2 as-of per value, wall clock | **Partly** | [V] Page code read. Chart context does print `stale Week N values still shown` (`syncContext`) and a "Reference freshness pipe" card shows the stale-ref count and up to four items. But per-source cards show a constant `Live` badge; "As of" and "Source snapshot" are both `built_at`; no wall-clock expiry. |
| BH-3 independent oracle | Partly | [L] Guard harness runs the page's own math. |
| BH-4 computes bound to inputs | Partly | [V] Input sweep (section 5): values change with each input and return identically when set back. Lineage binding to fixture hash does not exist. |
| BH-5 scheduled live synthetic | Partly | [V] `verify_live.py` is manual; the last "30-min health push" commit on `main` is 2026-10-01 16:07Z. |
| BH-6 end-to-end fidelity | Partly | [V] `source-fidelity.json` is 45 hours old; JEG-77 is Backlog [L]. |
| BH-7 remediation and one healthy signal | Partly | [L]. |
| BH-8 monitor monitors itself | **No** | [V] Section 4. |
| BH-9 SLOs and error budget | Unknown | [L]. Would be settled by writing one SLI. |
| BH-10 accessibility and performance | Not assessed | |

## 4. Freshness contract audit (measured now)

Ages at 17:15 UTC on 2026-10-02. "Would anything notice" asks whether a check or label would show it if it went further stale.

| Artifact | Measured | Limit (contract) | Would anything notice? | What the page shows |
|---|---|---|---|---|
| ESPN rows (Supabase) | last write 10-01 02:22Z; vintage 2026-09-30 (about 2.7 days) | 2 days (existing) | Import health daily rule might; the chain was red for other reasons | Card: `content 2026-09-30`, badge `Live` |
| CBS ROS rows vs promoted section | table 2026-10-02; section 2026-09-30 | zero lag (derived) | **No** | Section vintage shown as-is, no lag signal |
| Razzball rows vs section | both 2026-10-01 | within limit | n/a | `content 2026-10-01` |
| FantasyPros section | content vintage 2026-09-29, fetched 2026-10-01 20:13Z, `published` 2026-09-15 | **undefined** | No | `content 2026-09-15` (the `published` date, 14 days older than the content) |
| USA Today section | content vintage 2026-09-29, `published` 2026-09-15 | Tue + 1 day (existing) | Import health (rule exists) | `content 2026-09-15` (same stale field) |
| CBS section | `Week 4`, fetched 09-29, `published` 2026-09-15 | **undefined** | No | `content 2026-09-15` |
| FantasyCalc section | `Week 4`, fetched 09-30 | **undefined** | No | `content 2026-09-30` (pull date) |
| Fixture `built_at` | 12:45Z (4.5 h) | not a freshness signal | Enforced, but only measures last promotion | Top "As of" |
| `pipeline-checkpoints.json` | generated 10-01 16:07Z (25 h) | 1 h (proposed) | **No** | Not shown |
| `github-actions.json`, `scale-agreement.json`, `aggregate-diagnostics.json`, `source-fidelity.json`, `index-math.json` | 39 h, 28 h, 41 h, 45 h, 45 h | 1 h (proposed) | **No** | Not shown |
| `source-import-health.json`, `comparison-chain-status.json`, `player-trace.json`, `data-accuracy.json` | 4.3 h, 4.5 h, 4.0 h, 14.7 h | 1 h (proposed) | No | Not shown |
| Rebuild chain (CI) | last scheduled run red at 12:43Z; last green was local | 12 h (proposed) | **No** (no alert) | `chain` status on monitor |
| Served page | not checked (egress) | digest = repo fixture | C10 operator-side, see BH-5 | n/a |

A stale-compute path nobody would notice is a finding: **the CBS ROS lag, the wrong content dates (three sources show 2026-09-15; FantasyCalc shows its pull date), and the monitor files** are three of them.

## 5. Input flexibility audit

Headless Chromium against the built `dist/`; fingerprint is a hash of every player-table row. [V]

| Input | Result |
|---|---|
| Scoring and league size (3 × 4 shapes) | Pie readout sums to 100.0 in all 12; changing away and back restores identical table (hash equal). |
| Bench share | Table changes at 25%; slider label and feasibility note update; returns identical at 15%. **Weights readout stays at `Bench 15.0%`** (JEG-103). Context line says `15% bench share` by design (frozen display share). |
| Roster shape (RB 2→3, FLEX 1→2, real typing) | Table changes each time; back to original is identical. |
| Source toggle (one of 14) | Off and on restores identical table. |
| Lock order (ESPN → disagreement → ESPN) | Context changes; restored identical. |
| Position weight (QB +5 points) | Pie still sums to 100; "Reset to defaults" restores identical. |

**No proposed health measure below constrains any of these.** Rule used: recommendations label or alert; none hides or freezes an input.

## 6. Recommendations (ranked)

Ranking weights Muse's recurring findings: (a) "fresh stamp, old numbers", (b) guards that pass while wrong, (c) guards that fail while right, (d) fix exists but is not wired through. Each lists what it closes, expected effect, cost, risk to flexibility, and the guard that proves it (negative-tested against a simulated broken state, per `CLAUDE.md`).

| # | Recommendation | Closes | Effect on staleness and errors | Cost | Flexibility risk | Guard (must fail on the broken state first) |
|---|---|---|---|---|---|---|
| R1 | Make the ESPN CI path work (provide `identity`, or an env equivalent) and remove the fail-open from every pull workflow; every pull ends with "acquired N rows at vintage V" or "unchanged since V". **JEG-102.** | DH-8, PH-3, PH-9; pattern (d) | Restores a daily source that has been silently stale; removes the cheapest way to go stale | Cheap | None | Workflow test fails on `\|\| echo` swallowing a non-zero exit; a CI import test fails on the missing module. A verification run needs Muse's approval (production write). |
| R2 | Alert a named person when any scheduled job is red for a set time, and run an independent deadline checker (last good write per source, last green chain) | PH-2 | Turns "found in an audit" into "told within hours" | Cheap (alert), Costly (checker) | None | Simulate a source table stale past its limit; the alert must fire. Needs the recipient (Jeremy decision 3). |
| R3 | The monitor shows its own age: every monitor artifact carries `generated_at`, the page goes red past twice the heartbeat; and decide where the heartbeat runs (CI or operator-side) | BH-8; pattern (a) | Ends 25 to 45 hour old monitor data passing as current | Cheap | None | Render the monitor with a 2-day-old `generated_at`; it must show red (it shows nothing today). |
| R4 | One uniform `content_vintage` field on every section (raw and adjusted); the page uses it, not `published` or `fetched_at`; per-source badge shows Live / Amber / Red against per-source limits; top "As of" shows the oldest displayed vintage, not `built_at` | DH-1, DH-2, BH-2; pattern (a) | Removes the wrong content dates (2026-09-15 on three sources, a pull date on FantasyCalc); stale sources become visible instead of "Live" | Costly | Low (labels, not hiding; Jeremy decision 1) | Fixture with a source 3 days old must render red (it renders `Live` today). Needs the four undefined limits (decision 4). |
| R5 | Record input lineage: each derived section stores the vintage and content hash of its inputs; page and monitor flag a mismatch with the current inputs | DH-3, BH-4; patterns (a), (d) | Detects the CBS ROS lag class and any stale compute | Costly | None | Serve a section built from older inputs; it must be flagged (the CBS ROS lag today is the real example). |
| R6 | Deploy gate: evaluate `make validate` on every run regardless of the last commit's files, and require the rendered gate on direct pushes. First **exercise** the current hole on a scratch branch | PH-6, BH-1 | Closes a path by which a red build could ship | Cheap | None | Scratch branch: red validate plus a `dist/modules/`-only commit must block; it currently would not (read, not exercised). |
| R7 | "Done" means ran in production: require a first successful run for any new workflow (JEG-71's workflow has none), and split Merged from Production-verified in Linear | DH-8, PH-5; pattern (d) | Stops closing tickets whose automation has never executed | Cheap | None | A ticket template check; for JEG-71, one real run of the CBS ROS workflow (production write, needs approval). |
| R8 | Turn the input sweep into a rendered check: change each flexible input, assert labels agree, and that away-and-back restores identical values; fix JEG-103 first | BH-4, flexibility contract; patterns (b), (c) | Catches stale captions and non-restoring inputs automatically | Medium | Protects flexibility | The sweep fails on the current build (stale readout). |
| R9 | Scheduled live-page check from CI (GitHub runners have the network that agents lack): run the rendered gate against the production URL daily, store the report as an artifact, alert on failure | BH-5, BH-1 | Removes you and the agents as the live detector | Medium | None | Point it at a deliberately broken preview; it must go red. |
| R10 | Allow for scheduler slip in every limit (observed up to ~6 hours late) and record `started_at` vs cron in status | PH-4 | Prevents false reds and false greens at the limits | Cheap | None | A limit test that fails if a run 6 hours late is treated as missed. |
| R11 | Test that normative docs match code (source list in `import-health-schema.md`) | PH-11 | Prevents the next author trusting a wrong doc | Cheap | None | Fails on today's "five sources". |
| R12 | Make a negative test a merge requirement for every new guard (checklist now, registry check later) | PH-8; patterns (b), (c) | Stops new silent non-firing and false-alarm guards | Cheap then Costly | None | A guard added without a failing-state test is rejected. |
| R13 | An independent oracle for displayed values | BH-3 | Catches wrong-but-plausible numbers | Costly | None | Seed a wrong value; the oracle disagrees. Defer until R1 to R9 are in. |
| R14 | Vintage-over-vintage anomaly checks for every source | DH-6 | Catches restated or corrupt vintages | Costly | None | Feed a corrupted vintage; it must flag it. Defer. |

**Suggested order:** R1, R2, R3 (the same day, all cheap); R6, R7, R10, R11 (cheap); then R4 and R8; then R5 and R9; then R12 to R14.

## 7. Defects found during the audit (tickets already open)

- **JEG-102** ESPN daily CI scrape crashes on a missing `identity` module; job passes green.
- **JEG-103** Weights readout keeps saying `Bench 15.0%` after the slider moves.

## 8. Not checked

- The live production page; GitHub failure-email routing; branch protection on `main`.
- Whether the monitor artifacts on the live site are fresher than the committed copies.
- Run 1 of the ESPN workflow (only run 2's log was read).
- The curve canvas values; mouse use of the bench slider; roster and bench changes at league shapes other than 12 teams Full PPR.
- Every "established practice" tag (no sources fetched).
