# Best-practices standard: data, pipeline and dashboard health

JEG-82 (step 2 of the health program, JEG-78). Consolidates the three lane assessments merged on `main`: Claude (`claude-best-practices.md`, JEG-79), Muse (`muse-best-practices.md`, JEG-80) and Codex (`codex-best-practices.md`, JEG-81). Written 2026-10-02 against `main` at `bb51ebd`.

This is the **standard** that step 3 (JEG-83) audits the project against. It contains no recommendations to change code; it says what "healthy" means, how to check it, and how to tell when a check has stopped working.

## The two non-negotiables

1. **Never show stale data or stale computes on the trade value dashboard.** Stale means a source vintage, a derived fixture, or a computed curve, pie or table that is older than it should be, or built from inputs that have since changed. The page must refuse it or label it unmistakably, never show it silently as current.
2. **Preserve the dashboard's input flexibility.** League size, scoring, roster shape, bench share, source toggles and user inputs keep working. Health is never bought by freezing or removing an input.

## How to read this

Basis tags, as in the lane documents: **[E]** established practice named from general knowledge (**no sources were fetched for any lane, so none is cited or checked against a reference; treat [E] as widely held, not verified**), **[V]** verified by a named check, **[J]** judgement, **[U]** unverified. Where I checked something myself while consolidating, the check is named.

Lane references: `C-` Claude, `M-` Muse (section numbers), `X-` Codex (table and row).

Each practice has a **tier**: **Cheap** (hours to a day, mostly wiring existing parts) or **Costly** (several days or more). A **Cheap + high-leverage** subset is listed at the end.

## 1. Where the lanes agree, disagree, or were out of date

**All three agree on:**
- freshness must be clocked on content vintage, not pull time;
- the data path must not depend on one person's machine;
- gates should fail closed;
- every guard needs a test that proves it fails on the broken state;
- the project cannot yet tell a person that something is red or silently stale.

**Disagreements, and how I resolved them:**

