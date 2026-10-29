## 2026-10-29 - JEG-1225 / JEG-1288 shared-link value basis and overrides in get-values (PR #1124)

Contract: slices 4a and 4b of the JEG-1224 plan (docs/qa/jeg-1224/README.md, #1080), for Jeremy's pick B: one shared reader of a share link's `basis=`/`ov=` for the site and get-values, and get-values pricing under them with site parity in all three scorings. Then correction JEG-1288 from the independent review: answer only under the exact context asked for. No new value math, no default or ranking change, no deploy, no merge. Slice 4c (MCP pass-through) is JEG-1343.

### Verified (check named)

- 4a: `app/v2/ddf-value-link.js` holds the link format, lifted from overrides.js. overrides.js delegates to it with unchanged behaviour: `tests/node/ddf_value_link_check.cjs` (parse, format, round trips, frozen `z:` bytes, overrides.js booted in a vm with applyLink, shareParams and shareLink), run by `tests.test_ddf_value_link`.
- 4b: get-values prices under `basis`/`ov` exactly as the parity runner does, in standard, half PPR and PPR (single source; blend with absolute and adjustment overrides and an unpriced key; our methodology with an override). The cache key carries the context. The site's share link read back by get-values matches. canonicalBasis matches curve-widget.js on 2,000+ fuzzed bases. All of this is `tests/node/get_values_value_context_check.mjs`, run by `tests.test_get_values_value_context`.
- JEG-1288 1, unavailable basis. Before, on 66a5f4d with ESPN held, `basis=espn` and `blend:espn.50_fantasycalc.50` both returned 200 (the blend priced FantasyCalc-only). After, on 3d03331, both return 422 `basis_unavailable`, including on a repeat request: check section 8a.
- JEG-1288 2, partly unreadable. `blend:espn.50_nope.50`, `101:58,202:garbage` and `z2:AAABAgJEAQ` went from 200 to 400 `value_context_unreadable` with the reason. The strict reader rejects every listed malformed form, and 2,000 random links the site writes read back the same: ddf_value_link_check strict section, check section 8b.
- JEG-1288 3, size bounds. 10,001 plain and 2,001 packed overrides went from 200 to 413 `value_context_too_large`, and 2,000 still answer. The text bound is refused before the reader is consulted (413, not 503, with the reader removed): check section 8c.
- I reverted each JEG-1288 fix in turn, and all 8 reversions are caught by the two checks above (mutation run in the session, recorded on JEG-1288).
- Restack: merge 66a5f4d put the branch on #1119 at eef6bb9 in place of #1024 (#1119 has since merged). `git merge-tree` on 3d03331 is clean against #1119 and main. The independent re-review confirmed it is clean against #1119's newer head e11420b.
- Existing checks pass on 3d03331: get_values_week_check, get_values_handler_check, mcp_week_check, tests.test_build_v2_page, tests.test_mcp_week. The #1080 harness with its 3-line adaptation (posted on the PR as a diff): 22 cases, 0 harness errors, 0 differ from the record, and 20 of 20 mutations as expected.
- Independent Claude re-review of 3d03331: PASS on code (JEG-1288 comment, 20:19 UTC).
- CI: on 3d03331, preview-build, preview-shard 1, 3 and 4, and v2-render succeeded. #1119 then merged to main, and another Claude thread merged main into this branch (0ba3033, logged in `2026-10-29-jeg-1225-main-merge.md`). On 0ba3033 every check run succeeded: preview, preview-build, preview-shard 1 to 4 and v2-render (read from the check runs).

### Claimed, not confirmed

- `test_endpoint_parity.test_value_context_parity` (the site page against get-values, needs Chromium) is assumed to run in CI's preview shards. It skips locally, and I did not open the shard log to confirm which shard ran it.
- Every module in `make test-unit-modules`, run on its own at bf8dc64 (311 modules, 2,900 tests): 298 passed. The 13 red modules were red the same way on ff6e8c2, before this work. That run predates the restack and the JEG-1288 fixes and was not repeated.
- Review P3s, noted and not changed here:
  - A cached answer or 422 can outlive a source status change by up to the cache and bundle lifetimes (predates this PR).
  - Refusals take slots in the 6-entry answer cache.
  - An equal blend of the four charts with one held collapses to our methodology and answers 200 on three charts, as the site does.
  - `101:58.25` is accepted and rounds to 58.3.
  - A POST `ov` sent as a JSON array is joined into text.
- Deploy order: Pages (publishing `parseOvStrict`) before get-values. A get-values deploy without it gives 503 for every context request (fails safe). get-values and mcp each still need Jeremy's yes naming the function.
