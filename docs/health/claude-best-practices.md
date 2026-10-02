# Claude lane: best practices for data, pipeline and dashboard health

JEG-79 (subtask of JEG-78). Written 2026-10-02 against `main` at `a484462`. I did not read the Muse or Codex documents before finishing this one.

## How to read this

Every row carries a basis tag so a claim's weight is visible:

- **[E]** established practice. Named from general engineering knowledge (SRE, data-quality and CI/CD practice). **I fetched no sources this session** (egress is restricted), so nothing here is cited to a URL and none of it was checked against a reference. Treat [E] as "widely held", not "verified".
- **[V]** verified here. The check is named in the row.
- **[J]** my judgement for this project.
- **[U]** unverified. What would settle it is stated.

"Today" is one of **yes / partly / no / unknown**.

The two non-negotiables from JEG-78 apply throughout: never show stale data or stale computes, and keep the dashboard's input flexibility (league size, scoring, roster shape, bench share, source toggles, user inputs).

## Summary of what I found

1. **Freshness is measured but mostly not enforced.** The committed freshness report lists 16 items; 7 are past their 2-day budget (`players.as_of` is 9 days old, `news.generated_at` 12 days, `pm_snapshot` 10 days) and only one item, `comparison.built_at`, is enforced. `enforced_expired_count` is 0, so nothing trips. [V: `app/trade-value-chart/assets/reference-freshness.json`, read 2026-10-02.]
2. **The one enforced clock cannot see input staleness.** `comparison.built_at` is reset to "now" on any single promotion (`pipelines/promote_comparison_section.py:216-219`), so promoting one fresh source makes the whole fixture look fresh while other inputs are old. [V: code read] That it is a poor staleness signal is [J].
3. **The scheduled CI rebuild chain has failed on every scheduled run on record (runs 3 to 9, seven in a row)** and the latest green chain was a **local** run (`runner: "local"` in `output/comparison-chain-status.json`). Nothing told a person; the failures surfaced in audits. [V: Actions run list; status file.] That no alert exists is [V] for workflows in this repo (no notify/issue/webhook step in any `.github/workflows` file); whether GitHub's default failure emails reach anyone is [U].
4. **At least one pipeline step fails open.** `espn-supabase-sync.yml` ends the scrape with `|| echo "Scraper failed, using existing data"`, so a scraper failure is a green job. [V: line 41]
5. **The deploy gate has a hole by design.** `pages.yml` blocks only if the last commit touched a file outside `dist/modules/`. A commit touching only `dist/modules/` (the bot's "Automated chain status" commit does) passes the gate even if `make validate` is red, and so does the 11:30 scheduled deploy if the last commit was one of those. [V: workflow logic read; **not exercised**, so whether it has ever shipped a red build is [U].]
6. **Guards have failed in both directions** this week: never fired (JEG-51), fired falsely (JEG-68), and passed while destroying coverage (JEG-67). Policy requires negative tests; enforcement is by reviewer discipline, not by a mechanism. [V: tickets and merged commits.]
7. **Documentation that the code depends on has drifted.** `docs/import-health-schema.md` is marked normative and still says "exactly five sources" with Razzball a hard exclusion; the importer now handles seven including Razzball. [V: file read vs `rebuild-chain.yml` import loop.]

## Data health

| # | Practice | Why it matters here | Today and the check | Cost |
|---|---|---|---|---|
| D1 | A freshness SLO per input, clocked on **content vintage**, not pull time [E] | A pull can succeed on an unchanged page and look fresh; a source can skip a week. | **Partly.** Import health uses vintage kinds and a dated daily rule; the report above has budgets, but 6 of 7 expired items are unenforced. [V] | Low to set; medium to decide which items matter to the page |
| D2 | Freshness enforced **where the value is used** (the page refuses, or labels, stale values), not only reported [E] | Your first non-negotiable. A report nobody reads is the same as no check. | **Partly.** `comparison-dashboard.js` has `sourceIsStale` labelling (lines near 732, 887, 1075). [V: exists] Whether the live page shows them for the 7 expired items, and which of those items the page displays at all, is [U]. Settle with a rendered check of production. | Medium |
| D3 | **Staleness computed, not asserted**: each derived artifact records the hashes/vintages of the inputs it was built from; "stale compute" means recorded inputs differ from current inputs [E] | A curve or pie can be recomputed from new inputs yet served from old ones. A timestamp cannot detect that; a hash can. | **Partly.** `artifact_hashes` exist in the freshness report (4 files); the chain checks each leg's vintage before promotion (`rebuild_comparison_chain.py:494`). [V: read] No per-artifact input-hash record on the served fixture. [J] | Medium |
| D4 | Contract checks at ingestion: columns, types, ranges, uniqueness [E] | Prevents silent shape changes from upstream. | **Partly.** Unique indexes and saver tests exist (e.g. `razzball_projections` unique on `(player_key, razzball_snapshot_date)`); import health checks row counts. [V] | Low |
| D5 | **Vintage-over-vintage anomaly checks**: row-count delta, value-distribution shift, rank-correlation with the prior vintage [E] | The ESPN-zeroed-player class (a source pricing a player another source zeroes) is a drift symptom. | **Partly.** The ESPN-zero signal and cross-source agreement exist (JEG-51, merged). A generic check against the prior vintage: **unknown**, not found in `pipelines/`. [U] | Medium |
| D6 | Identity and join integrity with an explicit quarantine for unmatched or ambiguous rows, and measured coverage [E] | Wrong or dropped players are invisible in totals. | **Yes, with a gap.** The Razzball saver sent 9 of 701 rows to review instead of guessing. [V: my JEG-18 dry run on the real snapshot.] The curly-apostrophe mismatch (21 players) was found only by running the real file, not by synthetic tests. [V] | Low; the lesson is to test on real files |
| D7 | Provenance and lineage: every served number traces to source, vintage and content hash [E] | Lets you answer "where did this value come from" in minutes. | **Partly.** `payload_hash` on snapshots; `_run_id` / `_writer_identity` on rows; `build_source_value_lineage.py`. [V: seen] No `bake_id` on the Razzball snapshot. [V] | Low |
| D8 | Raw inputs live in **durable shared storage**, never only on one person's machine [E] | Single-machine inputs are a stale-data generator (the person is away, the machine is off). | **Partly.** Seven sources now round-trip through Supabase; ESPN, CBS ROS and FantasyCalc pulls run in CI. The Razzball puller is not in the repo, and the ESPN/CBS pull-in-CI move was raised on JEG-55. USA Today, FantasyPros and prediction-market pulls: **unknown** where they run. [U: `docs/watchdog.md` says the watchdog reads a goal-workspace on one machine, dated 2026-09-22 and may be out of date] | Medium to high |
| D9 | Missing is never zero [E] | A zero silently prices a player at nothing. | **Yes per register** (CTL-003 "Controlled"). [U: I did not re-test this] | Low |

## Pipeline health

| # | Practice | Why it matters here | Today and the check | Cost |
|---|---|---|---|---|
| P1 | **Fail closed** at promotion gates, with a visible verdict [E] | A bad leg must never overwrite a good fixture. | **Yes.** The chain publishes status only when red and never publishes the partial fixture (`rebuild-chain.yml`, "Publish chain status only"). [V: read] | Done |
| P2 | **Alert a person** when a scheduled job is red longer than its SLO [E] | Without it, a red chain is found by an audit, not by the system. | **No.** Runs 3 to 9 all failed; no notification step exists in any workflow. Default GitHub emails: [U]. | Low |
| P3 | **No fail-open steps**: a failed pull must fail the job or raise a flag, never continue quietly [E] | A silent pull failure is the cheapest way to go stale. | **No.** `espn-supabase-sync.yml:41` (`|| echo "Scraper failed, using existing data"`). The CBS ROS workflow does fail closed (`steps.scrape.outcome == 'success'` gate). [V] | Low |
| P4 | Idempotent, vintage-keyed, re-runnable writes [E] | Lets any run be repeated safely. | **Yes.** Upserts keyed on `(player_key, vintage)`; saver tests cover it. [V] | Done |
| P5 | **One canonical runner**; local runs are labelled and never the thing production quietly depends on [E] | If the green fixture comes from a laptop, the "automated" chain is decorative. | **Partly.** The current fixture came from a `runner: "local"` run while the scheduled CI run failed (12:43 UTC, run 9). [V: status file and Actions list] | Medium |
| P6 | **A deploy gate that cannot be bypassed by an unrelated commit** [E] | Your second line of defence for stale or wrong output. | **Partly.** See finding 5. The gate is intentional (monitor-only files should not need product tests) but its test is "what did the last commit touch". [V: read; not exercised] | Low |
| P7 | A pre-merge preview with a **rendered** gate [E] | Catches what unit tests cannot (page errors, pie sums). | **Yes.** `preview.yml` posts a build with a blocking rendered gate on every PR; self-test proves it can fail. [V: PRs #23, #30 comments] | Done |
| P8 | **Negative-tested guards**, enforced by mechanism not memory [E] | A guard that cannot fail is worse than none. | **Partly.** `CLAUDE.md` requires it. Evidence of the rule working: JEG-67 discrimination test. Evidence of it missing: JEG-51 (read a combo that does not exist), JEG-68 (false alarm). [V] Nothing mechanical checks that a new guard has a failing-state test. [J] | Medium |
| P9 | Reproducible builds with a manifest [E] | Same input, same bytes. | **Yes.** `test_dist_manifest.py`, preview manifest root. [V: seen in PR comments] | Done |
| P10 | **Environment parity**: one code path for credentials [E] | Divergence produces "works locally, fails in CI". | **Partly.** `rebuild-chain.yml` shims `sbclient` to a CI client "outside Muse"; two paths exist. [V: workflow comment] Whether they have diverged: [U]. | Medium |
| P11 | **Contract docs checked against code** [E] | A wrong "normative" doc misleads the next author. | **No.** Finding 7. [V] | Low |

## Dashboard health

| # | Practice | Why it matters here | Today and the check | Cost |
|---|---|---|---|---|
| B1 | A rendered-page gate that blocks on page errors and key invariants [E] | The page, not the files, is what you audit. | **Yes** for page errors and the DDF pie across 12 shapes; the other Chart Health checks warn rather than block. [V: `tests/rendered_gate/gate.mjs` header; PR comments] | Done |
| B2 | **As-of labelling and staleness state per displayed value** [E] | Directly your first non-negotiable. | **Partly.** See D2. The page also has a visible failure state ("comparison data could not be loaded", seen on JEG-8). [V: ticket evidence] | Medium |
| B3 | **Independent recomputation** of displayed values (a second implementation, or a golden) [E] | Catches wrong-but-plausible numbers, which unit tests on the same code cannot. | **Partly.** A Node guard harness runs the browser math against fixtures (`docs/guard-harness.md`; `tests/jeg68_markup_harness.cjs`). Whether any check recomputes in an independent implementation: [U]. | Medium |
| B4 | Guards tuned against **both** false alarms and silent non-firing; each has a "can fire" canary [E] | A noisy monitor trains people to ignore it; a silent one lies. | **Partly.** JEG-68 false alarm, JEG-69 knife-edge direction check, JEG-51 never fired. [V] | Medium |
| B5 | **Scheduled synthetic check of the live URL** (render production, assert invariants) [E] | Preview proves a PR, not what users get now. | **No.** I found no scheduled workflow that renders production. `verify_live.py` exists but is a manual script keyed to one fix set's markers and is not wired into any workflow. [V: `.github`, `verify_live.py`] | Medium |
| B6 | A single "is it healthy" signal that matches what the owner perceives [E] | You keep finding errors the monitor does not show, so the signal does not match your perception. | **Partly.** Chart Health panel and monitor exist; recurring audit findings after "fixed" suggest gaps. [J] Muse's recurring-finding list would settle this. | Medium |
| B7 | Accessibility and performance basics [E] | Secondary to correctness for this tool. | **Not assessed.** [U] | n/a |

## Staleness and input flexibility: how I would hold both (judgement)

[J] Three layers, none of which removes an input:

1. **Per-input vintage with a budget** (D1). A source that goes stale is *labelled and optionally greyed on the chart*, never silently included as current and never removed from the toggle list.
2. **Computed lineage** (D3). Each derived artifact stores the input vintages/hashes it used, and the page compares them to the current inputs. A mismatch is a stale compute. League size, scoring, bench share and custom inputs do not need to be frozen: they are part of the cache key, so any new setting recomputes live and is checked the same way.
3. **Enforcement at use** (D2/B2). The page shows an as-of next to each source and a banner when any displayed source is outside its budget or its compute is stale.

Risk to flexibility to watch: a freshness rule that hides sources by default would reduce what the user can compare. Prefer label-over-hide.

## Cheapest high-leverage steps (my ranking, [J])

1. Decide which of the 16 freshness items the page actually shows, enforce those, and retire the rest, so "expired" always means something. (D1, D2)
2. Remove the fail-open scrape (P3). One line.
3. Add an alert when the CI chain has been red for more than a set time (P2).
4. Add a scheduled render of the live page (B5).
5. Make the deploy gate also evaluate `make validate` on every run regardless of what the last commit touched, or document why not (P6).
6. Add a test that fails when `docs/import-health-schema.md` disagrees with the source list in code (P11).

## What I could not check

- The live production page (egress blocked), so D2/B2 behaviour on the 7 expired items is unverified.
- Who receives GitHub failure emails (P2).
- Where the USA Today, FantasyPros and prediction-market pulls run today (D8).
- Whether branch protection applies to `main`. Of the 20 most recent deploy runs (2026-10-02), 14 succeeded, 1 failed (JEG-73, caught by the gate and fixed in minutes) and 5 were cancelled by newer pushes; many are titled as direct pushes. [V: Actions list] Whether pushes bypass review: [U].
- Accessibility and performance (B7).
