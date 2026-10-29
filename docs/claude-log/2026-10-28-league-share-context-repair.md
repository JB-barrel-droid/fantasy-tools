## 2026-10-28 - Complete value context in finder and league links

Contract: repair independent P2 review block on release #1062 at `058595705bb88fe3e74977d541a07c51126d6e39`.
No added agents, main merge, deployment, source PR closure or ticket completion.

### Verified (check named)

- Pre-fix browser regression failed all four finder/league × custom/default sender
  cases (36.215s), because no complete-value-context marker was shared. The custom
  sender used the existing basis/override reader to set FantasyCalc and an override.
- New shared `DDFOverrides.shareLink` appends basis/ov and `valuecontext=1`, retaining
  the workspace codec's raw escaping/separators. Signed adjustments are URI-escaped.
  Reuses the 1800-character override budget; oversized overrides are omitted with
  the existing Export explanation. Existing oversized-roster fallback is retained.
- Finder applies basis/overrides before roster resolution/search. Accepted league
  imports apply them after league settings and before workspace replacement.
- Complete links replace in-memory basis/player overrides; defaults clear custom
  reader values. Session replay clears saved values before restoring linked ones.
  Saved local preferences are not overwritten. Legacy markerless behavior is retained.
- Fixture correction: the initial 999 override is clamped by existing normalization
  to 100. Changed the new regression fixture to valid 60 (saved-reader 77); production
  limits/assertions were not changed. An intermediate encoder reserialized the raw
  workspace query; replaced that before final validation with append-only encoding.
- `RENDER_TESTS_REQUIRED=1 CHROMIUM_PATH=/usr/bin/chromium python3 -m unittest tests.test_jeg1213_acceptance_render tests.test_v2_share_links tests.test_v2_share_links_render.ShareLinksRenderTest.test_finder_and_compare_share_links`: 13 PASS, no skips, 126.835s. Covers fresh/saved reader, default/custom sender, both routes, navigation replay, malformed/oversized links and signed adjustment escaping.
- Existing Override share/legacy/budget render regressions: 3 PASS, no skips, 80.426s.
- `node --check` on touched JS and `git diff --check`: PASS.

### Claimed, not confirmed

- Parent owns one independent delta review and required CI on the new release head.
- Pre-existing default-position-share precedence was explicitly excluded from this
  repair by parent; no share-weight or engine methodology change was made.
- Parent reports #1056/JEG-1170 live prerequisite complete: published
  `904d07ae99320dc5d47ed3d38499af891d6c2dcf` at 18:18:30 UTC, Mac live QA passed,
  build `tv-20261028-1235-904d07a` matches 12:35 -0500 / 17:35 UTC commit time.
  All shard/artifact/render gates passed, runtime 17m05s versus 40m15s baseline;
  separate queue time 25m36s. JEG-1170 marked Done. These production observations
  were supplied by parent, not independently repeated in this integration lane.
