## 2026-10-26 - JEG-894 share links (Copy link beside the verdict; a finder search link)

Contract: move "Copy link to this trade" out of the "Difference by source & method" table header and next to the
verdict (desktop) and into the phone sticky bar, and give Find a trade a "Copy link to this search" that encodes both
rosters, the package size, the two lineup ticks and the league settings and runs the search when opened.

Author: an OpenRouter deepseek-v4.1-flash run (T2/T3). **Untrusted until a Claude T1 review** re-reads the diff, runs
`make validate` and the render tests below, and merges.

### Verified (check named)

- `python -m unittest tests.test_v2_share_links` — 2 tests OK. `encodeFinderHash` / `decodeFinderHash` round trip the
  ids, the size and the ticks; a 2 x 16-man link plus the league tail is **231 chars** (asserted under 2000); each side
  caps at 40 ids with the extras counted; an id on both sides stays on "mine"; an id the engine no longer prices is
  skipped and counted; `size` is 2/3/4 (else 2); `km`/`kt` default on. The same module's
  `test_checks_fail_on_broken_builds` fails on five mutations of `finder.js` (theirs not encoded, the cap dropped, the
  cross-side rule dropped, a bad size accepted, unknown ids kept).
- `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_share_links_render` — 2 tests OK.
  `test_finder_and_compare_share_links`: a copied finder link in a **fresh browser context (cleared storage)** restores
  both rosters (names and positions, compared as strings) and the same "N trades found"; the size select reads 3; the
  copied Compare link is `location.href`, and a fresh context opens the same give / receive and the same verdict title
  and text; the desktop button is inside `.v2-cverdict-head`; the phone button is inside `#v2CVerdictBarWrap` and is
  44 px tall; the verdict card's bottom is inside 1366x768 with no horizontal overflow.
  `test_guard_fails_on_broken_builds` fails on four mutations (encoder drops `theirs`; decoder ignores `size`; the
  pending-link run removed from `setSides`; the `applyHash` call removed from `readTradeHash`).
- `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_share_render tests.test_v2_assist_render` — 4 tests OK, so
  the Compare link format is unchanged (old `give=&get=` links and the legacy `bench=` link still apply) and the
  DDFAssist `#find-trade?mine=..&theirs=..` links (names, unresolved names, `view=` reroute) still read.
- `node --check app/v2/finder.js app/v2/v2.js` — syntax OK. `python -m unittest tests.test_v2_share_links` green.
- The two guard anchors the other render tests pin are intact in `v2.js`: the DDFAssist `applyLink(query); return;`
  block (test_v2_assist_render) and `readTradeHash();   // may set a status` (test_v2_share_render).

### Verified, continued (regression surfaces)

- `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_waterfall_render tests.test_v2_contract_render` — 13 tests
  OK. The verdict-fit fold check passes at 1366x768 (verdict bottom 649.4, and 722.2 on the seeded win copy) with the
  new verdict header row, and the contract test's phone `#v2CVerdictBar` rect check (ct06) and
  `shown($('v2CShare'))` / example snapshots pass.
- `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_overrides_basis_render tests.test_v2_finder_render` — the
  finder tests pass; the overrides module reports 3 failures + 2 errors, all in the Overrides basis / indicator area
  (`getBasis().isDefault`, a disabled `#v2OvW-espn` weight slider, the picker radiogroup, the league-row indicator) and
  none in the share-link path. **Pre-existing**: `test_picker_is_a_named_radiogroup_with_arrow_keys_and_blend_sliders_are_named`
  reproduces the same failure on the clean stashed tree (checked 2026-10-26). The other four were not individually
  re-run on a clean tree.

### Claimed, not confirmed

- The other four `test_v2_overrides_basis_render` failures are claimed pre-existing from their subject matter (they
  never touch `#v2CShare`), not each reproduced on a clean tree.
- `make validate` was not run (no value math changed, so no 12-combo sweep is expected; the deploy gate still has to
  be read by the merging session).
- No live check: nothing was pushed, deployed or published.

### Design notes (deviations from the build spec, and why)

- **`leagueLinkParts()` already existed** as the extracted function (it is what `tradeHash()` appends). Nothing was
  extracted and `tradeHash()` is byte-identical, so no separate byte-identity test was added.
- **The finder link is read through the shared link path.** Since JEG-1026, `readTradeHash()` hands `#find-trade?mine=..`
  to `ddf-assist.js`, which sets both rosters and the league settings, and `test_v2_assist_render`'s guard pins that
  call. So `readTradeHash()` now calls `TradeValueFinder.applyHash(params)` **before** that branch: `applyHash` sets the
  package size and the two lineup ticks and raises a pending flag, and `api.ui.setSides` runs the search once the
  rosters are in. `applyHash` deliberately does not set the rosters itself, so the assist guard still fails when its
  `applyLink` line is removed. The spec's "readTradeHash returns unless base is `#compare-trade`" premise is out of date.
- **Unknown ids** are skipped and counted by `decodeFinderHash(query, knownKeys)`; the page reports unresolved ids
  through DDFAssist's existing "Not matched, left out" line rather than a second message.
- **The empty-side case** keeps the button enabled and answers the click with the reason ("Add at least one player to
  <side> to make a link.") instead of disabling it, so the reason is visible and testable.
- **Q7 (a privacy line) was not added** (Jeremy's instruction).
- The phone bar was restructured minimally: `#v2CVerdictBarWrap` (fixed, flex) holds the go button `#v2CVerdictBar`
  (id and behaviour unchanged, so `ct06` still finds it) and the copy button `#v2CShare2`.

## T1 review and main merge-in (Ba-Nana merge wave, 2026-10-27)

- Reviewed the diff against main: scope matches JEG-894 (finder search link, copy link on the verdict and the phone bar),
  no value math, bench or seat code touched. No code fixes needed.
- Merged `origin/main` (51b7e528) with no conflicts; main brought only data and status files, no app or test changes.

Verified (check named):
- `gh run view 40456070192` / `40456072386`: main at 51b7e528 itself fails `test_rank_guard.test_indexed_order_equals_native_order`
  (make validate) and `test_v2_waterfall_render` (`player_key` undefined), the same failures as this PR's `preview` and
  `v2-render` after the merge-in.
- The pre-merge PR head 84560c94 passed `preview` and `v2-render` in CI.

Claimed, not confirmed:
- `test_v2_share_links_render` and `test_v2_share_render` failed locally (sender found 0 trades); CI stops at the
  waterfall step before it reaches them, so they are unverified on the merged head. Main brought no app changes, so the
  local failures are most likely the local environment or data.
