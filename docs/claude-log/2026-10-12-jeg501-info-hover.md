## 2026-10-12 - JEG-501 info buttons open on hover

Contract: every ⓘ (one shared builder, `indexedInfoButton`) opens on hover on mouse pointers with `(hover: hover)`, keeping click, keyboard, touch and Esc.

### Verified (check named)
- `tests.test_v2_targets_render` (new `_hover_checks`): no open before the delay, opens after ~200 ms, stays while the pointer is in the popover, closes after leaving, click on a hover-opened popover pins it, Esc closes. Ran green with RENDER_TESTS_REQUIRED=1.
- Existing click / Enter / Esc / focus-return checks in the same test still pass.

### Claimed, not confirmed
- Touch behaviour is unchanged by construction (hover handlers ignore non-mouse pointerType); no touch emulation run.
