# Math and Logic Review Agenda

Jeremy (2026-10-08): "I expect we will need to do a full math and logic review
when everything else is working, so when it comes time for that we will need a
way to coordinate to get to the right answer. One off questions won't result in
the right outcomes."

This file lists every open math or logic question for that review in one
place. It is an agenda. It does not record decisions. A decision goes to
`docs/decisions.md`, and the rule it sets goes to `docs/methodology.md`. The
item here is then marked with the decision id.

**Rule for every session until the review:** if you find a new math or logic
question, add it here as a new `MR-` item with the same fields. Do not settle
it on its own in a branch. A fix that moves a number on a question listed here
waits for the review, unless the current number is plainly wrong (for example
a crash, a parity break, or a value that contradicts a rule already decided).

Numbers below are cited from the log or test that measured them. "Not
measured" means nobody has run that option yet.

## How the review runs

1. **Freeze one build.** Pick one `main` commit and its fixture after the
   pending engine branches have merged (at minimum `fix/views-invariants`,
   which changes all three views; see MR-01, MR-03, MR-04, MR-05). Record the
   SHA at the top of the review's log entry. Every number in the review comes
   from that build.
2. **Look at the numbers in the math inspector.** Use
   `modules/math-inspector.html` (live:
   https://jb-barrel-droid.github.io/fantasy-tools/modules/math-inspector.html,
   or `dist/modules/math-inspector.html` after `make sync`). It shows each
   source's inputs, its translation (rostered counts, waiver line, implied
   weights), the Indexed pie next to the anchor's, the VORP vs waivers and
   Adjusted values factors, and a one-player drill-down. Its "View checks"
   section measures the three view invariants. Use the same settings for
   every item: 12 teams Full PPR (the saved setup), 10 teams Half PPR,
   14 teams Standard, and 8 teams Full PPR. Add 12 teams Full PPR with
   Superflex 1 for roster items and bench share 5% / 30% for bench items.
3. **Decide in dependency order** (next section). For each item, Jeremy
   picks an option, or writes a new one. Each decision gets:
   - an entry in `docs/decisions.md` (`category: methodology`,
     `silence-default: explicit-tap`) that names the `MR-` id;
   - the rule written into `docs/methodology.md`;
   - the item here marked `Decided: <decision id>`.
   Nothing is implemented during the review. Implementing items one at a
   time is the one-off pattern this file exists to avoid. A later decision
   can also change what an earlier one means in practice.
4. **One implementation pass.** One branch implements every decision. It
   adds one test per decided invariant, and each test must fail on a
   simulated broken state (CLAUDE.md). Then it runs the 12-combo sweep
   (3 scorings x 8/10/12/14 teams) in all three views, plus a custom roster,
   Superflex 1 and two bench shares, on `make sync` builds of the frozen
   commit and the branch. The sweep reports `fixedPieIndexed`, the view
   invariants, `sourcePeaks` and every `getAllRows` value that moved.
5. **Jeremy reviews the movement table** (what moved, by how much, which
   decision moved it) before the merge. After the merge, re-run the
   inspector's View checks on the live page and log the result.

## Suggested order and dependencies

| Stage | Items | Why this order |
| --- | --- | --- |
| 1. Definitions | MR-01 (which total), MR-03 (what Indexed values are) | Every other view and guard is stated in terms of these two. |
| 2. The anchor | MR-02 (roster shape), MR-11 (bench share), MR-12 (ESPN display rules), MR-16 (reader position shares) | The anchor feeds every view. Decide how it moves before deciding what is scaled to it. |
| 3. Published-chart inputs | MR-09 (translation assumptions), MR-08 (short charts), MR-15 (publisher superflex values) | These set each chart's value above waivers, which VORP vs waivers and Adjusted values both use. |
| 4. The other two views | MR-04 (VORP vs waivers), MR-05 (Adjusted values) | Both need stages 1-3. |
| 5. Derived series | MR-06 (`*_adjusted` series), MR-10 (projection sources, option C) | Their role depends on what the views became. |
| 6. Time | MR-07 (prior week) | Δ is a difference of two values made by the rules above. |
| 7. Consumers and guards | MR-13 (deploy gate), MR-14 (spreads and trade targets) | Pin the decided rules, then check what reads them. |

Dependencies:

- MR-01 -> MR-03, MR-04, MR-05, MR-10, MR-13
- MR-03 -> MR-04 (if Indexed becomes value above waivers x one factor, it is
  the same as VORP vs waivers, and one of the two views needs a new meaning)
- MR-02 -> MR-04, MR-05, MR-12 (the tier pool), MR-07
- MR-11 -> MR-02 (both change the anchor's position pies), MR-10 (the CBS ROS
  checks are bench-share checks)
- MR-08, MR-09 -> MR-04, MR-05
- MR-02, MR-08 -> MR-15 (publisher superflex values sit on the anchor's
  unrepriced QB pie and on the short-chart extension)
- MR-05 -> MR-06 (does the `*_adjusted` series still have a job), MR-14
- Everything -> MR-13

---

## MR-01 - Which total must match (the shared basis)

**Question.** Jeremy's invariants say every source's total equals the
anchor's: "total pies are the same" for Indexed, "the same exact scale" for
VORP vs waivers, and the DDF weights for Adjusted values. Over which players?
(a) Players the source and the ESPN anchor both price (QB/RB/WR/TE). (b) All of
the chart's players against all of the anchor's players. (c) Only players above
waivers on both (the "VORP>0 overlap" that an old pipeline comment names).

**Why it matters.** It decides the scale factor of every published chart in
every view. It therefore moves every published value, every buy and sell gap
on v2 Trade targets, and the disagreement spread.

**Current behaviour (main).**
- Indexed published charts are not scaled to any total. The saved and derived
  value is `translate_ranked` output, value above waivers x
  `OUR_MAX[pos] / max_vorp[pos]` per position
  (`pipelines/vorp_translation/unified.py:508`). So the pie total is whatever
  falls out. Measured with the math inspector (GAP-VIEW-INVARIANTS-MEASURED,
  `docs/claude-log/2026-10-08-math-inspector.md`), each chart's total against
  the anchor's over the players both price:

  | Setting | USA Today | FantasyCalc | FantasyPros | CBS |
  | --- | --- | --- | --- | --- |
  | Full PPR, 12 | +5.2% | -23.0% | +22.4% | -11.9% |
  | Half PPR, 10 | +15.3% | -12.6% | +25.6% | -4.9% |
  | Standard, 14 | -3.0% | -31.1% | +8.2% | -19.0% |

  CBS ROS, Razzball and the `*_adjusted` series match to 1e-12.
