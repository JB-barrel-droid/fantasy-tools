## 2026-10-16 - JEG-700 tests import order, not checkout path

- Reproduced: six test modules fail alone on current main with ModuleNotFoundError 'lib' / 'timestamps', in any checkout.
- Root cause: JEG-625 added `from lib.timestamps` to 14 pipelines modules (and `from timestamps` fallbacks in 4 pipelines/lib modules) with no sys.path setup. They imported only if an earlier test had put pipelines/ on sys.path (full-suite order). The "passes in ~/code/fantasy-tools" report was a stale checkout without that import (its monitor_alerts.py had no lib import). CI passed because it ran in suite order.
- Fix: each of the 14 modules inserts its own dir on sys.path before the lib import; the 4 lib modules try `.timestamps` first.
- Guard: tests/test_pipelines_import_standalone.py (in Makefile) imports every lib-using module in a clean `python -I` from a temp copy of pipelines/ at another path.
- Verified: the six target tests pass alone (21/35/19/8/4/34); a scan of all lib-using modules finds none failing; negative test: reverting monitor_alerts.py makes the guard fail naming it, and a synthetic broken module is flagged.
- Not run: full make validate (not done in this lane).
