# How many backups should a fantasy roster hold?

---

## Abstract

How many bench spots does each position deserve, and why? We tested ten
different rules for dividing bench spots across positions and scored each one
on fit to 8,857 real drafts, accuracy on drafts the rule had not seen, and
stability across league settings. The winner: bench spots in proportion to
starters times the backups per starter that real drafters actually hold. It
fits real behaviour within 0.06 backups per team, adapts to any roster, and it
exposes a gap between what leagues hold and what the numbers say is worth
holding: net of what the waiver wire gives you for free, a bench spot is worth
only 0 to 0.5 points a week.

Terms used below. The **waiver line** is the quality of the best player you
can pick up for free at a position. **Value above waivers** is how much better
a player is than that waiver-line player. The **starter line** is the quality
of the worst starter at a position; everyone below it sits on a bench. A
**backup** is a bench player held behind a starter at the same position.
**Bench share** is the share of a position's total value held by players below
the starter line. **PPR** means points per reception. A **flex** spot is a
lineup spot that can start a running back, wide receiver or tight end; a
**superflex** spot can also start a quarterback. Positions are abbreviated QB
(quarterback), RB (running back), WR (wide receiver) and TE (tight end) in
tables and written out in prose.

A note on dates: the bench counts, bench shares and value effects quoted
below come from an analysis run on October 10, 2026, against the value engine
as it stood that day. The draft and game-log numbers come from the historical
data described where they appear.

## The question

Every trade-value tool needs a waiver line: the quality of the replacement
player available at each position. The waiver line depends on how many
players are rostered at that position, which depends on how many bench spots
go there.

Get it wrong, and every player's value above waivers is wrong too. Give too
many bench spots to quarterbacks, and the waiver line at quarterback drops,
making starting quarterbacks look more valuable than they are. Give too few
to running backs, and the waiver line rises, compressing the value of
running-back depth.

This started as a sanity check on one number, a 22.6% quarterback bench share
that turned out to be a measurement artifact, and became a question about
what a bench is for.

## The odd number that started this

The tool's bench-share readout showed 22.6% of quarterback value sitting on
benches in a 12-team PPR league. In a format where only one quarterback
starts per team, that seemed too high.

It was, and the reason was not football. Players had been sorted into tiers
(starter, bench) by the average of three projections, but their value was
measured on the tool's full blend of seven projection sources. One source,
Razzball, had a data bug: it listed Lamar Jackson at 7.1 points per game and
Patrick Mahomes at 10.5, far below every other source. On the three-source
average that did the sorting, both quarterbacks fell below the starter line
and were counted as "bench", while the seven-source blend that priced them
still valued them as starting quarterbacks. Those two players alone were 70%
of all quarterback bench value.

Tiering players on the same list that is being valued fixes it: the
quarterback bench share drops from 22.6% to 13.7% (October 10, 2026
analysis).

The lesson generalises: measure on the same basis you value on. A sort order
and a valuation that come from different inputs can quietly move real
starters into the bench tier, and every number built on the tiers inherits
the error.

## Does the bench mix even matter?

Mostly no. Across the mixes we tried, even one with zero backup quarterbacks,
the overall bench share stayed between 8.3% and 8.7% of total value, and the
ranking of the top 150 players barely moved: the rank correlation between
mixes was at least 0.98, where 1.0 would mean identical order (October 10,
2026 analysis).

What does move is how much starters at shallow positions are worth. The fewer
backups a league holds at a position, the better the best free agent at that
position is, and the less a starter is worth above him. With 3 backup
quarterbacks held across a 12-team league instead of 9, starting quarterbacks
lose about 9% of their value. Holding fewer tight-end backups costs the top
tight ends 3 to 5 points (October 10, 2026 analysis).

This is the real price of the bench decision: not how bench players are
valued, but how starters at shallow positions are valued.

## Five ways to think about a bench

Before scoring rules, it helps to ask what a bench spot is doing. Five ways
of answering give five different benches.

### 1. Lineup holes (the "man-games" approach)

