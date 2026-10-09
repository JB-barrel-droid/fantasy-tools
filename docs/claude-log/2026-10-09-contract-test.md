## 2026-10-09 - Feature contract test (JEG-506)

Contract: one quick check per live line of the Google Doc "Data Driven Football: feature contract" v1.1, a `docs/feature-contract.md` mirror, and a check that every mirrored ID has a test. First session on the Mac (JEG-523 handoff).

### What shipped
- `docs/feature-contract.md`: the Doc v1.1, exported through the Drive connector (the gws CLI export matched). 57 IDs: 45 live, 12 "to build".
- `tests/test_v2_contract_render.py`: 45 checks, one per live ID, and `PENDING` for the 12 with their tickets. Five page loads in about 35 s: desktop Player values (with two reloads), desktop tabs, phone, engine failure. The freshness file is replaced with a fixed one so every status (current, prior week, unknown, not updating) is exercised. In `make test-unit`.
- `app/v2/v2.js`, four defects the first run found:
  - Trade targets "from N sources" tooltip listed engine keys ("fantasycalc_adj_values chart"). The engine's DDF inputs are now `<chart>_adj_values` (JEG-508); `sourceMeta` did not know the suffix.
  - How values listed `ddf_value_charts` and `ddf_value_projections` as indexed publisher charts. They are now DDF Value versions (method "ddf"), so they leave the method lists until JEG-497 shows them.
  - Player detail header read "DDF Value · undefined · W5" (no method name for DDF).
  - A source on a prior week showed "Prior week" with no symbol in the freshness dialog, and the chip read "Week 5 · 1 source on a prior week" with no warning symbol (GL-04, GL-05). Both now lead with ⚠.

### Verified (check named)
- Mirror: `ContractMirrorTest` OK. It fails when a Doc line has no check (a synthetic PV-99), when a pending line goes live (GL-21 without "to build"), and when a checked ID leaves the Doc (TT-07 dropped).
- All 45 live checks pass on the fixed build: `tests.test_v2_contract_render` OK (4 tests).
- Broken builds caught (`test_guard_fails_on_broken_builds`): Manifesto moved after Player values (MF-01), Swap never shown (CT-01), DDF line at the others' weight (PV-02), Reset leaving Rank by (PV-09), prior-week status and chip without a symbol (GL-04, GL-05).
- The pre-fix v2.js from main fails GL-02 ("undefined"), GL-04, GL-05, TT-03 (engine key) and HV-01 (engine keys); one-off run of `run_contract` with main's v2.js served.
- Every `tests/test_v2_*_render.py` suite, run one at a time, plus `test_launch_front_door` and `test_ddf_composite_value`: all OK except the two below. `make validate` exit 0.

### Known, not ours
- `tests.test_v2_ux_render`: "How values work" tab hit area 43x44 at 390 px. `tests.test_v2_panels_render`: table scrolls 41 px at 1440 with the wide selection. Both fail identically on clean origin/main (0e0a89d) on this Mac; likely font metrics differ from Linux CI. Not changed here.

### Claimed, not confirmed
- GL-03 / TT-08 ("◐ 1 source") and RF-01 ("could not compare") checks compare the page with the engine; they only bite when the week's data has one-source players or uncompared players.
- TT-05 checks the scale label and its ⓘ, not the word "rescaled"; that wording is JEG-510 (GL-21).
