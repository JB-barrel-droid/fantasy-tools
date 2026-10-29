# Waiver board and Bench Churn: design concept

Proposal for Jeremy (JEG-1196, JEG-1197). Nothing here ships and no math
changes. The clickable mock is `docs/design/waiver-bench-churn-concept.html`
(open it in a browser; it shows the desktop layout with a 390px phone frame
beside it). All names and numbers in the mock are invented.

Last updated: 2026-10-29. Status: Proposal. Both tickets stay in Backlog behind
the weekly-input contract (JEG-1227, PR #1087) and producer (JEG-1228).

## The objective

Both views answer one question: **is this move worth making this week?**

Net gain = the free agent's DDF Value − what you give up.
What you give up = the bench player you drop, priced at his DDF Value.
FAAB is out of scope for v1 (Jeremy, 2026-10-29: "dont' even research it,
we aren't ready to approach it"), so a bid is never part of the sum.

Make the move when the net gain is above zero. Bench Churn is the same sum
run over this week's claim windows, with the chance each claim lands and hits.

Every input exists to fill in that one sum, or to say when it can be made:

| Input | Its job in the sum |
| -- | -- |
| Free agent's DDF Value (published chart) | the gain side |
| Dropped player's DDF Value | the cost side (the only cost in v1) |
| Rostered % | is he likely on your wire at all |
| Kickoff times | which windows exist and when each call locks |
| Status and bye | is the move allowed (out, IR, locked) |
| This week's expert points | context in a grey column, never in the sum |

All values are DDF Value (rest of season), so weekly data never enters the
sum, as long as neither option B under Still open (hit chance or landing
chance) is picked. That keeps Jeremy's rule: "do not blend weekly data with
ROS data, ever."
One computed artifact, the **waiver board** (`data/weekly/waiver-board-wk{N}.json`,
owned by JEG-1196), feeds both the Waiver board view and Bench Churn.

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
   No bid is shown or charged (FAAB is out of scope for v1).

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
- **Swap gain**: Value of the add minus Value of the drop. This is the
  objective sum above.

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
     target, landing chance, hit chance and the step's expected value. The
     ticket's "charge FAAB only when claims land" waits until FAAB is in scope.
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
- **Landing chance**: the chance the claim is won. Shown as a percent. No
  model for it exists in the repo; its source is still open (below).
- **Hit chance**: the chance the target becomes worth holding. Its source is
  still open (below).
- **Survival**: the chance the chain is still running at that step (earlier
  steps missed).
- **Step value**: survival × landing × hit × the target's DDF Value. The
  sum is rest-of-season DDF Value only; this week's points are counted
  nowhere in it.
- **Net chain**: the sum of step values, in DDF Value. CHURN iff Net chain >
  Keep. The ticket's `evaluateChain` / `bestChainFromItems` remain the
  reference; this concept only lays out what they return.

## Data each panel needs

| Panel | From the weekly-input contract | From elsewhere | Gap |
| -- | -- | -- | -- |
| Header, board week | `season`, `content_week` (Tuesday flip), `built_at` | `pipelines/nfl_week.py` | none |
| Source strip | every leg's `availability`, `freshness`, `label`, `missing_reason`, `content_vintage` | chart freshness from the chart build | chart freshness is not a contract leg |
| Value, Change, waiver line | none (by rule) | published `players.json`, value model at the league setting, last week's board | needs last week's board kept (versioned artifact) |
| Rostered %, most-added | none | ESPN roster % and adds trend (retired board read ESPN directly) | **not in the contract yet**; new contract field (decided) |
| This week column | `experts.<name>` values for the scoring, `status.values.injury_status`, `status.values.practice_participation`, `bye.values.bye_week` | none | which expert leg is named (S4 setting) |
| Your swaps | none | pasted roster, `players.json` | none |
| Slate strip, windows | `game_week` on slate fields | kickoff times per team | **not in the contract yet**; new contract field (decided) |
| Bench readout | none | lineup resolve `objective_window`, `bye_share`; JEG-1276 breakout rates | readout build ticket not filed yet |
| Chain steps | `status` (eligibility: out, IR, locked), `bye` | landing chances and league claim rules | claim rules have no home; FAAB is out of scope for v1 |

## Decided (Jeremy, 2026-10-29)

- **FAAB is out of scope for v1.** After first saying a FAAB conversion would
  have to be created, he said: "dont' even research it, we aren't ready to
  approach it". The cost of a move is only the bench player dropped, priced
  in DDF Value. No FAAB ticket, research or field.
- **This week's expert points:** shown in the grey column as context, never in
  a verdict or a sort ("2) yes").
- **Rostered % and kickoff times:** new fields on the weekly-input contract
  (a minor version bump, one ingestion), proposed on JEG-1227 ("3) yes").

## Still open

Hit chance and landing chance both multiply into Net chain, which decides
CHURN or KEEP, so whatever they read is part of the verdict. No pick is made
here.

1. **Hit chance** (the chance a claimed player turns out worth holding):
   - A: the JEG-1276 historical breakout rates by depth, looked up by a ROS or
     season measure of role (his depth on the team in the ROS projections, or
     his season-to-date snap share). Keeps the verdict ROS-only.
   - B: the same rates, looked up by this week's depth-chart order from the
     weekly-input contract. This feeds this week's depth chart into the CHURN
     or KEEP verdict, which the rule "do not blend weekly data with ROS data,
     ever" would have to allow.
   - C: hit chance left at 1 until research lands, labelled on the card.
2. **Landing chance** (the chance a claim is won). The retired board's model
   is not in the repo. Candidate sources:
   - A: the league's waiver order alone (in rolling-priority leagues, you win
     any claim where you are ahead of every team likely to want him). Season
     state, not weekly data.
   - B: demand from the adds trend (how fast he is being added this week).
     This feeds weekly data into the verdict, as in hit chance B.
   - C: landing chance left at 1, labelled on the card, until a source is
     chosen.
3. **Chain helpers.** JEG-1197 names `evaluateChain` and `bestChainFromItems`
   from the retired artifact; neither is in the repo or the archive. If they no
   longer exist, the build writes them fresh against this concept.

## Not in scope

No FAAB in any form. No engine, spec, reference, `config/` or Supabase change. No new threshold,
weight or default. No page in `app/` or `dist/`. The build tickets stay blocked
on JEG-1227/1228 and on the answers above.
