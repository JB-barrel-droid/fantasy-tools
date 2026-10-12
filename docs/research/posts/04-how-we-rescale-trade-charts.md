# How we rescale trade charts

Research post 4 (JEG-545, post 2 of 4). Draft for Jeremy's review.
Copy rules: for trades others will accept; no title abbreviations.

---

## Abstract

Every trade chart uses its own scale. One chart might give the top player a
value of 10,000; another might give him 100. To compare them, we need a common
scale -- but the rescaling must not change the chart's own ranking order. If
a publisher ranks player A above player B, our rescaled values must agree.

We use one factor per chart: a single multiplier that brings the chart's total
in line with DDF Value over the players they share. One factor preserves every
ranking the publisher made -- across positions, between starters and bench
players, everywhere. The older method used per-position rescaling, which
broke rankings. This post explains the problem it solved, the method, and what
it means for reading the "Trade charts (as published)" tab.

> Evidence: `docs/methodology.md` VP-6.4.
> Decision: JEG-482 (Jeremy, 2026-10-08).
> Engine: `value-model.js`, Indexed factor calculation.
> Guard: `pipelines/check_rank_guard.py`, `tests/test_rank_guard.py`.

## The problem: rescaling can break rankings

A trade chart is a publisher's own assessment of what each player is worth
in a trade. The ranking order is the chart's core product: if the chart says
WR3 is worth more than RB8, that is a claim about the trade market.

When we rescale a chart to put it on the same scale as DDF Value, we need
the total to match -- but we must not rearrange the chart's own rankings in
the process.

The old method rescaled each position separately (starters and bench players
got different factors, and each position got its own total to match). This
meant a chart's ranking across positions could invert. One chart ranked a
wide receiver third overall, but after per-position rescaling he showed as
fifth. Across all four charts, the 12-team saved values carried over 15,000
pairwise inversions.

## The fix: one factor per chart

The rule (JEG-482, Jeremy 2026-10-08): a published chart's Indexed values
are its native values times one factor per chart.

    factor  = DDF Value total / native total
              (over the players the chart lists that also have a DDF Value)

    Indexed = native x factor

That is it. One multiplication. The chart's total over shared players
matches DDF Value's total over the same players, and every ranking the
publisher made survives exactly.

### Why one factor works

Multiplying every native value by the same constant does not change any
ratio between two values. If the chart says player A is worth twice player B,
the Indexed values say the same thing. The order within a position is
preserved. The order across positions is preserved. The order between
starters and bench players is preserved.

Per-position rescaling applies different multipliers to different positions,
which changes the ratios between positions. That is repricing, not rescaling.

### What gets repriced, and where

The per-position repricing is not gone -- it moved to the Adjusted values
tab and the "Value above waivers" tab. Those views decompose each source
into value above waivers at the reader's league settings, with the league's
own position weights applied. That is where the tool's opinion about
positional value lives, informed by all seven sources.

The Indexed tab ("Trade charts (as published)") is the publisher's opinion,
on a common scale. The Adjusted tab is the tool's opinion, informed by
the publisher's data.

## The rank guard

A build-time check (`pipelines/check_rank_guard.py`) fails the build if any
pair of players a chart ranks apart has its Indexed order inverted. The guard
writes to `output/rank-guard.json` and `dist/modules/rank-guard.json` on
every `make sync`. It runs across all four charts at every league setting.

With one factor, the guard is trivially satisfied (one positive multiplier
cannot change order). It exists as a regression guard: if anyone changes the
Indexed calculation, the guard catches inversions before they ship.

## How to read the Indexed tab

When you open "Trade charts (as published)," each chart's values are its
native trade values multiplied by one factor so the chart's total matches
DDF Value's total over the same players. What this means:

- **The rankings are the publisher's.** If FantasyCalc ranks a player above
  another player, the Indexed values agree.
- **The scale is DDF Value's.** The numbers are comparable across charts:
  a value of 50 on CBS and 50 on FantasyCalc mean the same thing on the
  common scale.
- **Projections are available but off by default.** Projections do not have
  a "published" trade value, so in the Indexed tab they show their Adjusted
  values, turned off by default. Turn them on in Customize.

## Estimated players

When a chart does not list a player who is within the rosterable count, the
tool estimates his value from the other charts (the fill-in rule, VP-2.4).
An estimated player sits at or below the chart's lowest listed player at
that position, so the publisher's listed order is never disrupted. The
Indexed value of an estimated player is his estimate times the same one
factor, marked "estimated" with the reason.

---

## Evidence links

| Claim | Source |
|---|---|
| One factor per chart | `docs/methodology.md` VP-6.4 |
| Decision and rationale | JEG-482 (Jeremy, 2026-10-08) |
| Old method's inversions (15,000+) | `docs/methodology.md` VP-6.4 history note |
| Rank guard | `pipelines/check_rank_guard.py`, `tests/test_rank_guard.py` |
| Estimated players capped at lowest listed | `docs/methodology.md` VP-2.4f |
| Projections off by default in Indexed | `docs/methodology.md` VP-6.4 (OC-7) |
