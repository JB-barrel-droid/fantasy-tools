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
surplus(x) = max(0, ratio_x - 1)        need(x) = max(0, 1 - ratio_x)
get(p)     = min(surplus(theirs_p), need(mine_p))     their surplus that covers my need
give(p)    = min(surplus(mine_p),   need(theirs_p))   my surplus that covers their need
score      = sum over p of get(p) + give(p)
```

Order: score high to low; ties by `ratioAnalyst` high to low (DDF rates their starters above the Analyst charts =
you could buy them for less), "not judged" after every judged team; then league order. A position with no ratio on
either side adds nothing. Without my team (`me` null) the score is `null` and the order is the tie-break alone; the
page then asks the reader to confirm their team (setup.html).

Because the ratio is capped at 1.25, one position adds at most 0.25 per side. A position can only be a get or a give,
never both, so a reason names at most four positions.

## The page (`app/next/partners.html`)

- h1 "Who are the best trading partners to explore?"; the lede defines "ahead / behind" as compared with the league's
  middle team at that position.
- Ranked cards, rank number on each. The top 3 with a positive score are "Best matches" (green border, "Best match"
  badge); the rest are "Other teams". If no team has a positive score the group reads "No clear match yet".
- Reason line from `get` / `give`, biggest first: "You could get WR and give RB and QB: they are ahead where you are
  behind, and the reverse. Both sides gain." (one-way and no-fit variants in the page script).
- "Details" toggle per partner: their starters on DDF Value, on the Analyst charts and on the Live market (FantasyCalc),
  each with a verdict line (direction and percent; the 15% Analyst charts rule from DECISIONS "DDF edge threshold 15%"
  marks the discount as good for you), and a "What these compare" tap-to-explain line. The words "DDF edge" and
  "premium" are no longer on the page; `partnerTags().tags` keys ride on `data-tags` for the parity test.
- Kept: Include/Skip (ddf:skip), Include all / Skip all, waivers checkbox (ddf:waivers), sticky action bar, gating,
  Next last in `<main>`, empty state with a link to connect.html.

## Tests

- `tests/test_partners_rank_parity.py` (Makefile test-core + shard 3): order, get/give positions in each reason and
  the "Best match" set equal an independent oracle (curve rows + finder module, tiers recomputed) at 12 settings with
  the seeded league; drift test (give side halved in `ddf-league.js`) must change the order; render test (league / no
  league); banned-words test.
- `tests/test_team_engine_parity.py` reads partner values from the Details toggle (`[data-v]`) and tags from
  `data-tags`.

## Learned

- The seeded league's "My Squad" (pick 1 of a snake) is ahead at QB, RB and TE and behind at WR at the default setting, so top
  reasons are "get WR, give ..."; the order still moves with the give side, which the drift test relies on.
- `.partners .bulk{display:flex}` overrode the `hidden` attribute (Include all / Skip all showed with no league);
  a `[hidden]{display:none}` rule is needed next to any display rule on an element the script hides.
- The injected engine page has its own hidden `<h1>`: select the page heading with `main h1`.
