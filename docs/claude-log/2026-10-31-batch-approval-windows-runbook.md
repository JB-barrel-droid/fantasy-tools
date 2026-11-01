## 2026-10-31 - Batch approval window timing / JEG-1445

Contract: carry Jeremy's 13:26 UTC decision-13 timing update into the existing PR; other batch rules remain unchanged.

### Verified (check named)
- Source inspection: two batch/approval windows, 6:00 AM and 4:00 PM US Central, gather newly eligible PRs and request deploy approval in that window; overnight merge windows and asks prohibited.
- git diff --check, eight paired duties, policy equality and stale-timing search passed.

### Claimed, not confirmed
- No schedule activation, merge or deploy performed. make validate unavailable without headless Chromium; GitHub CI must run the gate before review.
