# JEG-1047: the waiver line rests on one player

Investigation only (2026-10-29). No value math, default or ranking changed.
Script: `tools/research/jeg1047_waiver_anchor.py`. Figures:
[data/jeg1047_waiver_anchor.md](data/jeg1047_waiver_anchor.md). Inputs: the
committed week 8 fixture (built 2026-10-28 23:27 UTC) and the saved weekly
projections in `data/history/`. Engine: the Python reference.

## Answer

Confirmed. Each projection source (ESPN, CBS ROS, Razzball) reads each
position's waiver line from one player: the first one past the league's
rostered count (`value_reference.py` `_source_lines`, `w = work[n_rost][1]`;
engine twin `value-model.js`, `waiver = work[N].native`). Every player's value
above waivers is his projection minus that number, so changing that one
fringe player reprices the whole position. All 144 lines (3 scorings x 4 league
sizes x 3 sources x 4 positions) work this way; none fall back to another
rule.

## How big it is

A 1 PPG change to only the waiver-line player, across all 144 lines:

- a median of 18 other players at the position change value;
- the biggest single move is 3.2 points (Razzball QB, 8 teams: Bo Nix at 14.7
  PPG moves to 15.1 and every other QB reprices; one player moves 61%);
- in 19% of cases at least one other player moves more than 1 point.

The same 1 PPG change to the best player at the position moves anyone else by
at most 1.3 points. So the fringe player has two to three times the pull of
the star. His pull is capped by the gap to his neighbours: once he passes the
next player, that player becomes the line.

It reaches DDF Projections (worst 0.8 points) and also DDF Value (worst 0.76),
even though DDF Value is built from the trade charts. Only part of that is
the anchor: under every rule below it still reaches 0.59, so the projection
change also flows into DDF Value through the shared lineup and bench model.
That second channel is a separate question and is not part of this ticket.

## Options (hypothetical, projection sources only)

| Option | Worst move from a 1 PPG fringe change | Cases within 1.0 pt | Within 0.5 pt | Week-to-week line movement | One-time repricing on switch | Cost |
|---|---|---|---|---|---|---|
| Today: one player | 3.2 | 81% | 59% | 0.44 PPG | none | none |
| A. Average band, 7 players around the line | 0.82 | 100% | 85% | 0.40 | 12-team PPR: 24 of 739 players change DDF Projections (biggest 0.26, QBs) and 23 change DDF Value (biggest 0.24) | one function in JS and Python |
| B. Median band, 7 players | 3.2 | 81% | 59% | 0.44 | none | drop: identical to today, because the middle of a sorted band is the waiver player himself |
| C. Fitted curve, 11 players | 0.99 | 100% | 78% | 0.42 | similar to A | more code, no better than A |
| D. Time smoothing, this week and last | 1.4 | 95% | 82% | 0.28 | largest (median 58 rank changes per line) | engine must read last week's projections for every source; real changes show up a week late |
| A + D | 0.73 | 100% | 99% | 0.26 | largest | both costs |

The average band keeps the line where it is today (median change 0.01 PPG),
so the switch reprices little. Most real week-to-week movement in the line is
the whole tail moving together, not one player, which is why only time
smoothing cuts it much.

## Proposed tolerance

A 1 PPG change to the waiver-line player moves no other player at that
position by more than 1.0 value point in that source's Adjusted value, on the
12-combo grid for all three projection sources. Today fails 19% of cases;
option A passes all 288. A 0.5 point tolerance is met only by A + D.

## Recommendation

Option A with the 1.0 point tolerance. It removes the single-player pull,
barely moves today's numbers and adds no dependency on weekly history. Time
smoothing can be decided later on its own.

## Not covered

- CBS ROS and Razzball were held (publisher vs stored fidelity) at this build;
  their numbers here are what the engine computes from the stored projections.
  The hold is a feed question, separate from the anchor.
- The trade charts also read their waiver line from one player. Not measured.
- Engine (JS) figures were not run; the reference mirrors the same line and
  `value_check compare` would hold them together in the implementation PR.
- Bench seat counts (JEG-1121) are separate and unchanged.
