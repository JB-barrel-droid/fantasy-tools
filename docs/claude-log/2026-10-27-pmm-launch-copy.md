## 2026-10-27 - JEG-1130 (part 1): approved PMM launch copy, paste-only and on this device

Contract: apply the approved PMM doc (Jeremy, 2026-10-26, amended by JEG-1126: no platform integrations or accounts at launch) to the strings outside the hot file `app/v2/v2.js`. Copy only, no layout or behaviour changes. Session `session:fe-cloud`, branch `fe/JEG-1130`.

Changed:
- Storage and paste copy says "on this device", never "in this browser" (league, finder, waivers, inputs status). The league box carries the doc's 3.5 tips and its "Saved on this device. Bookmark… Download…" line. Platform names appear only as how-to-copy tips; the waivers paste tip no longer names ESPN, Yahoo and Sleeper.
- Page subtitles follow doc 3.2: Risers & fallers, both Find a trade pages, Waivers, Methodology (Appendix A #5: "Two numbers for every player. Here's what they mean."), Overrides (settings copy), and Values auditing ("Trace any number back to where it came from.").
- "Value over a waiver player" panel titles and module summaries are now "Value above waivers" (glossary; Appendix A #3).
- Meta description and social tags: the v2 head (`pipelines/build_v2_page.py`) and the classic page head use the doc's value prop and name no publisher (positioning guardrail).
- New guard `tests/test_launch_copy_guard.py` (in test-core and shard 1): no platform-connection claim and no "in this browser" storage copy in `app/v2`; no publisher in any head copy. It fails on main (8 browser-storage strings, plus the classic meta) and passes here.
- `tests/test_v2_plain_copy_render.py`: the "old panel title" probe's anchor follows the new title. The assertion is unchanged; only the text it patches changed, because the copy rule moved (Jeremy, 2026-10-26, PMM doc).

Deviations, left for Jeremy or later tickets:
- Nav and H1 renames (Trade targets → Buy & sell, Compare a trade → Check a trade, Overrides → Settings, Values auditing → Show the math): Appendix B #3 is still open, and JEG-1138/JEG-1139 carry the v2 renames.
- Strings in `app/v2/v2.js` (hot file): the Value chart subtitle, the Trade targets intro, the Compare subtitle and "No verdict yet", the error state and about 48 "our value" strings. These are part 2, together with the FINAL naming (DDF Charted Value / DDF Projected Value, Jeremy 2026-10-26 2:38 PM).
- League ID loaders (Sleeper/ESPN) stay as they are and keep their labels; the separate integration-path issue covers them.
- Notice priority order (doc 3.6) is behaviour, not copy; not changed.

### Verified (check named)
- `python3 -m unittest tests.test_launch_copy_guard`: 4 OK with the change; 2 failures with the app changes stashed (the test fails without the fix).
- `python3 -m unittest tests.test_validate_shards`: OK after adding the guard to test-core and shard 1.

### Claimed, not confirmed
- Before/after screenshots of the League card (desktop 1366 and phone 390) are on JEG-1130.