| # | Topic | What the lanes said | Resolution |
|---|---|---|---|
| 1 | Is rendered-page verification in place? | Muse: **yes** (`verify_live.py`, checkpoint C10). Claude: **no** scheduled render of production. Codex: **partly/unknown**. | **Partly.** Verified here: C10 (`build_pipeline_checkpoints.py`) fetches the live served JSON and JS and checks content week and served bytes against the fixture, and is run by the operator-side 30-minute health push (per Muse's lane document and the commit titles; the last such commit on `main` is 2026-10-01 16:07Z, see BH-8). That is a live **data** check, not a rendered-DOM check. The rendered-DOM gate (`tests/rendered_gate/gate.mjs`) runs only in `preview.yml`. Verified: no workflow runs it against production and `pages.yml` never runs it. `verify_live.py` is a manual script. I was wrong to say "no" without mentioning C10; this corrects my lane document. |
| 2 | Are gates fail-closed? | Muse and Claude: yes. Codex: partly (partial per-source promotions; failures before the status step). | **Gates are fail-closed; publication is not atomic.** Verified by workflow read: an import or import-health step failure ends the job before the "publish chain status" steps run, so the monitor gets no status for that failure mode. Codex's refinement stands. |
| 3 | Is data acquisition machine-local? | Muse: **no**. Claude and Codex: **partly**. | **Partly.** Muse's text says the Razzball table holds 0 rows; that was true when written and is out of date (692 rows since 2026-10-02 11:32 UTC, verified read-only). ESPN, CBS ROS and FantasyCalc pulls run in CI; the Razzball puller is still not in the repo; where USA Today, FantasyPros and prediction-market pulls run is unverified. |
| 4 | Idempotent and deterministic builds | Claude: yes. Muse and Codex: partly. | **Different scopes, no conflict.** Writes are idempotent (upserts keyed on `(player_key, vintage)`). Full-chain byte determinism was not audited by any lane. |
| 5 | What to do first | Muse: finish JEG-77 (end-to-end fidelity vs the live publisher). Claude: enforce freshness and alert on red. Codex: no ranking. | **Complementary, not rival.** Fidelity checks look from the outside in; computed lineage and freshness enforcement look from the inside out. The standard requires both. Their order is step 3's call. |
| 6 | Does `make validate` pass? | Codex: it **failed** on its baseline `81b2a8d` in `test_vorp_translation_unified` (nine flex-count mismatches). | I ran `make validate` on `main` at `bb51ebd` today: **exit 0**. So `main` is currently green. I did not investigate the earlier red; whether it was fixed by a later commit is unverified. |

**Items only one lane raised, kept in the standard:** the monitor monitoring itself (new, from this consolidation; see BH-8); the rendered gate rejecting zero shapes but not fewer than 12 (Codex, confirmed by reading my own gate); checks reporting how many comparisons they actually ran (Codex); wall-clock expiry for an open browser tab (Codex); writer audit and versioned schemas (Muse, largely in place).

## 2. Data health

| ID | Practice and why it matters here | How to verify | Detect that it has stopped working | Today (lanes) | Tier |
|---|---|---|---|---|---|
| DH-1 | **Freshness clocked on content vintage, not pull, build or promotion time.** A re-pull of unchanged projections must not make them look current. [E] | Test: re-import byte-identical snapshot, vintage does not advance. Read the vintage derivation per source. | Scheduled check: a source whose vintage has not advanced past its window raises amber then red. | Partly (C-D1, M-2.1, X-D1). Import health and `check_reference_freshness.py` do it for some sources. | Cheap |
| DH-2 | **A per-source deadline and budget, with an owner and grace states.** Daily projections and weekly charts need different limits. [E] | One table: source, publication rule, grace, owner, red threshold. | A source with no rule is reported as "undefined", never as ok. | Partly (C-D1, X-D2). **Verified:** rules exist only for USA Today (Tuesday + 1 day) and ESPN (2 days); `publication_windows.py` marks CBS, CBS ROS, FantasyCalc and FantasyPros as unverified. | Costly (needs observed publication history) |
| DH-3 | **Staleness is computed, not asserted.** Each derived artifact records the vintage and content hash of the inputs it was built from; "stale compute" means the recorded inputs differ from the current ones. This addresses Muse's "fresh stamp, old numbers" recurrence. [E] | Change one input; the artifact built from the old input is flagged until rebuilt. Negative test: serve one built from an older hash and require detection. | A check counts artifacts whose recorded input hash differs from the current input, and must be able to return a non-zero count in a test. | Partly (C-D3, M-4.2, X-D7). `artifact_hashes` and leg-vintage checks exist at some boundaries; `comparison.built_at` is one fixture-wide stamp reset on any promotion (verified). | Costly |
| DH-4 | **Contract checks before valuation:** schema, units, ranges, uniqueness; null, unsupported and real zero kept distinct. [E] | Ingestion tests with malformed, non-finite and unexpected-version rows; missing-versus-zero test. | Row-count and null-rate deltas against the prior vintage. | Partly to yes (C-D4, C-D9, M-2.2, X-D4). | Cheap |
| DH-5 | **Identity integrity:** canonical player keys, fail closed on ambiguity, and a conservation report at each join (rows in, matched, quarantined). Real-file tests, not only synthetic. [E] | Join report per source; every unmatched or ambiguous row listed. | A drop in matched share, or a new quarantined name, between vintages. | Yes with a gap (C-D6, X-D5). **Verified earlier:** 21 Razzball players were lost on apostrophes and found only on the real file. | Cheap |
| DH-6 | **Vintage-over-vintage anomaly and live-publisher drift checks:** row counts, value distribution, largest movers, rank correlation, and a sample compared to the publisher's live page. [E] | Feed a corrupted vintage and a restated vintage; both must be flagged. | The check reports the number of comparisons it actually evaluated; zero evaluated is a failure, not a pass (X-P5). | Partly (C-D5, M-2.3, X-D6). FantasyCalc drift and the ESPN-zero signal exist; other sources have no drift check. | Costly |
| DH-7 | **Order and invariant checks across every value transformation** (if A above B going in, A above B coming out). [J] | A handful of fixed pairs per source, run on every rebuild. | The pair list is recomputed from data so it cannot go stale. | Yes (M-2.4, JEG-73's 16 pairs across 4 sources). | Cheap |
| DH-8 | **Raw inputs live in durable shared storage and can be re-pulled without one person's machine.** [E] | Clean-runner replay: delete local `data/raw`, run, and compare. | A scheduled pull that fails alerts a person (see PH-2, PH-3). | Partly (C-D8, M-2.5, X-D3). See disagreement 3. | Costly |
| DH-9 | **Provenance and writer audit:** versioned schemas; row-level `_run_id` and `_writer_identity`; payload hashes. [E] | Sample a served value and trace it to source, vintage, hash. | A row with no writer identity fails the import. | Yes (M-2.2, C-D7). No `bake_id` on the Razzball snapshot. | Cheap |

## 3. Pipeline health

| ID | Practice and why it matters here | How to verify | Detect that it has stopped working | Today (lanes) | Tier |
|---|---|---|---|---|---|
| PH-1 | **Fail closed at every promotion boundary, and publish a coherent generation atomically.** A failed stage must show itself and must not publish a mixed fixture. [E] | Inject a hold, an import failure and a health-check failure; in each case the status is published and the previous good fixture is served. | A test per failure stage. | Gates yes; publication partly (disagreement 2). Import-stage failure publishes no status (verified by read). | Costly |
| PH-2 | **Alert an accountable person when a job is red past its SLO or has not run at all.** [E] | Test delivery end to end, including a missed-run case. | An independent deadline checker (not the job itself) that fires when the last green run is older than the SLO. | No / unknown (C-P2, X-P3). Verified: seven consecutive scheduled chain failures (runs 3 to 9); no notify, issue or webhook step in any workflow. | Cheap for the alert; Costly for the missed-run checker |
| PH-3 | **No fail-open steps.** A failed pull fails the job or records an explicit acquisition result; success must mean fresh. [E] | Grep for `|| echo` and `continue-on-error`; each needs a recorded reason. | A job-level "acquired N rows at vintage V" line; zero is red. | No (C-P3, X-P2). Verified: `espn-supabase-sync.yml` line 41. | Cheap |
| PH-4 | **Idempotent, content-keyed runs; retry transport errors only, never review holds.** [E] | Run twice on the same input and compare outputs; interrupt a run and resume. | A byte-compare of consecutive no-change runs. | Writes yes; builds partly (C-P4, M-3.3, X-P2). | Cheap |
| PH-5 | **One canonical runner.** Local runs are labelled and never what production quietly depends on. [E] | `runner` recorded in status; the last green must come from CI. | Alert when the last green chain was `runner: local`. | Partly (C-P5). Verified: the current green fixture is from a local run while the scheduled CI chain was red. | Costly |
| PH-6 | **A deploy gate that no unrelated commit can bypass, and that includes the rendered gate.** [E] | Exercise it: push a `dist/modules/`-only commit with a deliberately red validate in a scratch branch. | The gate's own test (`test_preview_workflow_matches_pages` extended). | Partly (C-P6, X-P4). **Verified by read:** a `dist/modules/`-only last commit passes with red `validate`; `pages.yml` runs no rendered gate. **Not exercised.** | Cheap |
| PH-7 | **A preview with a blocking rendered gate on every change.** [E] | PR comment shows the gate result; self-test fails when the gate is broken. | The gate rejects fewer than the expected number of shapes. | Yes, with a gap (C-P7, M-3.4, X-B1). Verified: the verdict rejects zero shapes but not fewer than 12. | Cheap |
| PH-8 | **Every guard has a discrimination proof, and reports its denominator.** Correct case passes, named defect fails, missing prerequisites report unknown, and "N of M applicable comparisons ran" is shown. Avoid tests pinned to incidental wording. [J/E] | Merge checklist: guard ships with a failing-state test. | A registry test that every guard id has a negative test (mechanical); a guard that evaluated zero cases fails. | Partly (C-P8, M-3.2, X-P5). Reactive today: JEG-51, 67, 68. | Cheap (checklist) then Costly (mechanism) |
| PH-9 | **Reproducible builds from a clean runner with pinned dependencies and least-privilege secrets; one credential path.** [E] | Clean-runner replay. | A manifest hash of `dist/`; compare across runs. | Partly (C-P9, C-P10, X-P7). Two credential paths exist (a CI client shim and Muse's). | Costly |
| PH-10 | **Rehearsed backfill and rollback into a candidate area, with the same validation as forward changes.** [E] | A documented drill. | Not verifiable without the drill. | Unknown (X-P6). | Costly |
| PH-11 | **Contract documents and rules checked against code.** Rules that came from incidents are written down and tested (for example, monitor artifacts regenerate after deploy). [E] | A test fails when a normative doc disagrees with the code's source list. | The same test. | No (C-P11, X-D3, M-3.5). Verified: `import-health-schema.md` says five sources. | Cheap |

## 4. Dashboard health

| ID | Practice and why it matters here | How to verify | Detect that it has stopped working | Today (lanes) | Tier |
|---|---|---|---|---|---|
| BH-1 | **The rendered gate blocks on every path that can reach production, not only on PRs, and asserts coverage** (all intended shapes, the monitor route, console and resource errors). [E] | Make a direct push with an injected error; deploy must stop. | The gate's built-in self-test (exists). | Partly (C-B1, M-4.1, X-B1). See disagreement 1 and PH-6. | Cheap |
| BH-2 | **As-of and staleness shown next to every displayed value, evaluated against wall-clock and publisher deadlines, not against another stale fixture's week.** [E] | Rendered test: set an input past its red threshold; the label and state must appear. | Test the label with an old open tab (recheck on timer and on tab visibility). | Partly (C-B2, M-4.5, X-B3). Week labels exist (`sourceIsStale`); wall-clock expiry does not. | Costly |
| BH-3 | **Independent recomputation of displayed values** from pinned raw inputs with a small, transparent oracle, so a shared bug cannot hide. [E] | Known difficult players and configurations compared to the oracle with stated tolerances. | Oracle and page disagree on a seeded wrong value in a test. | Partly (C-B3, X-B2). The guard harness runs the page's own math. | Costly |
| BH-4 | **Computes and caches are bound to their full inputs** (fixture hash, settings) and refresh chart, pie, rank and table together; late results from a prior setting are rejected. [E] | Change away and back; rapid changes; mismatched asset versions. | A "computed from fixture X at time T" line in the page, compared against the served fixture. | Partly (X-B4 only; C-D3). Raised by one lane. | Costly |
| BH-5 | **A scheduled synthetic check of the live URL, outside the agent lanes:** renders production, asserts build identity, served digest, expected controls and values; blocked verification is reported as "unavailable", never "healthy". [E] | A run produces stored evidence with a timestamp. | An alert if the synthetic itself has not run within its window. | Partly (C-B5, M-4.1, X-B1, X-B6). C10 live-data check exists operator-side; no scheduled rendered-DOM check. | Costly |
| BH-6 | **End-to-end fidelity: live publisher values versus the numbers the page actually renders**, on a schedule and surfaced on the monitor. [E] | Seed a divergence; the check must flag it. | Evaluated-count shown; skipped pairs counted, not ignored (X-P5). | Partly (M-4.3, C-B3, X-B2). `check_source_fidelity.py` exists; scheduling and monitor surfacing are JEG-77 (Backlog); it skips absent pairs and stops after the first valid combo (Codex). | Costly |
| BH-7 | **The monitor names the remediation and gives one healthy signal that matches what the owner perceives.** [J] | Each red card states the command or owner. | Owner's audit findings that the monitor did not show are logged as monitor gaps. | Partly (C-B6, M-4.4). | Cheap |
| BH-8 | **The monitor monitors itself.** Every monitor artifact carries `generated_at`, and the page shows red when the monitor is older than twice its heartbeat. *(New in this consolidation.)* [J] | Hold the heartbeat; the page must turn red. | The same test. | **No. Verified:** the committed `pipeline-checkpoints.json` on `main` has `generated_at` 2026-10-01T16:07Z, about 22 hours old when I checked, last written by a "Dashboard 30-min health push". I checked the committed copy only; whether a live copy is fresher is unverified. | Cheap |
| BH-9 | **User-facing SLOs and an error budget:** the share of sessions that are fresh and correctly rendered; define the indicator before the target. [E] | One written SLI and a measurement. | Budget burn reported on the monitor. | Unknown (C-B6, X-B6). | Costly |
| BH-10 | **Accessibility and performance basics:** keyboard use, visible focus, non-colour status, responsive layout, interaction time at real data size. [E] | Keyboard and mobile pass; a timing budget. | Repeated measurement. | Partly / not assessed (X-B7; Claude lane did not assess). | Cheap to Costly |

## 5. Freshness contract

The first non-negotiable as rules a check can be written from. Numbers marked *existing* come from code in the repo; **proposed** numbers are my judgement and need the owner's confirmation before they are enforced. Where no rule exists the contract says **undefined**, because an invented limit would be worse than none.

**Two states, used everywhere:** *amber* = within grace and labelled ("awaiting Week N"); *red* = past its limit and labelled "STALE since <date>". Nothing is ever shown as current when it is red.

| Artifact | Age is measured as | Limit | On red, the page must | Stale-compute detection |
|---|---|---|---|---|
| Source snapshot, **USA Today** | content vintage (publisher week) | *existing:* Tuesday publish, 1 day grace (`publication_windows.py`) | label the source stale; keep it toggleable | n/a (an input) |
| Source snapshot, **ESPN** | content vintage date | *existing:* 2 days | same | n/a |
| Source snapshot, **CBS, CBS ROS, FantasyCalc, FantasyPros, Razzball** | content vintage | **undefined** for the first four (schedule unverified); Razzball has a daily dated rule in `verify_import_health.py` whose limit is to be restated here | the source must show "no freshness rule" rather than ok, until a rule is set | n/a |
| Rows landed in Supabase | vintage of the rows, not the import time | same as the source's limit | same | `source_import.<src>` age vs vintage |
| Promoted fixture section (per source) | its recorded `content_vintage` | not older than its source's limit | label that source stale | section's recorded input hash equals the current snapshot's hash |
| Adjusted sections, `adjustment-inputs.json`, VORP-translated values | the raw vintage they were built from | **zero lag**: built from the same raw vintage as the raw section they pair with (the JEG-73 rule) | do not show the adjusted line as current | recorded raw hash equals the raw section's hash |
| Fixture-wide `built_at` | last promotion | **not a freshness signal** (it resets on any promotion); report it as "last promotion", never as the age of the data | n/a | n/a |
| Player data, news and trace meta (`players.as_of`, `news.generated_at` and so on) | their own date | **proposed:** keep only the items the page actually displays, each with a limit; **retire the rest** from the freshness report so "expired" always means something | label what is displayed | n/a |
| Served page | build tag and served fixture digest | **proposed:** within 15 minutes of the last successful deploy | monitor red | served digest equals the repo fixture digest (C10 already checks this) |
| Monitor artifacts | `generated_at` | **proposed:** twice the heartbeat (the 30-minute push, so 1 hour) | monitor shows itself stale | n/a |
| Browser compute (curve, pie, table) | the fixture hash and settings it was computed from | recompute on every input or setting change; **proposed:** recheck on tab visibility and every 15 minutes | banner when its fixture hash differs from the served one | page shows "computed from fixture <hash> at <time>" |
| Chain (derived rebuild) | last green CI run | **proposed:** red after two missed 6-hour cycles (12 hours) | monitor red; person alerted (PH-2) | n/a |

**Open for the owner (step 3 or Jeremy):** the limits for CBS, CBS ROS, FantasyCalc and FantasyPros; the Razzball limit; and whether the proposed 15-minute and 12-hour numbers are right.

## 6. Input flexibility contract

The inputs the page exposes today (control ids read from `app/trade-value-chart/index.html`; shapes from `gate.mjs` and `curve-widget.js`). Every health measure must leave each of these working.

| Input | Control | Must keep working |
|---|---|---|
| Scoring | `curveScoring` (standard, half PPR, full PPR) | Changing it recomputes every curve, pie, rank and table value for that scoring, with no fallback to a different scoring (JEG-65). |
| League size | `curveTeams` (8, 10, 12, 14) | Same; a source that lacks a size shows "unsupported", not another size's values. |
| Roster shape | `rosterShapeControls` (slots per position, flex, superflex) | Any valid shape recomputes; the baseline and starter counts follow the shape. |
| Bench share | `weightsBenchSlot` (default 0.15) and per-position weights | The slider stays live; its feasible interval is re-solved per position; the pie readout sums to 100.0. |
| Lock mode | `curveLockOrder` | The lock caption and values follow the setting. |
| Source toggles | `sourceToggles` (raw or adjusted, per source) | A stale source stays toggleable and labelled; toggling never removes data from the table silently. |
| User deselection and custom weights | page state | Survives setting changes as designed. |

**Rules for any health check or fix:**
1. It evaluates the **requested** configuration. It may not force one configuration to make a test pass (the JEG-69 failure mode).
2. Changing a setting away and back returns identical values.
3. An unsupported configuration is shown as unsupported, never replaced.
4. A check that is only meaningful at the default shape must say so and be skipped elsewhere, with the skip counted.

**Gap:** the rendered gate sweeps scoring and league size (12 shapes) and checks the pie. It does not sweep bench share, roster shape or source toggles. Extending it is the cheap way to protect this contract (BH-1).

## 7. Cheap and high-leverage versus costly

**Cheap and high-leverage (do first, in roughly this order):**
1. **PH-3** remove the fail-open ESPN scrape.
2. **PH-2 (alert part)** one accountable alert when the CI chain is red for 12 hours.
3. **BH-8** make the monitor show when it is itself stale.
4. **PH-6 / BH-1** make the deploy gate evaluate `validate` regardless of the last commit's files, and run the rendered gate on direct pushes.
5. **PH-11** a test that fails when `import-health-schema.md` disagrees with the code's source list.
6. **DH-1 / DH-2** (partly): decide which freshness items the page displays; enforce those; retire the rest.
7. **PH-8 (checklist)** make "discrimination proof" a merge checklist item.
8. **BH-7** put the remediation on each monitor card.

**Costly (plan and sequence in step 3):** DH-2 (observed publication history), DH-3 and BH-4 (computed lineage and bound computes), DH-6 and BH-6 (drift and end-to-end fidelity, JEG-77), DH-8 and PH-5 (single canonical runner, durable pulls), BH-2, BH-3, BH-5, BH-9, PH-1 (atomic generations), PH-9, PH-10.

## 8. Values calls for Jeremy

These are choices about what the dashboard should do, not facts to find:

1. **When a source passes its red limit, what is the default?** (a) Show it, labelled "STALE since <date>", and keep it toggleable; or (b) hide it by default but keep it toggleable. My recommendation is (a): it satisfies "never silent" and protects flexibility; (b) is safer against a casual misread but removes sources from the first view.
2. **Should a stale input ever block the whole deploy?** Blocking protects against a wrong page and costs availability and flexibility. My recommendation: no for stale inputs (label them), yes for a failed `validate` or a failed rendered gate.
3. **Who is the accountable recipient for red alerts, and at what hours?** PH-2 cannot be finished without a named person.

## What I could not check

- The live production page (egress blocked), so BH-2 behaviour on expired items and C10's current output are unverified.
- Who receives GitHub failure emails; where several pulls run; branch protection on `main`.
- Whether a live copy of the monitor artifacts is fresher than the committed copy (BH-8).
- Why Codex's baseline `make validate` was red when mine on `main` was green (disagreement 6).
- Every [E] tag: no external sources were fetched.
