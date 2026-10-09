"""Clean-room spec reference for the two hardest pieces of the value math (JEG-479).

Written only from docs/methodology.md, docs/math-review-agenda.md, Jeremy's
decisions recorded there and in docs/claude-log/, and the data files (fixture
JSON, players.json, the built two-tier legs). It deliberately does NOT read or
import the browser engine (curve-widget.js, value-model.js), the line-for-line
Python ports (twotier_reference.py, parity/value_model_parity.py) or
vorp_translation/unified.py, so a bug copied into those ports shows up here as
a disagreement.

Modules:
- twotier: two-tier starter/bench pricing (pool, position pies, starter /
  flex / bench split, bench share, feasible window, display scale).
- value_model: value above waivers (roster allocation, waiver line, implied
  weights, short-chart extension), the published charts' three views and the
  projections' raw value-above-waivers series.
- compare: builds every series at the 12 league settings x 3 views from the
  data files and diffs it against the engine dump value_check.py writes.
  `compare.py pipeline` runs the JEG-508 pipeline below on the live snapshot.

JEG-508 source-neutral value pipeline (written only from docs/methodology.md
"Value Pipeline (source-neutral, 2026-10-09)", VP-0..VP-12, without reading
pipelines/value_reference.py or the engine):
- value_pipeline: native -> fill-in (OC-5) -> VORP vs waivers -> per-source
  weights (bench 15%) -> averaged DDF weights -> Adjusted on the fixed pie ->
  DDF Value in three versions -> Indexed; prior week and change (VP-8).
- worked_example: reproduces tests/fixtures/value_pipeline_worked_example.json
  leaf by leaf (1e-6).
- pipeline_live: the 12 combos plus PPR 12 superflex on the live snapshot,
  every value dumped (shape documented in the module).
- SPEC_AMBIGUITIES.md: where the VP text left a choice, the literal reading
  taken.

Where the (pre-JEG-508) written spec is silent the choice made is listed in
compare.SPEC_GAPS and in docs/math-review-agenda.md (MR-18).
"""

VERSION = "spec-reference/1"
