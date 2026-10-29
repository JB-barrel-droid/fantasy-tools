# A chart estimate that steps in and out at the rostered cutoff (JEG-1336)

Research only, 2026-10-29. No value math, default, ranking or published
output changed. Jeremy picks the rule; this page lays out the options.
Figures: [data/jeg1336_fill_in.md](data/jeg1336_fill_in.md). Script:
`tools/research/jeg1336_fill_in.py` (report: `tools/research/jeg1336_report.py`).
Side finding of [JEG-1286](jeg1286-flex-flips.md).

## The answer

The jump is not really about who is in the fill set. It comes from one
chart's guess for players no chart lists. When nobody lists a player, each
chart estimates him with a straight line fitted to its own lowest-listed
players (VP-2.4e, the curve path). CBS's lowest-listed RBs all sit at 5 or 6
on its scale, so its line is almost flat: it says a 1.5 PPG backup is worth
4.7, nearly as much as the last RB CBS lists. CBS's own waiver line is 0.3.
So the guess lands far above replacement, and that one chart lifts the
player's DDF Value to 1.4 to 1.95. The other three charts' lines put him at
replacement (0). Step him out of the fill set and he is 0 everywhere.

Today in standard/12 that gives five RBs no chart lists a DDF Value of 1.38
to 1.52 (Tank Bigsby, AJ Dillon, Kyle Juszczyk, DJ Herman, Raheim Sanders).
Herman and Sanders, at about 1.5 PPG, sit above Dameon Pierce (0.64), whom
the projections rank the same and two charts list. Raheim Sanders and Chris
Brooks are the two cases the JEG-1286 sweep caught.

**How often.** On the 1,372 consecutive-bake comparisons since October 1
(98 per setting, 14 settings), the fill set changed in 536 (39%), and a
player no chart lists came in on 184. With the allocation held, the
membership change alone moved someone's DDF Value more than 0.5 in 98 of
them and more than 1.0 in 56, worst 1.73 (AJ Dillon, standard/14, October
28). It is concentrated in the 12- and 14-team settings (83 of the 98) and
at RB (80 of the 98).

**Recommendation: option D.** A curve-path estimate can't be worth more on a
chart than a player the projections rank above him. The players no chart
lists drop to about 0 (where the other three charts already have them), real-
update steps over 1.0 go from 56 to 1, and every other player moves by 0.3
or less.

## Options

| | Rule | Real-update steps over 1.0 (over 0.5) | Sweep cases over 1.0 | One-time change to today's values |
|---|---|---|---|---|
| A | Leave as is | 56 (98), worst 1.73 | 23, worst 1.74 | none |
| B | Weight each estimate by the player's share of a fill-set place (σ 0.75 PPG, as JEG-1333) | 9 (40), worst 1.53 | 1 | Sanders 1.38 to 0.22; TEs shift too (Kincaid USO 5.48 to 5.02) |
| C | Estimate every projected player some chart lists, at any depth; never estimate a player no chart lists | 17 (47), worst 1.78 (listing changes) | 1 | stars move up to 1.2 (Gibbs USO 88.65 to 89.85), 30 to 119 players per setting move over 0.1 |
| **D (pick)** | **Order cap: a curve-path estimate is never worth more on a chart than any player the projections rank above him** | **1 (23), worst 1.13** | **0** | **players no chart lists drop to about 0 (Bigsby standard/14 1.95 to 0); everyone else 0.3 or less** |
| B+D | Both (BD in the figures) | 0 (3), worst 0.70 | 1 | as D, plus B's TE shifts (up to 0.6) |

Sweep: ±0.5 and ±1 PPG to one projection for each player within 3 places of
a fill cutoff, at every position and setting, allocation held (3,716 cases).
The one case over 1.0 left under B, C and B+D, and the worst left under D
(0.99), is Josh Allen in USO moving when a backup QB's projection moves: the
QB waiver line, which PR #1077's waiver band smooths. It is the same under A.

## What each option does to a real player

Two one-source changes from the JEG-1286 sweep, allocation held (DDF Value
before to after):

| Case | Player | A | B | C | D |
|---|---|---|---|---|---|
| standard/14, Ray Davis Razzball −1 PPG | Chris Brooks | 0 to 1.74 | 0.30 to 0.35 | 0 to 0 | 0 to 0 |
| standard/12, CJ Donaldson Razzball +1 PPG | Raheim Sanders | 1.38 to 0 | 0.22 to 0.19 | 0 to 0 | 0 to 0 |

- **A.** A standard 14-team manager sees Chris Brooks, a 1.05 PPG backup no
  trade chart lists, go from worthless to 1.74 because Razzball trimmed Ray
  Davis by a point. Nothing about Brooks changed.
