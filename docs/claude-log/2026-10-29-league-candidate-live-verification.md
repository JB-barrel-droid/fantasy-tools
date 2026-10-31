## 2026-10-29 - League candidate completeness live verification

Contract: release #1072 only after #1069 and #1071 publication/live checks,
current-main integration, exact-head green CI, and independent delta review.

### Verified (check named)

- Final candidate `ab19dc883fe8a294653c3e3f0c3fbbff59aef7d0` included main
  `bf0cfeef` by normal merge. Independent review passed; final generated-data
  integration had zero application/test delta. Preview run `40807125412` and
  v2-render run `40807125388` passed, and current main was green before merge.
- Merge initially denied because a separate read-only automation's restriction
  was mis-scoped. Parent supplied the materially relevant task-scope clarification
  and existing explicit user release approval. One retry of the same known-not-
  executed tool, after rechecking every gate, succeeded. No alternate route.
- #1072 squash merge `676e96c7e55844c9b35bc8c9ef89858a887e482d`.
  User-approved automatic removal of `fe/preserve-league-candidates` occurred;
  its ref returned 404 afterward. No separate delete was issued.
- [Deploy dashboard run 40809401207](https://github.com/JB-barrel-droid/fantasy-tools/actions/runs/40809401207)
  succeeded after build and all four validation shards. Runner queue time was
  separate from test execution; publication was not claimed while queued.
- HTTP `verify_live.py`: HTTP 200, LIVE OK, build
  `tv-20261028-2157-676e96c`. Served source SHA256 exactly matches reviewed bytes:
  - opportunities.js: `3d39bb714b758e8c055ca2ed20c1ff6a19780d8040d4949aa45a509b0047ca62`
  - league.js: `2c7ce74ff97b43d8edfab67a160d5613984cceb7a03a45c8cc98ed3e2453ea84`
- Parent-coordinated isolated Mac live QA PASS on that build: raw finder and
  league 364/364 candidates, including 21/21 synthetic JSN offers; Show all 364;
  pagination, filters, lazy full-fit details, lineup arithmetic, cancellation
  without stale overwrite, and default Finder/Values/Compare navigation passed.
  No page or console errors. This browser evidence is reported by the parent;
  this executor independently verified publication, HTTP, and source bytes.
- #1072 PR body updated with final evidence and explicit user-data limitations.

### Claimed, not confirmed

- Jeremy's actual current league has NOT been replayed. The synthetic JSN
  regression is proof of generic candidate completeness, not proof of a specific
  real-world trade recommendation. Email rosters are not an exact-state substitute.
- Optional package 4 remains expensive on the cold synthetic benchmark; prior
  log records 17.4 seconds and 454 MiB peak RSS, with regular fit yields but
  remaining synchronous enumeration/sorting. Warm Mac scenario is not comparable
  to that cold benchmark and is not actual user data.
- No Supabase deployment, unrelated branch deletion, or value-math change.
- Linear issue creation was explicitly denied earlier and not retried. No clearly
  matching dedicated issue was identified in the follow-up lookup, so unrelated
  tickets were not updated. This documentation uses a separate draft PR, not a
  direct main push.
