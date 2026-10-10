# 2026-10-09 · Front-end (v2) handoff: Windows PC → Jeremy's Mac

The v2 front-end work is moving to the Mac. The Windows machine was saturated by parallel browser test runs, and two back-end tests only run on Linux or Mac.

## Read first (sources of truth)

- **Feature contract (Google Doc, source of truth):** "Data Driven Football: feature contract", v1.1, https://docs.google.com/document/d/1UDRlVTdOiAdI6gSSklxwB-R9uINozVmIILMwbvCBiH0. Each revision is a new Doc, and older ones are retitled "(SUPERSEDED …)". Never remove or alter a line without Jeremy's yes.
- **Linear:** team Jegabee, project "Trade Value Chart". At most 3 tickets In Progress; Done means merged and live.
- **Repo `CLAUDE.md`** for the lane rules, and `docs/v2-design-notes.md` for the v2 design and the back-end contract sections.

## Mac setup (about 10 minutes)

```bash
git clone https://github.com/JB-barrel-droid/fantasy-tools.git && cd fantasy-tools
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # if present; otherwise: pip install playwright tzdata
python -m playwright install chromium
make sync && make validate        # native make; no Windows workarounds needed
```

- Render tests: `python -m unittest tests.test_v2_panels_render`, and so on. They are slow, so run them one tab-group at a time rather than many in parallel.
- Run a local preview with `cd dist && python -m http.server 8000`.

## What's live (2026-10-09)

- **DDF Value foundation (a311aa87, JEG-466 Done):** the default view is DDF Value plus the rescaled charts, ranked by DDF; Customize includes the DDF inputs; the choice is remembered in localStorage `ddf.v2.selection`.
- **Shared grouped picker (4714754d):** covers JEG-465 (Risers & fallers on DDF) and JEG-467 (Compare verdict on DDF). Both Done.
- **Freshness fails closed, and the bench share shown is the share used (7d85207c / 92daf575).**
- **Back end:** JEG-482 is fixed, so rescaled charts keep each publisher's order (`getNativeRank`). The deploy no longer cancels runs that are in progress (JEG-495).

## Queued branches (pushed to GitHub as backups; land to main in this order)

1. `fe/targets-ddf`: Trade targets on DDF (JEG-455), with tier following the ranking series everywhere through the `tierFor` helper (JEG-456 part 2), the "◐ 1 source" marker, and `missingReasons`. Its broken-build test "waiver rule removed" needs a simulated chart 0, because JEG-482 data has no zeros.
2. `fe/values-expand`: Player values restorations (JEG-483): expand chart and table, Reset zoom, filter chips. After rebasing on (1), use its `tierFor` instead of this branch's Player-values-only tier code.
3. `fe/manifesto`: the Manifesto tab (JEG-494), first in the nav. The landing tab stays Trade targets.
4. `fe/rank-align`: CSS fix. The hidden engine page has a global `.rank {display:flex}`, which broke the "#" column. Scoped to `.v2-vtable` as `table-cell`.

For each branch, rebase on main, re-run the v2 render suites plus `test_launch_front_door` and `test_ddf_composite_value`, push, then wait for the first successful "Deploy dashboard" run that contains it.

## Next work (contract tickets)

- JEG-506: the contract test, built first per Jeremy.
- Then JEG-505 (Compare headline: two questions plus confidence; Low below a 5% margin), JEG-503 (chart break lines, whole-range drag, legend toggles), JEG-504 (market average), JEG-498 (Customize on every page; Edit league primary), JEG-500 (expand and collapse everywhere), JEG-501 (ⓘ on hover), and JEG-510 (rename "as published" to "Trade charts (rescaled)").
- These wait on the back end: JEG-497 (three DDF versions; fields `ddf_value_charts` / `ddf_value_projections` / `ddfVersions`), JEG-502 (full NFL universe in search), JEG-499 (re-anchor, on hold), and JEG-508 (source-neutral pipeline).

## Gotchas learned

- Test HTTP servers need a bigger backlog (`request_queue_size = 128`) when two pages load at once.
- The engine guard `defaultGroupedSources` must survive view switches; the back end fixed this in #438. Run `test_ddf_composite_value` before pushing v2 defaults.
- Deploys: wait for the first *successful* run that contains your commit. Bot commits land often.
- GitHub Pages sometimes resets connections. An empty curl result is not proof that a file is missing; retry it.
- The back-end session coordinates through cross-session messages. On the Mac, coordinate through Linear comments if that channel isn't available.
