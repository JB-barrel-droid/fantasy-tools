## 2026-10-29 - JEG-1244 corrections to the JEG-1047 waiver band (#1077)

Codex review of #1077 head 07cc137d (JEG-1047 comments 92be7775 and
7e5fd552). Correction child JEG-1244. No new math: VP-2.3 as written already
covers the zero seat ("indexes N_p - 3 through N_p + 3, clipped to the work
list" whenever the work list is longer than N_p).

### Changed
- `pipelines/lib/roster_convention.py` `waiver_band_line` and the JS twin
  `roster-convention.js` `waiverBandLine`: a zero seat (rostered 0, non-empty
  list) is the band clipped at the top, values[0..3], as the engine's
  `vpWaiverBand` already computed. Only an empty list or a negative count has
  no line. Before, both returned None and the Python and spec references then
  crashed in `max(line, w)`.
- `docs/methodology.md` VP-2.3 says the zero-seat case in words.
- `app/values-explainer/template.html`: the per-player chain named a
  projection's waiver line by one rank (`RB37`); it now names the band
  (`average of RB34 to RB40`). Charts keep the one rank.
- `value-model.js`: comment only. The engine keeps its own copy of the band;
  the old comment's "twin" claim is now backed by an end-to-end test instead
  of a source-substring check.
- `tests/test_waiver_band_line.py`: the substring test is gone.
  `EndToEndTest` runs the production engine (`runValuePipeline` via
  `tests/value_pipeline_driver.js`), the Python reference and the spec
  reference on 30 fixtures built from the worked example (zero seat, zero seat
  with a short list, empty lists, short lists, exact fit, one past the seat,
  and 24 seeded random shapes), compares rostered, method, waiver line,
  starter line and every Adjusted value, and checks each projection line
  against VP-2.3 written out in the test. Three engine mutations (one-player
  line, 5-player band, zero seat as one player) each fail it. The 1.0 point
  tolerance test now covers all 12 settings (3 scorings x 8/10/12/14 teams).
- `app/values-explainer/reviewed.json`: logic-file hashes recorded after
  re-reading the narrative against the #1077 and JEG-1244 diffs.

### Verified (check named)
- Before the helper fix (07cc137d helpers): `EndToEndTest` errors with
  `TypeError: '>' not supported between ... 'NoneType'` in
  `value_reference._source_lines` and `spec_reference.price_source`, and
  `test_zero_seat_is_band_clipped_at_the_top` errors. After: 9 tests OK.
- Zero-seat fixture (TE no slot, no bench, flex 0): main and the engine at
  07cc137d agree with each other only on main's one-player line; at this
  head all three give p1 TE 8.85, p2 TE 9.0 (mean of the top 4).
- The 12 published settings (and superflex) have no zero seat, so no
  published value moves from this correction.
- Perturbation sweep on this head, Python reference, `data/fixtures/current`
  (ESPN, CBS ROS, Razzball all present): 144 cases, 288 moves of +/-1 PPG;
  every one within 1.0 (worst 0.908, Razzball TE, half PPR 10 teams);
  245 of 288 within 0.5.
- `make test-core`, each of its 97 unittest lines run on its own: all pass
  except `tests.test_week_history`, whose engine transition test needs
  Playwright (not installable here; Chromium download refused). Rank guard
  (`tests.test_rank_guard`) passes.

### Claimed, not confirmed
- `make values-explainer` (the rendered page) and `value_check compare`
  need Playwright Chromium; CI builds and runs them.

### Open (not decided here)
- Composition with JEG-1188 / #1105: in a loaded league #1105 reads the
  waiver line at the replacement index R (`work[R]`, each source's own value
  at that depth). #1077 averages the 7 players around N. Whether a loaded
  league uses the band around R or the one player at R is a methodology
  call, recorded on JEG-1244; neither branch composes them.
