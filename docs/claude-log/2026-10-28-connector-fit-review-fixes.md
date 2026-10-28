## 2026-10-28 — Connector fit review fixes (JEG-1115)

Contract: fix the two reproduced #1041 review defects: real fit replies exceed
their byte budgets, and duplicate opponent display names overwrite roster
identity. Parent authorized this follow-up branch/draft only; no merge or deploy.

### Verified (check named)

- #1041 merged externally at unchanged head `fd870dc9` as main `1bd85f76`.
  `git diff` confirmed neither fix was included. Work moved to
  `be/jeg-1115-fit-review-fixes`, which incorporates main `e931b84a`. The only newer main change since
  reviewed `79b9b435` is the generated fidelity-pulse report; runtime is unchanged.
- Correction to the original size claim: the old `sizeCharts` fixture omitted
  `bench_share` and listed only ESPN, so the fit context was null. The original
  independent probe measured 9,700 / 33,321 bytes for pair default / limit 50
  with actual chart sources and bench weights. The strengthened fixture now
  requires nonempty fit labels and full reasons for every returned candidate.
- `tests/node/mcp_remote_check.mjs` passes with 6,128 / 16,155 / 7,070 / 10,853
  UTF-8 bytes for pair default / 50 and league default / 100. Caps remain
  6,700 / 17,000 / 8,000 / 11,500. Limits are upper bounds (Jeremy, Oct 26);
  the actual ranked prefixes contain 5 / 27 / 4 / 11 candidates. Text shows
  at most five, counts agree, all reasons stay intact, and the entire selected
  package, edge total and projected lineup are preserved. Unicode and an
  irreducibly oversized envelope are covered.
- The same check compares duplicate-name roster fits across adding, renaming
  and reordering opponents, and requires a package containing two distinct
  same-name opponents. Internal input-index identity survives package selection;
  `opponent_index` identifies candidates, package offers and `perOpponent` rows.
  The original independent probe now finds zero changed fits (previously 20).
- Negative probes in a separate checkout: disabling prefix trimming fails the
  size case; replacing the internal opponent index with the display name fails
  the duplicate-name regression. No assertions were relaxed to hide a failure.
  Exact row-count assertions were replaced because the approved limit is an
  upper bound, while full-fit coverage and tighter byte caps were added.
- Local integration of #1024 `179288bf` and #1032 `a147b457` passes the remote
  check, `mcp_week_check.mjs`, and `get_values_week_check.mjs` using the built
  main artifacts. Integrated byte sizes: 6,291 / 16,318 / 7,233 / 11,016.
  #1032 overlaps these files: keep one `TEXT_ROWS`/`tradeLines` helper, the
  bounded render blocks and the new fit-producing assertions when merging.
- A separate integration probe appends oversized week metadata through the
  real #1024 `withWeek` path, confirms the decorated result exceeds 28KB, then
  confirms RPC returns an error under 300 bytes for both tools. Removing the
  final RPC size check makes that probe fail. Direct helper tests pin the exact
  UTF-8 boundary for all four budgets.
- `python3 -m unittest tests.test_mcp_remote tests.test_ddf_state
  tests.test_mcp_finder_loader tests.test_llm_surfaces tests.test_v2_finder_fit
  tests.test_edge_functions_parse`: 20 tests run, 19 pass, one Deno-unavailable skip.
- Independent reviewer PASS on runtime/test commit
  `d10ae660e4414c06da1223f11d75fc5f41c7c76b`: no blocking findings; reviewer reran
  remote, batch, original defect and integrated wire-size probes independently.
- The connected GitHub app created behavior commit `c2d03262dfbeb1466a742524d5aca51ba97d585b`
  on main `79b9b435`; its entire tree exactly matches reviewed local `d10ae660`.
  The local CLI credential is invalid, so publication uses the authorized app.
  The build stamp points to that published behavior commit.

- Full `make validate` exited 0 in the isolated checkout at `d10ae660` (the
  published behavior tree): build, all test-core suites, strict engine/reference
  comparison and all integration suites passed. Used `RENDER_TESTS_REQUIRED=1`,
  installed system Chromium via temporary Playwright paths, and a writable npm
  cache. This was one sequential gate run; generated output stayed outside the
  author checkout. Later changes are documentation and the build stamp only.

### Claimed, not confirmed

- Current-head hosted CI and live deployment of this follow-up are not verified.
  The 15:11 Linear comment reports get-values v9 / mcp v13 deployment of #1041;
  this session did not perform or independently verify that external deployment.
- Parent owns serial release: #1024, #1032, then the reconciled follow-up.
  Fresh explicit approval is still required for Supabase deployment. No schema,
  data, branch deletion, force-push, direct-main push or production write occurred.
