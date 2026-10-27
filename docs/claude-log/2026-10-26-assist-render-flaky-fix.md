## 2026-10-26 - JEG-1089 (assist round-trip render test flaked on the name-only link)

Contract: find why `tests/test_v2_assist_render.py::test_copy_paste_round_trip_links_and_footer` failed about 3 runs in 4 on the name-only find-trade link, and make it deterministic without a longer sleep, a looser assertion or a skip.

### Verified (check named)
- Root cause. A temporary probe in `pullMine` (finder.js, removed) logged every pull on the failing page: the first pull (about 250 ms, `start()`) runs before the link is applied; a second pull with `reason: "other-tab"` arrived at about 860-1005 ms, after `setSides` had set `mine=[Gibbs]`, and replaced it with the saved roster `[Gibbs, Puka]`. The failing assertion printed exactly that (`mine: ['2227','1370']`, note "your roster 1 player").
- Source of the event: the test kept every page in one Chromium context, so all pages shared localStorage. The still-open earlier page (the one that reopened the link Copy wrote) saved its workspace about a second late, which fires `storage` in the new page (workspace.js `reloadFromStorage` -> `notify("other-tab")` -> finder.js `pullMine`). Whether it landed before or after the link applied decided pass or fail.
- Fix: `open_page` in the test now gives each page its own browser context (own localStorage, clipboard permission granted per context), as every real visitor has. No assertion changed, no wait added.
- Counts and mutation guards: see the PR description (10 runs before and after in two font setups; `test_guard_fails_on_broken_builds` runs all 7 mutations).

### Claimed, not confirmed
- App side, not changed: the page does what it was built to do (a second tab's save wins, JEG-1021). Two real-use cases remain: a user with another DDF tab saving within about a second of opening a shared link can see that tab's roster replace the link's, and `finder.ui.setSides` does not push the link's roster to the shared store, so any later pull reverts it. Not fixed here because a minimal change does not make last-writer-wins deterministic and it is a product choice for Jeremy; to be raised as a separate ticket.