The earlier fixed bench mix, 10 quarterback : 27 running back : 33 wide
receiver : 10 tight end out of every 80 bench spots, turns out to be a
principle in disguise. It almost exactly equals the number of starters at
each position times the weekly chance a starter is unavailable (a bye week
or a missed game). At the default roster that ratio is
12% : 32% : 42% : 15%.

This is the "man-games" idea from value-based drafting, the practice of
ranking players by how much better they are than a replacement: bench spots
go where the lineup holes are. It is principled, and simple. As the test
below shows, it does not match what leagues actually do.

### 2. Ranking bench players by projected points

Give bench spots to whichever positions have the most valuable bench players
by projection. This fails. The quarterback and tight-end scoring curves are
flat near the starter line, so their backups sit close to starter quality,
and a points-based bench fills with quarterbacks and tight ends: 13
quarterback and 14 tight-end bench spots in a 12-team league. Running backs,
whose backups project further below the starter line, get starved. Real
managers do the opposite.

Proximity to the starter line is not the same as value.

### 3. Insurance, upside, and the waiver wire

A bench player adds value two ways: **insurance** (he fills in when a starter
is out) and **upside** (he might become start-worthy himself). History says
how often each kind of backup actually reaches a lineup. From NFL game logs,
2015 to 2025 (nflverse), starts per week for each held backup, by how deep he
sits at his position:

| Backup depth | Quarterback | Running back | Wide receiver | Tight end |
|---|---|---|---|---|
| First backup: starts per week | 0.28 | 0.30 | 0.33 | 0.21 |
| Second backup | 0.07 | 0.17 | 0.22 | 0.08 |
| Third backup | 0.00 | 0.09 | 0.14 | 0.04 |

The first backup starts about equally often at every position. The second
running-back or wide-receiver backup still starts regularly; the second
quarterback or tight-end backup almost never does. Deeper running-back and
wide-receiver benches are justified by use. Deeper quarterback and tight-end
benches are not.

Adding insurance and upside together, points per week added by each held
first backup, 12-team PPR:

| Position | Insurance | Upside | Gross total | Net of waivers |
|---|---|---|---|---|
| Quarterback | 0.33 | 0.48 | 0.81 | +0.19 |
| Running back | 0.48 | 0.41 | 0.89 | +0.37 |
| Wide receiver | 0.64 | 0.67 | 1.31 | +0.54 |
| Tight end | 0.26 | 0.35 | 0.61 | +0.09 |

Upside is about half of a bench player's gross value. But gross is not what a
bench spot earns you, because the alternative to holding a player is picking
up the best free agent that week. The last column compares each held backup
with the best player you could actually have picked up that week, chosen
without hindsight. Net of waivers, a bench spot is worth only 0 to 0.5 points
a week. A second quarterback or tight-end backup nets about zero. And
quarterback and tight-end *upside* disappears entirely net of waivers (it
nets to between -0.06 and +0.07 in every setting tested): whatever a backup
quarterback or tight end might become, you can grab it from waivers when it
happens. Running-back and wide-receiver upside survives in PPR.

One warning from this line of analysis: measuring how good the waiver wire
is, from history, is circular. Waiver quality depends on how deep everyone
else holds, so the measurement assumes its own answer. Assume every team
holds one backup, and the historical streams match or beat held backups at
running back, wide receiver and tight end (100% to 121% as good), falling
short only at quarterback (84% to 93%). Taken literally, that sends every
bench spot to quarterback, which is absurd. We kept it in the test below as a
candidate anyway; it failed on stability, as circular measures tend to.

### 4. What real drafters do

Fantasy Football Calculator (a public mock-draft site), 12-team PPR, 8,857
drafts from 2016 to 2024, counting human picks only:

| Position | Share of skill-position picks | Per team | Backups per starter |
|---|---|---|---|
| Quarterback | 14.3% | 1.86 | 0.86 |
| Running back | 35.6% | 4.63 | 0.85 |
| Wide receiver | 39.3% | 5.11 | 1.05 |
| Tight end | 10.7% | 1.39 | 0.39 |

The shares are stable within 1 percentage point across all nine seasons.
Nearly every team carries a backup quarterback. Fewer than half of teams
carry a backup tight end: at 0.39 backups per starter, the typical team
streams the position. Real drafters hold roughly one backup per starter at
quarterback, running back and wide receiver, and treat the tight-end backup
as optional.

