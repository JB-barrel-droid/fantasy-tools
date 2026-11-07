## 2026-11-07 - JEG-1565 trade value source audit (private draft article)

Contract: a fun, rigorous, private draft article grading the trade value sources people use (CBS Sports, USA Today, FantasyPros, FantasyCalc, plus ESPN, CBS rest-of-season and Razzball where we hold data, and documented methods for KeepTradeCut, DynastyProcess, Footballguys, Draft Sharks), with every number reproducible from one script.

Files: `pipelines/research_trade_value_audit.py` (evidence), `app/next/research/trade-value-audit.html|.js|-data.json` (page, published only at the unlisted noindex `/next/research/` path by `build_next_preview.py`), `tests/test_research_trade_value_audit.py`.

### Verified (check named)
- Every data-n number in the page text equals the script output, and the data file equals a fresh run on the week 9 fixture (built_at 2026-11-07T09:42:53): `tests/test_research_trade_value_audit.py` (7 pass).
- Page is noindex, not in `learn/posts.json`, not in `build_root_pages` ROOT_PAGES/ROOT_FILES, and no other file under `app/` names it: same test.
- No "player pool", no bare "market", no demo/illustrative/mock in page text or script: same test.
- 1440x900 and 390x844, light and dark (dark with reduced motion): 0 console errors, 0 horizontal overflow (Playwright script in the session scratch dir).
- FantasyCalc Full PPR / Standard is one factor per position (RB 0.994, WR 1.018, spread 0.001 over the top 36): script section `fantasycalc_scoring_factors`.
- CBS week 9 article method, 10%-off rule and unlisted-player rule; FantasyPros week 9 columns and "not league-specific"; KTC about page: read with WebFetch 2026-11-07.

### Claimed, not confirmed
- Footballguys, Draft Sharks, DynastyProcess, ESPN and Razzball method facts were gathered by a research subagent (fetched pages listed in the article); the independent accuracy review re-checks them.
- USA Today and FantasyCalc method pages did not load (blocked); the article makes no method claim for either.
- The reproduction test skips once the weekly refresh replaces `data/fixtures/current`; reproduce at this branch's commit.
- Local `make validate` needs Python 3.12 (3.9 fails history parsing on '+00' offsets) and a Playwright matching the cached browser; see the PR for the run.
