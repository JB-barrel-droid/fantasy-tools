# JEG-610 item 2: exclude-source-week divergence resolution

**Date:** 2026-10-16
**Ticket:** JEG-610

## What changed

Added 'exclude' as a fourth resolution kind for the source divergence check
(JEG-460). When a source-week is resolved as 'exclude', it gets held semantics
per JEG-569: the source stays in the pipeline (contributes to weights and pie
so no other source's values change) but is hidden from the DDF blend, the
Indexed basis and the bench-share readout. The UI shows it grayed out.

### Files changed

- `pipelines/check_source_divergence.py`: added 'exclude' to RESOLUTION_KINDS;
  status becomes 'excluded' (not 'reviewed'); freshness summary carries
  `resolution_kind`; report summary lists excluded source keys.
- `data/source-divergence-resolutions.json`: updated schema description.
- `pipelines/value_reference.py`: added `load_divergence_exclusions()` and
  `divergence_exclusions` parameter to Setting; state() treats excluded sources
  as hidden (same as held).
- `pipelines/value_check.py`: run_reference loads divergence exclusions and
  passes them through.
- `pipelines/sync_dashboard_artifacts.py`: injects `divergence_exclusions` list
  into the fixture copy for the browser engine.
- `app/trade-value-chart/assets/product-data.js`: exposes
  `divergence_exclusions` from the snapshot.
- `app/trade-value-chart/assets/curve-widget.js`: eligibilityReason checks for
  divergence exclusion and returns hidden.
- `app/v2/v2.js`: divergenceChip handles 'excluded' status.
- `app/v2/v2.css`: `.is-excluded` chip style.
- `tests/test_v2_divergence_chip_render.py`: updated patch anchors.

## Verified

- `value_check compare --rerun-engine --strict`: agree, 1,148,322 values, 0
  mismatches. No deltas (no exclude resolutions exist in the data file yet).
- `test_source_divergence`: 11 passed.
- `test_open_divergence_issues`: 5 passed.
- `test_value_check`: 21 passed.
- `test_v2_divergence_chip_render`: known red on main (fantasycalc held),
  unchanged by this PR.

## Not done

- Item 3 (projection thresholds): needs a few weeks of reports. Noted on ticket.
- Item 1 (auto sub-issue): built in PR 569, blocked on Jeremy adding
  LINEAR_API_KEY secret.
