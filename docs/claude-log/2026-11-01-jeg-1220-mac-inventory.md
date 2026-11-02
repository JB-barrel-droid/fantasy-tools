# JEG-1220 Mac inventory refresh

Jeremy requested a current-source spec, cheap expected-failure parity inventory and draft PR. This supplements the merged #1153 spec from an isolated worktree at main 992c8525; existing slice ownership and settled decisions remain in force. HANDOFF.md and runtime sources are untouched.

Verified: the new source-level inventory reports three expected failures (package choices, keep widgets, guardrail forwarding). Combined focused unittest run: 9 tests, 1 failure, 3 expected failures. The existing JEG-1229 context wrapper fails in JEG-1240 journey envelope on undefined settings (29 internal checks pass, 1 fails); JEG-1230 readout and trade-band wrappers pass. No retries, full validate, browser QA, live publication or numerical changes. Module parity is not proof of route rendering parity.

Next: independent review of draft; carry inventory into redesign acceptance and preserve existing implementation child owners. Migration and numerical boundary review questions are listed recommendation-first in the supplement. No merge/deploy/Supabase authorization is implied.
