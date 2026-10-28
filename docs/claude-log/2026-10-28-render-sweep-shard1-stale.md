## 2026-10-28 - Render sweep shard 1: stale render tests and three unwired modules (part of JEG-1117)

Contract: diagnose the render-sweep failures on main (customize cleanup D3, divergence chip guard, writing routes
link guard, mobile phase 1) and wire the three render modules that are in no Makefile list; fix stale tests as local
commits, leave presentation choices to Jeremy. Branch `fix/sweep-shard1-a`, not pushed.

### Verified (check named)
- `tests.test_render_sweep_coverage`: green after the Makefile edit (it listed chart_fullscreen, consistency and
  paste_only as unwired before). `tests.test_render_sweep_shards` still fails only on league_oppanel, league_parsed,
  league_top10 and find_split, which open PR branch `banana/jeg-1135-render-sweep` wires.
- D3 root cause: `git log -S'sameAs'` and the DDF_VERSIONS diff of 679fa54e (JEG-1073) show ddf_value_charts hidden
  from every picker after ee35f274 (the test's last edit); the dialog row the test clicks no longer exists.
- Divergence guard root cause: a68b106c (#916) `resolutionHref` returns "" for a ticket id, so the fixture's JEG-123
  never links; new patch anchor and every other PATCHES anchor occur in app/v2/v2.js (count script).
- Writing routes: the new anchor occurs exactly once in a fresh `build_v2_page.build` of dist/v2/index.html; 57f1c1b2
  (JEG-977) removed the arrow.
- Mobile phase 1 (b): `git show <rev>:dist/assets/reference-freshness.json` at b4c74bf6 (FantasyPros "reviewed" per the
  JEG-1048 log) and at HEAD (all four default charts ok or in range) shows the data change; `defaultShown()` in v2.js
  shows only the four trade charts by default.
- Mutation anchors in test_v2_chart_fullscreen_render, test_v2_consistency_render and test_v2_paste_only_render all
  match current app/v2 sources (count script); none of the three clicks a `.v2-tab`.

### Claimed, not confirmed
- None of the edited render tests was run: Chromium/Playwright cannot be installed here. Each fix is reasoned from code.
- The three newly wired modules are expected green on main (written 2026-10-26 to 2026-10-28 against the current nav,
  hash navigation only). Runtimes guessed at 1 to 4 minutes each.
- Mobile phase 1 (a), 28 tap targets under 44 px at 390x844: not fixed. Known element: the footer link "Connect the
  tool" (`#v2AssistLine a.v2-link`, 4ae3b8a4, JEG-1026), an inline anchor where `.v2-link { min-height: 44px }` has no
  effect; likely also the inline `a.v2-link` in the Find a trade intros (9cffc5cb, JEG-1093). The full list needs a
  render run (the CI log download is blocked here). Presentation choice for Jeremy.
- The mutation "Reviewed chip loses its hit area" is caught today only because (a) makes the tap check fail anyway:
  since #916 no chip is a link in the published data. It needs a pinned public resolution URL once (a) is fixed.

### Follow-up: 4(a) hit area (coordinator, from the CI log: the 28 messages are the footer link repeated)
- app/v2/v2.css: on `(max-width: 767px), (pointer: coarse)`, the footer link `#v2AssistLine a.v2-link` and the two Find a
  trade intro links (`#v2FindTrade` / `#v2FindLeague .v2-title p a.v2-link`, also inline `a.v2-link`, so the same failure
  where the check looks) get the JEG-1048 chip pattern (b4c74bf6): `position: relative` plus a centred empty 44 x 44
  `::after`. No visual change; follows the 44 x 44 rule in docs/v2-design-notes.md.
- Verified (comment-stripped brace count balanced in v2.css). Claimed, not confirmed: the tap check passes and the overlap
  guard (test_v2_phone_tap_targets_render) finds nothing. Reasoned from layout only: the ::after reaches 14.5 px past the
  footer link, inside the footer's 16 px / 28 px padding, with no other control in the footer. The find pages are not in
  the overlap guard's tab list. Not rendered (no Chromium).

### Follow-up: shard 1 after the hit-area fix (render run on the scratch copy, every module)
- At 320 px the footer link still failed (260x34): it wrapped to two lines, and a split inline link's box spans both lines,
  so its centre lands on the text before it. The links are inline-block on phones with min-height 0 (f01b40da).
- A landscape phone (844x390, coarse pointer) had 24 px Edit league and Dismiss on the settings strip (JEG-1084 kept them
  slim above 767 px). They are 44 px on any coarse pointer; desktop keeps the slim line. Pick logged.
- test_v2_finder_chips_render read the league screen's copy of each roster row (league.js draws `li.v2-find-row` too,
  later in the page), so the "missing average shown as 0" mutation of finder.js went unseen (probe showed DeVonta Smith
  still "no value" under the mutation). The check reads `#v2FindTrade`'s rows.
- "Reviewed chip loses its hit area" now serves pinned data with one linked Reviewed chip (FantasyPros, a public
  example.com page) and checks first that the chip is a visible link and that the unbroken page passes the tap check.
- Open, not fixed here: test_v2_divergence_chip_render no longer guards `noLink` (no chip in its fixture links since
  #916); a reviewed source with a public https resolution page would bring back the "link inside the header button" case.

### Reviewed chip pin found a clipped chip (JEG-1193)

Once a linked Reviewed chip was pinned, the baseline tap check failed on Player values, Trade targets and Compare a trade at 390 and 320 px. The chip in the one-line context strip (#v2ShowingLegend, JEG-1119) sits past the strip's `overflow: hidden` edge, and its 44 px hit area is clipped with it (run 40633812560). This is a product regression from JEG-1119, filed as JEG-1193 for Jeremy to decide. The tap check now skips that one chip, pointing to JEG-1193. The "Reviewed chip loses its hit area" mutation now removes the Targets list chip's hit area, which is the linked chip that stays on screen on a phone. The reviewedlink check counts chips outside the strip.
