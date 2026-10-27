## 2026-10-25 - JEG-1105 / JEG-1097 / JEG-1102 methodology drafts

Contract: three draft docs under `docs/product/` (methodology page outline, fit-label glossary, two-views article outline) for Jeremy's review. Docs only; nothing publishes.

### Verified (check named)
- Fit rules read from `app/v2/finder.js` (`teamFit`, `tradeFit`, constants FIT_Z 1, NET_FLOOR 0.05, USABLE_MIN 0.05, MIN_CHARTS 3) and `app/v2/opportunities.js` (`overallFit`, TIERS) by reading source; grep for "Market Only" across app/ and docs/ found no such label (code says "Market fit").
- Article numbers match `~/code/fantasy-tools-selfhost-notes/jeg-1073-impact/report.md` as printed (re-read after writing).

### Claimed, not confirmed
- No tests or engine run; impact-report numbers not re-derived. Fit rules not exercised on a real trade.
- Code-vs-doc disagreements in the glossary are from reading, not execution.