- **Why `fixedPieIndexed` passes anyway** (code read, this session):
  `fixedPieDiagnostics` (`app/trade-value-chart/assets/curve-widget.js:3883`)
  skips every key in `AS_PUBLISHED_KEYS` (usatoday, fantasycalc, fantasypros,
  cbs). It pushes `{basis:"pipeline", ok:true}` without computing a total. Its
  comment says the pipeline's `proportional_scaling_vorp_overlap` enforces
  the overlap total, but no such function exists under `pipelines/` any more.
  The saved values come from `translate_ranked`, which scales each position's
  top to a fixed maximum and never matches a total. So the guard is green
  because it checks only CBS ROS, Razzball, the `*_adjusted` series and the
  anchor. Both statements are true together: `fixedPieIndexed` is true in
  every combo, and no published chart's Indexed total equals the anchor's.
  Logged as GAP-FIXEDPIE-SKIPS-PUBLISHED.
- CBS ROS and Razzball (option C) and the derived VORP vs waivers views use
  basis (a).

**Options.**
- (a) Anchor ∩ source, QB/RB/WR/TE. This is what `fix/views-invariants`
  (views-audit lane, local work in progress, not pushed) implements for all
  three views (`ValueModel.scaleToSharedTotal`, `anchorGroups`). One factor per
  chart. The factor sizes are the inverse of the table above (FantasyCalc
  x1.30 at Full PPR 12, FantasyPros x0.82). Not swept yet.
- (b) All of the chart's players against the anchor's whole pie. A short chart
  (CBS lists about 116 players at Full PPR 12) would be stretched to cover
  players it does not price. Not measured.
- (c) Above-waivers overlap only. The players at 0 don't count, so the
  basis changes with the waiver line. Not measured.

**Depends on:** nothing. Decide first.
**Sources:** GAP-VIEW-INVARIANTS-MEASURED, `tests/test_view_invariants.py` on
`fix/views-invariants` (local), `docs/claude-log/2026-10-08-math-inspector.md`.

## MR-02 - Should the anchor follow roster shape (Superflex, QB/WR steppers)

**Question.** When a reader changes the roster (Superflex 1, QB 2, WR 4, more
bench), should the ESPN anchor and the raw value-above-waivers series
(espn_vorp, cbsros_vorp, razzball_vorp) be re-priced at that roster?

**Why it matters.** The derived published charts already follow the roster
through `positionalMaxForSetup`. The anchor does not. In a superflex league
the charts and our own line therefore disagree about the whole QB position,
and every QB buy or sell signal follows from that disagreement.

**Current behaviour.** The anchor is the built two-tier leg at the reference
roster. A roster change reaches it only through `applyRosterShape`'s top-N
average factor (`curve-widget.js:1774`). The raw value-above-waivers pies stay
at the reference roster. The ESPN tier pool (MR-12) also stays at the
reference roster. Measured at Superflex 1, 12 teams, Full PPR
(`docs/claude-log/2026-10-08-superflex.md`):

| | SF 0 | SF 1 |
| --- | --- | --- |
| ESPN anchor QB1 / QB12 | 29.5 / 6.5 | 30.9 / 6.8 |
| espn_vorp QB1 | 27.5 | 26.6 |
| FantasyCalc QB1 / QB12 | 25.0 / 3.6 | 70.0 / 11.1 |
| USA Today QB1 / QB12 | 25.0 / 9.8 | 70.0 / 27.6 |

At 10 teams the published QB1 goes 23.6 -> 35.6 while the anchor's goes
22.3 -> 23.1.

**Options.**
- (a) Leave it. The anchor is a reference-roster price and the caption says
  so.
- (b) Rebuild the anchor's two-tier leg live at the reader's roster. The
  browser already prices live two-tier legs for CBS ROS and Razzball, so this
  means building `twoTierConfig` from `rosterShape` instead of the reference.
  The tier pool (MR-12) would then follow too. Not measured.
- (c) Scale the anchor's position pies by the same ratio the published charts
  use (`positional_max_for_setup`: M_pos(setting) / M_pos(saved)). Not
  measured.
- (d) Turn the roster steppers off for the anchor-based views and label them.

Sub-question: publishers' own superflex values (FantasyCalc `numQbs=2`, CBS /
USA Today / FantasyPros 2QB columns). Saved and carried to the fixture since
2026-10-08 (feat/superflex-publisher-values); how the views use them is MR-15.

