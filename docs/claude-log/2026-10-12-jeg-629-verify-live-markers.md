## 2026-10-12 - JEG-629 verify_live.py stale markers

- Replaced the two stale comparison-dashboard markers (news timing badges, news max-3 cap) with current ones (`function sourceFreshness`, `function loadComparisonData`) and added a v2 shell marker (`src="v2/v2.js`) for index.html.
- `main()` takes an injectable fetch, so `tests/test_verify_live.py` serves the built `dist/`: good build exits 0, wrong tag exits 1, an absent marker exits 1. Added to `make test-core`.
- Runbook `runbooks/verify-live.md` section 3 no longer says the script has a known false failure.
- Verified: test_verify_live (3 pass) against local dist. Claimed: live run (see PR).
