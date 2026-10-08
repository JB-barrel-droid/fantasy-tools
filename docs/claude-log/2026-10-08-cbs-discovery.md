# 2026-10-08 cbs-discovery lane (fix/cbs-discovery)

Row: GAP-CBS-DISCOVERY-SLUG (new). Jeremy: "CBS published week 5's trade
value chart yesterday. So you need a better process for finding new CBS
charts. I'm open to light assistance from an LLM."

## What changed

- `ops/watchdog/article_discovery.py` (new): listing-link and news-sitemap
  extraction, week-from-slug/title, candidate ranking, the optional LLM
  picker (`llm_pick`, Anthropic SDK imported lazily, `claude-haiku-5-5`
  unless `DISCOVERY_LLM_MODEL`; no `ANTHROPIC_API_KEY` = no-op; the answer is
  a link number and must be one of the listed links), `is_overdue`.
- `pull_cbs.discover_url`: author page, fantasy football hub, fantasy news
  sitemap, plus two known slug shapes; a page is accepted only when its
  headline names a trade chart for exactly the requested week, the slug week
  (if any) agrees, and >= 4 TableBuilder tables parse. Never returns an
  older week. LLM consulted only when that fails; its pick goes through the
  same `check_article`. `DiscoveryFailed.quiet` is False when no listing
  could be read. `extract_week_from_url` reads any CBS slug shape (CBS hosts
  only). Table parsing moved to `parse_tables` (unchanged logic).
- `ingest_cbs`: CBS misses are now the quiet "not published yet" path
  (was: crash); the exact-week gate uses `pull_cbs.page_week` (slug week,
  else the page headline); the pull validates headline vs slug.
- `ingest_common`: `assert_not_overdue` on both quiet paths: once the
  current content week is `overdue_after_days` (2) old, a miss raises
  `DISCOVERY_OVERDUE` (backfills of old weeks stay quiet). Optional cfg
  `url_week_fn`.
- USA Today: reworded-slug match and LLM pick (must carry week N in the
  slug) before the week-1 fallback; overdue guard on.
- FantasyPros: articles news sitemap + monthly archives + LLM before the
  N-1/N-2 template fallback; `main()` returns 1 with DISCOVERY_OVERDUE on an
  overdue miss with --save, quiet otherwise (a DiscoveryFailed used to crash).
- `trade-chart-ingest.yml`: `url` input (single source only, through env,
  exact-week gate still applies), `ANTHROPIC_API_KEY` passed and the SDK
  installed only when the secret exists, error code `DISCOVERY_OVERDUE`.
- `tests/test_article_discovery.py` (+ trimmed live fixtures in
  `tests/fixtures/discovery/`), added to `make test-unit`.

## Verified (check named)

- **Week 5 article and URL pattern:** fetched the CBS author page and the
  fantasy hub (curl, 2026-10-08): both link
  `/fantasy/football/news/dave-richards-2026-week-5-trade-chart/`; og:title
  "Dave Richard's Week 5 Trade Chart and rest of season rankings: ...",
  datePublished 2026-10-07T00:48Z. The old template slug for week 5 is a 404
  on sportsfly; week 3's real slug is
  `trade-chart-fantasy-football-buy-sell-week-3-dave-richard`.
- **Parser unchanged-compatible:** the week 5 page parses with the existing
  TableBuilder regex: QB 35, RB 44, WR 45, TE 15; headers as week 4.
- **Live discovery:** `discover_url(5)` -> week 5 URL; (4) -> week 4 URL;
  (3) -> the week 3 slug above; (6) -> quiet DiscoveryFailed, newest week 5.
  USA Today `discover_url(5)` and FantasyPros `discover_url(5)` unchanged
  (week 5 URLs). FantasyPros sitemap candidate for week 5 is the `/2026/10/`
  URL.
- **Dry run:** `ingest_cbs.py --week 5 --dry-run` discovered, passed the
  gate, `tables ok: QB=35, RB=44, TE=15, WR=45`; it then stops at
  `fetch_players` (no local Supabase key, 401). Identity resolution was run
  offline with `public.players` read via MCP SQL (1,460 QB/RB/WR/TE rows):
  `build_cbs_rows(week 5)` -> 343 clean rows (standard 113, half_ppr 113,
  ppr 117), 74 review rows, all `missing_or_non_numeric_value` for CBS's
  `--` cells (1QB columns of lower QBs, non/0.5 of four players), 0
  unresolved names. Week 4 in the DB has 342 rows, same shape.
- **Tests:** `tests/test_article_discovery.py` 25 pass on the branch; on an
  origin/main worktree with the same test file and fixtures, 21 fail. The
  meaningful ones: CBS path tests get the week-4 sportsfly URL instead of
  week 5 (the exact production bug); USA Today returns the week-4 URL over a
  reworded week-5 slug. Existing suites pass: test_cbs_usatoday_recurring,
  test_trade_chart_ingest_ci, test_pull_fantasypros_parse,
  test_cbs_week_coding, test_workflow_no_event_interpolation (121 + 70).
- **Gate:** `make sync` then `make validate` (Chrome) both exit 0; build
  churn reverted.

## Claimed, not confirmed

- The LLM fallback has never been called against the real API (no key in
  CI, none used locally). Its behaviour is pinned with an injected
  `complete`; a wrong or invented answer cannot get past `check_article`.
- `${{ secrets.ANTHROPIC_API_KEY != '' }}` in the install step's env is
  assumed to evaluate to "true"/"false" on Actions; if not, the SDK just is
  not installed and the fallback logs "unavailable".
- `tests/test_pull_fantasypros.py` fails to import (`No module named
  'fantasypros'`) on origin/main as well; not part of any make target; not
  touched.
- The CBS listings were readable from this machine; GitHub runners were not
  tried (CBS served the old sportsfly slugs to CI, so www should be fine).