**Depends on:** MR-11 (bench share also sets the anchor's position pies).
**Sources:** JEG332-SUPERFLEX-FLEX (open decision half),
GAP-SUPERFLEX-PUBLISHER-VALUES, `docs/methodology.md` "Superflex".

## MR-03 - What Indexed values are

**Question.** The Three Views define Indexed as "the original published trade
charts are indexed to match the value range of the other charts". Today's
Indexed value of a published chart is its translated value above waivers,
with each position's top pinned to our positional maximum. Is that the
intended thing?

**Why it matters.** Indexed is the default view, and every published curve in
it starts at the same place: QB 25 / RB 70 / WR 55 / TE 30 at 12 teams
(engine sweep, `docs/claude-log/2026-10-08-engine.md`). The ESPN anchor starts
at 29.5 / 70.0 / 47.8 / 29.2 at Full PPR 12
(`docs/claude-log/2026-10-08-projection-total-only.md`). So a publisher's
cross-position weighting never reaches the Indexed curve's peaks. This
conflicts with two written rules: "There is no cap at the anchor's top value:
a publisher whose implied weighting puts its top player above ours shows
that" (methodology, Three Views), and Jeremy's "positions and bench/starter
have different weights" for Indexed. It is the reverse of what option C did
for CBS ROS and Razzball (MR-10).

**Current behaviour.** `translate_ranked`: value above waivers x
`our_max[pos] / max_vorp[pos]`, where `our_max` is `OUR_MAX` (QB 25, RB 70,
WR 55, TE 30; "today's fixed anchors", `unified.py:59`) at the saved setup
and `positionalMaxForSetup` elsewhere. Players at or below the waiver line are
0. No total factor (MR-01). `fix/views-invariants` (local work in progress)
multiplies these translated values by one factor to the anchor's shared
total. That keeps the per-position pin, so its claim that each chart "keeps
its own position x starter/bench split" holds within each position's shape
but not across positions.

**Options.**
- (a) Keep the per-position pin and add one total factor (the views WIP).
- (b) Value above waivers x one factor, with no per-position pin. That is
  numerically the same as VORP vs waivers (MR-04), so the two views would
  need different meanings.
- (c) The publisher's native values (not value above waivers) x one factor
  over the shared basis. This is a literal "index" of the published chart,
  and players below waivers keep their native value. Not measured.
- (d) Leave as is (per-position pin, no total).

Sub-questions: where do the `OUR_MAX` constants come from, and should they be
the anchor's own positional tops at each setting? The 2026-09 CLAUDE.md note
about "published charts' 75-80" RB peaks is stale: all four now start at RB 70
(`docs/claude-log/2026-10-08-projection-total-only.md`).

**Depends on:** MR-01.
**Sources:** JEG332-DERIVED-PEAKS, `docs/methodology.md` "League-settings
engine" and "Short charts" (last paragraph).

## MR-04 - VORP vs waivers: "the same exact scale"

**Question.** Jeremy: VORP vs waivers "shows the differences in deconstructed
values of each player on the same exact scale". Is that one factor per chart
so its total equals the anchor's total, or a common unit that needs no
per-chart factor?

**Why it matters.** One factor per chart makes every chart's pie equal by
construction, so differences between charts are only in how each one
distributes its pie. A common unit (for example projected points per game
above waivers) would also show that one chart values the whole pool more than
another. Projection sources have that unit natively. Published charts do not.

**Current behaviour.**
- Derived views (every setting except the saved one, and CBS everywhere):
  value above the setting's waiver line in publisher units x one factor per
  chart, matching the anchor's total over the players that chart ranks. They
  equal the anchor total at every setting (math-inspector log).
- Saved views at Full PPR 12 (FantasyCalc, FantasyPros, USA Today) come from
  `build_imputed_vorps.py`, a method with no waiver line
  (`docs/claude-log/2026-10-07-short-chart-waiver.md`). They carry the natives
  of the week they were built, and they fall short of the target total by
  358 / 284 / 389 points. `fix/views-invariants` (local work in progress) stops
  drawing them and derives these views at every setting.
- ESPN raw value above waivers and the ESPN anchor use different waiver lines.
  Darren Waller at Full PPR 12 is 3.7 on espn_vorp and 0.0 on the ESPN line.
  The raw series uses `projectionRoles` at the active roster with surplus over
  a starter baseline. The anchor uses the two-tier pool at the reference
  roster. Not investigated
  (`docs/claude-log/2026-10-08-espn-below-waiver.md`).

**Options.**
- (a) One factor per chart to the anchor's shared total (current derived
  views; the views WIP everywhere).
- (b) A common unit: projection sources in their own points per game above
  waivers, and published charts mapped into that unit by one factor fitted on
  shared players. Not measured.
- (c) Keep the saved views at the saved setup. They are short of target and
  out of date, so this is not recommended.

Sub-question: should espn_vorp and the anchor share one waiver line?

**Depends on:** MR-01, MR-02, MR-03, MR-08, MR-09.
**Sources:** GAP-VIEW-INVARIANTS-MEASURED (2), `docs/methodology.md` "Other
chart views".

## MR-05 - Adjusted values: group totals and DDF weights

**Question.** Jeremy: Adjusted values show "the differences in value of each
player when their positional and bench/starter weights have been normalized"
to DDF weights. How is each position x starter/bench group's budget set, and
what happens to the budget a chart cannot carry?

**Why it matters.** This is the only view where a chart's weighting is
removed, so it is the view that compares players. A dropped budget understates
a whole group. A different allocation policy moves bench players by a factor
of ten (jeg-209-001: Mark Andrews 0.56 vs 6.09).

**Current behaviour (main).** Players are grouped by position x
starter/bench, where starter = the setting's dedicated + flex count. Each
group shares the anchor's total for that group in proportion to value above
waivers. Then one factor across all published charts at the setting puts the
top player at 70. Measured (math-inspector log):
- The saved views' group totals at Full PPR 12 are not the budget x 70-factor
  in any of the 24 groups.
- Derived views match except where a chart has no player above waivers in a
  group. That group's budget is dropped: Full PPR 12 CBS QB bench 8.3;
  Standard 14 FantasyPros QB bench 25.8, CBS QB bench 1.4, CBS WR bench 17.6.

`fix/views-invariants` (local work in progress) removes the 70 factor ("no
top-of-scale cap"). Each group is scaled so its total over shared players
equals the anchor's same group, with the chart's own roles for the chart and
the anchor's roles for the budget. A group with no source players still gets
rate 0 and is reported, so the budget is still lost.

**Options.**
- Lost budget: (a) drop it (current); (b) move it to the same position's
  other group; (c) spread it over the chart's other groups in proportion;
  (d) show that chart's group as unavailable ("—" + reason). Not measured.
- Whose roles define a player's group: the chart's own (views WIP) or the
  anchor's (math inspector's reference). Not measured.
- Top of scale: one 70 factor (main) or none (views WIP). With none, a
  chart's Adjusted values can exceed 70.
- Allocation policy, **jeg-209-001, still pending in `docs/decisions.md`**:
  squared-surplus group budgets (Josh Allen 11.89, Mark Andrews 0.56) or
  linear (27.80 / 6.09), on the 2026-09-29 ESPN Half PPR 12 worked example
  (Gibbs 70.0 both). The review should close this entry.

**Depends on:** MR-01, MR-02, MR-08, MR-09, MR-11.
**Sources:** GAP-VIEW-INVARIANTS-MEASURED (3), jeg-209-001,
`docs/methodology.md` "Other chart views".

## MR-06 - The `*_adjusted` (bias-adjusted) series

