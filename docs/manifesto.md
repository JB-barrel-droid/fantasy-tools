# Fantasy Football Manifesto

The reasoning behind this project, as stated by Jeremy (2026-10-07). Features,
metrics, and copy should be judged against it.

> Terminology note: "Market Value" here means what other managers will pay in a
> trade. It is not the sportsbook side, which user-facing copy always calls
> **"Vegas"** (see `CLAUDE.md`). Likewise, user-facing copy says **"value above
> waivers"**, never VORP.

---

Fantasy football is usually treated as a game of player selection: identify the players who will outperform expectations, acquire them, and build the strongest roster.

That is part of the game, but it is not the game.

Fantasy football is better understood as a dynamic capital-allocation problem. Players are assets. Roster spots are scarce capital. Waivers provide a continuously changing replacement market. Trades provide liquidity. Information changes asset prices. And the value of an asset depends not only on how many points it will score, but on when those points occur, whether they will enter your starting lineup, what alternatives are available, and what your team is trying to accomplish.

The objective is not to accumulate the most projected fantasy points.

The objective is to continuously allocate roster resources in the way that maximizes the probability of winning a championship.

## 1. A player does not have one value

Every fantasy player has several different kinds of value.

**Market Value** is what other managers are willing to pay for the player. Like a stock price, it changes with performance, news, injuries, sentiment, and expectations.

**Fundamental Value** is what the player's expected production is actually worth given the league's scoring system, roster structure, and available replacement players.

**Portfolio Value** is what that player is worth specifically to your roster.

These values can be materially different.

A player may be worth more in trade than the production he is likely to provide. Another player may be difficult to trade but unusually valuable to your team because of its construction. A backup running back may have limited standalone value but substantial value to a roster whose starters carry significant injury risk.

Winning requires understanding these differences rather than treating rankings or trade values as a universal measure of worth.

## 2. The fantasy market is relatively efficient, but not perfectly efficient

Fantasy football has an enormous amount of high-quality information.

Professional analysts publish rankings and projections continuously. Their historical performance is measurable. Sportsbooks publish sophisticated player markets. Millions of fantasy managers collectively reveal their beliefs through drafts, waivers, trades, and lineup decisions.

Because of this, consistently outperforming the market simply by "liking" different players is difficult.

Over a large enough sample, blindly trusting personal conviction over aggregated expert and market information is unlikely to be a durable advantage.

That does not mean the market is perfectly efficient.

Fantasy leagues move much more slowly than financial markets. New information can materially change a player's value before every manager in a league fully reacts. Injuries, depth-chart changes, usage shifts, coaching comments, trades, and changing projections can create temporary dislocations.

The opportunity is therefore less about permanently knowing players better than everyone else and more about identifying where market price and underlying value diverge, and acting before that gap closes.

## 3. Fundamental value begins with replacement

Fantasy points do not have equal value.

A quarterback projected for 20 points per game is not necessarily more valuable than a wide receiver projected for 15. What matters is how much production the player provides relative to the alternatives available at that position.

The relevant baseline is replacement level: the quality of player that could reasonably replace the rostered player.

Replacement level is determined by league structure.

League size matters. Starting lineup requirements matter. Flex spots matter. Superflex matters. Bench size matters. Scoring rules matter.

If only one quarterback starts per team and competent quarterbacks remain on waivers, the difference between QB10 and QB15 may have little practical value. Meanwhile, if a league starts three wide receivers plus multiple flexes, the difference between WR30 and the waiver-level replacement may be substantial.

This means player value cannot be calculated correctly without understanding the league in which the player exists.

## 4. Value Above Replacement is necessary, but not sufficient

Traditional Value Over Replacement measures the production gained by owning one player instead of an available alternative.

That is an essential foundation, but fantasy football introduces another constraint:

Bench points do not count.

A bench player who outscores the waiver pool by three points per week creates little value if those points never enter your lineup.

Therefore, the value of a player must consider not just his expected production above replacement, but the likelihood and magnitude of that production actually affecting a starting lineup.

This creates an important distinction between player production and usable production.

The best fantasy roster is not necessarily the roster projected to score the most total points across all of its players. It is the roster most capable of putting valuable points into starting slots when they matter.

## 5. Bench players are options

Bench players should not be evaluated like weaker starters.

They are often better understood as options on future states of the world.

A player producing waiver-level numbers today may still be extremely valuable if there is a meaningful probability that an injury, role change, trade, or performance shift would turn him into an every-week starter.

Conversely, a player who reliably produces mediocre bench-level output may have little value if there is almost no plausible path to becoming meaningfully useful.

Consider two players:

- Player A has predictable bench-level production and a 10% probability of becoming a strong weekly starter.
- Player B currently produces at waiver level but has a 25% probability of becoming a strong weekly starter.

Player B may be substantially more valuable despite having the worse current projection.

This is why upside matters.

But upside is not abstract. It should be thought of as probability-weighted future utility.

## 6. Portfolio construction changes player value

The same player can have different values on different teams.

