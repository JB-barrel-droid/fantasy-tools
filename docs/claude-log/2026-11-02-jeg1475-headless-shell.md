## 2026-11-02 - JEG-1475 headless shell

Contract: build one draft PR from origin/main in an isolated worktree. Resolve
CHROMIUM_PATH, then installed Playwright chrome-headless-shell, then None;
never discover a desktop Chrome app. Leave HANDOFF.md and shared checkout alone.

### Verified (check named)
- Disk check: 25,225,612 KiB free, above 3,670,016 KiB minimum.
- `python3 -m unittest tests.test_chromium_resolver`: original resolver failed
  returning `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`;
  corrected resolver passes all three cases (temporary HOME/fake paths,
  explicit override/default, active registry priority).
- Resolver plus validate-shard, preview/Pages, deploy-gate and CI-speedup guards:
  89 tests passed. New resolver suite is in test-unit-modules.
- CI inspection: preview/Pages install playwright==1.49.1 and Chromium, set
  RENDER_TESTS_REQUIRED=1, and leave CHROMIUM_PATH unset. Workflows unchanged.
- _dist_server already delegates to _render_env; synthetic and NODE_CHROMIUM
  now use that same resolver. Registry paths come from the active driver;
  Mac cache fallback has no pinned revision.

- `env -u CHROMIUM_PATH RENDER_TESTS_REQUIRED=1 <venv-python> -m unittest
  tests.test_v2_contract_render.ContractRenderTest.test_every_live_contract_line`:
  passed (one test), no skips. Launched via Popen(start_new_session=True),
  test PGID 70770; Playwright created browser PGID 71077. No signals sent.
- `ps -axo pid,ppid,pgid,comm` restricted to the test PID's descendants:

```text
70770 70766 70770 /opt/homebrew/Cellar/python@3.12/3.12.12_2/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python
71063 70770 70770 /Users/botcomp/code/fantasy-tools/.venv/lib/python3.12/site-packages/playwright/driver/node
71077 71063 71077 /Users/botcomp/Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell
71078 71077 71077 /Users/botcomp/Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell
71079 71077 71077 /Users/botcomp/Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell
71188 71077 71077 /Users/botcomp/Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell
```

  All browser descendants are chrome-headless-shell; no Google Chrome.app.

### Claimed, not confirmed
- Full test-core and make validate deferred to CI (five core shards have
  documented multi-minute modules); no claim of local full-gate success.
- Independent review is pending the draft PR’s exact-head green CI.

## 2026-11-02 - JEG-1475 shard 3 saved-team keyboard test (Mac, Claude)

CI preview-shard (3) failed twice on head `fbb017a1`:
`test_keyboard_mobile_and_overlap_guard` line 416, `'' != 'beta'`, after the
test typed `s s Tab` into the closed native saved-team select.

### Verified (check named)
- CI pins `playwright==1.49.1`, so with this PR the Linux render tests launch
  `chromium_headless_shell-1148` (Chromium 131). Before this PR they launched
  full Chromium 1148, and shard 3 passed with the same type-ahead keys.
- On the Mac, an event probe on headless shell 1243 (Chromium 153) and on
  headless shell 1148 (Chromium 131) fires keydown, keypress, input and change
  for each `s` at 1366, 390 and 320 px, ending on `beta`, with no dialog. The
  failure only shows on Linux headless shell. Chromium version is not the cause.
- Chromium source: type-ahead (`HTMLSelectElement::TypeAheadFind`,
  `TypeAhead::HandleEvent`) has no platform branch. The closed-select arrow
  keys do: `MenuListSelectType` moves the selection on arrow keys unless
  `LayoutTheme::PopsMenuByArrowKeys()` is true (macOS, where they open the menu).
  The original JEG-1219 test used Home/ArrowDown on Linux, and #1233 switched
  it to type-ahead because arrows were inert on the Mac.
- Fix (test harness only): each platform drives the select with its own
  native keyboard model. macOS uses type-ahead; Linux and Windows use
  Home/ArrowDown. Every assertion is unchanged. The two selection assertions
  now carry a key, change and dialog log in the failure message.
- `RENDER_TESTS_REQUIRED=1 .venv/bin/python -m unittest
  tests.test_v2_finder_saved_team tests.test_v2_finder_saved_team_render`:
  11 tests OK on the Mac (headless shell 1243).

### Claimed, not confirmed
- The Linux-only mechanism behind the empty type-ahead selection is not
  proven. The Mac can't run Linux headless shell. The Linux arrow path is
  checked only by CI on this head.
