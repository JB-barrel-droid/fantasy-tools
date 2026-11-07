# JEG-1560: trading partners ranking (2026-11-07)

Jeremy, 2026-11-07: "DDF edge" and "Live market premium" on the trading partners page are not clear. The page must
answer one question: who are the best trading partners to explore?

## The metric (one function: `DDF.league.partnerRank()` in `app/next/ddf-league.js`)

Built only from numbers DDF.league already produces. No new value math; the value model and engine are unchanged.

Inputs:
- `positionTiers()` ratio per team and position: sum(min(starter value, 1.25 x slot median)) / sum(slot medians),
  over the league's per-slot medians. 1.0 = the league's middle team at that position (Strong >= 1.10, Weak < 0.90).
- `partnerTags(team).ratioAnalyst`: DDF Value / Analyst charts (average of CBS Sports, USA Today, FantasyPros) on
  that team's starters; `null` ("not judged") when a starter is missing from the charts. Missing is never 0.

For each opponent (never my team, never waivers), over QB, RB, WR, TE (FLEX / SUPERFLEX are excluded: a reason must
name a real position):

```
get(p)  = theirs_p >= 1.10 (Strong) and mine_p < 0.90 (Weak) ? min(theirs_p - 1, 1 - mine_p) : 0
give(p) = mine_p >= 1.10 (Strong) and theirs_p < 0.90 (Weak) ? min(mine_p - 1, 1 - theirs_p) : 0
score   = sum over p of get(p) + give(p)
```

Review of PR #1349 (2026-11-07, finding 6): a position counts only past the existing tier cut-offs (Strong >= 1.10,
Weak < 0.90, the tiers team.html shows), so "Best match" (the top 3 with a positive score) always means at least one
Strong-vs-Weak line-up and the reasons use the tier words ("strong" / "weak"). The first version counted any gap
around 1.0, so a 1.02 vs 0.98 position was named. The amount past the gate is still measured from 1.0.

Order: score high to low; ties by `ratioAnalyst` high to low (DDF rates their starters above the Analyst charts =
you could buy them for less), "not judged" after every judged team; then league order. A position with no ratio on
either side adds nothing. Without my team (`me` null) the score is `null` and the order is the tie-break alone; the
page then asks the reader to confirm their team (setup.html).

Because the ratio is capped at 1.25, one position adds 0.10 to 0.25 per side once it passes the gate. A position can only be a get or a give,
never both, so a reason names at most four positions.

## The page (`app/next/partners.html`)

- h1 "Who are the best trading partners to explore?"; the lede says a team ranks higher when it is strong where you
  are weak and the reverse (the team assessment tiers).
- Ranked cards, rank number on each. The top 3 with a positive score are "Best matches" (green border, "Best match"
  badge); the rest are "Other teams". If no team has a positive score the group reads "No clear match yet".
- Reason line from `get` / `give`, biggest first: "You could get WR and give RB and QB: they are strong where you are
  weak, and the reverse. Both sides could fill a gap." (position fit is not a value claim; one-way and no-fit variants
  in the page script).
- "Details" toggle per partner: their starters on DDF Value, on the Analyst charts and on the Live market (FantasyCalc),
  each with a verdict line (direction and percent; one rule for both sources: DDF Value 15% or more above the source,
  DECISIONS "DDF edge threshold 15%", marks the discount as good for you), and a "What these compare" tap-to-explain line. The words "DDF edge" and
  "premium" are no longer on the page; `partnerTags().tags` keys ride on `data-tags` for the parity test.
- Kept: Include/Skip (ddf:skip), Include all / Skip all, waivers checkbox (ddf:waivers), sticky action bar, gating,
  Next last in `<main>`, empty state with a link to connect.html.

## Why panel (JEG-1561, `app/next/ddf-why.js`)

- Numbers: `lineupValue` before / after (slots, FLEX moves) and `tradeFit` called exactly as `find-engine.js` calls it.
  Returns null when find-engine would leave the trade unjudged (no depth context, or an Analyst charts valuation with
  the charts missing); find.html then shows no Why button.
- Need / surplus come from tradeFit's depth readout, not value: need = a position a team receives at that is in its
  `towardAt` (it was short of the expected range); surplus = a position it gives from that is not in `awayAt` and is
  not "under" after. "Natural fit" in the panel = tradeFit natural AND need received + surplus given for both teams.
  A starter gain without a depth need reads "Upgrades your X starters", never "need".
- Headline leads with the card's number (your starters' change) and names the bench-weighted net when it reads
  differently ("counting your bench, ..."). Their side: "gets better too" only at net >= 0.05; between -tau and 0.05
  "stays about even, within how much the sources disagree" (tradeFit's tolerance); below -tau "gets worse".
- % line: only `DDFOpportunity.rosterImprovementPct` (JEG-1558), verbatim, hidden when absent or null. JEG-1558 is not
  on main: reconcile the contract (fields, labels) when JEG-1558 merges.

## Tests

- `tests/test_partners_rank_parity.py` (Makefile test-core + shard 3): order, get/give positions in each reason and
  the "Best match" set equal an independent oracle (curve rows + finder module, tiers recomputed) at 12 settings with
  the seeded league; drift test (give side halved in `ddf-league.js`) must change the order; render test (league / no
  league); banned-words test.
- `tests/test_ddf_why.py`: seven hand-made trades (DDF Value and Analyst charts differ; Natural with both gaining,
  Natural with their net inside tolerance, need, 2-for-1, FLEX re-slot, unpriced, no fit) vs independent
  lineupValue / tradeFit calls, depth needs, headline floor rule; weights and expected depth pinned in the test;
  drift test (one number nudged in ddf-why.js); render at 1440 / 390.
- `tests/test_team_engine_parity.py` reads partner values from the Details toggle (`[data-v]`) and tags from
  `data-tags`.

## Learned

- The seeded league's "My Squad" (pick 1 of a snake) is ahead at QB, RB and TE and behind at WR at the default setting, so top
  reasons are "get WR, give ..."; the order still moves with the give side, which the drift test relies on.
- `.partners .bulk{display:flex}` overrode the `hidden` attribute (Include all / Skip all showed with no league);
  a `[hidden]{display:none}` rule is needed next to any display rule on an element the script hides.
- The injected engine page has its own hidden `<h1>`: select the page heading with `main h1`.
