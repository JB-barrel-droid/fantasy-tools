## 2026-11-06 - Private /next/ preview of the redesigned pages (part of JEG-1534)

Contract: publish the redesign wireframes (ddf-handoff `03-built-site`) from the same Pages build at
`/fantasy-tools/next/`, noindex and unlinked, without changing any live route.

History: first opened as PR #1335. Its review found a screen-recorder avatar in some how-to
screenshots, nine of them unused. Jeremy, 2026-11-06: "Clean it and replace the PR branch." #1335 was
closed and its branch deleted; this branch starts again from `main` and never contains those images.

Changes: `app/next/` (verbatim copy of `03-built-site` minus `assets/doc*`, `assets/mascot-trust-me`,
`link-fixture.html`; the nine unused how-to images removed at the source, and the four Players slides
replaced by `-clean.jpg` copies with the avatar and account corner blanked); `pipelines/build_next_preview.py`
(copy to `dist/next/` without `README.md`, add robots noindex and fail the build if a page has no `<head>`,
site icon, `?v=<build tag>` on own js/css and, through a small injected script, on the pages' relative
`.json`/`.md` fetches; idempotent); one call in `sync_dashboard_artifacts.py`; `dist/next/` gitignored;
`tests/test_next_preview.py` wired into test-core and shard 5. The methodology post stays in
`learn/posts.json` with `"draft": true` and shows a "Draft" tag in the Learn list, post header and pager
(Jeremy, 2026-11-06: keep it, marked as a draft). Learn's list is its only index; there is no feed.

### Verified (check named)
- `python3 -m unittest tests.test_next_preview`: 8 tests OK, including a walk of every real
  `app/next` page through the build (noindex once, data-version script once, no root-absolute
  `src`/`href`, every own js/css versioned, rebuild idempotent) and no `README.md` in the output.
- `make sync` (Python 3.12) builds `dist/next/` (70 files) with the build tag stamped.
- `diff -rq` of a `main` `make sync` against this branch: only `next/` added; other differing
  files differ only in build tag, short SHA, timestamps and the value-logic commit subject.
- Playwright (Chrome channel) against a Pages-like server (`/fantasy-tools/` prefix, 404.html):
  16 pages x 1440/390 x no league/`#s=` league = 64 views, 0 console errors, 0 page errors,
  0 failed same-host requests, 0 horizontal overflow, noindex on every page; same-host link targets all 200.
- Every image in `app/next` (11 how-to JPGs) viewed: no avatar.

### Claimed, not confirmed
- The CI rendered gate (`tests/rendered_gate/gate.mjs`) and full `make validate` were not run locally.
- GitHub Pages serves `/next/` the same as the local Pages-like server (not deployed).
- The screenshots stay in the closed #1335 head commit on GitHub; this keeps them off `main` and Pages only.
