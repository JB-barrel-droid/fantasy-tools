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

## copy-vorp-002: User-facing term is "Value above waivers"; VORP never appears
- id: copy-vorp-002
- created: 2026-10-22
- deadline: 2026-10-22
- category: copy
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-22
- recommendation: Rename "VORP vs waivers" to "Value above waivers" everywhere and ban "VORP" from user-facing text (supersedes copy-vorp-001).

### Context

copy-vorp-001 locked "VORP vs waivers" as the one allowed user-facing use of VORP; `docs/manifesto.md` says copy says "value above waivers", never VORP. Live QA on 2026-10-22 (JEG-861) found the two rules in conflict.

### Options

- (a) Keep "VORP vs waivers"; amend the manifesto to name the one exception.
- (b) Rename to "Value above waivers" everywhere; retire copy-vorp-001; rewrite the copy test to ban VORP outright. Recommended.
- (c) "Points above waivers".

### Outcome Note

Jeremy, 2026-10-22 (multiple choice on JEG-861, recommendation taken): option (b). "VORP vs waivers" is renamed "Value above waivers" everywhere on the site; no "VORP" in user-facing text. Where a raw-vs-adjusted distinction exists the label is "<source> value above waivers, raw". Internal keys (`espn_vorp`, the `vorp` view ID, CSS classes, element ids, URL state) are unchanged. `tests/test_public_copy_no_vorp.py` now flags any "vorp" in widget string literals and sweeps the rendered page's text and accessible names.

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

Amended 2026-10-26 (Jeremy, in chat: "Set it up with two tickets for now, items in backlog that are low risk"; "I gave muse the one ticket"): Muse owns Linear tickets labeled `muse` (first: JEG-1145), on `muse/*` branches, and opens PRs but never merges. Everything else above stands.

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
- outcome: approved (option A, with the bench share as a computed readout; see Decision below)
- outcome_date: 2026-10-09
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

### Decision (Jeremy, 2026-10-09 20:51, JEG-533: "I'm good with this, do it")

Approved, in reply to Claude's proposal on JEG-533 (20:23 and 20:43):

1. **Option A.** The expected-starts parts (ES-5) replace the VP-2.6
   slices once JEG-508 has shipped with the fixed 15%.
