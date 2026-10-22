# Feature contract: ID map

Maps every line of the feature contract to the check or ticket that covers it. Owner ticket: JEG-602. Checked 2026-10-12 against `tests/test_v2_contract_render.py` (`ContractMirrorTest`, 4 tests, OK: the mirror, the CHECKS table and the pending tickets agree).

The contract text lives in [../feature-contract.md](../feature-contract.md), a mirror of the Google Doc "Data Driven Football: feature contract" (v1.2). Rebuild this table with the snippet at the end.

## Pending lines (14): "to build" in the contract

| ID | Ticket in the contract | Ticket status 2026-10-12 | Action |
|---|---|---|---|
| CT-02 | JEG-505 | Done | Ticket shipped: drop "to build" in the Doc, then switch the check live |
| GL-07 | JEG-498 | Todo | Waiting on the ticket |
| GL-09 | JEG-497 | Done (engine; front end is JEG-542) | Point the line at JEG-542 (the front-end ticket); JEG-497 shipped the engine |
| GL-19 | JEG-501 | Done | Ticket shipped: drop "to build" in the Doc, then switch the check live |
| GL-20 | JEG-502 (partial check live) | Done | Ticket shipped: drop "to build" in the Doc, then switch the check live |
| GL-21 | JEG-510 | Done | Ticket shipped: drop "to build" in the Doc, then switch the check live |
| GL-22 | JEG-498 | Todo | Waiting on the ticket |
| GL-23 | JEG-537 | Backlog | Waiting on the ticket |
| GL-24 | JEG-537 | Backlog | Waiting on the ticket |
| PV-04 | JEG-503 | Todo | Waiting on the ticket |
| PV-06 | JEG-503 | Todo | Waiting on the ticket |
| PV-07 | JEG-503 | Todo | Waiting on the ticket |
| TT-05 | JEG-510 (partial check live) | Done | Ticket shipped: drop "to build" in the Doc, then switch the check live |
| TT-09 | JEG-504 | Done | Ticket shipped: drop "to build" in the Doc, then switch the check live |

## Live lines (46)

Each has a check function in `CHECKS` in `tests/test_v2_contract_render.py`.

| ID | Check |
|---|---|
| CT-01 | `ct01` |
| CT-03 | `ct03` |
| CT-04 | `ct04` |
| CT-05 | `ct05` |
| CT-06 | `ct06` |
| CT-07 | `ct07` |
| GL-01 | `gl01` |
| GL-02 | `gl02` |
| GL-03 | `gl03` |
| GL-04 | `gl04` |
| GL-05 | `gl05` |
| GL-06 | `gl06` |
| GL-08 | `gl08` |
| GL-10 | `gl10` |
| GL-11 | `gl11` |
| GL-12 | `gl12` |
| GL-13 | `gl13` |
| GL-14 | `gl14` |
| GL-15 | `gl15` |
| GL-16 | `gl16` |
| GL-17 | `gl17` |
| GL-18 | `gl18` |
| HV-01 | `hv01` |
| MF-01 | `mf01` |
| PV-01 | `pv01` |
| PV-02 | `pv02` |
| PV-03 | `pv03` |
| PV-05 | `pv05` |
| PV-08 | `pv08` |
| PV-09 | `pv09` |
| PV-10 | `pv10` |
| PV-11 | `pv11` |
| PV-12 | `pv12` |
| PV-13 | `pv13` |
| PV-14 | `pv14` |
| PV-15 | `pv15` |
| PV-16 | `pv16` |
| PV-17 | `pv17` |
| RF-01 | `rf01` |
| TT-01 | `tt01` |
| TT-02 | `tt02` |
| TT-03 | `tt03` |
| TT-04 | `tt04` |
| TT-06 | `tt06` |
| TT-07 | `tt07` |
| TT-08 | `tt08` |

## Edits that need Jeremy's Drive (the Doc is still the source until it is edited)

The repo test and `scripts/sync_feature_contract.py` treat the Doc as the source and `docs/feature-contract.md` as generated output ("never edit by hand"). JEG-602 asks to flip that (repo source, Doc mirror). That needs the Doc edited and a decision recorded in its log, so it is not done here. To finish:

1. In the Doc, change GL-09 "to build: JEG-497" to "to build: JEG-542". Then edit the PENDING ticket in the test to match (the test fails until both agree).
2. In the Doc, drop "to build" from CT-02, GL-19, GL-20, GL-21, TT-05 and TT-09 (their tickets are Done); then run `python scripts/sync_feature_contract.py --doc contract <exported text>` and switch each check from PENDING to its live function in the test. Each check must be negative-tested.
3. Add contract lines for JEG-565 (default roster with K/DEF and 7 bench, roster controls, convention-based tiers). GL-23 and GL-24 are already taken (bench-share readout; Edit league), so the next free IDs are GL-25 and GL-26.
4. If the repo is to become the source: remove the Doc fetch step from the sync script, flip the header comments in the contract file and the test, and make the Doc a pasted copy. Record the decision (docs-location-001 covers where docs live; the contract direction needs its own line).

## Lines the Doc needs for the 2026-10-22 merges (JEG-874)

`docs/feature-contract.md` is sync output (`ContractMirrorTest.test_mirror_is_sync_output`) and every `**XX-NN**` in it must have a check in `CHECKS` (`test_mirror_every_id_has_a_check`), so new IDs cannot be added by a docs PR. The table lists what shipped on 2026-10-22, the test that already pins it, and the line the Doc should gain (next free IDs: GL-29 onward, TT-13, PV-21, MF/RS as shown; VA is a new section). Until the Doc carries them, the pinning tests are the contract.

