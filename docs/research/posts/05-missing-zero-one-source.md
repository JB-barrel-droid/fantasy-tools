# Missing is not zero, and the one-source rule

Research post 5.

---

## Abstract

When a source does not list a player, what value should the tool show? When
only one source prices a player, how much should you trust the number? These
two rules, how a missing value is shown and the one-source note, decide what
the tool shows for players at the edges of the roster, and they affect every
trade that involves a deep bench player.

The short version: a trade-value source that prices a position but does not
list a player gives him a real 0, or an estimate if he is rosterable, and that
number counts. A source with no opinion shows a dash, and a dash is left out,
never counted as 0.

The site sorts its sources into three kinds, explained on its
[Value chart](#player-values) in its source groups and player detail: published
charts (USA Today,
FantasyPros and CBS), published trade-value opinions; observed-trade estimates
(FantasyCalc), algorithmic estimates from completed fantasy trades; and
projections (ESPN, CBS rest of season and Razzball), projected scoring turned
into value. Below, "trade-value input" means any of the four sources of the
first two kinds: the three published charts and FantasyCalc. The rules for
missing values are the same for all four of them; projections have their own,
stricter rule.

Terms used below. DDF Value is our one number per player: the average of the
four trade-value inputs' weight-adjusted values at your league settings (value
above waivers, re-weighted to our position weights). It is not the plain
average of the rescaled inputs. DDF Value (projections) is the alternate: the
three projection sources, each turned into a value at your league settings and
averaged. The rosterable count is the
number of players at a position that the league's teams can actually hold,
worked out from league size, roster slots and bench spots, with players ranked
by projected points. A fill-in value is an estimate for a rosterable player a
trade-value input does not list. The waiver line is the value of the best player you could
pick up for free at a position; value is measured above it, so 0 means at or
below the waiver line.

When these figures were measured: every figure below comes from one data
build of the site, made on October 28, 2026 at 23:27 UTC, with every source at
its 2026 Week 8 release, in a 12-team, full PPR league unless the text says
otherwise. They were measured once on that build and have not been refreshed
since; they are Week 8 figures, not current-week ones. In that build two
projections, CBS rest of season and Razzball, were on hold as lagging: a check
had found that their stored numbers no longer matched the publisher's page. A
lagging source stays in use and is labeled on the site, so both are counted in
the projection figures below. "Rostered players" means the 168 players DDF
Value places in a starting lineup or on a bench in that league.

## What a trade-value input shows for each player

Each input is read position by position. For a position the input prices (it
lists at least one player there), every player gets one of three things on that
input's line:

### The input lists him

He gets the input's value, adjusted to your league. A listed player can still
be at 0 if the input puts him at or below the waiver line.

### He is rosterable, but the input does not list him

The tool estimates his value for that input from the other trade-value inputs
that list him, scaled to this input's own values. The estimate is capped at the
input's lowest listed value at his position, so the source's listed order is
never disrupted. It is marked "≈ estimated", with the reason.

Example: the CBS chart did not list Dalton Kincaid (TE) in Week 8. The other
three inputs put him at 6.6 (USA Today), 4.0 (FantasyCalc) and 10.5
(FantasyPros) after adjustment. CBS's estimate was 3.5, and his DDF Value the
average of all four, 6.1.

### He is past rosterable depth, and the input does not list him

He shows **0** on that input, with the note "Below rosterable depth; <source>
doesn't list him". The input prices players at his position, and he is past
the point where any team in the league would hold him, so the input's silence
is a judgment, not a gap.

Example: in Week 8 Emmett Johnson (RB) was on the bench in DDF Value's rostered
set, but he sat past CBS's depth by projected points, and the CBS chart did not
list him. USA Today had him at 0.2, FantasyCalc at 0.04 and FantasyPros at 4.0;
CBS showed 0. His DDF Value was (0.2 + 0.04 + 4.0 + 0) / 4 = 1.1. The zero
counts, and it pulls the average down, which is the point: one chart's view is
that he has no trade value at this depth.

### When an input shows a dash

A dash ("--") means the input has no opinion, and it is left out of DDF Value
entirely. On an input's line this happens only when the **input does not price
the position at all** (it lists nobody there): "<source> doesn't price <pos>".

An input can also be out for the whole week: paused because its data failed a
check, or not yet published for the current week. Its values are then not used
anywhere in DDF Value, and the page says why.

### The same rule in the player detail comparisons

The site's player detail also shows two comparison readouts that keep the kinds
of source apart: the Published chart average (the three published charts,
equal weight) and FantasyCalc's observed-trade estimate on its own. They follow
the same line between zero and missing. A numeric 0 is kept and counted; a
missing value is unavailable. The Published chart average appears only when all
three published charts have a value, so a dash on any one of them leaves it
unavailable rather than averaging the other two. Both are comparisons only and
do not change DDF Value.

### How often each case comes up

For the 168 rostered players in Week 8, each input's line was:

| Input | Listed | Estimated | 0, below its depth |
|---|---|---|---|
| USA Today | 168 | 0 | 0 |
| FantasyCalc (observed-trade estimate) | 162 | 6 | 0 |
| FantasyPros | 152 | 14 | 2 |
| CBS | 123 | 35 | 10 |