**Question.** The `*_adjusted` series (fantasycalc_adjusted, usatoday_adjusted,
fantasypros_adjusted, cbs_adjusted) are a different thing from the Adjusted
values view. Each is a fitted affine cell per position x tier
(alpha + beta x published) against the ESPN two-tier leg, then a per-position
peak pin and a shared total. Once MR-05 is decided, what are they for, and
should their hard tier stay?

**Why it matters.**
- Hard tier cliff: a player whose ESPN rate crosses the starter line changes
  cell and jumps about 10 points. At Standard 10 Jordan Mason vs Kyle Monangai
  (8.6469 vs 8.6508 ppg) moved fantasycalc_adjusted 18.64 <-> 7.76; the tie
  flip that exposed it is fixed, but the cliff is not
  (`docs/claude-log/2026-10-08-value-small.md`).
- Above 70: 15 `combo_reindexed` values above 70 in the 2026-10-07 fixture
  (usatoday_adjusted Bijan Robinson 76.4, cbs_adjusted Gibbs 82.4), so they
  are kept out of `consolidated_values` (GAP-CONSOL-CAP, consol-adjusted-001).
- Option C kept the peak pin for these series on purpose
  (`tests/test_projection_total_only.py`).
- Prior weeks are priced through the current fit (MR-07).

**Options** (cliff, from the value-small log; none measured):
(a) blend the starter and bench cells by the player's glide exposure
(`sliceExposures`), which makes the value continuous; (b) one cell per
position with a starter indicator, blending only near the line; (c) keep hard
tiers and document the cliff. Wider option: retire the `*_adjusted` series if
the Adjusted values view does their job.

**Depends on:** MR-05.
**Sources:** GAP-PPG-TIE-FLIP, GAP-CONSOL-CAP, `docs/methodology.md` "Source
Families And Adjustments".

## MR-07 - Prior week (Δ): which fit and which anchor

**Question.** A prior-week value can be computed with that week's anchor and
adjustment fit, or with today's. Which one should Δ use?

**Why it matters.** With today's fit, Δ shows only the source's own
movement. With that week's fit, Δ also includes our anchor moving. Example,
Bijan Robinson Full PPR 12, W4 -> W5 (`fix/weeks-tidy` log): ESPN 50.1 -> 56.2,
ESPN VORP 41.5 -> 45.9, FantasyCalc Adjusted 64.0 -> 62.5, USA Today Adjusted
56.5 -> 58.6.

**Current behaviour.** On main, Δ is not computed for ESPN, Adjusted or VORP
vs waivers (HISTORY-ESPN-PRIOR). `fix/weeks-tidy` (pushed, not merged) builds
prior ESPN legs from saved `espn_ppg` (within 0.06 of the pipeline leg). It
prices the prior Adjusted series through the **current** fit. ESPN weeks 2-4
lack the projects-0 players, so their prior value is "—", not 0.0.

**Options.** (a) Today's fit and anchor for both weeks (source movement only).
(b) Each week's own fit and anchor (total movement). (c) Show both. Not
measured.

**Depends on:** MR-02, MR-04, MR-05, MR-06.
**Sources:** HISTORY-ESPN-PRIOR, GAP-R4-PROJECTION-HISTORY, `fix/weeks-tidy`
`docs/claude-log/2026-10-08-weeks.md`.

## MR-08 - Short charts: extrapolating the waiver line

**Question.** When a chart lists no more players at a position than the
league rosters, the waiver line is read from an extension imputed from the
other charts. Are the mapping (bottom-half ratio) and the cap (last listed
value) right?

**Why it matters.** It sets the bottom of every short chart. CBS is short at
all four positions at Full PPR 12 (QB 12 listed / 21 rostered, RB 43/57, WR
44/69, TE 17/21). Once it was extended, all 116 CBS players got prices
(Matthew Stafford 0 -> 5.6). FantasyPros (12/14) and FantasyCalc (14) are
extended, but their values do not move because the imputed values hit the cap
(`docs/claude-log/2026-10-07-short-chart-waiver.md`).

**Current behaviour.** Per position and peer, one ratio = the sum of the
chart's natives over the sum of the peer's, using players both list in the
bottom half of the chart's list (at least 3, or the peer is not used). An
imputed native is the mean over peers of ratio x peer native, capped at the
chart's last listed value. Imputed players are hidden and never get a value.
`translate_ranked(peers=...)` and `ValueModel.imputeExtension` are held equal
by the parity test.

