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

### Correction pass (Codex review 629052e0, on head febfbb8d)
- Both contradictions were still present at febfbb8d (line numbers had moved: S1 is now line 94, AC2 line 120-122, AC4 line 129-132).
- AC4: now excludes only the K/DEF and no-row players from every sum; the player missing only the shown series stays in DDF Value and every other priced series. Pinned to current code, read in this session: `pickStarters` (finder.js:398-418) sets unpriced rows aside per series as `unvalued`; Compare shows no result for an incomplete row (v2.js:5443, :5904); League-wide trade edges go null on a missing value (opportunities.js:104); `withChartAverage` (finder.js:433) gives no market average when any compared chart is missing. No math change proposed.
- S1: the fit-label promise now applies only with at least 3 trade charts (`MIN_CHARTS`, finder.js:23; `market` gated at finder.js:1863, league.js:86, opportunities.js:88), matching AC2 and S13. AC1's Given now states 3+ charts so its "same fit label" check has a label to compare.
- Not touched: runtime, contract Google Doc, Natural-fit predicate, labels owned by JEG-1230/JEG-1249.
