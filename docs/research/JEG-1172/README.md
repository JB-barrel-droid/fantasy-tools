# JEG-1172: FantasyPros week 8 divergence (`divergence:fantasypros:w8`)

Read-only diagnosis, 2026-10-29 UTC, Claude (branch `claude/JEG-1172`, based on
main `b86306972f0a31e9a91cb2ea73fdcbfa723ece3c`). Parent: JEG-460.

## Verdict

**Week label error, not a parser error.** The flagged "week 8" run compared
the FantasyPros **Week 7** article with the other charts' Week 7 charts. The
disagreement it measured is FantasyPros' normal opinion, already accepted for
Week 7 (JEG-796). On the real Week 8 article FantasyPros is not flagged.

1. The alert comes from `dist/modules/source-divergence.json` at `e2c191c`
   (generated 2026-10-27T10:56:44Z), run on the fixture built
   2026-10-26T15:42:37Z. In that same commit `data/history/index.json` moved
   `content_week` from 7 to 8 (the Tuesday flip). Every chart was still served
   as week 7 (`served.*.label_week = 7`).
2. FantasyPros in that run: URL `.../fantasy-football-trade-value-chart-week-7-2026/`,
   `week_designated` Week 7, `content_vintage` 2026-10-20, snapshot fetched
   2026-10-26T00:35:45Z. Its 178 natives are identical to frozen
   `data/history/week-7.json` (178 of 178; same fingerprint `sha256:848f4664…`).
   USA Today and CBS fingerprints also match week 7. FantasyCalc differs only
   because its API was fetched again.
3. So "also warned in week 7" compared the Week 7 chart with itself. The
   headline was half PPR at 46.2% against a 45% ceiling, with FantasyPros'
   own baseline at 46.4%.
4. FantasyPros published the Week 8 article later (content 2026-10-27). It
   first reached the fixture at `e55755c` (built 2026-10-28T13:19:32Z): ok,
   42.4 / 44.1 / 44.7% (full / half / standard), baseline 44–46%. On main
   `b863069` (fixture built 2026-10-29T14:09:20Z): ok, 41.5 / 43.9 / 43.3%,
   bias −0.1 to −0.3. 115 of the 174 FantasyPros natives that are in both
   articles changed between Week 7 and Week 8.

## Checklist

- **Source URL, date, served week.** Flagged run: Week 7 article, content
  2026-10-20, served week 7 under content week 8 (mismatch). Current: Week 8
  article, content 2026-10-27, served week 8 (match).
- **Column.** One base `Value` column (the 1QB value), reused for standard,
  half and full PPR. `ops/watchdog/pull_fantasypros.py` `parse_tables` reads the
  header exactly named `Value` and fails closed without it. `2QB Value` is
  stored apart (`native_superflex`, 32 QBs). Natives are identical across the
  three combos for every sample.
- **native → Indexed → shown.** Indexed = native × one factor per combo
  (JEG-482; min = max over 178 players). Flagged factors: full 0.726632,
  half 0.799197, standard 0.652017. Current: full 0.713956, half 0.718691,
  standard 0.725766. Trade charts show the Indexed value.
- **Resolution.** Not recorded by this lane. See "Proposed follow-ons".

## Five sample players, half PPR

Flagged run (`e2c191c`, all charts week 7). Others = USA Today / FantasyCalc /
CBS shown values. Consensus = median of the others. Outlier = |dev| > 35% of
consensus and ≥ 2 points.

| Player | Pos | FP native | Factor | FP shown | Others | Consensus | Dev | Outlier |
|---|---|---|---|---|---|---|---|---|
| CeeDee Lamb | WR | 40.5 | 0.799197 | 32.37 | 38.4 / 59.4 / 54.6 | 54.6 | −22.3 | yes |
| Malik Nabers | WR | 33.8 | 0.799197 | 27.01 | 34.0 / 44.0 / 49.0 | 44.0 | −17.0 | yes |
| Christian McCaffrey | RB | 46.8 | 0.799197 | 37.40 | 37.7 / 67.1 / 51.8 | 51.8 | −14.4 | no |
| Josh Allen | QB | 29.1 | 0.799197 | 23.26 | 24.7 / 50.9 / 30.8 | 30.8 | −7.6 | no |
| Brock Bowers | TE | 28.0 | 0.799197 | 22.38 | 38.4 / 46.3 / 42.0 | 42.0 | −19.6 | yes |

