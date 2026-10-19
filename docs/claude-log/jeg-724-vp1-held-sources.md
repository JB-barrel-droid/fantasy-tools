## 2026-10-19 - JEG-724: methodology VP-1 held-source rule matches the code

Docs only. `docs/methodology.md` VP-1.1 said a held source is not eligible, and
VP-1.4 and two cross-references (VP-6.3 inputs, VP-2.4 peers) said it
contributes nothing to weights or peers. Since JEG-569 part 2 (PR 530) and
JEG-610 item 2 (PR 662) a held or divergence-excluded source that has a section
and values at the setting stays in the included set `I` (allocation, rosterable
set, DDF weights, peers, pie) and is hidden from DDF Value, the Indexed basis
and the bench-share readout.

Verified by reading: `pipelines/value_reference.py` `state()` (held and
divergence-excluded keys are appended to `eligible` and `hidden` when the
section exists and has natives); `curve-widget.js` `eligibilityReason`
(`run: true, hidden: true` for held and divergence-excluded). `tests/` has no
assertion pinning the old VP-1 text (grep for "not held" / "not eligible").

Not changed, flagged: `pipelines/spec_reference/pipeline_live.py` `eligibility()`
and `SPEC_AMBIGUITIES.md` SA-5 still implement the old rule (held = ineligible).
That is the independent spec reference, so aligning it is a code change and a
separate ticket. VP-12 text near "Their fixture sections go back to the last
published ones" (hold section) predates the 2026-10-12 decision and may also be
stale.