Suppose a roster has two excellent but aging running backs and no meaningful depth behind them. A high-upside backup running back may have substantial portfolio value because there is a meaningful probability that the roster will need him.

Now suppose another roster already has three strong backup running backs. Adding a fourth may create very little additional protection because several existing players already cover the same future state.

This is diminishing marginal utility.

A player should therefore be evaluated in the context of the other assets already owned.

Questions such as these matter:

- How likely is this player to enter my starting lineup?
- Which starter risks does he protect me against?
- Do I already own players who cover the same scenarios?
- What roster spot am I giving up to hold him?
- What is available on waivers if I later need replacement production?
- Could I trade this player for an asset with greater utility to my roster?

Roster construction is therefore a portfolio-allocation problem, not simply an exercise in accumulating independently valuable players.

## 7. Roster spots have opportunity cost

Every roster slot has a cost.

Holding one player means not holding another.

That makes the waiver wire an important part of player valuation. A bench player should not be compared with zero. He should be compared with the best realistic alternative that could occupy the roster spot.

As long as useful players remain freely available, mediocre bench assets have little scarcity value.

This creates an incentive to churn the bottom of the roster aggressively when the expected value of a new option exceeds the expected value of the incumbent.

The optimal bench is not necessarily stable.

It is a portfolio of bets that should continually change as probabilities, roles, injuries, schedules, and available alternatives change.

## 8. Starter-grade weeks matter more than season totals

Fantasy football is played in discrete weekly matchups.

That means two players projected for the same number of season-long points may not have the same value.

A player who misses eight games but provides starter-quality production during the other eight can be much more useful than a player who plays every week but produces below the threshold required to meaningfully improve a starting lineup.

The second player may accumulate more usable-looking season points while contributing very little marginal value.

The relevant unit is therefore not simply total points.

It is closer to:

How many weeks does this player materially improve the lineup, and by how much?

This is particularly important for bench players, injured players, high-variance players, and positions where replacement production is readily available.

## 9. Future fantasy value should be discounted

There is inherent uncertainty in fantasy football.

The farther into the future a projected benefit occurs, the more opportunities there are for circumstances to change before that benefit can be realized.

Players get injured. Roles change. Teams change. Better waiver options emerge. Standings change. NFL teams change incentives. Projections become obsolete.

Therefore, all else being equal, useful production in the near term is more valuable than identical expected production much later in the season.

This does not mean future value should be ignored.

It means it should be discounted for uncertainty.

A roster spot devoted to a potential Week 14 payoff carries a larger opportunity cost than one likely to create value next week.

## 10. The objective function changes during the season

Fantasy football has two distinct competitive stages:

- Stage 1: Make the playoffs.
- Stage 2: Win the playoffs.

Early in the season, every team's probability of reaching the playoffs is uncertain. Immediate regular-season wins therefore have substantial value.

As standings become clearer, the optimal strategy changes.

A team fighting for the final playoff spot should continue prioritizing near-term production and weekly floor.

A team that is highly likely to make the playoffs can rationally sacrifice some regular-season expected value in exchange for greater championship upside, stronger playoff matchups, injury recovery timelines, or high-variance assets.

A team with little chance of reaching the playoffs has yet another objective: maximize the probability of producing the sequence of wins necessary to survive.

There is no single optimal player ranking independent of team state.

The value of future production changes as the probability of reaching each stage changes.

## 11. Market price creates the opportunity

Once fundamental value and portfolio value can be estimated, the market becomes actionable.

The important question is no longer simply:

"Is this player good?"

It becomes:

"What is this player worth, what does the market think he is worth, and what is he worth specifically to me?"

That creates a simple decision framework.

- When Market Value is below Portfolio Value, there may be an opportunity to acquire the player.
- When Market Value exceeds Portfolio Value, there may be an opportunity to sell.
- When a player has low current Fundamental Value but high Option Value and low roster-slot opportunity cost, he may be an attractive stash.
- When a player has low Portfolio Value but meaningful Market Value, he may be an especially attractive trade candidate.
- When Market Value, Fundamental Value, and Portfolio Value are all below the best freely available alternative, the player should probably be dropped.

Fantasy football therefore becomes a continuous exercise in identifying misallocated capital.

## 12. Winning is continuous portfolio optimization

The fantasy season should not be thought of as a draft followed by weekly lineup decisions.

The roster is a portfolio that should continuously respond to changing information.

Every week creates new prices, new probabilities, new replacement levels, and new constraints.

The manager's job is to continually answer:

What allocation of my roster spots and trade capital gives me the highest probability of ultimately winning the league?

Sometimes that means making a trade.

Sometimes it means declining a seemingly fair trade.

Sometimes it means holding an injured player.

Sometimes it means dropping a recognizable player for an unknown backup.

Sometimes it means paying heavily for immediate production.

Sometimes it means sacrificing present value for playoff upside.

The correct action depends on the relationship between the player's market value, fundamental value, portfolio value, option value, timing, and the team's competitive position.

The goal is not to predict every player correctly.

The goal is to repeatedly make better allocation decisions than the other managers in the league.

Over an entire season, those small advantages compound.

That is the game.