Two-quarterback leagues are the exception that proves the supply point. In
Fantasy Football Calculator 12-team two-quarterback drafts (2018 to 2024),
teams roster 2.56 quarterbacks each, only 0.28 backups per quarterback
starter, because a 12-team league starting two quarterbacks each already
rosters nearly every NFL starter. There is nobody left to hold. (That data
pool is labelled "2 QB" and does not separate superflex leagues from true
two-quarterback leagues.)

### 5. What the field does

An open-web survey of how others set the replacement level a bench decision
implies:

- **PlayerProfiler** (Value Over Stream): replacement is the waiver stream
  itself, the best player available to pick up. That puts the line at about
  the 19th quarterback and 19th tight end (roughly 1.5 rostered per team),
  and about the 49th running back and 49th wide receiver (roughly 4 per
  team).
- **Subvertadown**: with 20 to 25 quarterbacks claimed, streaming the
  position lands within 2 to 3 points per game of an average top-5
  quarterback; there is no value holding quarterbacks past roughly the 12th
  to 16th best. The approach breaks down in 16-team leagues, where the stream
  runs dry.
- **Fantasy Football Analytics**: baselines set by the worst starter, by
  man-games, or by a fixed cutoff at pick 100.
- **Harvard Sports Analysis Collective**: a weekly replacement level, reset
  each week rather than fixed for the season.
- **Footballguys** (Harstad): value over replacement per game, multiplied by
  games played.
- **Football Perspective**: games a player misses are valued against an
  "average backup" (the 18th tight end in a 12-team league).
- **RotoWire** (35,000 leagues analysed): the most common setup is 12 teams,
  PPR or half PPR, one quarterback, two running backs, two wide receivers,
  one tight end, one flex, a kicker, a defence and 7 bench spots. The roster
  our analysis started from (three wide receivers, 6 bench spots) is not the
  typical league. Our product default has since moved to the most common
  shape above: two wide receivers, 7 bench spots, a kicker and a defence.

The field's answers cluster where the draft data does: about one and a half
quarterbacks and tight ends rostered per team at most, and far deeper benches
at running back and wide receiver.

## The test: scoring the candidate rules

Every candidate rule was scored on three things:

1. **Fit to observed rosters**: how far its backups per team land from the
   draft data, averaged across positions (lower is better).
2. **Held-out fit**: the same error on draft years the rule was not fitted
   on.
3. **Stability**: whether the rule behaves across 12 different league
   settings, or breaks, cliffs or reverses in some of them.

| Rule | Fit error (backups per team) | Held-out error | Stable | Adapts to roster |
|---|---|---|---|---|
| Fixed 10:27:33:10 | 0.18 | 0.18 | yes | no |
| Lineup holes | 0.36 | 0.40 | yes | yes |
| **Draft ratio per starter (chosen)** | **0.06** | **0.10** | **yes** | **yes** |
| Draft ratio per team | 0.05 | 0.06 | yes | no |
| Draft ratio with the quarterback ratio halved | 0.22 | 0.21 | yes | yes |

Also tested and rejected: open by points, open by chart value, lineup holes
times drop-off, starts by depth round, insurance-plus-upside points,
net-of-waivers value, and measured streaming coverage. Each was unstable,
circular, or produced cliffs in some setting.

One row deserves a comment. Draft ratio per team fits a hair better than the
chosen rule (0.05 against 0.06), because it is fitted directly to the default
roster. But it is frozen to that roster: change the starters and it has
nothing to say. The per-starter version carries the same information in a
form that travels, and its held-out error of 0.10 backups per team is the
price of that portability. We paid it.

## The answer

**Bench spots are proportional to starters times the measured
backups-per-starter ratio from draft data.**

Applied to the most common league shape (12 teams; one quarterback, two
running backs, two wide receivers, one tight end, one flex, a kicker, a
defence, 7 bench spots), the rule gives roughly:

| Position | Bench spots |
|---|---|
| Quarterback | about 1 |
| Running back | about 3 |
| Wide receiver | about 3 |
| Tight end | about 0 |

