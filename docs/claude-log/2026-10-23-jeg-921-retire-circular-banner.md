## 2026-10-23 - Retire the circular-blend banner; all-projections-paused state (JEG-921, closes JEG-878)

Decision (Jeremy, 2026-10-23): retire the JEG-826 circular-blend banner. DDF Value is projections-only
(JEG-804, #814), so it can no longer be built from the charts it is compared with. Branch `fe/JEG-921-retire-banner-2`.

### What changed
- Removed the whole JEG-826 mechanism from `app/v2/v2.js`, `shell.html`, `v2.css`: `blendIndependenceCheck`,
  both banners, the How-values inline note, the softened deal read, softened "every source agrees" lines
  (story, verdict) and the Targets "rescaled values sit above/below ours" meta. All keyed off `circular`.
  `trade.js` had no references.
- Deleted `tests/test_v2_circular_banner_render.py`. This closes JEG-878 (that test's missing negative proof);
  nothing else was weakened.
- Edits avoid the lines JEG-863 (#856) changes; plain merge of origin/main only.

### All projection sources paused
Prior session reproduced headless (pinned fixture plus ESPN, CBS rest of season, Razzball held): no number, no
chart fallback; search cell showed "—" with a note, but the default empty state said only "No player is priced
for this selection." Fix: shared reason reads "All projection sources are paused this week"; the Player values
empty state says "..., so DDF Value shows — for every player. Search for a player to see why."
New `tests/test_v2_all_projections_paused_render.py` with a guard that serves a v2.js with the note broken and
requires both checks to fail.

### Verified / not
See PR body for the run results. Targets, Compare and Risers wording in the all-paused state keeps its own
blocked states and was not changed.
