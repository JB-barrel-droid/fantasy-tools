## 2026-10-30 - JEG-1379 shared league links wait for the page's link reader

Contract: a `#find-league?workspace=` share link must bring its player overrides and league settings, not only its teams,
even when the league card sees engine rows before v2.js has finished booting. Found while getting #1193 (JEG-1191) green.

### Verified (check named)
- Cause traced in code: `league.js` polls every 250 ms for engine rows and then reads the link; `v2.js` polls every
  120 ms and sets `window.TradeValueV2` only after its boot chain; `applyImported` skips `TradeValueV2.applyLinkLeague`
  and `DDFOverrides.applyLink` when `TradeValueV2` is missing.
- Symptom on CI: `test_round_trips_by_file_and_link` got `{}` overrides on the opened link page on #1193 head 1633d5e
  (runs 40993434549 and its rerun); the same code passed on a scratch run (40994713501), and main passed (40993969905).

- The new render test `test_link_waits_for_the_page_reader` fails without the league.js change
  (`scratch/jeg1379-test-without-fix`, run 40996475558: `{} != {'2227': 61.5, '2730': {...delta -4}}`) and passes with
  it (this branch at 152643d4, run 40996477894; all 9 settings render tests ok).

### Claimed, not confirmed
- That this race is the whole cause of the intermittent `test_round_trips_by_file_and_link` failure on #1193; it
  matches the symptom exactly, and #1193 with this fix ported is still waiting on CI.
