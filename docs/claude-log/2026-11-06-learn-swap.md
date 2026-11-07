## 2026-11-06 - Learn swap to the live root (JEG-1536, plan step 2 of JEG-1534)

Contract: replace the live Writing and Values auditing routes with the redesigned `learn.html` at the site root,
wired to the live engine (no week-9 snapshot files), and redirect the old `#writing/*` and `#values-auditing/*`
links to it. Auto-merge on green gates and an independent review (Jeremy, 2026-11-06).

What changed
- `app/next/learn.html`, `learn/numbers/numbers.js`, new `learn/numbers/learn-engine.js`: Value pie, Source build-up,
  Trace and Glossary read the engine that runs hidden on the page (`ddf-engine.js` from JEG-1535 over
  `TradeValueCurveControls`). The live Health check (verdicts, totals by source, by position, filled-in players) is on
  the Value pie tab and uses `AuditPie` from `v2/audit-pie.js`; Source build-up uses `DDFAuditSource.build` from
  `v2/audit-source.js` and gains the live features the wireframe lacked: all seven sources, a position filter, all
  players 50 at a time, a curve, the source's own page link. New "Full value logic" sub-tab frames `value-logic/`.
- Settings bar (scoring, teams, superflex): starts from the reader's saved league (applied by `ddf-engine.js`);
  a change applies to this page only (engine setters with publish off, never `DDF.engine.apply`, which saves).
  Routes carry `?scoring=&teams=&roster=` so a Trace permalink reproduces its numbers.
- Glossary examples are filled from the engine; the week-9 numbers and "Change them under Advanced" (weights on
  hold, JEG-1540) are gone; Missing (—) and Zero terms added (from the live How values work page).
- Removed `learn/data/` (lineage-week9, vaw-week9, raw-week9; D8). The methodology draft moved to
  `docs/learn-drafts/methodology.md` and is out of `posts.json` (D6). Draft tag code kept.
- `pipelines/build_root_pages.py`: learn.html in ROOT_PAGES and ENGINE_PAGES; learn files in ROOT_FILES; a folder
  entry (`learn/posts`) is copied whole so a new post needs no builder edit.
- `app/v2/v2.js` SWAPPED_ROUTES: `#writing/manifesto` -> `learn.html#manifesto`, `#writing/how-values` ->
  `learn.html#numbers/logic`, `#writing/*` -> `learn.html`, `#values-auditing/health-check` -> `#numbers/pie`,
  `#values-auditing/single-source` -> `#numbers/build-up`, `#values-auditing/*` -> `#numbers/pie`.

Independent review (separate Opus subagent, diff only, head 97160a729): CHANGES NEEDED, fixed at b768948f3:
- Trace showed a stored override as "the model's own value" (blended.value holds the override): Learn now reads
  `blended.pipelineValue` when overridden, and sets a custom value basis aside on this page only (engine setter,
  publish off); both are named on the page. New test `test_overrides_and_basis_not_applied` compares against a
  clean browser.
- Real engine zeros showed as dashes when a chart does not list the player: indexed and adjusted now come from the
  engine row; only the published value is a dash. The parity test reads the engine the same independent way.
- Settings query appended twice after a fallback replaceState; the projection worked path (waiver line, starter
  line, parts, rates) from the old build-up restored; "Set one on Values" -> "Add one on Values".
- Kept as is: no "Change" column and no "≈" mark in the build-up (Indexed and Adjusted are side by side; est. marks
  filled-in players).

### Verified (check named)
- `tests/test_learn_engine_parity.py` `test_numbers_match_engine`: at 3 scorings x 10/12 teams x superflex on/off,
  every picker DDF Value, the Trace (published, factor, indexed, adjusted per chart) for the top three, the Value pie,
  the Health check totals and the CBS and FantasyCalc build-up rows equal the engine read directly from
  `TradeValueCurveControls`; no console errors.
- Same file `test_guard_catches_a_wrong_number`: the comparison fails when DDF Value is nudged by 0.2.
- Same file `test_manifesto_verbatim_and_one_h1`: Manifesto equals `docs/manifesto-mirror.md` word for word (MF-01
  rule); one visible h1 on every Learn view at 1440 and 390.
- Same file `test_old_routes_redirect`: 11 old hashes (incl. legacy `#manifesto`, `#how-values`, `#research/x`,
  `#values-auditing/value-pie`) from `/` and `/v2/` land on the right Learn view; `value-logic/` ends on
  `learn.html#numbers/logic` with the explainer framed.
- Same file `test_no_snapshots_or_drafts_published` and `test_overrides_and_basis_not_applied`.
- `make validate-base` passed locally at 97160a729 (before the review fixes).
- QA sweep (scratch script, Playwright, hermetic): 13 views x 1440/390 x no league / saved league = 52 views,
  0 page errors, 0 failed same-host requests, 0 horizontal overflow, 0 broken same-host links (345 links),
  no banned words outside the Manifesto. The only console errors were the hermetic DNS block of Google Fonts.
  Interactions: Show 50 more, settings change (did not write `ddf.v2.league-settings`), picker, Copy, arrow keys.

### Claimed, not confirmed
- CI `make validate` shards and the rendered gate on the PR head: see the PR checks.
- Live behaviour after deploy (verify_live.py and the live Playwright pass) is recorded on JEG-1536.
- When step 5 retires `dist/v2/`, `v2/audit-pie.js` and `v2/audit-source.js` must stay published (Learn loads them).
