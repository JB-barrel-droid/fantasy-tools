Frozen copies of the value engine as it was on origin/main at 61ecb39e (JEG-1035, before JEG-1044 added the value
basis). tests/test_basis_overrides_render.py serves these in place of the live engine files and requires the current
engine, on the default basis, to give the same values at every league setting (the default path is byte-identical).

When a later change deliberately changes our default values, re-freeze: copy the engine files from the commit's
parent over these, and say so in docs/claude-log.md. Do not edit them to make a test pass.

JEG-1073 (Jeremy, 2026-10-25: "Keep adj trade chart avg as the main ddf and projections as an alt"): our default values
changed deliberately (DDF Value is the four charts' Adjusted average). These frozen engines are pre-basis, so they were
not re-copied from a parent; instead the same default-rule edits as the live engine were applied to them
(value-model.js `blendedI = chartsI`; curve-widget.js `COMPOSITE_INPUT_KEYS`, `OVERRIDE_VERSIONS`, `COMPOSITE_VERSIONS.ddf_value`).
Nothing else in them changed, so the test still proves the basis feature leaves the default path untouched.
