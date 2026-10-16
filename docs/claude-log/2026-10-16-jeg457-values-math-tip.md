# 2026-10-16 JEG-457 remaining: published-number tip on Player values (part of JEG-588)

- A rescaled trade chart cell on Player values now opens the same tip as Trade targets (published number first, rescale factor, rescaled value, link to the chart), on hover, focus or tap. Reuses attachPublishedMath and the engine's getPublishedMath; no recomputation. Clicking such a cell opens the tip, not the drawer (click the name for the drawer).
- Not built, needs back end (value-model.js, hot file): the chart-totals line (anchor total / chart total) and per-step adjustment lines (engine applies one factor per chart).
- Verified: tests.test_v2_values_math_tip_render (2 broken builds caught). Not verified: spot-check against live publisher pages.
