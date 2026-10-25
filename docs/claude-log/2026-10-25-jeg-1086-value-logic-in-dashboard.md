## 2026-10-25 - JEG-1086 DDF Value Logic moves from the claude.ai artifact into the dashboard

Contract: Jeremy, 2026-10-25: "Ddf value logic should migrate from a Claude artifact to part of the dashboard". Multiple-choice answers: placement Writing -> How values work; snapshot at the default setting, rebuilt every deploy; keep the artifact until the dashboard version is verified live, then retire; review "in a collapsed section at the bottom".

### What changed
- `make sync` builds the explainer to `dist/value-logic/index.html` (needs Playwright; skipped locally without it, error under `RENDER_TESTS_REQUIRED=1`).
- Template: "internal" eyebrow now links back to How values work; review banner and "Things to look at" moved into a collapsed `Review` section at the bottom.
- How values work has a card linking to the page (no numbers in the copy; the how render test checks that).
- CLAUDE.md and the Makefile comment describe the new path.

### Verified (check named)
- Local `make sync` writes the page; headless load: no page errors, Review section collapsed, opens on `#review`.
- `tests.test_v2_how_render` (first run failed on my own copy, "12" not from the engine; reworded, rerun OK), `tests.test_v2_contract_render` (6, OK), `tests.test_public_copy_no_vorp` (12, OK).

### Claimed, not confirmed
- Live site after deploy; the artifact is NOT retired yet (waits on live verification).
- The page is a separate page linked from How values work, not inline in the v2 shell; still noindex; VORP wording in the page is unchanged (public-copy test covers the v2 shell only).
- CI's `test_launch_front_door` failed on the first push: public pages must not link into `modules/` (monitor pages). The page moved to `dist/value-logic/index.html`; the test is unchanged and passes.
