# Outline: DDF (Trade Charts) vs DDF (Projections), pros and cons

Outline only, draft for Jeremy's review (JEG-1102). Nothing publishes; research posts are reviewed per Google Doc and published only on his yes. Working labels: **Trade Charts view** and **Projections view**. Final names are undecided (JEG-1081); every title and heading below changes with them.

Numbers cited come only from `~/code/fantasy-tools-selfhost-notes/jeg-1073-impact/report.md` ("impact report", Opus 4.6, 2026-10-25, builds at fb8ede17 and 42562990) or from the docs named. Anything else is listed under "Still to measure".

## Working title and one-line claim

"DDF Value from the trade charts or from the projections: what each is good for". Claim to test: the Trade Charts view is the better reading of what other managers will accept; the Projections view is the only independent check on it. They are most useful together, where they disagree.

## Terms to define up front (public copy rules)

DDF Value; Adjusted value (a source's value above waivers after it is put on your league's scale, summing to a fixed league total); Trade Charts view (equal-weight mean of FantasyCalc, USA Today, FantasyPros and CBS Adjusted values); Projections view (mean of ESPN, CBS rest of season and Razzball Adjusted values); Trade chart average (the charts rescaled with one factor each, the market's price); value above waivers; position weights; bench share. Source: `docs/methodology.md` VP-0, VP-6, "Live and pending".

## Sections

1. **Why two numbers.** Manifesto idea that a player has no single value (`docs/manifesto.md` section 1) and that the market is efficient but not perfectly (section 2). The site used to blend, then went projections-only (2026-10-22), then back to charts with projections as the alternate (2026-10-25, JEG-1073 reversed JEG-804). Say that plainly; the reversal is a fact (`docs/methodology.md` "Live and pending").
2. **How each view is built.** One diagram: four charts to Adjusted to mean; three projection sources to Adjusted to mean. Shared steps: position weights, bench share, waiver line.
3. **Trade Charts view: pros.**
   - Reads the prices managers actually see; best for "will they accept".
   - Covers more players: Adjusted fills in a player a chart does not list (impact report section 4, fill-in effects).
   - Includes the position-weight and bench-share adjustment, which is the product's own contribution (Jeremy 2026-10-25, quoted in `docs/methodology.md`).
4. **Trade Charts view: cons.**
   - Not independent of the market: it is built from the same four charts as the Trade chart average. At Full PPR, 12 teams, 738 players: mean absolute gap 0.994 points, median 0.000, 90th percentile 3.276, correlation 0.979, 16.9% of players differ by more than 2.0 (impact report section 1).
   - The gap is systematic by position, not player-specific: WR starters DDF above Indexed (+0.517 mean signed WR gap), TE -0.601, QB -0.418, RB -0.234 (section 1, by position). Starters differ most: mean 5.434 points for the 84 starters vs 0.151 for waiver players.
   - So a "buy below DDF Value" signal here is partly a position-budget effect (the impact report calls it by design). Target lists get shorter (section 3a).
5. **Projections view: pros.** The only independent source of the pair (impact report section 4 recommendation); lets Risers and fallers and Compare a trade compare two readings again (section 3f, 3g: movers/disagree and the trade production check become live comparisons).
6. **Projections view: cons.** Does not say what other managers will pay; depends on three sources, so one held or bad source moves it more; per-source noise is higher for some players (noise floor, below).
7. **Where they disagree.** At Full PPR, 12 teams: the new Trade Charts view vs the old projections-only DDF Value, mean absolute difference 0.761, median 0.000, 90th percentile 2.469, 12% of players differ by more than 2.0, mean signed difference -0.017 (not directional in aggregate) (impact report section 1, last table). Half that gap is the noise floor the fit rule uses: mean 0.407, 90th percentile 1.461, 94 of 736 players above 1.0 at ppr:12 (section 2). Across the 12 league settings the Trade Charts vs Trade chart average gap correlation runs 0.888 to 0.987, smaller leagues lower (section 1 table).
8. **Which view each tool should lead with.** A table: Trade targets, Compare a trade, Find a trade, Waivers, Risers and fallers, Player values. Content waits on JEG-1081. Facts available now: Find a trade and Waivers fit rule uses `ddf_value` for you and chart average for them (impact report 3b, 3c); Health check thresholds are not affected (3e).
9. **How to use both.** Rule of thumb to draft from data, not asserted: act where the Trade Charts view says win and the Projections view does not say lose.
10. **What we do not know yet.** Section built from the list below.

## Still to measure

- Predictive value of each view: does the gap to the market predict next-week movement for each version? Research post 07 measured this for projections-only (six saved weeks, weeks 2 to 7, 2026, 22 October); it needs a rerun for the Trade Charts view. Do not reuse post 07 numbers as is: they are for the older definition.
- Agreement between the charts on starters vs bench (post 08 covers the older definition).
- Superflex and 2-QB leagues: the impact report tabulates 12 one-QB combos (3 scorings x 4 league sizes); its header says 13 combos but the thirteenth is not tabulated.
- Fit-label shift on real trades under each default: the held-out measurement in the JEG-1081 PR 2 log was not run (`docs/claude-log/2026-10-25-jeg-1081-pr2-tri-view-fit.md`).
- Per-position variation of the Projections view vs Trade chart average (the report compares Trade Charts to Indexed, and Trade Charts to Projections in aggregate only, not by position).
- Whether the target lists are shorter by how much (report 3a: "Jeremy noted this", no count).
- Error of each view against realized value (season points above waiver) for matured weeks.
- Reader task test: do users find the Natural fits more useful under one default.

## Not done / not verified

I read the impact report and docs; I re-ran no engine dump and verified none of the report's numbers against code. The report's mean-signed figures are quoted as printed; the report's prose labels the WR gap "DDF > Indexed (+22 at top)" and I quote only the table rows. Numbers are PPR/12 unless a setting is named.

## Open decisions for Jeremy

1. Final view names and default (JEG-1081); this outline cannot be titled until then.
2. Does the article run before or after the reader-facing Methodology page "The two DDF views" (`methodology-outline.md` page 2)? Recommend the article second, as the evidence behind that page.
3. Research posts 03, 06, 07, 08 and 10 still define DDF Value as projections-only. Revise them or add a dated note before this article links to them.