- **B.** The jump becomes a ramp: Brooks sits at about 0.3 and moves a few
  hundredths. But the inflated guess is still there, just scaled down, and
  every estimate near a cutoff is scaled, so TEs like Dalton Kincaid lose
  0.3 to 0.6 for no reason a manager would see.
- **C.** Brooks and Sanders are always 0, because no chart lists them. But
  charts that list few players at a position now estimate dozens more, which
  moves their waiver lines: Jahmyr Gibbs gains 1.2 in USO and Jaxon
  Smith-Njigba 1.1, from bookkeeping rather than football. And a player
  now drops to 0 whenever the one chart that lists him stops listing him
  (Roschon Johnson 1.78 to 0, standard/14, October 12).
- **D.** Brooks and Sanders are 0 before and after, the same as every chart
  but CBS already says. Tank Bigsby (3.8 PPG, no chart lists him) goes from
  1.95 to 0 in standard/14 once. Kenneth Walker III moves 83.44 to 83.74,
  one of the two largest moves for anyone else; in 11 of the 14 settings
  nobody else moves more than 0.06.

## Option D in detail

**What it does.** VP-2.4e fits a line to a chart's lowest listed players and
reads off the unlisted player's value. D keeps that line but adds one check:
walking down the projected order at that position, the curve estimate can't
be higher than the lowest value the chart gives anyone projected above him
(listed or estimated from another chart). On CBS at standard/12 the RBs
projected above Raheim Sanders include several CBS estimates at or below its
0.32 waiver line, so his estimate is capped there and his Adjusted value is
0.

**Why it fits the method.** An estimate exists to fill a chart's list to the
rosterable depth in a way that agrees with the other charts (OC-5). The ratio
path (a peer lists him) already does that. The curve path, with no peer to
anchor it, should not rank a player above players the projections and the
other charts rank higher. D only binds on curve-path estimates; the ones worth
anything today are all on CBS (section 2 of the figures).

**What it leaves.** D removes the large steps but not every fill-set step: a
player some charts list still gets a ratio-path estimate from the others when
he enters, and at TE that can move the position's top player by about 1
through the pie (Dalton Kincaid entering at standard/10 on October 22 moved
Brock Bowers 28.23 to 27.09, the one step over 1.0 left). B+D removes those too (worst 0.70), at the cost of B's TE shifts. If
Jeremy wants it fully smooth, B+D is the follow-up, not the first step.

**What it costs.** One rule in three places, paired on one branch per the
value-change rules: the curve path in `value-model.js` (estimate block near
`info.path = "curve"`), `_estimate` / the fill-in loop in
`pipelines/value_reference.py`, and the spec reference, with `value_check
compare` at 0 and zero rank-guard inversions, a before/after table on live
data, a sentinel fixture row (Sanders standard/12), the VP-2.4e line in
`docs/methodology.md` and a decision record. T1, small.

**How it sits with JEG-1333.** Fractional seats make the rostered count a
weighted mix of whole allocations, so the fill set's size varies across that
mix. Under A, each mix member can carry or drop a CBS curve guess; under D
that guess is about 0, so the mix stays smooth.

## Limits

- Python reference only. The browser engine builds the same fill set
  (`fillSets`, `value-model.js` line 941) and the same curve path, checked by
  reading it, not run.
- The history replays today's code on each bake's fixture, not what the site
  published at the time.
- A history step is measured with the allocation held to the earlier bake, so
  it leaves out flex and bench flips (JEG-1286). Players with no projection in
  the earlier bake (back from injury, new) follow today's rule in both runs.
- USO and Charlotte are measured at their own roster settings with no league
  loaded.
- B is a one-pass prototype (each estimate times its share), not a weighted
  mix of whole fill sets like JEG-1333's seats. It is continuous; a mix
  version would land between B and A.
- None of the options mixes weekly and rest-of-season data: the estimates use
  each chart's own values and the mean of the projections the pipeline
  already uses.

## Reproduce

```
python3 tools/research/jeg1336_fill_in.py --repo . --out <dir>
python3 tools/research/jeg1336_report.py <dir>/jeg1336_fill_in.json > docs/research/data/jeg1336_fill_in.md
```

Needs full git history for the replay (`git fetch --unshallow` on a shallow
clone) and imports `tools/research/jeg1286_flex_flips.py`. About 30 minutes
on 4 cores. The JSON (about 6 MB) is not committed. The script first checks
that its hooked copy of `run_pipeline` equals the reference on every setting,
and stops if not.
