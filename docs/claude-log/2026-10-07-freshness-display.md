## 2026-10-07 - Freshness display: one content-week rule on every label (GAP-043)

Contract: every freshness label on the trade-value page (and /v2/) shows each
source's own content week, from its section (`week_designated`, then
`content_vintage`), on the Tuesday-flip content calendar, with older-week
sources marked. Branch `fix/freshness-display`; not merged.

### What the live page showed (before)
Headless Chrome on https://jb-barrel-droid.github.io/fantasy-tools/, 2026-10-07:
- Dataset health: every card badge `LIVE`. Freshness: USA Today, FantasyPros
  and CBS `content 2026-09-15` (the `published` field; fixture says Week 5 / Week 5
  / Week 4); FantasyCalc `content 2026-10-06`; all four adjusted cards
  `fit unavailable` (the regex wanted `YYYY-MM-DD`, the bake id is `ddf-20261003-...`).
- Header: "Source snapshot Oct 7, 6:00 PM CDT · 9 shown" (fixture `built_at`).
- Chart caption: "Week 4 references plus ESPN live"; CBS toggles "CBS Wk 4"
  with no older-week mark (build-time week rule said Week 4 was current).
- Table note: "source weeks current" while CBS was Week 4.

### Change
- `product-data.js`: `freshnessLabel(row)` words a `buildSourceFreshness` row:
  `Week 5`; `Week 4 · newer week not yet published` (weekly chart);
  `Week 4 · projections dated Oct 3` (rest-of-season projections).
- `index.html` health cards: badge `Current week` / `Older week` / `Undated`,
  "Content week" fact from `freshnessLabel`, fit date parsed from the bake id.
  Header box is now "Source content: Week N" with "K of M on an older week".
  The card label "ESPN live" is now "ESPN".
- `curve-widget.js`, `comparison-dashboard.js`: `weekForSource`,
  `activeReferenceWeek`, `sourceIsStale` read `getSourceFreshness()`; the
  build-time `rolloverDate` rule and the `value_weeks.monday` fallback are gone.
  Toggle meta "newer week not yet published"; caption "Week N references plus
  ESPN projections (Week 4 · projections dated Oct 3)"; table note names each
  older source with its week.
- `v2.js`: source-reason text uses the same `freshnessLabel`.
- No value math touched.

### Verified (check named)
- `tests/test_freshness_display_render.py` (new, in `make test-unit`): headless
  page vs fixture for every card badge, card week, header box, weekly toggle and
  table note; a fixture edit (USA Today -> Week 3) moves the labels; negatives:
  a constant `Live` badge and a product-data that ignores `week_designated`
  are both caught. 4/4 pass.
- Same checker against origin/main rebuilt (`make sync`) with the same
  fixture: 29 violations (constant Live badges, `content 2026-09-15`, header
  build time, CBS toggles not marked, "source weeks current").
- `tests/test_week_for_source_designated.py`: two assertions changed because
  the rule they pinned changed in this task: a `fitwk` bake id no longer beats
  the source's own `week_designated`, and rest-of-season sources are dated by
  their own vintage instead of `value_weeks.monday` (undated -> no week).
- 12-combo sweep (3 scorings x 4 team counts), origin/main vs branch build:
  `fixedPieIndexed`, `sourceScaleAgreement` and the top-40 row values identical
  in all 12.
- `CHROMIUM_PATH=... make validate` exit 0. The rest of `make test-unit` passes
  except `test_trade_chart_ingest_ci` (fails identically on origin/main).
- /v2/ built from the branch with the current fixture: chips FC/USAT/FP `W5`,
  ESPN `W4`; source reasons `Week 4 · newer week not yet published` for CBS,
  `Week 4 · projections dated Oct 3/2/1` for ESPN/CBS ROS/Razzball. No page errors.

### Claimed, not confirmed
- The live page after merge (branch only pushed, no PR).
- ESPN, CBS ROS and Razzball now show as older week (projections dated Oct 3/2/1,
  content Week 4). That is what their data says; whether ESPN's pull should
  have refreshed after Tuesday is a separate pipeline question.
- `tests/test_content_vintage_render.py` (not in any Makefile target) fails
  8/8 on origin/main and on this branch: it pins an unmerged JEG-131 design
  (`PUBLICATION_SCHEDULES`, Amber/Red badges). Left as is.
- The committed `app/` and `dist/` copies of comparison-sources-data.json are
  the Oct 3 build (all Week 4); the deploy's `make sync` writes the current
  fixture. Regenerated JSON was not committed.
