# Source discovery shortlist (JEG-623) and FantasyFootballAnalytics.net access check (JEG-622)

Measured 2026-10-15 from a Mac, anonymous requests (browser user agent, no cookies, no login). "Public" below means: HTTP 200 with the data in the response body, no login, no paywall, no key. Legal and ToS review is out of scope (Jeremy, 2026-10-12). Nothing here is wired into DDF Value; a source enters only after its puller fails closed and its fidelity pulse is green (pattern: `pipelines/pull_draftsharks.py`).

## Already in the repo or tracked (not candidates)

ESPN and CBS (season and ROS projections), Razzball ROS, FantasyCalc, USA Today, FantasyPros trade values (not ECR), Sleeper weekly projections (measurement only, `pull_sleeper_projections.py`), Draft Sharks (JEG-620, puller merged), Fantasy Sharks (JEG-621), Pro Football Focus (JEG-612 list).

## JEG-622 result: FantasyFootballAnalytics.net publishes nothing we can pull publicly

Fail-closed finding, no puller written.

| Surface | Check | Result |
|---|---|---|
| `/projections` page | 200, 84 KB | Explanatory article only, no data table |
| `apps.fantasyfootballanalytics.net` | 200, 24 KB | WordPress landing page; the tools are Shiny apps behind "FFA Insider" (paid, $4.99/month per their 2016 post) |
| Weekly cheat sheet posts (`/2026/10/...week-6-2026.html`) | 200 | One sentence, zero tables, no attachment or image; the content is not in the page |
| API (`proj`, `adp` endpoints, JSON) | docs page 200 | Paid key required ($1,000 or $1,500 per season, "intended for commercial users"). Not public |
| `ffanalytics` R package (open source) | repo readable | Scrapes other sites (CBS, ESPN, NFL, FFToday and so on) on the user's machine; FFA's own averaged projections are not in it |

FFA's projections are an average of third-party sources, so even a successful pull would double count sources we already take or are adding. Recommendation: close JEG-622 as "no public access; superseded by direct sources below". Revisit only if Jeremy decides to buy API access.

## Ranked shortlist

Rank is by fit with the pipeline (a numeric value or per-stat projection we can map to `player_key`, public today, stable layout) over effort. Effort: S under a day, M one to two days, L more.

