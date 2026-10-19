## 2026-10-19 - JEG-718: panels allowlist and targets hover-pin (cluster 2)

Contract: fix the two test-side causes in test_v2_panels_render and test_v2_targets_render; leave the design calls open.

### Changes and why
- panels: the "controls other than brushes and zoom inside the chart" allowlist lacked `v2ChartSize`, the taller/shorter toggle added on purpose in JEG-477 (#701). The assertion was stale, not the product; the control is added to the allowlist.
- targets: "[390x844] hover: a click on a hover-opened popover must pin it" failed because the centred phone popover covers the trigger, so `mouse.click` at the trigger's centre hit the popover. The check now dispatches the click on the trigger when the point is covered, otherwise clicks as before. The product behaviour (a click on the trigger while hover-opened pins) is unchanged.

### Still red (not fixed; needs Jeremy, JEG-718 is labelled needs-review)
- panels, 1440: wide selection scrolls 9px sideways (was 31px in the ticket). Check chip on the FantasyCalc and FantasyPros headers; options (a) shrink or stack the chip.
- panels, 1366x768: chart card ends at 800px, fold is 768 (options (b) one-row or scrolling legend, (c) relax the spec).
- targets guard "equal case duplicates the number": the mutant is no longer visible since JEG-677 sorts an equal row last (never in the top 25). Not dropped: removing a mutant weakens the guard, so this is the ticket's option for Jeremy.

### Verified (check named)
- `python -m pytest tests/test_v2_targets_render.py`: only the equal-case subtest fails (the 390 hover-pin failure is gone).
- `python -m pytest tests/test_v2_panels_render.py`: only the two design-call errors above remain after the allowlist change (the v2ChartSize error is gone).

### Claimed, not confirmed
- That the hover-pin check still fails when a click does not pin (no negative test run on that line).