2. **No bench-share slider as the input.** The bench share is an output,
   shown as a readout by position ("Bench share this week: QB x%, RB y%,
   WR z%, TE w%, from your league settings"), ES-14.
3. **Reader settings are the causes, not the share.** The existing league
   size, roster and bench size, plus league weeks (last regular-season
   week, playoff weeks) and what to optimize for (season, regular season,
   playoffs), ES-12 / JEG-527.
4. **Two advanced settings behind a disclosure.** Injury history ("recent
   seasons", the default, weighted with a five-season half-life per MR-25,
   or "all seasons equal"), and projection confidence (scales the
   uncertainty).
5. **One bench-share override,** off by default.

Claude's reading, flagged on JEG-533: the injury-history default is
"recent" (the MR-25 recommendation). The approval covered the settings
design, which offers it as a setting; Jeremy did not separately say yes to
the default.

Lands through JEG-508's pipeline after it merges. The engine, the Python
reference and the spec reference are on one branch, `value_check` at 0, the
12-combo sweep and the rank guard at zero inversions, and the before/after
is shown to Jeremy on that week's data before publishing (CLAUDE.md, JEG-450).


## roster-convention-001: One roster convention everywhere; market bench is separate from fundamental bench
- id: roster-convention-001
- created: 2026-10-10
- deadline: 2026-10-17
- category: methodology
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-10
- recommendation: Bench seats, tiers, starter and waiver lines and flex follow one definition (JS and Python twin). Market bench (backups per starter from real drafts: QB 0.86, RB 0.85, WR 1.05, TE 0.39) sets tiers and the waiver line; the fundamental bench module never does.

### Context

Back-filled 2026-10-12 (JEG-598) from JEG-556 and its child tickets (JEG-558, 559, 560, 561, 562, 564). An audit found the same step implemented differently in several live paths (bench seats, tier basis, starter line, waiver line on short lists, flex, roster shape).

### Problem

Which single rule defines bench seats, tiers, lines and flex, and how are the descriptive and prescriptive bench logic kept apart?

### Options

1. One convention with market bench from draft ratios (candidate C1 of five scored).
2. Keep per-path rules.
3. Fixed 10:27:33:10 mix.

### Recommendation

Option 1.

### Outcome Note

Jeremy, 2026-10-10 on JEG-556: "I don't want some corner case logic for QBs that should be applied in other places too, the transformations logic should be consistent." And: "Like market values vs fundamental values, there is also market bench expectations vs fundamental bench strategy, and we need to separate the logic for the two." The market bench sets the waiver line (replacement is what real leagues leave on waivers); the fundamental bench is its own module (JEG-564) and never sets tiers or lines. Evidence: Fantasy Football Calculator 12-team PPR drafts 2016-2024 (8,857 drafts). Jeremy, 2026-10-12 on JEG-556 (decision 3, waiver line on short lists): estimate from other charts (impute from published-chart behavior; not the last listed value, not 0.0). Decision 4, starter line: the midpoint of the last starter and the first non-starter (today's live two-tier behavior). Both are recorded in the convention module by JEG-559 (PR 546); its parity test marks four divergences as expected failures that go green as JEG-560, 561 and 563 land. Earlier (2026-10-10) Jeremy had said to fill short lists "the simplest way" at the last listed value; the 2026-10-12 answer replaces that.

## default-roster-001: Default roster is the most common real league, with kickers and defenses as starters
- id: default-roster-001
- created: 2026-10-10
- deadline: 2026-10-17
- category: methodology
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-10
- recommendation: Default league becomes 12 teams, 1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX / 1 K / 1 DEF, 7 bench; K and DEF are starters but not valued and stay outside the value pie.

### Context

Back-filled 2026-10-12 (JEG-598) from JEG-556 comments and JEG-563. RotoWire's count of 35,000 leagues shows this as the most common build; the previous default was 1/2/3/1/FLEX with 6 bench and no K/DEF.

### Problem

Should the default roster match the most common real league?

### Options

1. Switch the default to the most common league.
2. Keep 1/2/3/1/FLEX, 6 bench.

### Recommendation

Option 1.

### Outcome Note

Jeremy, 2026-10-10: "We should expect our leagues to have kickers and defenses as starter positions too". Default switch decided the same day (JEG-563, front end JEG-565). Measured: leagues hold about 0.00 backup kickers and 0.06 backup defenses per starter (they stream), so K and DEF take two starting spots and almost no bench spots. Expected effect at 12-team PPR: bench 12 QB / 27 RB / 40 WR / 5 TE, about 10.5% of league value on benches, zero inversions in all 12 settings. It changes every default value; shipping needs the before/after table, 12-setting sweep and rank guard. Status 2026-10-12: JEG-563 not yet shipped (blocked behind the engine work).

## copy-rescaled-001: Trade charts are labeled "rescaled", not "as published" or "indexed"
- id: copy-rescaled-001
- created: 2026-10-09
- deadline: 2026-10-16
- category: copy
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-09
- recommendation: User-facing label is "Trade charts (rescaled)"; internal keys such as `indexed` are unchanged.

### Context

Back-filled 2026-10-12 (JEG-598) from JEG-510 (contract line GL-21). Follow-up JEG-615 finished the legacy dashboard strings.

### Problem

What wording describes a publisher's values after we index them to our scale?

### Options

1. "Trade charts (rescaled)".
2. Keep "as published".

### Recommendation

Option 1.

### Outcome Note

Jeremy, 2026-10-09 (GL-21): "anywhere we are saying "as published" we are really saying indexing what was published; so sort out copy to properly say the wording, else it may confuse the reader". Meaning line: "Each publisher's trade values, rescaled to our point scale for your league. Their ranking order is unchanged." The scale anchor (ESPN or DDF) is not described until JEG-499 settles.

## fe-contract-2026-10-09: Three DDF Value types on every page, full NFL player search, trade headline with confidence
- id: fe-contract-2026-10-09
- created: 2026-10-09
- deadline: 2026-10-16
- category: methodology
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-09
- recommendation: Build contract lines GL-09, GL-20 and CT-02 as Jeremy worded them.

### Context

Back-filled 2026-10-12 (JEG-598) from JEG-497 (GL-09), JEG-502 (GL-20) and JEG-505 (CT-02). The source of truth for contract wording is the repo `docs/feature-contract.md` (JEG-602 makes the Google Doc a mirror).

### Problem

Record the contract lines that exist only in ticket text.

### Options

1. Record the quotes here and in the contract.

### Recommendation

Option 1.

### Outcome Note

Jeremy, 2026-10-09, GL-09: "All DDF Value Types should be available on every page - The total blended one, the one sourced from trade value charts only, and the one sourced from player projections only." GL-20: "All players in the active NFL universe should be available in the search; even if they are not rostered, on practice squads, etc. The user knowing they are a 0 is better than the use questioning why they aren't in the tool." CT-02: "The headline language needs to be simple and answer - Should you propose or accept this trade? + level of confidence. And will a competing manager accept this trade based on published value charts? + level of confidence." Confidence is agreement plus data quality (JEG-505).

## research-tab-001: A Research tab holds posts on the tool's opinionated choices
- id: research-tab-001
- created: 2026-10-10
- deadline: 2026-10-17
- category: publish
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-10
- recommendation: Add a Research tab after the Manifesto tab; Claude drafts posts from methodology and decisions, Jeremy approves.

### Context

Back-filled 2026-10-12 (JEG-598) from JEG-543.

### Problem

Where do evidence write-ups for specific choices live?

### Options

1. A Research tab linking back to the Manifesto tab.
2. Fold them into the Manifesto.

### Recommendation

Option 1.

### Outcome Note

Jeremy, 2026-10-10: "a section that is posts about anything opinionated in the tool and how we arrive at those opinions; perhaps blog like posts live there too." The Manifesto stays its own tab, first in the nav. Research claims link to a repo doc and a script (JEG-604, JEG-566).

## timestamp-parse-001: ISO timestamp parsing tolerates 1-digit fractional seconds on Python 3.9
- id: timestamp-parse-001
- created: 2026-10-12
- deadline: 2026-10-19
- category: engineering
- silence-default: proceed
- outcome: proceeded
- outcome_date: 2026-10-12
- recommendation: One helper (`pipelines/lib/timestamps.py`, `parse_iso_timestamp`) pads or truncates the fraction so parsing works on 3.9 and 3.11+.

### Context

Back-filled 2026-10-12 (JEG-598) from JEG-625: `datetime.fromisoformat` on 3.9 rejects "...30.1+00:00", so `latest_save._ts` returned None.

### Problem

Fix the parser or require a newer Python?

### Options

1. Tolerant parser helper.
2. Require Python 3.11+.

### Recommendation

Option 1.

### Outcome Note

Jeremy, 2026-10-12 (JEG-625): "make the parser tolerant so it works on 3.9 and 3.11+." Implementation tracked in JEG-625.

## usage-minimax-001: MiniMax is not used
- id: usage-minimax-001
- created: 2026-10-09
- deadline: 2026-10-16
- category: ops
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-09
- recommendation: Do not route work to MiniMax; M2.5 is banned and M3 is not configured.

### Context

Back-filled 2026-10-12 (JEG-598) from Jeremy's usage rules (user-level Claude instructions). Draft briefs in the archive name a minimax lane that is retired.

### Problem

Is MiniMax a worker lane?

### Options

1. Not used.
2. Use M3 for routine work.

### Recommendation

Option 1.

### Outcome Note

Jeremy, 2026-10-09: MiniMax not used; M2.5 is banned; M3 is not configured.

## docs-location-001: Docs stay as Markdown in the repo with a browsable index
- id: docs-location-001
- created: 2026-10-12
- deadline: 2026-10-19
- category: publish
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-12
- recommendation: Keep the .md files in the repo `docs/`; add `docs/README.md` (naming conventions, one line per doc) and a generated index artifact.

### Context

Back-filled 2026-10-12 (JEG-598) from JEG-596 and JEG-619.

### Problem

Where do the durable docs live and how are they navigated?

### Options

1. Repo Markdown plus an index artifact.
2. Move docs into a hosted doc tool.

### Recommendation

Option 1.

### Outcome Note

Jeremy, 2026-10-12 (JEG-596): keep .md in GitHub plus an easy-to-browse index with clear naming conventions and one-line descriptions per doc. Built in JEG-619 (PR 536).

## name-resolver-001: One canonical player-name resolver; a position conflict is final
- id: name-resolver-001
- created: 2026-10-10
- deadline: 2026-10-17
- category: methodology
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-12
- recommendation: Every saver and builder resolves names through the canonical resolver and the player table; no per-source exception; use the ESPN or Sleeper position; never flag inactive players.

### Context

Back-filled 2026-10-12 (JEG-598) from JEG-75, JEG-438 and JEG-539 (PRs 498, 497, 501, 514, 532).

### Problem

How do sources that name or position a player differently map to one identity?

### Options

1. One canonical resolver and table; conflicts go to review; no per-source exceptions.
2. A curated per-source exception list.
3. Keep legacy matchers for some savers.

### Recommendation

Option 1.

### Outcome Note

Jeremy, 2026-10-02 (JEG-75): all player naming resolves through the canonical player naming table. Jeremy, 2026-10-07 (JEG-438): all player name concepts tie back to the player name table; partial solves are replaced. Jeremy, 2026-10-10 (JEG-539): "Use canonical resolver" for Razzball, so the test "nicknames are not guessed" became "matched only via curated aliases"; CBS, FantasyPros and FantasyCalc followed with zero resolved keys changed on current data. Jeremy, 2026-10-12 (JEG-539 Q2, Connor Heyward): use the ESPN or Sleeper position (where the game is played), not CBS; no per-source exception, so CBS rest of season loses Heyward. Q3 (Max Hurleman and inactive players): never flag; add to the player table and move on. Q1: the front end drops the deprecated fit and `*_adjusted` aliases and the back end retires the fit. Implemented in PR 532; the one remaining legacy matcher is the chain's own (GAP-IDENTITY-LEGACY-MATCHERS).

## math-review-2026-10-15: Math review answers Q1-Q4 (JEG-450)
- id: math-review-2026-10-15
- created: 2026-10-15
- deadline: 2026-10-15
- category: methodology
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-15
- recommendation: Q1 label the tier column "ESPN Tier"; Q2 close as moot (fit retired); Q3 retire the CBS ROS and Razzball direction and markup checks; Q4 keep zeros counted in the Indexed factor (option A).

### Context

Jeremy answered the four questions in docs/math-review-questions-2026-10-12.md.

### Problem

Q1 GAP-TIER-FROM-ESPN, Q2 GAP-ADJ-IDENTITY-FALLBACK-UNLABELLED, Q3 GAP-CBSROS-DIRECTION-RED, Q4 OC-8 zeros in the Indexed factor.

### Options

As listed per question in the questions file.

### Recommendation

Q1 label only; Q2 moot; Q3 option (B), retire; Q4 option A.

### Outcome Note

Jeremy, 2026-10-15 (JEG-450): Q1 "ESPN Tier" is the column label (another agent implements it). Q2 closed as moot, the fit is retired. Q3 retire the CBS ROS and Razzball direction and markup checks, which judge the starter/bench scales in buildVorpRows and price nothing those sources display; keep any check that still guards displayed values. Q4 keep zeros counted in the Indexed factor (option A, confirmed). Q3 code state: the checks (starterMarkupSane, fixedPieDirectionSane) were already deleted from the engine by JEG-508/JEG-539 and are pinned absent by test_published_league_settings_engine; no Chart Health record or test for them remains. The only leftover is the unused `starter_markup_sane_band` contract constant (product-data.js, sql/contract/api_v1.sql, fe-read-contract-v1.md), left because it is part of the frozen read contract.

## jeremy-review-2026-10-16: Five agent defaults reviewed (JEG-505, JEG-477, JEG-526/529, JEG-534, JEG-535)
- id: jeremy-review-2026-10-16
- created: 2026-10-16
- deadline: 2026-10-16
- category: methodology
- silence-default: explicit-tap
- outcome: modified
- outcome_date: 2026-10-16
- recommendation: Keep the compare-trade cutoffs; taller chart with a user control; leave handcuffs out; weekly matchups lineup hint only; keep loosened QB thresholds and review QB values.

### Context

Agents chose defaults on five items without asking. Jeremy reviewed each on 2026-10-16.

### Problem

Whether each agent default stands.

### Options

Keep the default, change it, or park the item. Per item below.

### Recommendation

As recorded in the Outcome Note.

### Outcome Note

Jeremy, 2026-10-16:
1. JEG-505 compare-trade headline: KEEP the agent-chosen cutoffs. Likely at 2/3 or more of charts siding, Unlikely at 1/3 or fewer; confidence High at 75% agreement, Medium at 60%; capped at Medium with fewer than 3 charts; a one-chart player lowers only the "should you" line. His own 5% thin-margin rule stays.
2. JEG-477 taller chart on Player values: "Taller chart on larger screens and ability to expand size or contract size". This supersedes the agent's decision to decline it to keep the JEG-470 fold rule. Laptop screens keep the fold, larger screens get a taller default, and a user control expands or contracts the chart. JEG-477 reopened.
3. MR-26 handcuffs (JEG-526, JEG-529): "Leave out for now, we can come back to this post launch". The stash signal PR 578 was converted to draft and parked. Both tickets moved to Backlog, label Parked.
4. MR-23 weekly matchups (JEG-534): lineup hint only, values untouched (option a, confirmed).
5. PR 637 direction-check thresholds (2-QB +3, peak >28): KEEP loosened, then have QB values reviewed (new ticket, High).

## coverage-fill-in-001: A shorter or longer chart list is filled in, not held (JEG-667)
- id: coverage-fill-in-001
- created: 2026-10-16
- deadline: 2026-10-16
- category: methodology
- silence-default: explicit-tap
- outcome: proceeded
- outcome_date: 2026-10-16
- recommendation: Follow the fill-in convention (OC-5 / VP-2.4, approved 2026-10-09). A chart list that got shorter or longer passes the coverage review when fill-in reaches the rosterable set; the dropped and added names are a warning. Hold only when fill-in cannot reach the rosterable set, or a dropped player is still priced live (or still listed, or in the identity review rows).

### The rule

**When a chart's list gets shorter or longer, fill in from the other charts to full league rosters. Do not hold the source and do not ask for a floor accept.** Hold only when fill-in cannot reach the rosterable set, or a dropped player is still priced live.

### Context

CBS's Week 6 list is shorter (WR 41 vs 43, TE 10 vs 14), and the coverage review held CBS. The fill-in rule already fills a short chart to full rosters from the other charts.

### Outcome Note

Jeremy, 2026-10-16: "When lists get longer or shorter we need to follow the conventions we've set, filling in where needed from other charts to get to full rosters in leagues. I've shared this multiple times and it needs to be clear in the project."

Jeremy, 2026-10-17, on PR #670: "Review #670 against what merged, keep what the convention still needs."

Implemented in `pipelines/review_comparison_candidate.py` (`coverage_fill_in_reaches`, checked before the tail-churn slack and recorded accepts), test `tests/test_coverage_fill_in.py`. Rule text: `CLAUDE.md` (Standing constraints), `runbooks/source-held.md` 3b.

### Record correction (2026-10-17)

PRs #668 and #669 (merged 2026-10-16) recorded a CBS floor accept (WR 41 / TE 10, Week 6, all three combos) in `data/triage/coverage-accepted.json` with `approved_by: Jeremy, approved_on: 2026-10-16`, and their commit messages and the JEG-667 comments describe it as Jeremy's decision. That was another session's reading of his answer, not his decision. His decision was the convention above. The floor accept entries stay in the file as history and are not reverted; they expire with Week 6 and are only a fallback where fill-in does not apply. The convention governs.

## amber-hold-001: Amber fidelity holds never hide a source from DDF Value
- id: amber-hold-001
- created: 2026-10-19
- deadline: 2026-10-26
- category: methodology
- silence-default: proceed
- outcome: proceeded
- outcome_date: 2026-10-19
- recommendation: An amber fidelity hold (merely lagging: stored_vs_chart value-only drift, or publisher_vs_stored with 0 value mismatches and at most 2 unresolved names) labels the source on the page but does not hide it from DDF Value or projection ordering. Red holds keep hiding.

### Context

JEG-726: the fidelity pulse held ESPN (stored_vs_chart: value-only drift), CBS ROS (publisher_vs_stored: 0 value mismatches, 1 unresolved name) and Razzball (stored_vs_chart) at the same time. With every projection held, there was no projected-points order (VP-2.2 f): bench-share was None and projection-based DDF Value was not offered. The engine and reference agreed and JEG-569 part 2 made gate tests handle it, but the page lost projection values because sources were merely lagging, not wrong.

### Problem

Should a merely-lagging source be hidden from DDF Value?

### Options

1. **(a) Amber holds never hide.** The source gets a visible "lagging" label but stays in DDF Value and projection ordering. Red holds (genuine wrong data) keep hiding.
2. **(b) Never hold the last included projection.** Keep at least one projection visible, regardless of hold severity.
3. **(c) Leave as is.** All holds hide equally.

### Recommendation

Option (a), agent-chosen per Jeremy's instruction (2026-10-19, editable). Amber holds now carry `hold_level: "amber"` through the fixture's `validationHold` field. The page reads `hold_level` and includes amber-held sources in DDF Value (eligible, not hidden). The degenerate state (all three projections amber-held) can no longer produce bench-share None from amber holds alone, because amber-held projections stay in the pipeline as full participants.

### Outcome Note

2026-10-19: implemented per Jeremy's delegation (JEG-726). Agent chose option (a). Files changed: `pipelines/fidelity_pulse.py` (amber hold detection in `hold_decision`), `pipelines/fidelity_hold.py` (`hold_level` passed through to `validationHold`), `app/trade-value-chart/assets/curve-widget.js` (amber holds not hidden). Negative-tested: all three projections amber-held => still present; red hold => still hidden.

## render-fix-001: v2 render test CSS and fixture fixes (JEG-718)

- id: render-fix-001
- created: 2026-10-19
- deadline: 2026-10-26
- category: implementation
- silence-default: proceed
- outcome: proceeded
- outcome_date: 2026-10-19
- recommendation: Agent-chosen per Jeremy's delegation (2026-10-19, editable). Five changes below.

### Context

Three v2 render test modules were red. Jeremy delegated fix decisions to the agent.

### Problem

1. 9px horizontal scroll at 1440 in panels test (table overflows its wrap).
2. Chart card below fold at 1366x768 in panels test.
3. Obsolete "equal case duplicates the number" mutant in targets test (never caught because no player has consensus == ours in current data).
4. Missing-step waterfall path unchecked (gap player's missing source not in pointKeys).
5. Verdict cards below fold at 1366x768 in waterfall test.

### Options

Each sub-fix had one clear approach (CSS tightening, fixture logic change, or assertion update). No alternative was considered because the root cause was unambiguous.

### Recommendation

1. Reduce `--v2-cell-pad-x` clamp max from 8px to 7px (saves ~10px across 7 columns).
2. Add chart-h media query for short viewports: `calc(100vh - 520px)` at max-height 800px.
3. Replace "equal case duplicates" mutant with "consensus always shows equal note" (always-true mutation caught by check_market).
4. Change PICK to find gaps against `compareView.pointKeys` (waterfall table sources), not `shown()`. Fix SIMULATE_DISSENT to pick from pointKeys minus ddf_value.
5. Add `#v2Compare .v2-cverdict { gap: 2px }`, reduce `.v2-deal` and `.v2-cstory` padding in short-viewport rule.

Bonus: two panels guard mutations ("Tier column says ESPN Tier", "shares not applied") were only caught by the now-fixed scroll error. Fixed the actual checks: shares test value from 10% to 30%, tier check opens expanded-table mode briefly.

### Outcome Note

2026-10-19: all three test modules green (6 tests, 52 subtests). Agent-chosen, editable.
2026-10-19 (follow-up): PR 713 item 2 (chart-h media query) conflicted with JEG-470's 280px floor -- plot was 248px instead of 280px. Replaced the `--v2-chart-h` override with chrome trimming (card padding, legend gap, plot margin) in the same media query. Both test_v2_chart_height_render and test_v2_panels_render now pass. All 39 v2 render modules green.

## qa-wave-2026-10-19: contract-line and QA defaults (agent-chosen per Jeremy's instruction, editable)

Jeremy, 2026-10-19: "make your best choices and log the decisions; I'd rather edit something working."

- **JEG-726 (amber holds):** option (a). Amber holds (value-only drift, <=2 unresolved names, 0 value mismatches) never hide a source from DDF Value; label only. Red holds still hide. See amber-hold-001. Python reference brought into line in PR 714.
- **TT-09 "Market average":** recommend retiring it and folding into TT-03/TT-04 (the build uses median "Market consensus" + "Gap vs consensus" since JEG-677). Google Doc contract lines are Jeremy's to edit; mirror stays "to build" until he does. 9 lines remain pending for that reason (CT-02, GL-07, GL-09, GL-19, GL-20, GL-21, GL-22, TT-05, TT-09); all but TT-09 have partial live checks.
- **GL-07:** recommend rewording the Doc to the four chart groups the UI shows (no "Trade charts (adjusted)" group).
- **Header copy:** the header must not claim "all sources current" while sources are held (PR 706).
- **Render suites:** panels/waterfall fixed in product code (fit the 1366x768 fold), targets mutant replaced not dropped (render-fix-001).
- **Research tab:** shows "No posts are published yet." Recommend hiding the nav item until the first post is approved (JEG for follow-up); not yet done.

## jeremy-review-2026-10-16-qb: QB values on a 2-QB board (JEG-702)
- id: jeremy-review-2026-10-16-qb
- created: 2026-10-16
- deadline: 2026-10-16
- category: methodology
- silence-default: explicit-tap
- outcome: modified
- outcome_date: 2026-10-16
- recommendation: Q1 (d) both; Q2 (c) park; Q3 (a) no cap.

### Context

The QB values review (`docs/research/qb-values-review-2026-10-16.md`) found that PR 637's loosened 2-QB checks guard a translation no page prices from, and asked three questions.

### Problem

What guards 2-QB QB value, whether the engine's 2-QB QB level is right, and whether to cap part-timers' per-game rates.

### Options

Section 6 of the review.

### Recommendation

Q1 (d), Q2 (c), Q3 (a).

### Outcome Note

Jeremy, 2026-10-16:
1. Q1: "Both: point the checks at the live engine and retire the unused code." The +3 / >28 checks on `unified.positional_max_for_setup` are retired with that function, `projection_max_vorp`, and the browser translation port in `value-model.js` (`translatePublishedVorp`, `positionalMaxForSetup`, `imputeExtension` and helpers). The new guard, `tests/test_two_qb_direction.py`: at every scoring and team count, the 2-QB top QB's blended DDF Value is at least 1.2 times its 1-QB value, on the Python reference and on the engine headless (which must also equal the reference). The server translation (`unified.translate_source`) stays: its grains are a record.
2. Q2: "Park until a second superflex source." Revisit when one is wired (KeepTradeCut, JEG-669, is the candidate).
3. Q3: "Undo the per-game change (JEG-535) for ESPN." Not the recommended option. Implementation notes are added below when it lands.

## JEG-792: remove the self-host Supabase stack (cancelled)

Jeremy, 2026-10-22 (multiple choice): cancel the move to a Mac-mini self-hosted Supabase and remove it; cloud Supabase on Pro stays.

- Removed (repo only): `selfhost/` (compose stack, gateway, init SQL, backup/restore, key generator, `migrate/` export/import/verify scripts), `docs/selfhost-runner.md`, `docs/selfhost-supabase.md`, `docs/selfhost-tables.md`.
- Kept: `sql/reference/cloud_cron_jobs_2026-10-21.sql` (moved from `selfhost/migrate/cron_and_functions.sql`), the only repo record of the 20 cloud pg_cron jobs and dispatch function bodies; `docs/supabase-egress-notes.md` points to it. Also kept: the bounded value-check log (`pipelines/load_value_check.py`, migration 014), which is cloud-side work that only cites the ticket.
- No workflow, Makefile target, pipeline or test imported selfhost code (grep 2026-10-22).
- Restore: `git checkout 86d3f37d5cf8991e09057ac4dedb791b3662e34c -- selfhost docs/selfhost-runner.md docs/selfhost-supabase.md docs/selfhost-tables.md` (last commit touching `selfhost/`; the docs files are in the same history).

## JEG-856: ESPN gets no source link

Jeremy, 2026-10-22 (multiple choice, on JEG-856): ESPN gets no source link for now; nothing login-gated or stale is shown. Revisit when someone confirms a public ESPN page. `tests/test_source_link_urls.py` keeps `NO_LINK_YET = {"espn"}`. The USA Today link question (keep the pulled article URL, or spot-check it in a browser; it answers 402/403 to automation) is open and non-blocking.

## JEG-850: Customize dialog copy and layout

Jeremy, 2026-10-22 (multiple choice, all took the recommendation; quoted on JEG-850): two tabs "Chart lines" and "DDF blend"; variants "DDF Value", "DDF Value: charts only", "DDF Value: projections only"; chips "Under review" / "Normal range"; stacked phone footer; Done blocked with "Pick at least one source" when the draft has no engine series (no engine change); the last usable DDF input stays on, locked, and a held input does not count; "Using N of M sources" on the DDF blend tab only; VORP group collapsed unless a VORP series is selected. Shipped in #811; details in `docs/v2-design-notes.md`.

## JEG-855: nav order

Jeremy, 2026-10-22: Manifesto, How values work and Research fold into one Writing tab, first in the nav; order Writing, Player values, Trade targets, Risers & fallers, Compare a trade, Values auditing. The landing tab stays Trade targets. Shipped in #810.

## JEG-1310: CBS rest of season stays as it has been

Jeremy, 2026-10-29 (multiple choice, on JEG-1310): "Leave as is", then "CBS logic should follow what it has been." CBS rest-of-season handling is unchanged: CBS's printed points are used as published, at equal weight in DDF Value (projections). Not the recommended option, which was to rescore CBS from its own stat line. Don't propose rescoring or reweighting CBS again. The research (CBS QBs about 2.5 ppg high from 6-point passing TDs, RBs about 1.1 low, player gaps such as Jalen Coker are CBS's own view) is in `docs/research/JEG-1310/README.md`. No divergence resolution was recorded, so the CBS warn can recur.
