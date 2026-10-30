## 2026-10-30 - Deploy gate: the input sweep toggles a source that draws a curve (JEG-1381)

Main's Pages build went red at 64f7303e ("JEG-135 rendered input sweep failed"). The automated rebuild 137c5531
put a review hold on USA Today; a held source keeps its checkbox checked and enabled but is left out of the curves
and `activeSources`. `tests/rendered_gate/gate_flexibility.mjs` toggled the first checked box (USA Today), so the
legend could not move: "legend entries 3 -> 3, want -1".

Change: the sweep toggles the first checked, enabled source that is in `getState().activeSources`. The assertion
was wrong, not the page: it assumed every checked box draws a curve, which a data hold makes false. No value math,
data or hold changes. With no active checked source the gate still reports a mismatch.

### Verified (check named)

- `node --check tests/rendered_gate/gate_flexibility.mjs`.
- `python3 -m unittest tests.test_deploy_gate_unconditional tests.test_jeg135_rendered_flexibility` (the second
  skips here: no Chromium in cloud).
- Failing before: main's Pages run 40998956641, job 123879480023 (mismatches read from its log).

### Claimed, not confirmed

- The preview's rendered gate turning green with this change is CI's to show (PR checks).
- Side note left alone: the USA Today hold has no `hold_level`; the widget reads that as red (curve-widget.js ~1120)
  while the chain status says amber.
