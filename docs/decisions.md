# Decisions Log

This file is the durable record of time-boxed decisions the project queues
for the human reviewer. The mechanism exists because not every parked item
deserves a synchronous tap — but every parked item must have an explicit
deadline, an explicit default-on-silence, and an explicit outcome once the
queue closes.

This log is **not** a backlog and **not** a planning doc. It is the queue
itself. Each entry is one open or recently-closed decision.

## Queue Rules (JEG-93)

1. **Default deadline is 7 days** from the date the entry is added. The
   `deadline` field carries the exact date; the 7-day default is a floor,
   not a ceiling — a longer deadline is allowed when the reviewer asks
   for one, but never silently.
2. **Silence by the deadline = proceed with the recommendation and record
   the outcome as `proceeded`.** No further tap required.
3. **A veto any time before the deadline stops the decision.** The
   outcome is `vetoed`, the `outcome_date` is set to the day of the veto,
   and a short note goes in the `Outcome Note` block. No replacement
   recommendation is recorded here — that belongs in a new entry.
4. **A modification before the deadline replaces the recommendation but
   keeps the entry open.** The outcome is `modified`, the new
   recommendation is appended under `Outcome Note`, and the deadline is
   either preserved (the reviewer's call) or extended with a new
   `deadline` line. A `modified` entry is still in the queue until a
   subsequent `proceeded` or `vetoed` closes it.
5. **Methodology, copy, and publish decisions are EXCLUDED from the
   silence-default.** They always need the explicit tap. Entries of
   this kind carry `silence-default: explicit-tap` and the queue rule
   that closes them is the human reviewer tap, not the clock.

The 7-day default is a calendar default. The reviewer may also force
`explicit-tap` on any entry by setting `silence-default: explicit-tap`
in the front matter — the queue treats that as "even if the clock
runs out, do not auto-execute."

## Entry Format

Each entry is a second-level heading `## <id>: <title>` followed by
a front-matter block, four required content sections, and an outcome
block.

Required front-matter keys (every key must be present, in any order).
Blank lines between the `## <id>:` heading and the first `- key:`
line are tolerated by the validator.

| Key | Format | Notes |
| --- | --- | --- |
| `id` | slug like `jeg-93-001` or `draft-2026-10-02-usatoday-drift` | Stable. Used by the validator. |
| `created` | `YYYY-MM-DD` | Day the entry was added to the queue. |
| `deadline` | `YYYY-MM-DD` | Day the silence-default expires. Default 7 days after `created`. |
| `category` | free text, lowercase-hyphen | e.g. `native-drift`, `leg-promotion`, `methodology`, `copy`, `publish`. |
| `silence-default` | `proceed` or `explicit-tap` | Methodology / copy / publish entries must use `explicit-tap`. |
| `outcome` | `pending` / `proceeded` / `vetoed` / `modified` | `pending` while the queue is open; closed once an outcome is recorded. |
| `outcome_date` | `YYYY-MM-DD` or empty | Empty while `outcome: pending`. |
| `recommendation` | one short line | The single exercised recommendation the silence-default would execute. |

Required content sections:

- `### Context` — what parked the item; the surrounding state.
- `### Problem` — the question the decision answers.
- `### Options` — bulleted or numbered list of the realistic choices.
- `### Recommendation` — the one option above, expanded, with the
  rationale in plain language.
- `### Outcome Note` — empty while `outcome: pending`. When the queue
  closes, the outcome is recorded here (the `outcome` field alone is
  not enough — the note carries the date and the short justification).

Drafts that have not yet been queued live under `docs/decisions/drafts/`
and follow the same shape, but their `outcome` is `pending` and their
recommendation line starts with `DRAFT:` so the validator and any
reader can tell drafts apart from queued entries.

---

<!-- New entries go below this line. The validator parses the file from
top to bottom; do not insert narrative between entries. -->

## source-resiliency-001: Any single source failure keeps that source's last section; the others publish
- id: source-resiliency-001
- created: 2026-10-08
- category: publish
- outcome: proceeded
- outcome_date: 2026-10-08
- recommendation: Extend per-source-promotion-001 from review holds to every single-source failure (failed import, match/reference/section/reindex/promote failure, malformed review, crashed stage script, ESPN or CBS ROS failure). The failed source's fixture is restored byte-for-byte to its pre-run state (and its DDF legs for espn/cbsros/razzball), it is recorded in `held` with `reason`/`stage`, and the page labels it with its own older week. A failed import no longer ends the workflow job. Still fail-closed: an unverifiable restore, every review-gated source held or failed, any shared-stage failure (re-translate, fit, _adjusted), and a red `make validate`.

### Context

Jeremy 2026-10-08: "have resiliency for when some of the sources fail". Pre-launch direction: block only on wrong numbers; staleness is a warning. Before this, only a review hold was isolated; a USA Today 402 (no snapshot), an L1 promote refusal or an ESPN leg crash failed the whole chain and nothing published. Session record: docs/claude-log/2026-10-08-source-resiliency.md.

## per-source-promotion-001: A held source keeps its last section; the others publish
- id: per-source-promotion-001
- created: 2026-10-07
- deadline: 2026-10-14
- category: publish
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-07
- recommendation: A review hold in one published-chart source keeps that source's last promoted section (labelled with its own week) and lets every other source publish; the hold is never overridden, it is recorded amber (red after two weeks behind), and anything else still fails the chain closed.

### Context

rebuild-chain.yml failed 107 of its last 126 runs (last success 2026-10-04). A recurring cause: one source's review returned `hold` (for example FantasyCalc `coverage:full_10_qb1/WR` "candidate priced 76 < fixture 78") and the whole chain failed, so none of the other five sources' fresh data published. Every week some source drops a few players, so every week needed a hand-written unblock ticket. GAP-CHAIN-PARTIAL-PUBLISH (JEG-436) recorded why this was not a small change: half-promoted sections, skipped fit/_adjusted, the ESPN anchor, and JEG-8's no-push rule.

### Problem

Should one source's review hold block every source from publishing?

### Options

1. Keep all-or-nothing. Every hold blocks the whole site until a human clears it.
2. Per-source isolation. A held source keeps its last promoted section; the others publish; the hold stays loud.
3. Auto-resolve holds. Rejected: a hold means a human must look first (Jeremy 2026-09-29).

### Recommendation

Option 2, as built in `pipelines/rebuild_comparison_chain.py`:

- Only a genuine reviewer verdict of `hold` in usatoday, fantasycalc, fantasypros or cbs is isolated. The held source's fixture section and `built_at` are restored to exactly their pre-run state (sections promoted earlier in the run are rolled back; verified by canonical sha) and rolled-back promotion records are renamed `*.rolled-back.json`. The held candidate is never promoted and the review artifact is never edited.
- Still fails closed: any other failure (snapshot, match, section, reindex, promote refusal, malformed review, error), any ESPN or cbsros failure (their builders write the fixture before their gate, and ESPN's legs are the reindex anchor and fit target), a restore that cannot be verified, and a run in which every review-gated source held.
- The fit and `_adjusted` sections run on the resulting fixture, so a held source's adjusted series is rebuilt from its kept raw section.
- The site already labels each source by its own week (`week_designated` / `content_vintage`; product-data.js marks it `older`, curve labels show "Wk N"); a held section keeps its old label, so it reads as older, never current.
- Loud: chain status `held` / `held_detail` / `hold_severity` / `outcome: published_with_holds`, run-summary table and warning (amber) or error (red) annotations, and two monitored checks: `rebuild_chain_source_held` (warn, any hold) and `rebuild_chain_source_held_stale` (page, kept section two or more content weeks behind; the build-lag-001 one-week tolerance).

### Outcome Note

2026-10-07: approved by Jeremy (relayed to the implementing session by the coordinating session the same day). Implemented in PR per-source-promotion. The monitoring migration `supabase/migrations/chain_source_holds_20261007.sql` must be applied when the PR merges.
## build-lag-001: Build on each source's newest week; a one-week lag does not block
- id: build-lag-001
- created: 2026-10-07
- deadline: 2026-10-14
- category: publish
- silence-default: explicit-tap
- outcome: pending
- outcome_date:
- recommendation: A week-designated source exactly one content week behind is a non-blocking LAGGING_ONE_WEEK warning and is built under its own week label; two or more weeks behind blocks; the green check blocks on everything outside an explicit allow-list (so red blocks).

### Context

The rebuild chain had not promoted since the week-5 rollover (Tuesday 2026-10-06). `pipelines/verify_import_health.py` held the gate RED because CBS and FantasyPros were `STALE_VINTAGE` (Week 4 against content week 5), and `rebuild-chain.yml` stops before the chain on a red gate. FantasyCalc already had Week 5 and ESPN was current, so nothing was promoted, even the sources that were fresh. Jeremy (2026-10-07): "Tighten or loosen whichever gates you need"; the build should run on the newest data each source has (weeks 4/3 fine), each source labelled by its own week; he will review the math later.

The audit also found that the green check was `stale == 0 and missing == 0 and failed == 0`. A publication-window `red` (MISSED_WINDOW), a `yellow`, and any status outside that list passed without notice. USA Today's 2026-10-07 entry was `yellow`; on Thursday it would have turned `red` and still passed.

### Problem

How far behind can a source be and still be built, and which statuses should hold the gate?

### Options

1. Keep exact-week freshness. The chart stays frozen until every publisher posts the new week, and fresh sources are held back by the slowest one.
2. Tolerate a one-week lag. One week behind is a non-blocking warning, two or more weeks behind blocks, and the green check fails closed on any status outside an allow-list.
3. Ignore freshness and build whatever exists. A source months stale would then publish silently.

### Recommendation

Option 2, implemented 2026-10-07 under Jeremy's authorization (pending his review):

- `verify_import_health.py`: a week-designated source (fantasycalc, usatoday, fantasypros, cbs, cbsros) whose content week is exactly one behind `--nfl-week` gets `status: "warning"` and reason `LAGGING_ONE_WEEK (non-blocking): <source> content Week N is one week behind current content Week N+1; built and labelled as Week N. Window verdict <yellow|red|stale>: <publication-window reason>`. Two or more weeks behind keeps the window status (`red` for a verified schedule, `stale` for an unverified one). Both block.
- Green = no entry is blocking. Non-blocking: `ok` and `warning` (TABLE_DRIFT stamping lag or LAGGING_ONE_WEEK), plus Razzball's snapshot-age verdicts (`warn`/`bad`/`unk`). Razzball is not a chain source and has no CI puller (GAP-024); its byte or table failures still block. Everything else blocks, including `red`, `yellow` and unknown statuses. Each entry now carries `blocking` and `content_week`.
- A source ahead of the check week (FantasyCalc Week 5 when a caller passes 4) is `ok`. `--nfl-week` defaults to `pipelines/nfl_week.py`, which flips Tuesday. A caller passing a different week gets a loud NOTE line, not a block.
- Promotion (`promote_comparison_section.check_l1_freshness`) accepts `ok` or a LAGGING_ONE_WEEK warning. The candidate's `content_vintage` must still equal the health entry's vintage, so a Week-4 source is promoted as Week 4 and never relabelled. A TABLE_DRIFT warning is still refused.
- The chain status (`comparison-chain-status.json`) records `source_vintages`: each source's content vintage, week, health status, and whether it is lagging. The chain's `nfl_week` is the current content week, not every section's week. The VORP-translation grain week stays the chain week: it is a refresh-cycle label computed from the promoted fixture's natives, not a content week.

### Outcome Note

## copy-vorp-001: User-facing term is "VORP vs waivers"
- id: copy-vorp-001
- created: 2026-10-06
- deadline: 2026-10-06
- category: copy
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-06
- recommendation: Replace the locked user-facing term "value above waivers" (and the "never say VORP" rule) with "VORP vs waivers".

### Context

The locked user-facing term was "value above waivers", with a "never say VORP" rule. Jeremy asked for the abbreviation to appear in copy.

### Problem

What exact wording may user-facing copy use for value over the waiver line?

### Options

1. Keep "value above waivers" and the no-VORP rule.
2. "VORP vs waivers" as the single allowed phrase.
3. Allow bare "VORP" or "VORP vs replacement" wherever convenient.

### Recommendation

Option 2, chosen by Jeremy (2026-10-06, explicit): "Do 'VORP vs waivers'." Consequences:

- The exact phrase "VORP vs waivers" is now the only allowed user-facing use of "VORP". Other wording ("Raw VORP", bare "VORP", "vorp vs waivers", "VORP vs replacement") is still blocked by `tests/test_public_copy_no_vorp.py`, which has negative cases for each.
- Labels, titles, badges and methodology copy in the chart widgets, `app/trade-value-chart/index.html` and the monitor pages now say "VORP vs waivers". Internal data keys (`espn_vorp`, the `vorp` view ID) are unchanged.
- Code comments and pipeline provenance strings baked into fixtures (`method` notes) were not rewritten; they are not chart labels, and rewriting baked text would need a re-bake.

### Outcome Note

Approved by Jeremy in session on 2026-10-06 ("Do 'VORP vs waivers'"); recorded as `proceeded` because the format has no `approved` outcome.

## ops-ownership-001: Muse owns nothing except as a last resort; Supabase-first tooling
- id: ops-ownership-001
- created: 2026-10-06
- deadline: 2026-10-06
- category: publish
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-06
- recommendation: Move ownership of merges, deploys, production QA and scheduled jobs on the trade-value project from Roman (Muse) to Claude; use Muse only as a last resort. Prefer Supabase tools (pg_cron, Edge Functions, database-side checks) over GitHub Actions for new automation.

### Context

Merges, deploys and production QA on the trade-value project were owned by Roman (Muse), with GitHub Actions as the default scheduler.

### Problem

Who owns merges, deploys, production QA and scheduled jobs, and which tooling is the default for new automation?

### Options

1. Keep Muse ownership and GitHub Actions scheduling.
2. Claude owns them; Muse is a last resort; Supabase tools are preferred over GitHub.
3. Split ownership by task type.

### Recommendation

Option 2, chosen by Jeremy (2026-10-06, explicit): "I don't want muse owning things anymore, unless it's the last resort. And I think we should favor supabase tools over GitHub as a general guideline." Consequences:

- Supersedes the AGENTS.md rule that Roman owns review, integration and all deploys to `main`.
- Muse's trade-value crons (dashboard push, overnight QA loop, PR merge sweep, CBS/USA Today ingests) are retired as Claude-owned, Supabase-scheduled replacements go live; handoff note drafted 2026-10-06 for Jeremy to send to Muse.
- Existing GitHub workflows stay where Supabase cannot do the work (Pages build/deploy, `make validate`); their schedules come from pg_cron.

### Outcome Note

Approved by Jeremy in session on 2026-10-06; recorded as `proceeded` because the format has no `approved` outcome.

## league-settings-001: Save one league setup; derive other league settings in the browser
- id: league-settings-001
- created: 2026-10-06
- deadline: 2026-10-06
- category: methodology
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-06
- recommendation: Save and validate one canonical setup (12 teams, standard roster) end to end, per scoring format (standard / half / full PPR). Derive every other team count, roster shape and bench share in the browser from that saved base. Never save rows per league-setting permutation.

### Context

Saving finished values for every (teams x roster x scoring x view) permutation multiplies storage per source per week (12 combos x 2 views today in `consolidated_values`, more with roster shapes) and would exhaust the Supabase tier. The 2026-10-04 hybrid decision (JEG-364) already baked one team size through and kept roster and bench flexibility client-side; this extends it to team count. JEG-331 found the saved chart values already depend on team count, so the browser must start from a deeper, setting-independent layer.

### Problem

Which league setups are saved and validated in the backend, and which are derived in the browser?

### Options

1. Save finished values for every (teams x roster x scoring x view) permutation.
2. Save one canonical 12-team standard-roster setup per scoring format and derive the rest in the browser.
3. Derive everything, including scoring, in the browser.

### Recommendation

Option 2, chosen by Jeremy (2026-10-06, explicit tap):

1. Backend: 12-team, standard-roster values are computed all the way through and are the only league setup saved, reviewed and validated.
2. Scoring stays saved: three formats at 12 teams. Scoring changes a source's own numbers, so it is not derived; every saved number stays one a source actually published (or our model computed at the canonical setup).
3. Frontend: team count, roster shape and bench share are derived in the browser from saved per-player base inputs (source native value or per-game points, plus position). Nothing is saved per permutation.
4. Validity: the backend validates the 12-team output; a parity gate proves the browser engine, set to 12 teams, reproduces the saved values exactly (JEG-364). Other settings inherit that guarantee because they run the same formula.
5. Accepted trade-off: for sources that publish their own per-league-size numbers (FantasyCalc `numTeams`), only the 12-team publication is saved; our derived 8-team value will not match the source's own 8-team page.

**Consequences**

- Answers architecture-target Q6: the Postgres on-demand view family (JEG-329/332/333/334 as written) is retired in favour of browser derivation; PR #202 was closed unmerged.
- FantasyCalc weekly producer: pull and save 12-team only, three scorings (GAP-FC-PRODUCER).
- `consolidated_values` stops growing per league setting; non-12-team rows become removable once the browser engine passes parity.

### Outcome Note

Approved by Jeremy in session on 2026-10-06 ("Good with your recommendation"); recorded as `proceeded` because the format has no `approved` outcome.

## jeg-209-001: Eight-group VORP reweight — approve the allocation policy
- id: jeg-209-001
- created: 2026-10-02
- deadline: 2026-10-09
- category: methodology
- silence-default: explicit-tap
- outcome: pending
- outcome_date:
- recommendation: Approve the squared-surplus allocation with ESPN as the pinned economics reference and the all-source batch 70 anchor, OR choose plain global linear rescale and keep the bench-share slider as the bench-economics control.

### Context

JEG-209 produced a design proposal (PR #41, draft) for reweighting VORP into chart values on the 0-70 scale, covering group budget allocation across the 8 position x starter/bench groups plus the per-player VORP-to-value mapping. Roman independently re-ran the pinned worked example (2026-09-29 ESPN half-PPR 12-team leg, 351 rows) and verified the arithmetic: all 8 group numbers reproduce the doc table, full-group conservation holds exactly, total budget B = 1940.94, 70 anchor = Jahmyr Gibbs. No math bug. The proposal is pure algebra (no optimizer), as Jeremy required. Nothing is implemented and nothing is merged; JEG-182 stays in Backlog until this spec is approved.

### Problem

Which allocation policy governs the Adj values view: (a) the proposed reference-squared-surplus policy, where each group's budget share is proportional to the sum of squared waiver-line surpluses (rewarding concentration of hard-to-replace surplus), or (b) plain global linear rescale, where group budgets follow raw VORP sums and allocation collapses to a single scale factor? The choice also settles two downstream questions: whether the standing bench-share slider (default 15%, user-settable) applies to Adj values, and whether the 70 anchor stays ESPN-only or moves to the all-source batch maximum.

### Options

1. **Approve the squared-surplus policy as proposed.** Group budgets derive from one pinned granular reference (ESPN in the example); bench economics are derived, not user-set (bench shares of each position's budget: QB 9.3%, RB 6.4%, WR 6.6%, TE 3.1%; TE/bench gets 0.09% of the total budget); the all-source batch shares one 70 anchor. Cross-role inversions are reported, not ironed.
2. **Approve with linear rescale instead.** Keep the 8-group structure and conservation, but set group budget shares proportional to raw group VORP sums (allocation collapses to one global scale factor). Bench economics stay closer to the standing 15% slider; Mark Andrews (TE/bench) reads 6.09 instead of 0.56.
3. **Approve with modifications.** e.g. squared-surplus allocation but the bench-share slider retained as an explicit override for the Adj view; or a different pinned reference than ESPN; or retain the ESPN-only 70 anchor and allow values above 70.
4. **Reject.** The Adj view does not ship; the chart keeps the current fixed-pie indexing for as-published sources.

### Recommendation

Put the choice to Jeremy with the worked-example numbers in front of him: the squared premium is a real economic judgment (bench players are worth nearly nothing) dressed as algebra, and it retires the user-settable bench-share control for the Adj view. The honest comparison is Option 1 vs Option 2 on the same sample table (Gibbs 70.0 both; Josh Allen 11.89 vs 27.80; Mark Andrews 0.56 vs 6.09). Jeremy's call; nothing proceeds without his explicit tap.

### Outcome Note

## jeg-434-001: USA Today CI ingest — relay strategy (Supabase relay primary, Firecrawl secondary)
- id: jeg-434-001
- created: 2026-10-07
- deadline: 2026-10-14
- category: ops
- silence-default: proceed
- outcome: proceeded
- outcome_date: 2026-10-07
- recommendation: Use the Supabase Edge Function relay as primary fallback (SUPABASE_URL + SUPABASE_SERVICE_KEY already CI secrets); Firecrawl only when FIRECRAWL_API_KEY is set.

### Context

PR #382 adds `fetch_via_relay` (calls `usatoday-fetch` Edge Function on project iskiybsimubiujwuchsl) and `fetch_via_firecrawl` (paid API, inert without FIRECRAWL_API_KEY) to `ops/watchdog/pull_usatoday.py`. Both are fallbacks on BLOCK_STATUSES (401/402/403/429). Jeremy stated on 2026-10-07: "merge PR #382, Supabase edge-function relay first, Firecrawl as second fallback only when FIRECRAWL_API_KEY is set" (JEG-434 decision entry).

### Problem

usatoday.com returns HTTP 402 to GitHub-hosted runner IPs (bot wall). The ingest records SOURCE_BLOCKED every CI run; no USA Today week-5+ data will land without a workaround. Two workarounds were proposed: (a) Supabase relay using existing CI secrets, verified to work via pg_net; (b) Firecrawl paid scrape API.

### Options

1. **Relay only.** Add relay; no Firecrawl code. Simpler; fails if Supabase starts walling usatoday.com too.
2. **Relay primary, Firecrawl secondary (if key set).** Add both; Firecrawl remains inert until FIRECRAWL_API_KEY is added as a secret. Defense in depth; code path is untested in CI.
3. **Firecrawl only.** Requires paid key; no redundancy with existing infrastructure.

### Recommendation

Option 2. Relay is live and verified (CI dry run 37614204115). Firecrawl code is inert without the secret so it adds no risk; it can be activated by adding a secret later without a code change.

### Outcome Note

Jeremy authorized on 2026-10-07 (JEG-434): "merge PR #382, Supabase edge-function relay first, Firecrawl as second fallback only when FIRECRAWL_API_KEY is set." Implemented in the PR branch; merge commit 9e44e3e. `make validate` exit 0.

## consol-adjusted-001: Bias-adjusted sources stay out of public.consolidated_values
- id: consol-adjusted-001
- created: 2026-10-07
- deadline: 2026-10-07
- category: methodology
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-07
- recommendation: Do not write the *_adjusted sources to public.consolidated_values. They stay on the chart, served from the fixture. Keep the 70 cap (ck_combo_reindexed_cap) and the writer's pre-check unchanged for the core sources. No Supabase constraint change.

### Context

Once the consolidation writer set the NOT NULL columns (PR #400), the 2026-10-07 fixture still could not be written. Fifteen bias-adjusted combo_reindexed values exceed 70 (for example usatoday_adjusted Bijan Robinson 76.4 and cbs_adjusted Jahmyr Gibbs 82.4), and the live CHECK rejects them (GAP-CONSOL-CAP).

### Problem

How should adjusted values above the table's 70 cap be handled?

### Options

1. Cap the adjusted sections at 70 in the builder.
2. Relax or drop the cap for the *_adjusted sources.
3. Keep the adjusted sources out of public.consolidated_values.

### Recommendation

Option 3, chosen by Jeremy (2026-10-07, explicit). `build_consolidated_values.write_supabase` skips every `*_adjusted` source explicitly (`split_for_table`) and logs each skipped source with its row count. The served JSON export still carries them. The skip is pinned by `tests/test_consolidated_write_fields.py::AdjustedExcludedTest`.

### Outcome Note

Approved by Jeremy on 2026-10-07 and implemented in PR #400.

## consol-nonblocking-001: The consolidated_values write does not block the Pages deploy and is monitored on its own
- id: consol-nonblocking-001
- created: 2026-10-07
- deadline: 2026-10-07
- category: publish
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-07
- recommendation: In rebuild-chain.yml the consolidation write is its own `continue-on-error` step. Its outcome is recorded as the monitored check `consolidated_values_write` (red on failure). The Pages dispatch does not depend on it.

### Context

Rebuild run 37641559947 pushed the fixture (0b0ddee), then failed at "Build consolidation layer". The Pages dispatch's implicit `success()` skipped, so main and the live site diverged. The site serves the fixture, not public.consolidated_values.

### Problem

Should a failed Supabase consolidation write block the Pages deploy?

### Options

1. Non-blocking, with its own monitored check.
2. Blocking but consistent: write before the fixture push.
3. Leave as is: the fixture is pushed but not deployed.

### Recommendation

Option 1, chosen by Jeremy (2026-10-07, explicit).

- The step has `continue-on-error: true` and `id: consolidate`.
- `Record consolidated_values check` runs with `always()` and records `steps.consolidate.outcome` through `record_monitor_check.py`.
- The Pages dispatch runs on `!cancelled() && steps.push.outputs.pushed == 'true'`.
- The check row is in `supabase/migrations/jeg324_consolidated_values_write_check.sql` (applied after merge).
- Guard: `tests/test_rebuild_chain_consolidation_nonblocking.py`.

### Outcome Note

Approved by Jeremy on 2026-10-07 and implemented in PR #400.

## es-value-001: Expected-starts value replaces the VP-2.6 slices (answer to OC-2 and OC-3)
- id: es-value-001
- created: 2026-10-09
- deadline: 2026-10-16
- category: methodology
- silence-default: explicit-tap
- outcome: pending
- outcome_date:
- ticket: JEG-533 (moved from JEG-525, closed 2026-10-09 as superseded)
- recommendation: Adopt OC-9 A: each source's value above waivers is split into a start-worthy part and a fill-in part by the expected lineup share of the player's level (docs/methodology.md ES-0 to ES-11), with m_pos, the bye share and sigma measured weekly by pipelines/derive_lineup_parameters.py; the bench share becomes an output; the default roster is WR 3 / FLEX 1 and config/roster.json is corrected when the fit retires.

### Context

JEG-521 G1. The manifesto (sections 4, 5, 7, 8) says value is usable
production: points that reach a starting lineup. Today a flat 15% bench
share, which nobody derived, is the only thing separating starters from
bench, and the VP spec's recommended replacement (OC-2 A, source-implied
slices) measures at 39% to 49% of the pie on bench slices on live data
(MR-19). Update 2026-10-09: Jeremy decided OC-2 at a fixed 15% with slices
on JEG-508, so MR-19 is moot and option C now means "keep the fixed 15%".
This decision is the follow-up: replace the 15% with expected starts after
JEG-508 ships. The parameters were derived from 2024-2026 player-game actuals,
the schedule, the three projection sources' spread and their week-to-week
movement (`output/lineup-parameters.md`).

### Problem

Which rule turns value above waivers into trade value: the slices as
written, the expected-starts parts, or the slices with a bench budget set
from expected starts? And which default roster shape?

### Options

1. OC-9 A: expected-starts parts replace the slices (ES-5). Bench tier holds
   7.8% to 9.8% of the pie across the 12 settings; starter-level points are
   worth 1.1x to 3.8x bench-level points; zero order inversions; no
   calibration clamp. Top-12 share of the RB pie rises from 52% to 57%.
2. OC-9 B: keep the slices, set the per-position bench budget from A. Same
   bench-tier share; keeps the kink and gives no per-player share.
3. OC-9 C: keep the slices as written. 39% to 49% on bench slices.

### Recommendation

Option 1, with the convex option value kept out of the pie and shown as the
Stash signal (MR-21). The measured before/after is
`output/expected-starts-before-after.md`. The engine change lands through
JEG-508's pipeline with the Python reference and the spec reference on one
branch, `value_check` at 0 disagreements, the 12-combo sweep and the rank
guard at zero inversions, and the table shown to Jeremy before publishing.

### Outcome Note

Pending Jeremy's tap (JEG-521, JEG-450 rule).
