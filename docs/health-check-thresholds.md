# Health check thresholds (JEG-1011)

What the Health check tab flags, the numbers behind each limit, and how they were derived and validated.
Code: `THRESHOLDS` in `app/v2/audit-pie.js` (protected: change only with a dated justification here and in
`docs/claude-log/`). Tools: `tools/audit_health_dump.py` (engine output for any saved week and league setting),
`tools/audit_health_thresholds.py` (derive and validate), `tools/audit_health_fixtures.py` (frozen test fixtures).

Derived 2026-10-24 from the engine after #867 (flex-filled bench seats, promotion model), on the saved weekly
inputs the page's history reader uses (`assets/history/week-N.json`), run through the same value pipeline at all 12
league settings the engine accepts (standard, half PPR, PPR x 8, 10, 12, 14 teams; default roster). The week 7 runs
equal the live engine's own output (`liveMatch` true for all 12). The spec's numbers (starter spread 5.4%, QB 23.1%,
bench 53.8%) predate #867 and are not used.

## Rule

- Train weeks 5, 6, 7 (36 combinations). Held-out weeks 3, 4 (24 combinations; CBS rest of season has no week 3 or 4 inputs, so six sources).
- For a spread: limit = 1.5 x the largest healthy value on the training weeks, rounded up to a whole point (the
  spec's own rule of thumb: "8% on a 5.4% spread is about 50% headroom").
- For the filled-in share: a share cannot be scaled 1.5x (the largest healthy share is 63%), so limit = largest + 10 points, rounded up to 5.
- Metrics that are zero by construction (position totals across sources, each source's total against the pie,
  Player values against the pie or DDF Value) keep the spec's tolerance as a floor: 1%, 0.5 points, 1.0 point.
- Stability: re-derive on the held-out weeks; the limit may move at most 20% relative. A limit that moves more is unstable.
- Fire check: no limit may fire on any held-out combination.

## Result (`python3 tools/audit_health_thresholds.py --dump DIR`)

| Check | Metric | Train max | Limit | Held-out max | Re-derived | Shift | Fires on held-out |
|---|---|---|---|---|---|---|---|
| Starter totals agree | spread of all starters across sources | 10.8% | 17% | 10.2% | 16% | 6% | 0 of 24 |
| Positions agree | worst of RB, WR, TE starter spread | 15.5% | 24% | 14.8% | 23% | 4% | 0 of 24 |
| Few fill-in values | largest filled-in share of a position's rostered slots | 63.5% | 75% | 64.5% | 75% | 0% | 0 of 24 |
| Totals add up | position totals spread across sources | 0.0% | 1% (floor) | 0.0% | 1% | 0% | 0 of 24 |
| Totals add up | a source's total vs the value pie | 0.0 | 0.5 (floor) | 0.0 | 0.5 | 0% | 0 of 24 |
| Player values tie out | projection Player values vs the pie | 0.0 | 1.0 (floor) | 0.0 | 1.0 | 0% | 0 of 24 |
| Player values tie out | chart Rescaled vs DDF Value on listed players | 0.0 | 1.0 (floor) | 0.0 | 1.0 | 0% | 0 of 24 |

Information rows, never flagged (Jeremy, 2026-10-24): the QB starter spread (3.4% to 13.7% across all 60 combinations)
and the bench spread (37% to 97%). The numbers are shown with an explanation; they are not judged.

## Today (week 7, PPR, 12 teams)

Starters 7.5% (limit 17%), RB 4.7%, WR 13.0%, TE 1.9% (limit 24%), QB 6.4% (information), bench 59.6% (information),
largest filled-in share CBS Sports WR 43 of 90 slots, 48% (limit 75%). Flags firing today: none. The page says
"Nothing is wrong: all 5 checks pass."

## What each limit is for

A limit sits above everything the engine produces on healthy inputs, so a flag means something moved, not that a
source is built differently. A 20% error in one source's starter values flags (mutation tests in
`tests/test_v2_health_check_render.py`); a 10% one does not. Tighten a limit only by re-running the derivation with
a smaller headroom and logging why. The filled-in share looks loose on purpose: CBS Sports fills in about half of
its WR slots by design (a short chart), so the check is for a chart that stops listing most of a position.

## Frozen fixtures (`tests/fixtures/audit/`, do not edit without a logged justification)

| File | Case |
|---|---|
| `healthy_week7.json` | week 7, PPR, 12 teams, 7 sources |
| `perturbed_espn_starter.json` | healthy, every ESPN starter's Adjusted value x 1.2 |
| `missing_cbs.json` | healthy, CBS Sports removed (6 sources) |
| `extreme_8team_halfppr.json` | week 7, half PPR, 8 teams (the smallest league the engine accepts; the spec's 4-team case is not a setting the engine accepts) |
| `history_week5.json` | week 5, PPR, 12 teams |

Reduced `getInspection()` shapes: only the fields `audit-pie.js` reads (valuePipeline diagnostics, per-player
adjusted/role/position/estimated, per-row Rescaled and DDF Value).

## Not a flag, on purpose

- Reconciliation does not ask a trade chart's whole Player values column to equal the pie: that column is
  Rescaled (native x one factor so the listed players add up to their DDF Value), and fill-ins and unlisted players change
  its sum. Measured on week 7, PPR, 12 teams: FantasyCalc -5.0, USA Today +10.3, FantasyPros -12.6, CBS Sports +53.5
  against the pie, projections 0.0. The table shows the sum; the check is the listed-players tie to DDF Value (VP-6.4).
- Week-over-week change tracking is a follow-up (see the notes folder).
