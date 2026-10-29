# Waiver board and Bench Churn: design concept

Proposal for Jeremy (JEG-1196, JEG-1197). Nothing here ships and no math
changes. The clickable mock is `docs/design/waiver-bench-churn-concept.html`
(open it in a browser; it shows the desktop layout with a 390px phone frame
beside it). All names and numbers in the mock are invented.

Last updated: 2026-10-29. Status: Proposal. Both tickets stay in Backlog behind
the weekly-input contract (JEG-1227, PR #1087) and producer (JEG-1228).

## The answer in one paragraph

One computed artifact, the **waiver board** (`data/weekly/waiver-board-wk{N}.json`,
owned by JEG-1196), feeds two views: the **Waiver board** (who to add, pass on,
hold or drop this week) and **Bench Churn** (for each bench player: keep him, or
rotate the spot through this week's waiver windows). Every value on both views is
in the trade-value unit (DDF Value, ROS, from the published chart). Weekly data
from the contract only decides *when* and *whether* a move is possible (status,
bye, kickoff slate, freshness). It never enters a value, a gain or a verdict.
That keeps Jeremy's rule: "do not blend weekly data with ROS data, ever."

## Settled picks this concept follows

- Waiver line: the 7-player average around the replacement spot, loaded
  leagues too (JEG-1244, pick A). A DDF Value of 0 sits on that line.
- Bench keeps its share of value through the season (JEG-948, pick B). DDF
  Value is unchanged. A weeks-left, byes-left and breakout-odds readout sits
  beside the values (proposed build ticket in the JEG-948 decision comment).
- Weekly and ROS are never blended (Jeremy, 2026-10-29).
- DDF Value is the average of the weight-adjusted indexed values (Jeremy,
  2026-10-28).
- Missing stays missing: a null with a reason, never a zero.

## Two lanes, drawn apart

| Lane | Source | Unit | Where it shows | May decide a verdict |
| -- | -- | -- | -- | -- |
| Value (ROS) | published chart `players.json` through the value model at the league setting | DDF Value (TV$) | Value column, gain chips, chain totals | Yes |
| This week | weekly-input contract legs (`status`, `bye`, `experts.*`, `vegas`) | fantasy points, status, bye week | a grey "This week" column and the slate strip | No. Timing and eligibility only |

The "This week" column has its own label and a different tone, and the two
lanes are never added, averaged or sorted together. Sorting is by Value only.

## Waiver board (JEG-1196)

### Desktop

1. **Header.** "Week 9 waiver board". Under it: "Lasts through Mon, Nov 2 ·
   Half PPR · 12 teams" with the league chip (opens settings).
2. **Source strip.** One chip per input with its freshness word from the
   contract (`current`, `one week behind`, `stale`, `unknown`,
   `unavailable`). A stale or unavailable source greys out the column it feeds
   and shows its `missing_reason` on tap. Example: "Vegas · unavailable · feed
   on hold".
3. **Controls row.** Availability ("Rostered below 70%", slider) and
   "Your league's wire" overrides (Add to wire / Remove from wire), carried over
   from the retired board.
4. **Sections**, in this order, each a table:
   - *Hot pickups*: most-added since Sunday, each with **ADD** or **PASS**.
   - *Other pickups*: under-the-radar players the values like.
   - *Hold*: rostered players who fell but still sit above the line.
   - *Drop*: rostered players now at or below the waiver line.

   Columns: player and position chip, team, rostered %, **Value**, **Change**
   since last board, then the grey *This week* group (projected points, status,
   bye), and a one-line grounded case ("Took 71% of snaps after the trade").
5. **Your swaps.** Paste a roster. Rows read "Drop X, add Y · +3.1 value",
   gain 2 or more, each player used once, thin positions protected (as before).
   A FAAB hint shows in dollars beside the gain, never folded into it.

### Phone

The source strip collapses to one line ("4 of 5 sources current · 1 off"),
which opens a sheet. Each section becomes a list of cards: name, position chip,
verdict pill and Value on the first line; rostered % and the grey This week line
on the second; the case on the third. Controls sit behind one "Adjust" pill.

### What each number means

- **Value**: the player's DDF Value at this league setting, rest of season.
  0 means he sits on the waiver line.
- **Change**: Value now minus Value on last week's board, same setting,
  like-for-like pricing (current against pre-week, as the ticket requires).
- **ADD / PASS**: ADD when a player on the wire has Value above 0 and the
  board's existing rule ranks him in; PASS when he is being added but the value
  layer prices him at or near the line. No new threshold is proposed here.
- **Rostered %**: the share of leagues rostering him (ESPN), used only to guess
  who is on the wire.
- **This week**: points from the named weekly expert leg, status and bye.
  Shown for context, never ranked.
- **Swap gain**: Value of the add minus Value of the drop.

## Bench Churn (JEG-1197)

### Desktop

1. **Header.** "Bench Churn · Week 9 slate". Under it: "Lasts through Mon,
   Nov 2 · times in Chicago time". The bench readout from pick B sits here:
   "9 weeks left · 2 byes left on your roster · bench share held".
2. **Slate strip.** The week's windows across the top: Thu night, Sat claims,
   Sun early, Sun late, Mon. Locked games are hatched. Each bench player's own
   game shows as a dot on the strip.
3. **One card per bench player**, sorted by the gap between the chain and
   keeping him:
   - Left: **Keep** value (his DDF Value).
   - Right: **Best rotation** as a chain of steps, one target per window:
     *After his game* (Thu, if he plays early) then *Before the weekend*
     (Sat claims), then continuation if a claim misses. Each step shows the
     target, landing chance, hit chance, FAAB (charged only if it lands) and
     the step's expected value.
   - Footer: **Net chain** value and the verdict, **CHURN** or **KEEP**.
     CHURN only when the net chain beats Keep.
4. **Three lists** under the cards: *Grab* (targets worth a claim this week),
   *Avoid* (popular adds the chain rejects) and *Partial-cycle upgrades*
   (moves that only pay for part of the week, shown separately so they don't
   look like full upgrades).
5. "Show the math" opens the step-by-step sum for any card.

### Phone

Cards stack. Keep and Net chain sit side by side as the two big numbers with
the verdict pill. The chain steps fold into a stepper that opens on tap. The
slate strip scrolls sideways.

### What each number means

- **Keep**: the bench player's DDF Value. With pick B it keeps its share as
  weeks pass; the readout shows weeks and byes left.
- **Landing chance**: the chance the claim is won (from the board's existing
  model). Shown as a percent.
- **Hit chance**: the chance the target becomes worth holding. Source is an
  open question below.
- **Survival**: the chance the chain is still running at that step (earlier
  steps missed).
- **Step value**: survival × landing × hit × the target's future usable DDF
  Value, minus FAAB cost if it lands. Future value only, so this week's
  lineup points are not counted twice.
- **Net chain**: the sum of step values, in DDF Value. CHURN iff Net chain >
  Keep. The ticket's `evaluateChain` / `bestChainFromItems` remain the
  reference; this concept only lays out what they return.

## Data each panel needs

| Panel | From the weekly-input contract | From elsewhere | Gap |
| -- | -- | -- | -- |
| Header, board week | `season`, `content_week` (Tuesday flip), `built_at` | `pipelines/nfl_week.py` | none |
| Source strip | every leg's `availability`, `freshness`, `label`, `missing_reason`, `content_vintage` | chart freshness from the chart build | chart freshness is not a contract leg |
| Value, Change, waiver line | none (by rule) | published `players.json`, value model at the league setting, last week's board | needs last week's board kept (versioned artifact) |
| Rostered %, most-added | none | ESPN roster % and adds trend (retired board read ESPN directly) | **not in the contract**; see question 4 |
| This week column | `experts.<name>` values for the scoring, `status.values.injury_status`, `status.values.practice_participation`, `bye.values.bye_week` | none | which expert leg is named (S4 setting) |
| Your swaps | none | pasted roster, `players.json` | none |
| Slate strip, windows | `game_week` on slate fields | kickoff times per team | **kickoff times are not in the contract**; see question 5 |
| Bench readout | none | lineup resolve `objective_window`, `bye_share`; JEG-1276 breakout rates | readout build ticket not filed yet |
| Chain steps | `status` (eligibility: out, IR, locked), `bye` | landing chances, FAAB budget and league claim rules | **FAAB budget and claim rules have no home**; see question 2 |

## Open questions for Jeremy

Each has a recommendation. None is decided here.

1. **Which weekly numbers may the waiver board show?** The contract notes say
   JEG-1196 "takes no weekly data for now".
   - A: status, bye and kickoff only, no weekly points.
   - B: also this week's expert points, in the grey column, never in a verdict
     or sort. *(Recommended: useful context, and the lanes stay apart.)*
   - C: weekly points may break ties between equal values. (This blends; not
     recommended.)
2. **How does FAAB cost become DDF Value?** The ticket wants the chain "net of
   expected waiver cost" in the same unit.
   - A: reuse the retired Bench Churn artifact's conversion as is. *(Recommended
     if you can point me to that artifact; it isn't in the repo.)*
   - B: a new conversion, designed and approved as T1 value math.
   - C: keep FAAB in dollars beside the chain, and require both "net chain
     beats keep" and "bid under your cap".
3. **Where does the hit chance come from?**
   - A: the JEG-1276 historical breakout rates by depth (O3), looked up by the
     contract's weekly depth-chart order. The lookup uses a weekly category,
     not a weekly number, so nothing is blended. *(Recommended.)*
   - B: the retired artifact's hit chances.
   - C: leave hit chance at 1 until research lands, and say so on the card.
4. **Where do rostered % and the adds trend live?**
   - A: a new `espn_roster` leg on the weekly-input contract (a minor version
     bump, one ingestion). *(Recommended.)*
   - B: the waiver-board builder reads ESPN itself.
5. **Where do kickoff times live?**
   - A: slate fields on the contract (`game_week` plus kickoff per team).
     *(Recommended.)*
   - B: a separate schedule file the board reads.
6. **Where is the retired Bench Churn artifact?** The ticket says to reuse its
   `evaluateChain` and `bestChainFromItems` with snapshot tests; neither is in
   the repo or the archive. A link or file would let the build start from it.

## Not in scope

No engine, spec, reference, `config/` or Supabase change. No new threshold,
weight or default. No page in `app/` or `dist/`. The build tickets stay blocked
on JEG-1227/1228 and on the answers above.