| # | Site | What it publishes | Access method (verified) | Update cadence | Scoring / league coverage | Fit with pipeline | Effort |
|---|---|---|---|---|---|---|---|
| 1 | KeepTradeCut (`keeptradecut.com/dynasty-rankings`) | Trade value per player, 1QB and superflex, plus TE-premium block, ranks, tiers, 7-day trend, kept/traded/cut counts | Page embeds JSON in `<script id="ktc-players">`: 500 players, 200 OK, 2.7 MB, no login. Python `urllib` failed TLS (TLSv1 alert), `curl` works, so the puller must use curl or a pinned TLS context | Daily (market-driven) | PPR full; 1QB, superflex, TEP; 12-team implied; dynasty-framed values | Direct market trade value, the same shape as Draft Sharks `market` columns. Only gap: dynasty basis, so it needs a methods decision before DDF use | M |
| 2 | RotoBaller trade value chart | Redraft trade value 0-100 per player, rank, position | Server-rendered HTML table, about 400 rows on the page I fetched, no login. The stable URL redirects to a dated weekly article (`...-week-1-trades-...-2026/1925996`), so the puller must find the current week article | Weekly article (the fetched copy was labelled Week 1, stale at Week 6) | Single scoring (not stated per row); league size not stated | Redraft 0-100 scale like Draft Sharks. Risk: stale article and unstated scoring; needs staleness guard | M |
| 3 | Fleaflicker (`fleaflicker.com/nfl/leaders?statType=7`) | Weekly projections, per stat (rush att/yd/td, rec, tgt, rec yd/td, fumbles, FPts), rank, ownership | Server-rendered HTML table, 20 rows per page, paged with `?position=` and offset parameters, no login | Weekly, updated in season | Fleaflicker default scoring; per-stat lets us rescore to any league | Per-stat weekly projections are rare and the best fit for the rescoring engine. Needs pagination and bye-week handling | M |
| 4 | Dynasty Daddy (`dynasty-daddy.com/api/v1/player/all/today`) | JSON, 765 players: `trade_value`, `sf_trade_value`, ranks, history highs and lows, and ROS ranks from ESPN, FantasyPros, FanDuel, FantasyGuys; carries sleeper/mfl/espn/yahoo ids | Public JSON endpoint, 930 KB, no key | Daily | 1QB and superflex | Easy ids and clean JSON, but its trade value is an aggregate of other markets (double counting risk against FantasyCalc and KTC). Best used as a comparison or id bridge, not a weighted source | S |
| 5 | FanDuel Research / NumberFire remaining-season projections | "Remaining fantasy projections" (ROS) | Page loads (200) but data is client-side: the Next.js payload carries no projection rows. The backing API was not located | Weekly | Unknown | Real ROS candidate, but unverified; first task is to find the data call. Probe only | S to find, M to build |
| 6 | Sleeper projections (`api.sleeper.app/projections/nfl/{season}/{week}`) | Weekly per-stat projections (provider RotoWire), 355 QB rows for week 6, pts std/half/ppr | Public JSON, already pulled by `pull_sleeper_projections.py` | Daily | std, half, ppr | Already a measurement source; promoting it to a value input is a methods choice, no new puller | S |
| 7 | FantasyPros projections (`/nfl/projections/{pos}.php?week=N`) | Per-stat season and weekly projections | Public HTML, but only 10 player rows per position in the anonymous page I fetched; rest not confirmed available | Weekly | Several scorings via parameter | Partial anonymous view; ECR-flavored rows are excluded repo-wide, projections are not ECR but coverage is thin. Hold | M |
| 8 | DynastyProcess `values.csv` (public CSV, 483 rows, `value_1qb`/`value_2qb`, scrape date 2026-10-09) | Trade values derived from FantasyPros ECR | Public CSV | Weekly | 1QB, 2QB | Derived from ECR, which the repo hard-excludes. Do not use unless Jeremy lifts the ECR rule | S |

## Public but not worth a ticket

| Site | Why |
|---|---|
| Fantasy Football Calculator ADP API | Public JSON (`/api/v1/adp/ppr`, 12 team, dated), but ADP, not a value or a projection |
| RotoWire projections | Anonymous table has 3 data rows; the rest sits behind a subscription |
| Underdog rankings | Rankings page with no table in the HTML; ranking-only, ECR-like |
| NFL.com, Yahoo | Pages load but carry no projection data anonymously (client-side or login) |

## Blocked or dead

| Site | Check |
|---|---|
| FFToday | HTTP 403 on projections pages |
| Dynasty League Football | HTTP 403 on trade value chart |
| Pro Football Focus | Page loads, projections behind PFF Pro trial wall (JEG-612 already tracks) |
| Footballguys, 4for4, FantasyNerds, FantasyLife, Establish The Run, CBS trade-value URL I tried | 404 at the guessed URLs; subscription products for the first three |

## Not verified

- Update cadence for KTC, Dynasty Daddy and Fleaflicker is from page text and behavior, not from watching changes over days.
- RotoBaller's scoring format and league size are not shown on the page; I did not open the full article.
- Fleaflicker pagination parameters were read from the link list, not exercised.
- FantasyPros anonymous row limit was counted on three pages (QB season, RB week 6, ROS rankings); I did not test whether XHR loads more rows.
- Name-to-`player_key` matching was not run for any candidate; each puller ticket must do it through `lib/canonical_players`.

## Tickets created from this list

See the JEG-623 comment for the links. The top four (1 to 3 and 5) become child tickets; Dynasty Daddy (4) is a comparison feed ticket at lower priority.
