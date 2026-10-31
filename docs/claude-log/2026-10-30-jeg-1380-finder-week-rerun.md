## 2026-10-30 - Find a trade re-runs on a week change (JEG-1380, correction for #1012 / JEG-1178)

Finding (P2, Codex bot on #1012, confirmed in the post-merge review): after a week change from the selector or a
`wk=` link, Find a trade kept the previous week's listed trades, because neither path sent
`ddf:league-settings-changed`. Values elsewhere on the page were correct.

Change: `app/v2/v2.js` sends `announceLeagueChange("week")` from the week selector's change handler, and from
`applyLinkLeague` when only the link's week moved (other link settings already announce `link`).
`app/v2/finder.js` names the week in its note ("Updated for Week N."). No value math changes.

### Verified (check named)

- `node --check` on both files.
- `tests/test_jeg1380_finder_week_render.py` fails before the fix: v2-render run 41006157745 at 18930df3 (the
  test-only commit plus the JEG-1382 and JEG-1383 ports), job 123901976610, 15 errors. The first is "selector to
  Week 7: listed edge 7.413 is not Week 7's -13.020". Passing-after is the dispatched v2-render run on the fix
  commit, named on JEG-1380.

### Claimed, not confirmed

- The cloud session can't run Chromium, so the render result is CI's alone.
- No overlap with #1193's v2.js lines (5187-5540, ~6300, 6610-6650), read from that PR's diff hunks; JEG-1137
  slice 2b's lines are not known yet.
