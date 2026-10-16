## 2026-10-12 - JEG-543 Research tab framework

- Added the Research tab (after How values work), route `#research` (index) and `#research/<slug>` (post).
- Posts: one file per post in `app/v2/research/<slug>.html`, first line `<!--post {json} -->` with title, summary, date, `published`. `pipelines/build_v2_page.py` skips drafts (`published` not true), so a draft never reaches the page. Zero posts are published: the five posts in the ticket are drafted by Claude and need Jeremy's Google Doc approval first. The index shows "No posts are published yet." until then.
- Seven tabs overflowed the 390 px nav by 36 px; mobile tab type is now 13 px with 2 px side padding.
- Contract: RS-01..03 added to `docs/feature-contract.md` (RS-01 pinned by the new test; RS-02/03 are process/future rules).
- Verified: `tests/test_v2_research_render.py` (index lists exactly the published posts, each post routes, draft route falls back to the index, no overflow at 390, ~70 ch column; negative-tested with draft published, post dropped, route removed) and `tests/test_v2_manifesto_render.py`.
- Claimed, not checked: no live widget exists yet, so RS-03 is untested.
