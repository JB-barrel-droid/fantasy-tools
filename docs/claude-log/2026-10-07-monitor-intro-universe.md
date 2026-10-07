## 2026-10-07 - JEG-437 / JEG-428 item 6: monitor intro denominator

### Verified (check named)
- `python3 -m unittest tests.test_coverage_intro_dynamic_universe` FAILED on main:
  app/trade-value-chart/index.html line ~2280 had the literal "596-player canonical
  snapshot" again (the QA-007 fix, 2026-10-04, had been lost; the test was not in
  `make validate`, so nothing noticed). The per-source cards use
  `universe = embedded.players.length` (the /613 in the coverage rows).
- Fix: the intro is now a template literal using `${universe}`; the same test passes,
  and it is added to Makefile `test-unit`. The pre-fix literal is the broken state
  (test failed on it; the test also carries its own negative case).

### Claimed, not confirmed
- Did not re-measure how many players the live embedded fixture holds (613 is the
  figure quoted in JEG-428); the wording now follows whatever the fixture holds.
- Did not find why the literal came back (likely a merge of an older index.html).
