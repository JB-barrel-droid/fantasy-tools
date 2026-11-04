## 2026-11-04 - Lifecycle source URL correction / JEG-1505

Contract: address the independent adversarial P2 against
`f10d400b6db0780bb37ef934ac5d464dd4af9b8a` with a narrow owned-adapter change.
No network source verification, identity restoration, snapshot changes,
consumer edits, production policy or pricing/methodology changes.

### Verified (check named)

- Read the exact independent report at
  `/var/folders/cs/5b34cp357gz4byzqmvh8zxbw0000gn/T/jeg1505-adversarial-20261104-0_rigc6o/REPORT.md`.
  It found five malformed URL variants among 4,810 probes. This session
  reproduced all five with a new regression against the old adapter: each
  failed because ValueError was not raised. The independent scratch reports
  were not modified and the 4,810-case run was not independently repeated.
- The five reproduced sources are `https://:443/retirement`,
  `https://@/retirement`, `https:// /retirement`,
  `https://exa mple.invalid/retirement`, and an embedded literal newline in
  `https://example.invalid\n/retirement`.
- Validation now rejects raw whitespace/C0/DEL controls before urlsplit can
  normalize them, requires an HTTP(S) scheme and nonempty hostname, and
  evaluates the parser's explicit-port syntax/range checks. It never fetches
  the URL. Caller responsibility for source provenance is documented.
- Three added tests cover all five reproduced variants, six raw whitespace/
  control variants, two malformed ports and five valid syntax controls:
  HTTP/HTTPS, explicit port/query/fragment, IPv6 and an encoded path space.
  Valid synthetic URLs remain unchanged in history. Syntactic acceptance is
  not source trust; none is asserted as a real retirement record.
- `python3.12 -B -m unittest -v tests.test_searchable_identity_eligibility`:
  all 22 tests passed; log: `../jeg-1505-url-focused-tests.log`.
- `python3.12 -B -m pipelines.baseline_reds --context local -- python3.12 -B
  -m unittest tests.test_searchable_identity_eligibility
  tests.test_jeg1505_search_only_consumer_contract tests.test_nfl_universe
  tests.test_sync_players_active tests.test_universe_chart_only
  tests.test_bake_espn_zero_universe`: all 78 tests passed; log:
  `../jeg-1505-url-targeted-tests.log`. Existing sync writes are mocked.
- Pure full-fixture comparison with the old adapter returned identical
  results: 1,161 identities and 1,155 eligible keys. Inputs and numeric fields
  remained unchanged; actual computed pricing membership was not inferred.
  Thirteen protected files remain byte-identical to f10d400b. Evidence:
  `../jeg-1505-url-invariance.json`.
- The same six position disagreements remain documented and unchanged:
  keys 955, 1011, 2127, 3472, 3677 and 3837. No historical key was restored.

### Claimed, not confirmed

- URL parsing and character checks do not establish source authority,
  availability, factual correctness or retirement provenance. Those remain
  caller/evidence-review responsibilities; no new trusted-source policy is
  introduced.
- Adapter remains unwired. No live coverage, independent delta approval or
  full validation success is claimed. Prior localhost-bind failure was not
  retried or routed around. Nothing was pushed, published or deployed.
- Later integration handoff, coordinator-supplied evidence only: #1296's
  owner reports 14 new cases requiring explicit ID namespaces (Sleeper 4046
  resolves to Mahomes canonical 3594; canonical 4046 is Hyatt), resolution
  and deduplication before ownership filtering, and pending status for
  unknown/conflicting IDs. Raw override additions can reintroduce another
  team's player after filtering, so future callers must filter overrides
  too. These are scratch proposed contracts, not code or results independently
  verified in this URL correction. The owner's adapter remains untouched.
