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