**Options.** (a) Keep it. (b) Fit the ratio on the whole shared list.
(c) Extrapolate by rank (the chart's own tail slope). (d) Drop the cap.
(e) Return to the last listed value (`insufficient_coverage`). None of (b)-(e)
is measured. The branch author asked Jeremy to review (a).

**Depends on:** MR-09.
**Sources:** V2-WAIVER-COVERAGE, `docs/methodology.md` "Short charts".

## MR-09 - Assumptions in the published-chart translation

**Question.** The translation assumes things about each publisher: the
standard default roster, a bench of 6 per team split by the 12-team bench
mix, flex shared out by D'Hondt in one pass (no self-consistent waiver lines),
and only 12-team saved inputs. Which of these does the review confirm?

**Why it matters.** These assumptions set each chart's rostered counts,
waiver lines and implied weights. Those feed MR-03, MR-04 and MR-05.
FantasyCalc's derived 8-team values will not match FantasyCalc's own 8-team
page (accepted in league-settings-001).

**Current behaviour.** `docs/methodology.md` "Publisher Flex Allocation" and
"League-settings engine". Nothing has been measured against a publisher's own
non-12-team numbers.

**Options.** Confirm as is; or pull one publisher's own 10-team page
(FantasyCalc `numTeams=10`) and measure how far the derived values are from it
before confirming. Not measured.

**Depends on:** nothing. Can run in parallel with stage 2.

## MR-10 - Projection sources matched by total only (option C)

**Question.** CBS ROS and Razzball now keep their own positional weighting and
are matched to the anchor by one total factor (Jeremy, option C,
2026-10-08). What follows from that, and do the CBS ROS health checks still
mean anything?

**Why it matters.** The curve starts now differ from ESPN's. At Full PPR 12:
Razzball QB 41.3 vs ESPN 29.5, CBS ROS RB 82.1 vs ESPN 70.0. Starts go above
70: CBS ROS RB 90.0 at Half PPR 12, 85.6 at Standard 14
(`docs/claude-log/2026-10-08-projection-total-only.md`). Any rule that assumes
a 70 top (MR-05's factor, the consolidated cap) has to allow for this.

**Current behaviour.** Two ChartHealth checks fail on CBS ROS on main. Run this
session: `python3 -m unittest tests.test_jeg68_starter_markup
tests.test_jeg69_direction_check` gives 3 failures.
- Direction check: the raw starter share is above the 85% target + 1pp at
  Full PPR 8 (0.8681) and Standard 10 (0.8609).
- Stale pins: the knife-edge Standard 14 share is now 0.8452 (pinned 0.8534),
  and the markup fixture count is 350 (pinned 349).
The views-audit WIP turns these into notes. Its reasoning is that the
starter/bench scales they check no longer price anything CBS ROS or Razzball
display after option C.

**Options.** (a) Retire both checks for CBS ROS / Razzball. (b) Demote them to
notes (views WIP). (c) Keep them and re-pin them to current data. Also decide
whether values above 70 are acceptable in Indexed.

**Depends on:** MR-01, MR-11.
**Sources:** GAP-PROJ-PEAK-PIN, GAP-032 (JEG-68), JEG-69.

## MR-11 - Bench share and the feasible window

**Question.** The two-tier legs solve a bench rate for the requested bench
share (default 15%). When that share is outside a position's feasible window,
what share should be used, and should the reader be told?

**Why it matters.** The share sets how much of each position's pie goes to
the top starters. When the share landed on the lower edge of the window, Josh
Allen took 30.6% of the CBS ROS 8-team QB pie. Forcing the QB share to 0.10 at
8 teams would move Allen 27.2 -> 31.9 and QB9-15 down 20-60%
(`docs/claude-log/2026-10-07-qb8-investigation.md`).

**Current behaviour.** Below the window, the share steps up to
`STEP_INSIDE_WINDOW` = 0.01 inside the lower edge (halving up to 8 times if
the window is narrower). Above the economics break, it falls back down. The
same rule is in the browser and the Python leg builders
(GAP-STEPUP-EDGE-PB0). It does not fire on today's data at the default share.
A low slider setting that used to withhold a position now prices it at the
nearest feasible share, and nothing on the chart says so
(`docs/claude-log/2026-10-08-cbsros-8t-qb.md`). The bench-share-low lane is
working on this now.

**Options.**
- Distance inside the window: 0.01 (current), the window's midpoint, or a
  fixed fraction of its width. Not measured.
- Below the window: step inside (current), withhold the position with a
  reason, or set a per-position share floor.
- Tell the reader: a note when the share used differs from the share asked
  for (closed PR #397 proposed one).
- Harden the fallback bisection (GAP-QB8-FEASIBLE option B) so a window
  between 0.08 and 0.15 is never missed.

**Depends on:** nothing upstream. It feeds MR-02 and MR-10.
**Sources:** GAP-STEPUP-EDGE-PB0, GAP-QB8-FEASIBLE, GAP-CBSROS-8T-NO-QB.

## MR-12 - ESPN tier and ESPN zero display rules

**Question.** Are the display rules for ESPN's tier and zeros consistent with
the decided math?

**Why it matters.** The tier labels every table row. A 0.0 creates a sell
target, while "—" does not.

**Current behaviour.**
- The tier is the ESPN line's own two-tier pool at the reference roster
  (V2-TIER-VS-ESPN-LEG). A custom roster does not change it, and a Waiver row
  has no ESPN value.
- ESPN-zero (ESPN lists the player and projects 0): 0.0 with a badge. Display
  only; the anchor's pie is not changed (GAP-025).
- Below the leg's pricing line on ESPN / CBS ROS / Razzball: 0.0, display only.
  That is 132-221 ESPN cells per combo, 14-21 of them paid by a chart
  (GAP-ESPN-BELOW-LEG).
- Residuals:
  - A Bench-tier player can show ESPN 0.0 when the live refit cell clips him
    (Woody Marks, Standard 8).
  - The Tier column still shows the ESPN tier when CBS ROS or Razzball is our
    value on v2 Trade targets.
  - ESPN weeks 2-4 show "—" for projects-0 players (MR-07).

**Options.** Confirm the rules. Decide whether the tier follows the roster if
MR-02 picks (b). Decide whether the Tier column follows the chosen "our value"
source. Decide whether a clipped Bench-tier player should be 0.0 or carry a
floor.

**Depends on:** MR-02.

## MR-13 - What the deploy gate asserts after the review

**Question.** Which invariants does the gate pin once the review is decided?

**Current behaviour.** `fixedPieIndexed` does not check published charts
(MR-01, GAP-FIXEDPIE-SKIPS-PUBLISHED). `sourceScaleAgreement` was retired
(GAP-026). `fix/views-invariants` (local work in progress) adds
`viewInvariantsDiagnostics` and `tests/test_view_invariants.py`, with broken
engines that must fail (Indexed without its total factor, VORP vs waivers on
the old basis, Adjusted capped at 70, Adjusted with one factor instead of
eight groups). Several of those are choices this agenda is still asking
about (MR-01, MR-03, MR-05).

**Action.** After stages 1-6, write one test per decided invariant, and
negative-test each against a simulated broken state. Keep CLAUDE.md's
positional-start check: compare where each position's curve starts, not only
pie totals.

## MR-14 - Consumers that compare across views

**Question.** Which view do the cross-source readouts use, and are their units
consistent?

**Current behaviour.**
- The disagreement spread leaves out the VORP vs waivers series and, in that
  view, the published charts. In Adjusted values it assumes the published
  charts are on the point scale, which was not measured
  (`docs/claude-log/2026-10-07-disagreement-units.md`). If MR-05 removes the
  70 factor, that assumption needs re-checking.
- v2 Trade targets compute sell and buy gaps between a published chart and our
  value. The gap size depends on MR-01 and MR-03 (the factor) and on MR-12
  (0.0 vs "—").

**Depends on:** MR-03, MR-05, MR-12.

## MR-15 - Publisher superflex values in the views

**Question.** With a superflex slot on the roster, the engine replaces a
chart's 1-QB natives with the publisher's own superflex values
(`native_superflex`, `savedPublishedNative`) and then runs the same league
math. Is that the right use of them in each view, and in the waiver-line
extension?

**Why it matters.** They are the only superflex numbers a publisher states.
Once the producers save them (GAP-SUPERFLEX-PUBLISHER-VALUES), every
superflex chart on the page uses them, and the QB depth they imply is very
different from the 1-QB derivation.

**Current behaviour.** Overlay by player: FantasyCalc replaces every
position (its `numQbs=2` list reprices RBs too); CBS, USA Today and
FantasyPros replace QBs only. The overlaid natives also feed the other
charts' short-chart extension (`publishedPeers`, MR-08). Measured on a
fixture carrying the live publisher columns (FantasyCalc `numQbs=2` pulled
2026-10-08, CBS Week 4 2QB, FantasyPros Week 5 2QB Value; USA Today blocked
locally, so it stays derived), Full PPR, QB1 / QB12 / QB24
(`docs/claude-log/2026-10-08-sf-values.md`):

| View, teams | Source | SF 0 | SF 1 derived from 1-QB | SF 1 publisher values |
| --- | --- | --- | --- | --- |
| Indexed, 12 | FantasyCalc | 25.0 / 3.6 / 0 | 70.0 / 11.1 / 0 | 70.0 / 22.9 / 8.4 |
| Indexed, 12 | CBS | 25.0 / 5.6 / 0 | 70.0 / 16.0 / 0 | 70.0 / 9.5 / 0 |
| Indexed, 12 | FantasyPros | 25.0 / 4.1 / 0 | 70.0 / 11.5 / 0 | 70.0 / 49.5 / 37.3 |
| Indexed, 10 | FantasyPros | 23.6 / 3.9 / 0 | 35.6 / 5.8 / 0 | 35.6 / 18.0 / 7.7 |
| VORP vs waivers, 12 | FantasyCalc | 31.4 / 5.6 / 0.5 | 43.5 / 6.9 / 0 | 76.1 / 24.9 / 9.2 |
| Adjusted values, 12 | FantasyCalc | 32.3 / 5.8 / 0.4 | 31.1 / 5.7 / 0 | 13.0 / 4.4 / 2.2 |
| Adjusted values, 12 | FantasyPros | 21.6 / 4.2 / 1.2 | 24.6 / 5.1 / 0 | 6.7 / 4.7 / 3.7 |

FantasyCalc RB1 / RB12 / RB24, Indexed 12: 66.5 / 28.2 / 11.4 derived,
66.5 / 21.1 / 6.9 with its own list.

Not decided here:
- *Adjusted values push superflex QBs below their 1-QB values* (FantasyCalc
  QB1 32.3 -> 13.0, FantasyPros 21.6 -> 6.7). The DDF weights the groups are
  normalized to come from the anchor, which does not reprice QBs for
  superflex (MR-02), so a chart that prices QBs as superflex QBs is scaled
  down to a 1-QB QB pie. This is the one result that looks wrong.
- *FantasyPros QB24 at 37.3 (Indexed 12)* is faithful to the chart:
  FantasyPros' own 2QB Value prices QB24 at 37.5 (QB1 69.5, QB32 1.0) against
  RB24 at 25.8. Its list stops at 32 QBs, so the waiver line comes from the
  MR-08 extension, which is now fed by the other charts' superflex values.
- *CBS QB12 falls* (16.0 derived -> 9.5): its 2QB column is steeper than the
  derivation. That is CBS's view.

**Options.**
- (a) Keep the overlay as is (the ranker's stated superflex numbers, then the
  same league math).
- (b) Use publisher superflex values only where the chart prices every
  position (FantasyCalc); derive the QB-only columns' charts from 1-QB values.
- (c) Use them for QB ordering only and keep the derived scale (rank-map the
  superflex column onto the derived QB values).
- (d) Hold all superflex values until MR-02 is decided (no overlay; the
  saved rows wait).
None of (b)-(d) is measured.

**Depends on:** MR-02 (anchor follows roster shape), MR-08 (short charts),
MR-05 (Adjusted values weights).
**Sources:** GAP-SUPERFLEX-PUBLISHER-VALUES, JEG332-SUPERFLEX-FLEX,
`docs/methodology.md` "Superflex".

## MR-16 - Reader position shares: how far an edit reaches, and the bounds

**Question.** `TradeValueCurveControls.setPositionWeights` (JEG-452, BE-2)
lets the reader set the QB / RB / WR / TE shares of the total pie. Which
views and series should a share edit move, should the anchor's total stay
fixed when it does, and what range should each share have?

**Why it matters.** Frame 11 of v2 puts the shares in the reader's hands. A
share edit is a statement of the reader's own weights, so it is the most
direct input to Adjusted values ("re-weighted to DDF weights"), yet today it
reaches the views only through the live two-tier calibration.

**Current behaviour** (built with the API, no rule changed; Full PPR, 12
teams, QB 6.4% -> 16.4%, the other three scaled down in proportion):
- A share scales that position's calibration pie (`activePies`), the same
  path as the classic page's linked sliders (`setPositionWeight`). The live
  DDF calibration, the ESPN anchor fitted to it and the `*_adjusted` series
  move: ESPN top QB / RB / WR / TE 29.5 / 70.0 / 47.8 / 29.2 ->
  70.0 / 58.0 / 39.6 / 24.2; FantasyCalc adjusted QB1 27.3 -> 64.2.
- The anchor's total is not kept: 2,636 -> 2,444 (-7%), because the display
  scale pins the overall top player at 70. CBS ROS and Razzball are matched to
  the anchor by total, so they scale down about 7% at every position.
  `fixedPieIndexed` holds (it checks against the moved anchor).
- The published charts' Indexed values do not move. In the VORP vs waivers and
  Adjusted tabs the CBS series also moves; FantasyCalc, FantasyPros and
  USA Today do not.
- Bounds: 1% to 97% per share (`getPositionWeightBounds`). The two-tier solve
  is linear in the pie, so any share above 0 calibrates like the default and
  only 0 would withhold the position; 1% matches the bench-share floor.
  Out-of-range shares are clamped, the four always total 1, and a league
  change (scoring or teams) resets them to the derived defaults.
- With no edit, every value is unchanged (12 combos x three views, 148,716
  values, before/after sweep in the JEG-452 PR).

**Options.**
- Reach: (a) keep (calibration pie only); (b) also set the DDF group weights
  the Adjusted view normalizes to (MR-05); (c) also reprice the published
  charts' Adjusted values directly. Not measured.
- Anchor total: keep the 70 top pin (current), or hold the anchor's total and
  let the top move (MR-01, MR-03). Not measured.
- Range: 1% floor (current), a per-position floor (for example the share
  where the position's top player would fall below waivers), or the bench
  share's feasible window logic applied per position. League change: reset
  (current) or carry the shares over.

**Depends on:** MR-01, MR-03, MR-05, MR-11.
**Sources:** JEG-452, `docs/v2-design-notes.md` BE-2,
`tests/test_position_weights_setter.py`.

---

## From views-audit

Lane 12 (branch `fix/views-invariants`), 2026-10-08. Under the review rule
this branch changes **no values**. It measures every view against Jeremy's
three invariants and gates only what already holds. Every number below comes
from one build: `origin/main` fcf7da6 (Week 5 fixture), `make sync`, measured
headless on the live page at the 12 combos (3 scorings x 8/10/12/14 teams),
a custom roster (RB 3, FLEX 2, BENCH 8, Full PPR 12), and bench shares of 30%
(Full PPR 12) and 5% (Half PPR 10). The basis is the players the source and
the ESPN anchor both price (QB/RB/WR/TE), which is MR-01 option (a). The page
publishes the same numbers as `TradeValueCurveDiagnostics.viewInvariants`
(field list at the end). They agree with the math inspector to the 0.1%
(Full PPR 12: USA Today +5.2%, FantasyCalc -23.0%, FantasyPros +22.4%,
CBS -11.9%).

### VA-1 - Where each invariant holds today (all 15 settings)

| View | Source | Ratio to the anchor (min - max) | Holds? |
| --- | --- | --- | --- |
| Indexed | CBS ROS, Razzball, 4 x `*_adjusted`, 3 x raw value above waivers | 1.000000 | yes (now gated) |
| Indexed | USA Today | 0.897 (Full 12, bench 30%) - 1.693 (Half 10, bench 5%) | no |
| Indexed | FantasyCalc | 0.658 - 1.280 | no |
| Indexed | FantasyPros | 1.041 - 1.823 | no |
| Indexed | CBS | 0.766 - 1.341 | no |
| VORP vs waivers | raw ESPN / CBS ROS / Razzball | 1.000000 | yes (now gated) |
| VORP vs waivers | USA Today / FantasyCalc / FantasyPros | 0.712 - 0.995 | no: 0.98-0.995 at derived settings, 0.71-0.73 at Full 12 standard roster (saved views, VA-3) and with the bench share moved (VA-4) |
| VORP vs waivers | CBS | 0.988 - 1.000 | no (different basis, VA-2) |
| Adjusted | 4 published charts | group spread 1.00 - 6.7 (inf where a group's shared players are all 0); level 0.62 - 1.10 | no (VA-5) |

"Own split" (Indexed, "positions and bench/starter have different weights"):
every published chart's position x starter/bench shares differ from the
anchor's by 1.4-13.3 percentage points, so that half of the Indexed invariant
holds. CBS ROS 2.1-7.2pp, Razzball 0.5-3.3pp.

**Why `fixedPieIndexed` is green while the published totals are off.**
`fixedPieDiagnostics` skipped every published chart with `{basis:"pipeline",
ok:true}` and no total. The note said the pipeline indexes them to the anchor
(`proportional_scaling_vorp_overlap`). That stopped being true when the saved
values became the `translate_ranked` output (JEG-64). That output puts each
position's top at `OUR_MAX` / `positionalMaxForSetup` and never matches a
total. This branch fixes the guard's honesty only: the published rows now carry
the measured shared total, target and delta, labelled "not gated (published)",
still `ok:true`. The Chart Health note no longer says they are checked
upstream.

### VA-2 - Two bases in use for "the anchor's total"

CBS ROS, Razzball, the `*_adjusted` and raw series, and the fixed-pie guard
use shared/shared (`sharedPieBasis`): source total over shared players = anchor
total over shared players. The derived VORP vs waivers view uses the chart's
total over **all** its translated players = the anchor's starter + bench group
totals over the chart's players (`derivePublishedViews`). The second basis
leaves the shared ratio at 0.98-0.995 and leaves out about 2.7 points of anchor
value held by its waiver-role players. Pick one basis for every view (MR-01).

### VA-3 - Saved `vorp_views` are a different vintage

At Full PPR, 12 teams, standard roster, the VORP vs waivers and Adjusted tabs
draw the saved `vorp_views` (generated 2026-10-03) for FantasyCalc, FantasyPros
and USA Today. The Indexed tab beside them uses the Week 5 natives. Top native
values: FantasyCalc saved 10,825 vs current 10,696 (Gibbs); USA Today saved 72
vs current 77 (Gibbs). USA Today also has a different top 3 (saved: Gibbs,
Smith-Njigba, St. Brown; current: Gibbs, Smith-Njigba, Robinson). FantasyCalc's
saved view lists 199 players against 196 now. Every other setting derives the
views from the current natives. Options: (a) derive at every setting (what
option A below does); (b) keep the saved views but rebuild them every week with
the natives; (c) as now. MR-04 option (c) covers the same point.

### VA-4 - The bench-share slider moves the anchor but not the published charts

The ESPN anchor re-prices on the bench-share slider. The published charts do
not. So every published total ratio swings with the slider: FantasyPros Indexed
1.22 at 15% vs 1.82 at Half 10 / 5%; VORP vs waivers 0.71-0.73 at 30%.
Whatever MR-01 and MR-11 decide, the published charts are scaled to the anchor
at 15% only, unless a total factor is applied live (option A does that).

### VA-5 - Adjusted values: proportional, but not equal, to the DDF weights

Derived Adjusted groups get the anchor's group budget over the chart's players
(anchor roles), shared in proportion to value above waivers inside the
chart's own group (chart roles). Then one batch factor puts the top player at
70. Measured on the shared basis against the anchor's group totals, the group
ratios agree with each other only for CBS at Standard 14 (spread 1.000).
Elsewhere the spread is 1.08-6.7 and the level (pie) is 0.62-1.10 of the anchor's.
Two reasons: the 70 factor, and budgets spread over chart players the anchor
does not price. Unfunded groups (a group the anchor funds where the chart has
nobody): CBS QB bench at every 12- and 14-team setting, plus WR bench at 14
and RB/WR bench on the custom roster; FantasyPros QB bench at 14 teams.
Covered by MR-05.

### VA-6 - CBS ROS and Razzball in the Adjusted tab

They show the same values in every tab (option C, total only). Their own split
differs from the DDF weights by 2.1-7.2pp (CBS ROS) and 0.5-3.3pp (Razzball).
So in the Adjusted tab they are the only curves whose weights are not
normalised. Options: (a) leave them (option C everywhere); (b) in the Adjusted
tab, re-weight their raw value above waivers to the anchor's eight group
totals, as for the published charts. Option (b) is not measured. Depends on
MR-05 and MR-10.

### VA-7 - The CBS ROS fixed-pie direction and markup checks (Chart Health FAIL)

Week 5 data, live page: `CBS ROS fixed-pie direction` FAILs at Full PPR / 8
teams (raw starter share 86.8% vs 85% + 1pp) and Standard / 10 (86.1%).
`CBS ROS starter markup ratio sane` FAILs at Full PPR / 8 (0.979, band
0.98-1.6). `tests.test_jeg69_direction_check.test_cbsros_passes_all_twelve_shapes`
and `test_knife_edge_shape_pinned` (share pinned at 0.8534; Week 5 gives
0.8452) are red in `test-unit`.

Measured raw starter share by shape (`tests/jeg68_markup_harness.cjs`):
- ESPN: 80.5-84.6%
- Razzball: 81.4-83.9%
- CBS ROS: 83.4-86.8%, not monotone in team count (Standard 8: 83.4%;
  Standard 10: 86.1%)
- The simulated pre-valued-inputs defect the check exists for: 88.2%.

So genuine data now sits 1.4pp from the defect signature.

What the checks judge: the starter/bench scales in `buildVorpRows`. For CBS ROS
and Razzball those scales price **nothing displayed**. The CBS ROS line is its
own two-tier leg (`ddfTwoTierValuesForSource`), total-matched under option C.
Its raw curve is `pure`, one factor. Only ESPN's fall-back leg uses the
`adjusted` field, and only when the built leg is missing; for ESPN the check
already warns instead of failing.

Options:
- (a) Make the two checks informational (warn) for CBS ROS and Razzball, like
  ESPN's undisplayed fall-back. Implemented and tested in option A (below).
- (b) Keep FAIL and widen the band. The band then stops separating genuine
  data from the defect (86.8% vs 88.2%).
- (c) Replace them with a source-purity check on the inputs (per-game
  projections, not trade values).

Under Jeremy's Adjusted wording, a starter markdown below 1.0 is legitimate
weight normalisation. That argues against these checks encoding an invariant.

### Option A: one coherent implementation, ready for the review

Branch `review/views-option-a`, pushed and not for merge before the review. It
implements MR-01 (a), MR-03 (a), MR-04 (a) + VA-3 (a), MR-05 (no 70 factor,
eight group factors on the shared basis, chart roles, unfunded groups
reported) and VA-7 (a).

Every invariant then holds exactly at all 15 settings: ratio 1.000000, groups
to 1e-6. The check recomputes them independently from `unified.translate_ranked`,
and four broken engines are caught: Indexed unscaled, VORP on the old basis,
Adjusted capped at 70, Adjusted with one factor.

12-combo sweep, origin/main vs option A. Only the four published charts move;
every other series and `fixedPieIndexed` is unchanged.

- Indexed: one factor per chart per setting, 0.77-1.45. The published curves'
  starts stop being identical (QB 25 / RB 70 / WR 55 / TE 30 at 12 teams).
  The top RB becomes FantasyCalc 72-102, FantasyPros 54-67, USA Today 58-72
  and CBS 68-86.
- VORP vs waivers: x1.001-1.041 at derived settings. At Full PPR 12 the saved
  views are replaced: per-player ratios 0.005-4.9, because the vintage changes
  (VA-3).
- Adjusted: the level rises x1.11-1.53 at derived settings (Full PPR 8: x0.92-1.22)
  without the 70 factor. Peaks become 58-107.
- v2 Trade targets, the comparison table and the disagreement spread follow,
  since they read the engine's rows.

Option B for MR-03 (c), natives x one factor, at Full PPR 12, shown as top QB /
RB / WR / TE:

| Chart | Option A | Option B |
| --- | --- | --- |
| CBS | 28.4 / 79.5 / 62.4 / 34.1 | 27.9 / 64.3 / 63.1 / 40.1 |
| FantasyPros | 20.4 / 57.2 / 45.0 / 24.5 | 22.0 / 56.7 / 43.1 / 21.1 |
| USA Today | 23.8 / 66.5 / 52.3 / 28.5 | 22.8 / 48.8 / 48.2 / 40.6 |
| FantasyCalc | 32.5 / 91.0 / 71.5 / 39.0 | 44.3 / 79.6 / 71.4 / 43.4 |

Under option B, players below waivers keep a native value (CBS's lowest is
6.1). The anchor starts at 29.5 / 70.0 / 47.8 / 29.2.

### `TradeValueCurveDiagnostics.viewInvariants` (read-only, for the math inspector)

`{version: "views-audit/1", informational: true, tolerance, basis, gatedHold,
indexed: {holds, gatedHold, sources: {key: {shared, total, target, ratio,
holds, maxShareDiff, gated}}}, vorp: {holds, gatedHold, sources: {key: {shared,
total, target, ratio, holds, gated, mode?}}}, adjusted: {holds, gatedHold,
sources: {key: {groups: {"POS|role": {total, anchor, players, ratio,
unfunded}}, spread, level, holds, gated, mode}}, notReweighted: {cbsros|razzball:
{reason, maxShareDiff}}}}`. All three views are measured on every rebuild,
whichever tab is open. Published Indexed rows also appear in
`fixedPie.checks` with basis "not gated (published)".

---

## Outside this review

- K/DST: being removed from the pipeline (kdst lane, Jeremy's decision).
- Freshness, cadence and monitoring: no value math (refresh-cadence,
  monitoring and ops-dashboard lanes).
