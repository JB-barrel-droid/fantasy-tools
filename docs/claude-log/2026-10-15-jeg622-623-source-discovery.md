## 2026-10-15 - JEG-622 FFA access check and JEG-623 source discovery

Contract: find public sources, rank them, ticket the top ones. Docs only; no code, no numbers changed.

### Verified (check named)
- FFA: anonymous GETs of /projections, /apps, apps. subdomain, the weekly cheat-sheet posts and the API docs page. No data table anywhere; the API needs a paid key; cheat-sheet posts are one-line stubs. Conclusion: no public machine-readable FFA output, so no puller.
- Candidates: one parallel anonymous fetch of about 40 URLs (status, size, content type) and a body inspection of each 200: KTC embedded JSON (500 players), Dynasty Daddy JSON (765), RotoBaller HTML table (about 400 rows), Fleaflicker HTML table (20 rows per page), Fantasy Sharks CSV (380 rows), Sleeper JSON (355 QB rows), DynastyProcess CSV (483 rows).

### Claimed, not confirmed
- Update cadences, RotoBaller scoring format, Fleaflicker pagination and the FantasyPros anonymous row limit (see "Not verified" in docs/research/source-discovery-2026-10-15.md).
- No name matching to player_key was run for any candidate.

Doc: docs/research/source-discovery-2026-10-15.md
