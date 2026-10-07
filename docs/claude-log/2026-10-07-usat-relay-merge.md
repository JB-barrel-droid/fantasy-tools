## 2026-10-07 - USA Today CI ingest unblocked via Supabase relay (fix/usat-ci-relay)

Contract: get USA Today trade-chart data flowing from CI again without a paid
service (GAP-USAT-CI-BLOCKED / GAP-USAT-FIRECRAWL).

### Verified
- Supabase egress is not walled. Edge Function `usatoday-fetch` (project
  iskiybsimubiujwuchsl, verify_jwt on, allowlist usatoday.com / amp / gannett-cdn,
  plain descriptive UA, no spoofing) called via pg_net returned 200 for
  web-sitemap-index.xml and for the week-5 article (6 `gnt_ar_b_tbl` tables).
- Discovery bug found: the week-5 slug is `fantasy-trade-value-charts-week-5-ros-rankings`
  ("charts"). The singular-only match missed it. `pull_usatoday.SLUG_RE` and
  `extract_week_from_url` now accept `charts?`. Not fixed here:
  `pipelines/check_source_fidelity.py` LIVE_SECTION_SLUG has the same singular-only
  pattern (gate owner).
- `pull_usatoday.fetch_article` (new default for `pull`): direct fetch, then on
  401/402/403/429 the relay (needs SUPABASE_URL + SUPABASE_SERVICE_KEY, already CI
  secrets), then Firecrawl only if FIRECRAWL_API_KEY exists. A failed fallback
  keeps the original status so SOURCE_BLOCKED still raises. Parsing, week gate and
  fail-closed logic are untouched.
- CI dry run, branch ingest/dry-relay1, run 37614204115, job 112768503861:
  "direct fetch blocked (402); fetched via supabase relay", tables QB=36 RB=75 TE=37 WR=106,
  747 rows clean, bake usatwk4 (the ingest's own week rule = 4 until Thu Oct 8 CT).
- CI dry run with `--week 5` (throwaway branch ingest/dry-relay2, run 37614365318,
  job 112769035281): URL = week-5 article, tables QB=36 RB=79 TE=37 WR=109, 756 rows
  clean (69 review), bake usatwk5. (CBS week 5 failed in that run: not published yet,
  unrelated.) Throwaway branches deleted.
- tests/test_trade_chart_ingest_ci.py + tests/test_cbs_usatoday_recurring.py green.
  Negative test: with HEAD's old pull_usatoday.py the new tests fail (1 failure,
  5 errors).

### Claimed, unverified
- Firecrawl path: written to Firecrawl's v1 /scrape `rawHtml` format from memory of
  its API; never executed (no secret). It is inert without FIRECRAWL_API_KEY.
- Relay durability: usatoday.com may start walling Supabase IPs; then the run records
  SOURCE_BLOCKED as before. The relay is callable with the anon key (verify_jwt only);
  it is host-allowlisted but not otherwise rate-limited.
- Real write mode not run (write needs a push to ingest/write-* or the pg_cron dispatch).
