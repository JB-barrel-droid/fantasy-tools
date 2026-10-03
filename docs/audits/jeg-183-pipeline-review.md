# JEG-183: independent review of the new Option C / Adj pipelines

Reviewed main1678697, including JEG-182 clean rewritea89b992 and
JEG-209 implementation1678697. Verdict: **not ready for integration/promotion**.
This records independent code/arithmetic review, not deployment or live QA.
Jeremy's approved method is the authority; comments saying "Done" or docstrings
saying "all-source" do not establish behavior.

## Reproduced defects and follow-ups

| Ticket | Location | Reproduction / consequence |
| --- | --- | --- |
| JEG-237 | build_imputed_vorps.py:115-119,146-153 | Native0 with positive group target20 silently returns0; native1/-0.5 returns40/-20; NaN propagates to output. Invalid target/input and infeasible denominator need rejection before output. |
| JEG-238 | build_imputed_vorps.py:130-131 | Three equal native1 rows with target20 produce6.67 each: sum20.01. Intermediate/output rounding violates conservation/ratio reproducibility. |
| JEG-239 | build_imputed_vorps.py:31-35,53 | Only hardcoded12-team shape supported; equal-value13QB input reversed makes key0 starter→bench. Cut inputs omitted rather than explicit0. Configurable roster and deterministic classification required. |
| JEG-240 | build_reweighted_values.py:130-144,164 | SourceA provisional10/10→70/70 (total140); B18/2→70/7.8(total77.8). Independent maxima violate one batch scale/shared budgets. |
| JEG-241 | build_reweighted_values.py:121-125 | QB starter budget20 onU1/10; bench budget10 onU1/2. Clamping bench to minstarter*0.999 changes total30→23.632727, bench10→3.632727 and collapses distinct bench values. |
| JEG-242 | Makefile/refresh/browser + tests/test_imputed_vorps_clean.py | New producer modules have no refresh/browser/promotion wiring; unittest invocation discovers0tests and proportional test is assertTrue. No current-method Sheet/real-grain/rendered oracle. |
| JEG-243 | build_reweighted_values.py:44-50 | Any single calibration leg accepted as "blend"; starter_raw/bench_raw are legacy calibrated quantities, not verified raw linear blended surplus. No units/source/weight/horizon/config manifest. |

Raw-vs-calibrated export provenance is separately addressed by JEG-233/PR45.
Preserve the approved legacy publisher-reference quantities until reviewed explicit
migration; do not silently change JEG-180 economics while correcting units.

## Commands and results

```bash
python3 -m unittest tests.test_imputed_vorps_clean -v
python3 tests/test_imputed_vorps_clean.py
python3 -m unittest tests.test_vorp_translation_unified tests.test_translate_via_vorp tests.test_vorp_refresh
rg -n 'build_imputed_vorps|build_reweighted_values' Makefile pipelines app tests .github
```

First command: **0 tests**, exit0. Second: two roster-count functions pass; it
does not call the proportional placeholder. Legacy suite:43 pass, exit0; those
passes validate the old pipeline, not migration of this new one. Search finds
only the new module/docstring and test import, no producer integration. Repros
below run against the reviewed main, and deliberately show the defects:

```python
import sys
sys.path.insert(0, 'pipelines')
from build_imputed_vorps import compute_imputed_vorps, infer_roster, GROUPS
from build_reweighted_values import linear_reweight, iron_within_position_inversions, apply_70_anchor
G = {g: 0 for g in GROUPS}; G['RB', 'starter'] = 20
print(compute_imputed_vorps({str(i): ('RB', 1.) for i in range(3)}, G))
print(compute_imputed_vorps({'1': ('RB', 0.)}, G))
print(compute_imputed_vorps({'1': ('RB', 1.), '2': ('RB', -.5)}, G))
print(compute_imputed_vorps({'1': ('RB', float('nan'))}, G))
a = {str(i): ('QB', 100) for i in range(13)}
print(infer_roster(a)['0'], infer_roster(dict(reversed(list(a.items()))))['0'])
print(apply_70_anchor({'A1': 10, 'A2': 10}), apply_70_anchor({'B1': 18, 'B2': 2}))
im = {str(i): {'group': 'QB|' + ('Starter' if i < 3 else 'Bench'),
              'imputed_vorp': u} for i, u in ((1, 1), (2, 10), (3, 1), (4, 2))}
b = {g: 0 for g in GROUPS}; b['QB', 'starter'] = 20; b['QB', 'bench'] = 10
before = linear_reweight(im, b); after = iron_within_position_inversions(before, im)
print(before, after, sum(before.values()), sum(after.values()))
```

No current full-suite or rendered/production readiness claim: main's separate
Indexed guard fix is PR43; new pipeline tests are not in required validation.
Full Sheet oracle/config/source coverage and the browser's VORP/Adj numerical
parity remain unverified. This review does not approve deployment.

## Independent second review and rejected assertions

Read-only Claude Code MCP review also found missing configurable shape,
Cut omissions, placeholder tests and absent provenance. Its report contained
incorrect claims: a supplied four-player conservation example was claimed to
sum225 vs250; independent rerun yields250 vs250. It also called positive-target/
zero-denominator handling, calibration-as-blend and0.999 clamping correct. Those
conclusions conflict with the approved contract and reproduced failures above;
they were rejected. Findings here rely on inspected code and executed arithmetic,
not the reviewer's endorsement. Exact zero/zero is valid; positive target/zero
pool is infeasible.

Next: resolve one defect per ticket, with meaningful negative regressions, then
re-run this review on the integrated head. Keep JEG-183 open until its reviewed
numerical/artifact/rendered/production prerequisites are met. Roman owns final
integration and deployment; Codex can supply isolated validated draft fixes.