| Shipped (PR, ticket) | Pinned by | Line for the Doc (proposed ID) |
|---|---|---|
| Values auditing tab: last top-level tab `#values-auditing`, sub-routes `#values-auditing/value-pie` and `/single-source` (unknown falls back to value-pie); `DDFAudit` registry (#808, JEG-847) | `tests/test_v2_audit_render.py`, `test_v2_nav_render.py` | VA-01: a Values auditing tab with sub-sections; each sub-section is its own module registered through `DDFAudit`. |
| Value pie tab: per-source starter/bench/total Adjusted against the league pie (VP-5), by position, raw vs adjusted group totals, coverage vs rosterable slots, verdict rows at a 10% spread; never a zero for a missing value (#802, JEG-848) | `tests/test_audit_pie.py` (31 tests, VP-5 and raw-vs-adjusted negative-tested) | VA-02: every source's Adjusted values sum to the league pie on the Value pie tab; a source more than 10% from the cross-source middle is flagged. Open: JEG-871 (pie total vs Player values column sum), JEG-872 (source names). |
| Single-source build-up view (JEG-849) | not merged (#803 open) | none yet |
| Writing tab: Manifesto, How values work, Research as sections at `#writing/<section>`; old routes redirect (#810, JEG-855) | `tests/test_v2_writing_routes_render.py`, `test_v2_manifesto_render.py`, `test_v2_research_render.py` | MF-01 and RS-01 already reworded in the mirror by #810 (the Doc still needs the same edit). |
| Customize dialog: two tabs "Chart lines" / "DDF blend"; Done blocked with "Pick at least one source" when the draft has no engine series; the last usable DDF input stays on, locked, held inputs not counted; "Using N of M sources" on the blend tab only; VORP group collapsed unless selected; variants "DDF Value: charts only" / "DDF Value: projections only"; stacked phone footer, 44 px targets (#811, JEG-850; Jeremy's copy decisions 2026-10-22 on the ticket) | `tests/test_v2_customize_cleanup_render.py` (each guard negative-tested), `test_v2_ddf_versions_render.py`, `test_v2_source_count_render.py` | GL-07 rewrite: replaces the five-group list with the two tabs and the Done, last-input and counter rules. |
| Divergence chip: in range is a green SVG checkmark (aria-label and title "Normal range: ..."), out of range is plain amber "Under review"; one helper feeds Trade targets, the strip, Customize and Player values heads (#805 and #811, JEG-856 A, JEG-850) | `tests/test_v2_divergence_chip_render.py` (8 guard patches) | GL-25 rewrite: "Check" becomes "Under review", "Reviewed" stays; the in-range state is a green check with the accessible text, never a boxed word. Open: JEG-870 (held source must show no check). |
| Source links: every source id except ESPN has a URL in `assets/comparison-sources-data.json` (`sources.<id>.url` or `source_url`) that is not a bare domain root; FantasyCalc is `/trade-value-chart`; weekly articles (usatoday, fantasypros, cbs) are rewritten by promotion from `source_provenance.source_url` (#806, JEG-856 B) | `tests/test_source_link_urls.py`, `test_v2_source_links_render.py` | GL-27 addendum: ESPN gets no link (Jeremy, 2026-10-22, JEG-856: nothing login-gated or stale is shown); the USA Today URL is the pulled article (unverified in a browser: 402/403 to automation). |
| Shared player search: one helper `app/v2/namesearch.js` for Player values, Trade targets, Risers, Compare, Find a trade rosters and the Not valued lists; word-start matches, any word order ("Nacua Puka"), suffix/accent/apostrophe ignored, fuzzy only at 4+ letters within 1 (4 to 6) or 2 (7+) edits, never inside a name ("nac", "cmc" match nothing); search never invents a player (#819, JEG-861 B) | `tests/test_v2_name_search.py` (8 mutants), `test_v2_name_search_render.py` | GL-20 addendum: the matching rule above. |
| Plain copy: "middle of N charts" not "median"; Deal read sentences no longer claim what the other manager will do; every value page title carries "NFL Week N · as of Mon D" (#821, JEG-861 C) | `tests/test_v2_plain_copy_render.py` | GL-29: every value page shows the NFL week and as-of date in its title; copy never says "median". |
| Trade targets: any one chart can be Our value or Compare against (not both); with one compared chart `minCharts` is 1 and the heading names the chart instead of the market consensus; rank-gap, `BUY_RANK_MARGIN` 2, `SELL_FLOOR` 5 and the out/estimated exclusions unchanged (#807, JEG-851) | `tests/test_v2_targets.py` (4 harnesses, 4 mutations), `test_v2_targets_render.py` | TT-03 / TT-04 addendum: single-chart comparison. Open: JEG-868 (TypeError when Our value is a chart and Compare is All charts), JEG-869 (single-chart headings). |
| Roster paste parser `app/v2/roster-paste.js` (`window.DDFRosterPaste.parse(text, playerIndex)`): deterministic, no LLM, no network; ESPN and Yahoo team and matchup page text; 100% on the four scrubbed fixtures; not wired to any UI yet (#804, JEG-853 phase 1) | `tests/test_v2_roster_paste.js` (34, run by hand with node; not in a Makefile target) | none until phase 2 wires it (after JEG-852, #809 open). |
| Find a trade as its own tab (JEG-852) | not merged (#809 open) | none yet |

## Rebuild this table

```
python -c "import sys; sys.path.insert(0,'.'); from tests import test_v2_contract_render as t; ids=t.contract_ids(open('docs/feature-contract.md').read()); [print(k, t.CHECKS[k]) for k in sorted(ids)]"
```
