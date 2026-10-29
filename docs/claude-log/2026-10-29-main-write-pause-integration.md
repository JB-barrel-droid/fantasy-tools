# Current-main pause control integration, 2026-10-29

Base main 6de0bffb. Original #1059 head 45b16fcb is retained unchanged.
This branch merges that tested default-off pause control into current main;
all ten writer workflow preimages matched. The only merge conflict was the
HANDOFF top section, resolved by retaining both lane sections. Main's Makefile
recipes, including newer workflow tests, were preserved. Separate CI-wiring
branch `be/ci-regression-wiring` remains untouched.

No live pause is active. The control starts `paused:false`. A valid enabled
control lasts at most six hours. Malformed or unavailable control defers
publication until manually repaired or connectivity recovers; expiry applies
only to valid controls. Old queued jobs using old workflow code must finish
before treating main as stable. Ingestion, validation, Pages and Supabase jobs
remain enabled. Parent owns review, CI, merge, activation and restoration.