Exact counts depend on where the flex spot lands. (Spots are shared out with
the D'Hondt method, a highest-averages way of dividing a fixed number of
seats in proportion to a weight, so the total always matches the bench size.)

Just as players have a market value (what others will pay) and a fundamental
value (what their production is worth), benches have a market expectation
(what leagues actually hold) and a fundamental strategy (what is worth
holding). The draft-ratio rule tracks the market, because the market is what
sets the waiver line every player is valued against. The fundamental numbers
from section 3 say what a team should do inside that market:

- Your bench is mostly insurance plus a lottery ticket, and the waiver wire
  already sells most of the lottery tickets at quarterback and tight end.
- One backup quarterback is defensible; a second one isn't. Backup tight
  ends are optional, about 0.4 per team in real drafts.
- Running-back and wide-receiver depth earns its spots: second and third
  backups still start.
- The real price of bench decisions shows up in starter value at shallow
  positions: a thin waiver wire makes good quarterbacks and tight ends worth
  more, and leagues that over-hold backup quarterbacks thin their own wire.

## Methodology lessons

- Measure on the basis you value on. The 22.6% artifact came from sorting
  players by one set of projections and valuing them on another.
- Prefer rules that need no iteration and no projections where possible.
  Watch for circular measurements: waiver quality depends on how deep
  everyone else holds, so it cannot be measured independently of the answer
  it is meant to give.
- Score candidates on fit, out-of-sample fit and stability, not on whether
  they confirm a prior. Several intuitive rules (points, holes times
  drop-off, net-of-waivers value) failed the test outright.

## Limitations

- Draft data is draft-day mock drafts, not in-season rosters. In-season
  quarterback backups are probably fewer, because managers stream the
  position once the season starts, but that is unmeasured.
- Only 12-team archives were available; other league sizes are extrapolated
  by the per-starter ratios. Two-quarterback and superflex leagues were
  measured separately (0.28 backup quarterbacks per starter, capped by
  supply), but the data does not separate the two formats.
- Real-league rostered-percentage data from the big platforms (ESPN,
  Sleeper) could not be reached from the analysis environment. It is the
  natural validation of the draft-based ratios, and it is still open.

## Sources

- [Value Over Stream, PlayerProfiler](https://www.playerprofiler.com/article/introducing-value-over-stream-vos/)
- [Streaming QBs can be viable, Subvertadown](https://subvertadown.com/article/streaming-qbs-can-be-a-viable-strategy-if-your-league-is-not-too-deep-)
- [Value over replacement and value-based drafting, Fantasy Football Analytics](https://fantasyfootballanalytics.net/2024/08/winning-fantasy-football-with-projections-value-over-replacement-and-value-based-drafting.html)
- [Fantasy Value Handbook, Harvard Sports Analysis Collective](https://harvardsportsanalysis.org/2013/09/hsacs-fantasy-value-handbook-part-i/)
- [Value Over Baseline, Footballguys (Harstad)](https://www.footballguys.com/article/HarstadValueOverBaseline)
- [How to value a player who will miss games, Football Perspective](https://www.footballperspective.com/fantasy-football-how-to-value-a-player-who-will-miss-games-fbg/)
- [We analysed 35,000 fantasy football leagues, RotoWire](https://www.rotowire.com/football/article/we-analyzed-35000-fantasy-football-leagues-heres-how-america-actually-plays-119607)
- [Replacement level, Stick to the Model](https://sticktothemodel.com/encyclopedia/replacement-level)
- Fantasy Football Calculator ADP, 12-team PPR: [2016](https://fantasyfootballcalculator.com/adp/ppr/12-team/all/2016), [2018](https://fantasyfootballcalculator.com/adp/ppr/12-team/all/2018), [2020](https://fantasyfootballcalculator.com/adp/ppr/12-team/all/2020), [2022](https://fantasyfootballcalculator.com/adp/ppr/12-team/all/2022), [2024](https://fantasyfootballcalculator.com/adp/ppr/12-team/all/2024)
- nflverse weekly stats, 2015–2025: https://github.com/nflverse/nflverse-data