USA Today and FantasyCalc list deep enough that their lines are almost all
their own numbers. The CBS chart listed 123 players in this format, so a fifth
of its rostered values were estimates. Across scoring formats (12 teams, the
672 input values for rostered players):

| | Standard | Half PPR | Full PPR |
|---|---|---|---|
| Estimated | 82 | 63 | 55 |
| 0, below the input's depth | 14 | 15 | 12 |

Over all 741 players with a row in Week 8, 545 had a DDF Value of exactly 0:
every input put them at or below the waiver line. That is a measured 0, and
it is different from a missing value.

## What a projection shows for each player

Projections follow a stricter rule, because a projection that skips a player
is not making a judgment about his trade value; it simply did not project him.

- **The projection projects him:** its value, turned into value above waivers
  at your league settings.
- **The projection does not project him:** a dash, "<source> doesn't project
  this player". It is left out of DDF Value (projections). Projections are
  never filled in.
- **The projection does not price the position:** a dash, left out.

Example: Razzball did not project Jonah Coleman (RB) in Week 8. ESPN had him at
3.4 and CBS rest of season at 12.7, so his DDF Value (projections) was the
average of those two, 8.0, not of three values with a zero.

## The rules in plain terms

| Situation | What shows | Counts in DDF Value? | Counts in DDF Value (projections)? |
|---|---|---|---|
| Trade-value input lists the player | The input's value | Yes | No |
| Input gives a fill-in value | The estimate, marked "estimated" | Yes | No |
| Input prices the position, player below rosterable depth | 0 ("Below rosterable depth") | Yes, as 0 | No |
| Input does not price the position | -- ("Source doesn't price this position") | No (left out) | No |
| Input paused or not yet published this week | Labeled on the page | No (left out) | No |
| Projection projects the player | The projection's value | No | Yes |
| Projection does not project him | -- ("Source doesn't project this player") | No | No (left out) |

## When only one source prices a player

When exactly one of a version's sources has a value for a player and the
others are left out, that version's value equals that one source's value. The
tool shows it with the note "Only one source prices this player", next to the
value it applies to.

How often this happens depends on the version:

- **DDF Value: 0 of 741 players in Week 8.** Every trade-value input priced
  every position, and an input gives each player either his value, an estimate
  or a 0. So while all four inputs are in, every player has four. The note
  appears on DDF Value only when three of the four inputs are out for the week,
  or when you build DDF Value from a blend of sources of your own and only one
  of them prices the player. A basis of one source you chose yourself is not
  flagged.
- **DDF Value (projections): 202 of 741 players in Week 8**, almost all past
  rosterable depth; 2 of them rostered. Example: only ESPN projected Malachi
  Fields (WR), so his DDF Value (projections), 0.9, was ESPN's value, with the
  note.

### Why this matters for trades

A one-source value is not wrong, but it is less trustworthy than one confirmed
by several sources:

- **No cross-check.** With three or four sources, a value is robust to any one
  of them being off. A one-source value has no check.
- **The source might be an outlier.** The one source that prices the player
  might be high or low for reasons specific to its method.
- **He is usually at the edge of relevance.** A player only one projection
  covers is almost always outside the rosterable count.

When a trade involves a player with a one-source value, treat that number as
directional (he is worth roughly this much) rather than precise.

## When no source prices a player

When none of a version's sources has a value, that version is missing for the
player: "No source prices this player", or "No source available this week" when
every source of that version is out. The player still has a row, but no value
in that version. DDF Value never falls back to the projections when the
trade-value inputs are missing. In Week 8 it happened to no player in DDF Value
and to 2 players in DDF Value (projections).

## How the pieces fit together

Take a rosterable running back that two trade-value inputs list, that a third
does not list but estimates, and that sits past a fourth's depth:

- DDF Value averages four numbers: the two listed values, the estimate and the
  0. The zero is real information about how that source sees him.
- DDF Value (projections) averages the projections that project him. If one
  projection skips him, it averages the other two, with no penalty for the
  source that had no opinion.

The two rules point the same way: a source that has looked at a position and
passed on a player is counted, and a source that has no view is not.

---

## Sources

| Claim | Where it comes from | When |
|---|---|---|
| The three kinds of source and their names | The Value chart's source groups and player detail | Current rule |
| What each trade-value input and projection shows for an unlisted player | The value methodology, section on rows, DDF Value and Indexed values | Current rule |
| DDF Value is the four trade-value inputs, DDF Value (projections) the alternate | The value methodology, section on DDF Value (decision of October 25, 2026) | Current rule |
| Fill-in values, the cap and the rosterable count | The value methodology, section on filling in rosterable players | Current rule |
| One-source note and "No source prices this player" | The value methodology, section on DDF Value | Current rule |
| Zero and missing in the player detail comparisons | The site's player detail comparisons | Current rule |
| Counts and the Kincaid, Johnson, Coleman and Fields examples | The Week 8 data build of October 28, 2026 (23:27 UTC) run through the reference value engine | Measured once, Week 8 |
| CBS rest of season and Razzball on hold as lagging, and still counted | The same build's source checks | Week 8 build |
