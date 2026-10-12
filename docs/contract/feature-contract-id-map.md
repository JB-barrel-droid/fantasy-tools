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

## Rebuild this table

```
python -c "import sys; sys.path.insert(0,'.'); from tests import test_v2_contract_render as t; ids=t.contract_ids(open('docs/feature-contract.md').read()); [print(k, t.CHECKS[k]) for k in sorted(ids)]"
```
