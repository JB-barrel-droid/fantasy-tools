## 2026-10-12 - JEG-571 Start / Hold / Stash / Drop tag rules (back end)

Contract: land the ungated back-end part of JEG-571: the tag rules as a pure function of the engine's row fields, pinned by a test. Front end (chips, drawer line) stays with the FE chain (v2.js).

Docs relied on: docs/methodology.md ES-10 (lineupShare, startWorthy), docs/wave-plan-2026-10-12.md.

### Decisions (defaults, Jeremy can overrule; recorded on JEG-571)
- Start = `ddfTier === "starter"` (the roster convention's starter tier on the reader's settings, no hard-coded counts).
- Stash = not a starter and `startWorthy` >= 0.25 (`STASH_START_PROBABILITY`, an option on the function).
- Drop = waiver tier and not a Stash. Hold = bench tier and not a Stash. No tier gives no tag.
- Alternative for Drop = the waiver line (JEG-529 waiver upside and JEG-526 handcuff are parked; they will change the Stash and Drop tests).

### Verified (check named)
- `python -m unittest tests.test_player_tags`: 9 fixture players (including the ticket's Mason 50% and Keaton Mitchell 12.5%) get the expected tags; the guard mutates the module with five named bugs and each changes the output.

### Claimed, not confirmed
- The 25% Stash threshold is a judgement call; no live-data check of how many players it tags at each league setting.
- Not wired into the page; no render check at every league setting (needs the v2.js lane).
