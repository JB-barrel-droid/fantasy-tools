# Research post 1 (JEG-544): facts register

Owner ticket: JEG-604. Post: "How much is a bench player worth?" (JEG-544, Todo). Written 2026-10-12 from the JEG-544 comments. The draft is a Google Doc owned by Jeremy; this page keeps the decisions and the fact list in the repo.

## Decisions on the draft (Jeremy, 2026-10-10)

- Remove the old flat 15% method entirely; keep pay ratios as a "what this does to prices" result with no "before" column.
- Pay ratio: use measured figures (RB 1.0x to 1.7x and WR 1.0x to 3.0x at 12-team PPR); the early estimate 1.4x to 4.6x is dropped.
- Re-run the fill-in rates, the Week 5 to Week 17 decline and the top movers on the approved model so every number comes from one model.
- Examples are labelled by rank, not name, and pulled live from the engine: "Is live from the engine using numbers that are already going to be rerun each week? Yes relying on rank is smart."
- Structure: abstract with the answer first, question, method, data, results, sensitivity, limitations, conclusion. Show the math for the value pie, the waiver line and both bounds. Write it to read correctly at any point in the season.

## Facts to gather, and where each stands

| Fact | Ticket | Status 2026-10-12 | Where the answer lives |
|---|---|---|---|
| QB bench share 22.6% is an artifact | JEG-546 | Answered | [qb-bench-share.md](qb-bench-share.md) |
| Value pie and waiver lines per position | JEG-547 | Mostly answered by the convention (waiver line = first player past the market-bench rosters) | [roster-convention-audit.md](roster-convention-audit.md) |
| Bench-share bounds (8.6% / 13.3% in the approved-defaults log, 8.1% / 13.1% in methodology ES-7) | JEG-548 | Reconciled; script committed; re-run after JEG-562 | [bench-share-bounds.md](bench-share-bounds.md), `tools/bench_research/bench_share_bounds.py` |
| Decompose the 8.9% (start-worthy versus fill-in, displacement) | JEG-549 | Answered (displacement absorbs 83% of SW gain); re-run after JEG-562 | [bench-share-decomposition.md](bench-share-decomposition.md), `tools/bench_research/bench_share_decomposition.py` |
| Starter downside (does the start-worthy term apply to starters; Hubbard RB16 at 71.6% against a 78.9% ceiling) | JEG-550 | Wave 7, not done | |
| Fill-in rates (34% / 4% / 48%, decision build) | JEG-551 | Wave 6, must be recomputed | |
| Ceiling as a function of week (78.9% was arithmetic, not printed by the repo) | JEG-552 | Wave 7, not done | |
| Bench-slots effect | JEG-553 | Wave 6; use the market bench rule and the 7-bench default | |
| Worked example by rank at a fixed reference point | JEG-554 | Wave 7, not done | |
| Commit the scripts | JEG-566 | Wave 7 | `tools/bench_research` (does not exist yet) |

The numbers in the draft will change before the rewrite because JEG-562 moves the readout to the convention, JEG-563 makes the default roster 1 QB / 2 RB / 2 WR / 1 TE / FLEX / K / DEF with 7 bench, and JEG-555/593 fixed the Razzball input. Both JEG-562 and JEG-563 block the rewrite.

## Related

- Bench-construction research (post 2, JEG-557): [bench-rule-research.md](bench-rule-research.md).
- Manifesto sections the post links back to: `docs/manifesto.md` section 4 to 8.
- Rule from the Research tab decision `research-tab-001`: Claude drafts, Jeremy approves.

## Rule for every research claim (JEG-604)

Each claim must link to a doc page and a script. Today no bench script is committed, so every number in these pages is a record of a run, not a reproducible one, except the market bench ratios (`pipelines/derive_market_bench.py`). Closing that gap is JEG-566.
