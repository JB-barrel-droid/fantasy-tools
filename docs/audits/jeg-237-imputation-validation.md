# JEG-237: reject invalid and infeasible Option C inputs

On main5792ba5 the new producer accepts negative/NaN native values and returns
zero for a positive group target with an empty/zero native pool. CLI float
coercion also turns boolean/string values into apparently valid numbers.

This narrow fix validates every native row/position and all eight group targets
before roster inference or output. Numeric values must be finite and nonnegative;
boolean/string/null inputs are rejected. Targets must define exactly the eight
skill position/role groups. A positive target without a positive native sum
raises ValueError. True zero target/zero sum emits genuine zero. Finite aggregate,
factor and computed output checks reject overflow. JSON duplicate keys and
unknown/duplicate group rows reject; CLI types are preserved until validation.
Validation completes before touching the output path, and strict JSON forbids NaN.

Eight real unittest cases cover valid60/40→12/8, native immutability, true zeros,
invalid native/target types, missing/extra group keys, invalid rows/positions,
aggregate/factor overflow, and CLI duplicate/bool rejection with unchanged
sentinel output. Makefile includes this new module in required validation.

```bash
python3 -m unittest tests.test_imputed_vorps_validation -v
git diff --check
```

Eight tests and diff check pass. Independent read-only Claude Code MCP review
reran all eight and found no correctness gap. `make validate` exits0 on an
isolated composite of this slice on main5792ba5 plus pending PR43. Loading the original main module and rerunning the empty/zero-funded
regression produces both expected test failures, proving discrimination against
the reported defect. Independent review and composite full-suite results are
recorded in PR/Linear. Main's separate Indexed guard regression needs PR43 for
a clean suite; do not confuse composite verification with production readiness.

No rounding, roster shape/tie/Cut, publisher-reference units, reweight economics,
fixture/promotion, or browser changes. JEG238–243 remain open; JEG183's review
prerequisites remain unmet. Canonical authority/config/source/coverage provenance
belongs to the reviewed integration boundary; this arithmetic function does not
resolve identities or certify any caller-supplied key. Roman integrates/deploys.