Current run (`b863069`, all charts week 8):

| Player | Pos | FP native | Factor | FP shown | Others | Consensus | Dev | Outlier |
|---|---|---|---|---|---|---|---|---|
| CeeDee Lamb | WR | 40.5 | 0.718691 | 29.11 | 36.2 / 55.6 / 55.4 | 55.4 | −26.3 | yes |
| Malik Nabers | WR | 39.1 | 0.718691 | 28.10 | 33.4 / 43.8 / 50.9 | 43.8 | −15.7 | yes |
| Christian McCaffrey | RB | 48.9 | 0.718691 | 35.14 | 33.4 / 54.6 / 44.3 | 44.3 | −9.2 | no |
| Josh Allen | QB | 29.1 | 0.718691 | 20.91 | 23.0 / 46.6 / 27.4 | 27.4 | −6.5 | no |
| Brock Bowers | TE | 28.0 | 0.718691 | 20.12 | 32.9 / 40.0 / 30.0 | 32.9 | −12.8 | yes |

The same players stay far from the consensus in both weeks, in the same
direction, after their natives trace exactly. That is the chart's own opinion,
not a broken step. Josh Allen's 2QB Value (69.5) is not what was used.

Missing versus zero: Davante Adams is priced by the other three charts and
absent from FantasyPros. He stays out of FantasyPros' count and is not read as
0. USA Today stores 0 for four QBs (e.g. Carson Wentz). The check does not
read that 0 as a price.

## Fixtures and test

- `tests/fixtures/JEG-1172/fantasypros-w8-trace.json`: values copied from
  committed files at `e2c191c` and `b863069` by `extract_fixture.py`. No source
  page was fetched or reconstructed.
- `tests/test_jeg1172_fantasypros_w8_trace.py` (12 tests): served week and
  article, base column, exact trace for five players and three scorings, week 7
  equality, independent consensus against the recorded report examples, the
  reporter's `divergence()` agreeing on the frozen rows, missing versus zero.
  Negative mutations: 2QB column, another combo's factor, the other week's
  natives (Nabers, McCaffrey) and missing read as a price each break the trace.

## Commands

```
git fetch --depth=600 origin main
git worktree add <scratch>/wt-e2c191c e2c191c
cd <scratch>/wt-e2c191c && python3 pipelines/check_source_divergence.py --out <scratch>/div-e2c191c.json
# FantasyPros investigate, 46% (usually 46%); per-combo numbers identical to the committed dist report
git worktree add <scratch>/wt-e55755c e55755c
cd <scratch>/wt-e55755c && python3 pipelines/check_source_divergence.py --out <scratch>/div-e55755c.json
cd <repo> && python3 pipelines/check_source_divergence.py --out <scratch>/div-head.json   # main b863069
python3 docs/research/JEG-1172/extract_fixture.py
python3 -m unittest tests.test_jeg1172_fantasypros_w8_trace -v
```

`--out` pointed outside the repo every time, so no tracked output changed.

## Unknowns

- The raw FantasyPros captures (`data/raw/sources/fantasypros/2026-10-20/` and
  `2026-10-27/`) live only on the Actions runner, not in git. The article
  itself was not re-read here. Article dates come from the fixture's
  `source_content_date` provenance ("unanimous across 534 rows").
- Both article URLs sit under `/2026/09/` with `published` 2026-09-15. That
  looks like FantasyPros' slug for the season-long article, but this was not
  checked against the live site.
- `dist/modules/source-divergence.json` on main is still the `e2c191c` copy
  (generated 2026-10-27). It still says investigate. Why later rebuilds did not
  refresh it was not traced.
- The new test is not in a Makefile run list (only render tests must be).
  Wiring it into `test-unit-modules` is a one-line change outside this lane.

## Proposed follow-ons (need review and an owner, not done here)

1. Divergence reporter: label each source-week by its served `label_week`, not
   `content_week`. Skip or tag the "also warned in week N" escalation when the
   current and prior inputs share a fingerprint.
2. Resolutions: whoever owns the file can record FantasyPros week 8 as
   reviewed, citing this note. The kind (`accepted` or a new label-error kind)
   is a decision for the reviewer.
3. Find out why `dist/modules/source-divergence.json` has not been rebuilt
   since 2026-10-27.
