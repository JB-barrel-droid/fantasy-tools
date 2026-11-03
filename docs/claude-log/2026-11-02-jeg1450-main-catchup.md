## 2026-11-02 - JEG-1450 main catch-up

Contract: merge current main into PR #1255 to receive JEG-1477, preserving both histories and leaving stacked PR #1260 untouched.

### Verified (check named)
- GitHub settings-render run 41400118110, job 125129929827: the sole failure is test_focus_ring_is_three_pixels, 0px != 3px, matching JEG-1477 (#1282, 6d8375e7).
- Merged origin/main 4911da5ef50f0d88e5fcaf3de84eb47db2089cd7 into exact PR head 3e8225121dd88116450456e4f6b6c9800973ac0b with no conflicts. HANDOFF.md has no merge delta.
- Baseline registry and three workflow modules: 78 tests pass.
- actionlint with shellcheck disabled passes for preview/pages/full-suite/render-sweep. Default shellcheck reports inherited SC2155 warnings in preview/pages; no workflow change made for those warnings.
- Live pgrep subsequently found another make validate (PID 11947); full local gate deferred to CI under the standing concurrency rule.

### Claimed, not confirmed
- Settings, explainer and contract render tests running at commit time; results will be reported on the ticket.
- Exact pushed-head CI and independent catch-up delta review remain required. This job does not review its own merge or change #1260.
