## 2026-10-29 - JEG-1221 trade-page parity glossary and UX acceptance review

Contract: review the user-facing labels, help, empty and unavailable states of Find a trade: your team, Find a trade: league-wide and Compare a trade against `docs/feature-contract.md`, the JEG-1220 parity matrix and the pending JEG-1130 / JEG-1212 wording, and hand off strings and acceptance cases. Docs only: `docs/product/jeg-1221-trade-page-parity-review.md` plus its index line. No application, test, math, default or ranking change.

### Verified (check named)
- Every finding cites a file and line on `main` `021c5bfd`, read with `sed`/`grep` in this session.
- `git diff --stat bf117c5f origin/main -- app/v2` is empty, so the reviewed source equals the last successful Deploy dashboard run (`bf117c5f`, GitHub Actions API).
- #1037 and #1071 strings were read from their PR diffs (GitHub REST), not from the branches' runtime.
- `grep -c ddfLowConfidence` / `appendLowConfidence` is 0 in finder.js, league.js, opportunities.js and team-summary.js (finding F2).
- finder.js:162 sets `minCharts = Math.min(MIN_CHARTS, chartKeys.length)` and finder.js:1769 only warns below 3 charts; league.js:1069 warns only at 0 charts (finding F7).

### Claimed, not confirmed
- No browser QA: the live site could not be loaded from this environment (proxy refused github.io; a web fetch returned an older cached build tag).
- F11's league re-paste merge of same-named teams is read from league.js:617-630, not reproduced.
- The JEG-1130 PMM Google Doc was not opened; the JEG-1130 description and #1037 stand in for it.
