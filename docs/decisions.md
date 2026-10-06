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
## ops-ownership-001: Muse owns nothing except as a last resort; Supabase-first tooling
- id: ops-ownership-001
- created: 2026-10-06
- deadline: 2026-10-06
- category: publish
- silence-default: explicit-tap
- outcome: approved
- outcome_date: 2026-10-06
- recommendation: Move ownership of merges, deploys, production QA and scheduled jobs on the trade-value project from Roman (Muse) to Claude; use Muse only as a last resort. Prefer Supabase tools (pg_cron, Edge Functions, database-side checks) over GitHub Actions for new automation.

### Decision (Jeremy, 2026-10-06, explicit)

"I don't want muse owning things anymore, unless it's the last resort. And I think we should favor supabase tools over GitHub as a general guideline."

### Consequences

- Supersedes the AGENTS.md rule that Roman owns review, integration and all deploys to `main`.
- Muse's trade-value crons (dashboard push, overnight QA loop, PR merge sweep, CBS/USA Today ingests) are retired as Claude-owned, Supabase-scheduled replacements go live; handoff note sent to Muse 2026-10-06.
- Existing GitHub workflows stay where Supabase cannot do the work (Pages build/deploy, `make validate`); their schedules come from pg_cron.

### Outcome Note

Approved by Jeremy in session on 2026-10-06.

## league-settings-001: Save one league setup; derive other league settings in the browser
- id: league-settings-001
- created: 2026-10-06
- deadline: 2026-10-06
- category: methodology
- silence-default: explicit-tap
- outcome: approved
- outcome_date: 2026-10-06
- recommendation: Save and validate one canonical setup (12 teams, standard roster) end to end, per scoring format (standard / half / full PPR). Derive every other team count, roster shape and bench share in the browser from that saved base. Never save rows per league-setting permutation.

### Context

Saving finished values for every (teams x roster x scoring x view) permutation multiplies storage per source per week (12 combos x 2 views today in `consolidated_values`, more with roster shapes) and would exhaust the Supabase tier. The 2026-10-04 hybrid decision (JEG-364) already baked one team size through and kept roster and bench flexibility client-side; this extends it to team count. JEG-331 found the saved chart values already depend on team count, so the browser must start from a deeper, setting-independent layer.

### Decision (Jeremy, 2026-10-06, explicit tap)

1. Backend: 12-team, standard-roster values are computed all the way through and are the only league setup saved, reviewed and validated.
2. Scoring stays saved: three formats at 12 teams. Scoring changes a source's own numbers, so it is not derived; every saved number stays one a source actually published (or our model computed at the canonical setup).
3. Frontend: team count, roster shape and bench share are derived in the browser from saved per-player base inputs (source native value or per-game points, plus position). Nothing is saved per permutation.
4. Validity: the backend validates the 12-team output; a parity gate proves the browser engine, set to 12 teams, reproduces the saved values exactly (JEG-364). Other settings inherit that guarantee because they run the same formula.
5. Accepted trade-off: for sources that publish their own per-league-size numbers (FantasyCalc `numTeams`), only the 12-team publication is saved; our derived 8-team value will not match the source's own 8-team page.

### Consequences

- Answers architecture-target Q6: the Postgres on-demand view family (JEG-329/332/333/334 as written) is retired in favour of browser derivation; PR #202 was closed unmerged.
- FantasyCalc weekly producer: pull and save 12-team only, three scorings (GAP-FC-PRODUCER).
- `consolidated_values` stops growing per league setting; non-12-team rows become removable once the browser engine passes parity.

### Outcome Note

Approved by Jeremy in session on 2026-10-06 ("Good with your recommendation").

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
