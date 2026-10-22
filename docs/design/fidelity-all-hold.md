# Fidelity holds at a week boundary: every source held, chain fails closed

Design, JEG-799 (2026-10-22). Risk register row `GAP-FIDELITY-ALL-HOLD`.
Docs only: nothing here changes code. The decision for Jeremy is at the end.

Read with: `runbooks/source-held.md`, `docs/fidelity-tolerances.md`,
`docs/decisions.md` (`amber-hold-001`, JEG-726), `pipelines/fidelity_hold.py`,
`pipelines/fidelity_pulse.py`, `.github/workflows/rebuild-chain.yml`.

## 1. What happened (measured from run 39706506402 and the files on main)

Chain run 39706506402, dispatched 2026-10-22 01:35Z, NFL week 7
(content week 7 opened Tuesday 2026-10-20).

1. **Import** (`rebuild-chain.yml:112-130`) stamped: fantasycalc **Week 7**
   (594 rows), cbs **Week 7** (362), fantasypros **2026-10-20** (534; stored
   bake `fpwk7_2026-10-22t0035_v1`, saved 00:35Z), usatoday 2026-10-13
   (Week 6; the publisher's Week 7 article was not stored yet), espn, cbsros
   and razzball 2026-10-19.
2. **Chain** (`pipelines/rebuild_comparison_chain.py`) promoted every source:
   usatoday 3/3, fantasycalc 3/3, fantasypros 3/3, espn 1/1, cbs 3/3,
   cbsros 1/1, razzball 1/1 (log 01:36:09). The candidate build therefore
   carried Week 7 for the three charts that had Week 7 data.
3. **Fidelity hold** (`rebuild-chain.yml:319`, `pipelines/fidelity_hold.py`
   `cmd_apply`, line 147) read `dist/modules/fidelity-pulse.json` as committed
   at **00:55Z** (commit 70afae04, `checked_at` 00:54:20Z). That pulse was
   measured against the **live page**, i.e. the Week 6 build, forty minutes
   before the chain started. It held:

   | Source | Level | Stage(s) | Pulse summary (00:54Z) | Cured by this candidate? |
   | --- | --- | --- | --- | --- |
   | usatoday | red | freshness | publisher posted Week 7 30 h ago; chart shows Week 6; not stored yet | No (still Week 6) |
   | fantasycalc | red | publisher_vs_stored, freshness | 3/1116 values match: the stored bake `fcwk6_...t2205_v1` compared with the publisher's Week 7 page | **Yes**: candidate is the Week 7 bake |
   | fantasypros | amber | stored_vs_chart | chart equals `fpwk6_...`; newer stored bake `fpwk7_2026-10-22t0035_v1` is not on the chart yet | **Yes**: candidate is that bake |
   | cbs | red | scrape_validity | player count dropped vs week 5: stored TE 14->13, chart TE 14->10 | **Partly**: candidate is the Week 7 stored set (TE 13: a 7% drop, below the 10% red line, `DROP_RED`, `fidelity_pulse.py:150`) |
   | espn | red | publisher_vs_stored, stored_vs_chart | 824/1752 mismatches; publisher changed since the save (fingerprint); re-sync not landed; import health STALE 3 d | No |
   | razzball | red | stored_vs_chart | 50 stored players not on the chart; held since 2026-10-18 | No (a build defect, separate) |
   | cbsros | - | - | not held | - |

   `apply_fidelity_holds` (`fidelity_hold.py:81-107`) writes `validationHold`
   on every section of every held root with no check of **which build the
   pulse measured**. The pulse records what it compared (`identity`, the
   stored bake id or `snapshot@saved_at`; `fidelity_pulse.py:2173, 2259`) but
   `fidelity_hold.py` never reads it.
4. **Validate** (`rebuild-chain.yml:322`, `make validate`) ran
   `tests/test_launch_front_door.py::test_v2_table_equals_engine_and_guard_fails_on_drift`
   on the held candidate and failed at line 291:
   `AssertionError: 2 not greater than or equal to 3 : {'compared': 50,
   'skipped': 0, 'cells': 100, 'columns': 2, 'problems': []}`. Red holds hide
   a source's columns (`curve-widget.js:707-709`, `v2.js:2753-2762`); amber
   keeps them (JEG-726). Five reds plus one amber left too few series.
5. **Fail closed** (`rebuild-chain.yml:428-437, 459-480`): only the status
   files were committed (`31011f56 Automated chain status (chain failed;
   fixture not updated)`). The fixture on main, and the live site, stayed on
   the last successful build: **Week 6 charts, with only the espn and razzball
   holds** that were on the fixture already. The Week 6 fantasycalc numbers
   the pulse calls "red" are therefore still live, unlabelled: failing closed
   removed the label and kept the number.
6. **The loop.** The pulse runs after every chain run (`fidelity-pulse.yml`,
   `workflow_run`) and every 3 h (pg_cron `fidelity-pulse-live`). It measures
   the same live page, finds the same holds, `holds_changed` is false, so it
   does not re-dispatch the chain (`fidelity-pulse.yml:145-154`); the 6-hourly
   chain runs again and fails identically. `stored_vs_chart` "newer bake not
   on the chart yet" can only clear through a chain publish, which the hold
   prevents. The deadlock lasts until every held source clears on its own,
   which `stored_vs_chart` never does.

   JEG-676 found this exact deadlock for `freshness` and downgraded it to amber
   when the stored rows already have the new week (`fidelity_pulse.py:1299-1304`:
   "Red here would hold the source, strip it from the build that would cure
   it, and deadlock publishing (every source at once on a new week)"). JEG-726
   then made amber holds label-only. The pattern recurs one stage at a time
   because the root cause, applying a verdict about build N to candidate N+1,
   was never addressed.

### Local reproduction (measured, this worktree, origin/main 041c87af)

The pulse of commit 70afae04 applied to the committed fixture with
`fidelity_hold.apply_fidelity_holds`, `make sync`, then the front-door test
(script in the JEG-799 session log):

| Fixture variant | Holds applied | Result |
| --- | --- | --- |
| The run's holds | usatoday, fantasycalc, cbs, espn, razzball red; fantasypros amber | FAIL, `2 not greater than or equal to 3`, compared 50, cells 100 (the chain's exact failure) |
| Same six holds, all amber | six amber | OK |
| No holds | none | OK |

Surviving table series under the run's holds (probed in the built page):
`plotKeys = ['ddf_value', 'fantasypros']`, `vorpKeys = []`; cbsros is
eligible but not a default column; the header reads "7 sources not
updating". So the reader of an all-held build would see a DDF Value blended
from fantasypros (amber) and cbsros only, beside one FantasyPros column.

So the failure is entirely the hold level: the same data with amber labels
passes every gate. (`tests/test_seeded_hold_build.py` seeds only 2 of 7 roots,
both red, which is why this was untested.)

## 2. Is holding because stored data lags the publisher the right action?

No. Two different things are being called "red":

- **Wrong numbers**: the stored values differ from the publisher's values for
  the *same* content (a broken save), the chart differs from the stored set it
  was built from (a broken build; razzball's 50 missing players), a block of
  players missing (`BLOCK_SHARE`). These are what JEG-520 meant. Hide (red).
- **Old numbers**: the publisher has moved to Week 7 and we still serve Week 6.
  The Week 6 values are the publisher's own Week 6 values; they were right when
  published and the page already says which week a source shows
  (`weeks_behind`, "Prior week", JEG-675/721). Jeremy's rules: block only on
  wrong numbers; amber labels, red hides (#731). Lag is amber.

Today's code treats lag as red in three places:

1. `freshness` after `NEW_WEEK_GRACE_HOURS` = 24 h (`fidelity_pulse.py:1298`)
   unless the stored rows caught up (JEG-676). usatoday's hold.
2. `publisher_vs_stored` for a chart compares the publisher's *current* page
   with the stored bake the chart was built from, with no week check: Week 7
   vs Week 6 reads as "1113/1116 values differ, systemic" (fantasycalc). That
   is a category error, not a mismatch.
3. ESPN `publisher_vs_stored` "stale: the publisher changed since the save"
   when the re-sync has not landed. Jeremy (2026-10-10): "Amber, then re-sync";
   red only when a mismatch survives a fresh sync. A sync that never ran is
   lag, not a surviving mismatch.

Hiding last week's chart because this week's is not loaded yet gives the
reader nothing, and a DDF Value blended from fewer sources is a *worse* number
than one that includes a labelled prior-week source. The right action for lag
is: label the week, keep the source in DDF Value, and get the loader to run
(the pulse already dispatches re-syncs). Red is for data that is wrong.

Independently of that classification, **a hold must apply to the build it was
measured on.** The pulse's verdict on the Week 6 page says nothing about a
Week 7 candidate it has never seen; that candidate is checked by the pulse
that runs after the deploy, exactly as every unheld source's fresh bake is
checked today.

## 3. Options

What the reader sees, the risk of a wrong number, size, files, and the test
that proves it. "Now" numbers use the 2026-10-22 state above.

### A. Loosen the front-door test for the all-held degenerate case

Change `test_launch_front_door.py:290-292` so that when
`tests/_holds.held_source_roots(fixture)` covers all but one root, the test
accepts `columns >= 1` (the drift mutation at line 295 still needs one column
to prove itself). Seed an all-red variant in `test_seeded_hold_build.py`.

- **Reader sees now:** the held candidate publishes. Page: Week 7 data for
  fantasycalc, fantasypros, cbs present in the fixture but *hidden*; usatoday,
  espn, razzball hidden; cbsros alone, DDF Value from one projection, Trade
  targets and Compare degraded. Then, because the hidden sections are the
  Week 7 bakes, the next pulse clears fantasycalc, fantasypros and cbs
  (`held_chart_stage`, `fidelity_pulse.py:2062`; freshness reads the stored
  week) and the chain after that releases them: about two cycles, 6 to 12 h,
  of a one-source site.
- **Wrong-number risk:** none from the test change itself; the risk is a
  near-empty page and a DDF Value nobody should trade on. Does not stop the
  deadlock recurring every Tuesday; only shortens it.
- **Size:** ~15 lines. Files: `tests/test_launch_front_door.py`,
  `tests/test_seeded_hold_build.py`.
- **Proving test:** the seeded all-red fixture passes the front door, and the
  2% drift mutation still fails on it (negative half kept).

### B. Never hold every source at once / release the best available

Two shapes.

**B1, a quota.** If the holds would leave fewer than K (3) visible sources,
downgrade the least severe or newest holds to amber until K remain.

- **Reader sees:** whichever sources the tie-break picks, labelled. Arbitrary:
  on 2026-10-22 it would have shown usatoday Week 6 or espn's 3-day-old
  projections because they were "least bad", not because they were right.
- **Wrong-number risk:** real. A quota can un-hide a broken save (razzball's
  missing 50 players) to make a count. Violates "never publish a known flaw".
- Not recommended; listed because it is the literal reading of "never hold
  every source".

**B2, a hold applies to the build it measured (recommended).**

The pulse already knows what it compared. Record it on the hold, and have the
hold step skip a hold whose measured identity is not the candidate section's.
The next pulse (after every chain run, `fidelity-pulse.yml`) measures the
candidate itself and, if it is bad, `holds_changed` re-dispatches the chain,
which holds it with a matching identity.

Rule: `apply_fidelity_holds` applies a hold to a section only if the
section's identity equals `hold.measured_site` (what the live page showed when
the pulse ran) **or** `hold.identity` (the stored save the pulse compared).
Otherwise it prints `hold measured on <x>; candidate is <y>: not applied, the
post-deploy pulse checks it` and the section publishes unheld.

- Identity fields that exist today. Charts: `source_provenance.snapshot_fetched_at`
  and `content_vintage` (`site_meta`, `fidelity_pulse.py:728-740`; fantasycalc's
  live section says `2026-10-19T22:05:22`, the same save as the hold's
  `fcwk6_2026-10-19t2205_v1`). Projections: `snapshot_id` (sha256) and
  `lineage.raw_content_sha256`. The pulse's `identity` for projections is
  `snapshot@saved_at` (`:2173`); for charts the bake id (`:2259`). Chart
  sections do not carry the bake id, so the comparison is
  `snapshot_fetched_at` against the bake's `saved_at` within
  `ACK_MATCH_MINUTES` (15, the tolerance the pulse already uses to match an
  ack to a save, `:1735`), or the import writes `bake_id` into
  `source_provenance` (`import_supabase_references.py` already scopes rows by
  `bake_id`, line 456-463). Prefer the latter; it is one field.
- **Reader sees now:** fantasycalc, fantasypros, cbs at Week 7 (unheld, a
  fresh bake the pulse checks within one cycle); cbsros; usatoday Week 6 still
  hidden (same identity, freshness red) unless Q2 below says lag is amber;
  espn and razzball hidden (same identity, red). Four or more series: the
  front door passes, the chain publishes, the site moves to Week 7.
- **Wrong-number risk:** a fresh bake is live for one pulse cycle before the
  pulse has seen it: Pages deploy plus a pulse run (15 to 23 min measured on
  2026-10-22) plus a chain run (8 min), roughly 30 to 45 min. That is the same
  exposure every unheld source has today on every publish; B2 adds no new
  class of risk. A hold on the same save (a broken save, a broken build) still
  applies because the identity matches.
- **Size:** ~40 lines. Files: `pipelines/fidelity_pulse.py` (`hold_decision`,
  `:2114-2134`: add `measured_site` from `site_meta`), `pipelines/fidelity_hold.py`
  (`apply_fidelity_holds`, `:81-107`: identity check and the skip message),
  `pipelines/import_supabase_references.py` or the chain's promote step (write
  `bake_id` to `source_provenance`), `tests/test_fidelity_hold.py`,
  `tests/test_seeded_hold_build.py`, `runbooks/source-held.md`,
  `docs/fidelity-tolerances.md`. No hot file.
- **Proving test:** (i) the 70afae04 pulse as a fixture against a candidate
  whose fantasycalc, fantasypros and cbs sections carry a newer identity:
  those three are not held, usatoday, espn, razzball are, the front door
  passes; (ii) negative: the same pulse against sections with the measured
  identity holds all six and the front door fails with `columns 2`, proving
  the guard still catches the state it names; (iii) a hold on a broken save
  (identity equal) against a re-promoted section of the same save stays held.

### C. Order of operations: loaders refresh before the fidelity check

Make the producers run and the pulse re-measure before the chain holds.

**C1, scheduling.** Producers are dispatched by pg_cron change probes or at a
max age (`docs/watchdog.md`); the chain runs 6-hourly at :17, the pulse 3-hourly
at :40. Move the chain's boundary run after the Tuesday producer window.

- On 2026-10-22 the loaders *had* refreshed: fantasycalc, fantasypros and cbs
  Week 7 were stored before the chain ran, and the chain promoted them. The
  chain still failed because the pulse it read was measured on the old page.
  C1 does not touch the cause; it narrows the window in which it bites, and
  usatoday (not stored for 30 h) shows that producer timing is not something
  the schedule controls.
- **Reader sees:** unchanged on a day like 2026-10-22.
- **Size:** pg_cron migration only. Not recommended on its own.

**C2, measure the candidate inside the chain.** Run
`fidelity_pulse.py --site-json data/fixtures/current/comparison-sources-data.json
--out output/candidate-pulse.json` after the chain promotes and before the hold
step, then `fidelity_hold.py apply --pulse output/candidate-pulse.json`. The
`--site-json` flag exists (`fidelity_pulse.py:2463`).

- This is the principled version of B2: the hold is measured on the thing it
  holds. It also fixes usatoday-style lag only if Q2 reclassifies it.
- **Reader sees now:** fantasycalc, fantasypros, cbs at Week 7, checked
  against the publisher *before* publishing (no exposure window); the rest as
  in B2.
- **Wrong-number risk:** lowest of all options.
- **Cost:** the pulse fetches publishers (4 ESPN API calls, 4 CBS and 4
  Razzball pages, USA Today via the relay; 15 to 23 min per run measured) inside
  the deploy path. A publisher outage makes a stage `unknown`, which never
  holds, so the chain still publishes; but the chain's validate was made
  offline on purpose (GAP-MAIN-STATIC-PIN) and this adds 15+ min and network
  to every 6-hourly run. The workflow is on main and is being operated by
  another session this week.
- **Size:** ~10 lines of workflow plus a Supabase-credentialled step; the
  chain's pulse must not write `public.fidelity_runs` or dispatch re-syncs.
  Files: `.github/workflows/rebuild-chain.yml`, `pipelines/fidelity_pulse.py`
  (a `--no-dispatch` guard if needed).
- **Proving test:** the same (i)/(ii) fixtures as B2, run through the chain's
  hold step with a candidate pulse instead of the published one.

### Summary

| | Reader sees now | Wrong-number risk | Fixes the deadlock | Size |
| --- | --- | --- | --- | --- |
| A | one source for 6 to 12 h, then Week 7 | none, but a useless DDF Value | shortens it | 15 lines, tests only |
| B1 | arbitrary "least bad" sources | can un-hide a known flaw | yes | 30 lines |
| **B2** | Week 7 for the three refreshed charts, bad ones stay hidden | one pulse cycle, same as today's unheld path | yes | 40 lines, pipelines + tests |
| C1 | unchanged | unchanged | no | pg_cron only |
| C2 | Week 7, checked before publish | lowest | yes | workflow + 15 min/run |

## 4. Recommendation

**Now: B2**, then **C2 as the hardening step** once the Week 7 chain is clear
and the workflow is not being operated by hand (gates-slack-then-harden,
JEG-704 list). B2 is small, touches no workflow and no hot file, and its
negative test reproduces the exact chain failure. It needs no decision from
Jeremy: it does not change what a hold means, only which build it applies to.

Alongside, two classification follow-ups that **do** need Jeremy (Q2 below),
tracked as their own ticket after the decision:

- `freshness` red -> amber (label "Week 6; publisher has Week 7"), removing the
  24 h cliff at `fidelity_pulse.py:1284, 1298`.
- chart `publisher_vs_stored` compares like with like: when the publisher's
  week is newer than the stored bake's week, report lag (amber), not
  mismatch.

Not in scope here, each already a defect of its own: razzball's 50 missing
players (a build defect, red is right), ESPN's re-sync not landing for 3 days
(JEG-721 lane).

Option A is the fallback if B2 cannot land before the next Tuesday boundary:
it is 15 lines and gets the site to Week 7 within two cycles, at the cost of
a one-source page for up to 12 h.

## 5. Decision for Jeremy (multiple choice)

Plain English: at the start of each NFL week the publishers post new charts a
day before our loaders fetch them. Our checker compares the live site with the
publishers, sees "different", and tells the next build to hide those sources.
But that build already has the new data; hiding it leaves too little to show,
the safety test refuses to publish, and the site stays a week behind until
someone intervenes. Last week's numbers stay up, unlabelled, the whole time.

**Q1. How the hold should work (pick one).**

- **(a) A hold applies to the build it measured (B2).** Recommended. A source
  is hidden only when the checker has looked at the exact data being
  published and found it wrong. Fresh data publishes and is checked within
  the hour, the same as today for any source that is not held.
- **(b) Check the candidate inside the build (C2).** Strictest: nothing
  publishes unchecked. Adds 15+ minutes and publisher fetches to every
  6-hourly build, and edits the workflow another session is operating now.
- **(c) Let the near-empty page through (A).** Smallest change, in tests only.
  The site would show one source for 6 to 12 hours every Tuesday, then catch
  up.
- **(d) Do (a) now and (b) later** when the chain is stable. This is the
  recommendation.

**Q2. Is a last-week number a wrong number?** Today a source whose publisher
posted a new week more than 24 h ago is hidden, even though the page labels
it "Week 6" and the values are the publisher's own Week 6 values.

- **(a) No: lag is amber.** Keep showing Week 6, labelled, in DDF Value, until
  the new week loads; hide only when the numbers themselves are wrong.
  Recommended; consistent with #731 and JEG-726.
- **(b) Yes after 24 h (keep today's rule).** A source a day behind is hidden
  and DDF Value is built without it.
- **(c) Yes after a full week.** Label for 7 days, hide at two weeks behind
  (the point `rebuild_chain_source_held_stale` already turns red).

Answer format: "Q1 (d), Q2 (a)" is enough.
