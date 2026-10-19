## 2026-10-19 - Contract QA: the 9 pending lines (part of JEG-491)

Contract: for CT-02, GL-07, GL-09, GL-19, GL-20, GL-21, GL-22, TT-05, TT-09, check the Linear ticket and whether the feature is in the built dashboard; add live checks for what shipped, record gaps for what did not. No product code or copy changed.

### Verified (check named)
- Linear: JEG-505, 498, 497, 501, 502, 510, 504 are all Done (get_issue).
- Built page (headless playwright against the served dist, `tests/test_v2_contract_render.py` harness): Customize on all four data pages with the groups, Select all/none, Reset to default, Cancel/Done (GL-07); ⓘ opens on hover, keyboard and click (GL-19); no "as published" or bare "indexed" in visible text, group "Trade charts (rescaled)" with its meaning line (GL-21); Edit league primary and before Position weights (GL-22); both Compare headlines with a confidence word (CT-02). New partial checks `gl07_partial`, `gl19_partial`, `gl21_partial`, `gl22_partial`, `ct02_partial`; `tt05_partial` now requires "rescaled". GL-09, GL-20 partials already existed and pass.
- Negative tests: `test_guard_fails_on_broken_builds` group 4 breaks ⓘ hover, the chart group name, Customize's Reset, Edit league's primary class and the Compare headlines; each named check reports a real finding. Full run of `tests.test_v2_contract_render` + `tests.test_contract_qa_report`: 11 tests OK. `python scripts/contract_qa_report.py`: 75/75 pass, 9 pending.
- TT-09 is not in the build: no "Market average" column or "equal" note; JEG-677 (2026-10-16) replaced the mean with the median consensus and gap columns (seen in the Trade targets table headers).

### Claimed, not confirmed
- The lines stay PENDING because the mirror (from Jeremy's Doc) still says "to build"; switching them needs the Doc to drop it (the mirror test enforces that). Not run against the live GitHub Pages URL, only the local build of main (d26f3fc6).
- GL-07 drift: the Doc lists "Trade charts (adjusted)"; the UI has no such group (GAP-508-V2-CONTRACT). Commented on JEG-498. TT-09 decision commented on JEG-504.
