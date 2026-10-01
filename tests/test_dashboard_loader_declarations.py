"""Regression: monitor dashboard loader sections must not die from JS
declaration-order bugs.

On 2026-10-01 the Player Trace and Aggregate Diagnostics sections showed
their "not available" fallbacks on production for weeks while both JSONs
served 200 with correct data and shapes. Root causes found in
modules/dashboard.html (strict mode):

1. TDZ: `const TRACE_PATHS` / `const DIAG_PATHS` were declared AFTER the
   top-level `loadPlayerTrace();` / `loadDiagnostics();` calls. Evaluating
   the const inside the loader threw "Cannot access ... before
   initialization", swallowed by the loader's try/catch into the fallback.
2. `traceRes = await firstOk(...)` assigned to a never-declared variable,
   which throws ReferenceError under "use strict" (would have fired as soon
   as the TDZ bug was fixed).

These tests fail against that broken state and pass with the fix.
"""
import re
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parent.parent / "modules" / "dashboard.html"


class LoaderDeclarationOrderTest(unittest.TestCase):
    def test_paths_consts_declared_before_loader_calls(self):
        text = HTML.read_text()
        lines = text.splitlines()
        call_idx = next(
            i
            for i, l in enumerate(lines)
            if "// Load the new framework sections" in l
        )
        decls = [
            (i, m.group(1))
            for i, l in enumerate(lines)
            for m in [re.search(r"const\s+(\w+_PATHS)\s*=\s*\[", l)]
            if m
        ]
        self.assertTrue(decls, "no *_PATHS consts found -- test wiring is stale")
        late = [name for i, name in decls if i > call_idx]
        self.assertFalse(
            late,
            "these path consts are declared AFTER the framework loader calls, "
            "so evaluating them throws a TDZ ReferenceError inside the loaders "
            "and the sections permanently show 'not available': "
            + ", ".join(late),
        )

    def test_firstok_results_assigned_to_declared_vars(self):
        """Every `x = await firstOk(` target must be declared; under
        'use strict' an undeclared target throws ReferenceError."""
        text = HTML.read_text()
        targets = re.findall(r"(?<!\.)\b([A-Za-z_$][\w$]*)\s*=\s*await\s+firstOk\(", text)
        # strip declarations on the same statement: `const x = await firstOk(`
        declared_targets = set(
            re.findall(
                r"\b(?:let|const|var)\s+([A-Za-z_$][\w$]*)\s*=\s*await\s+firstOk\(",
                text,
            )
        )
        bare = [t for t in targets if t not in declared_targets]
        undeclared = [
            t
            for t in bare
            if not re.search(rf"\b(?:let|const|var)\s+{re.escape(t)}\b", text)
        ]
        self.assertFalse(
            undeclared,
            "these firstOk() results are assigned to never-declared variables; "
            "'use strict' throws ReferenceError on assignment: "
            + ", ".join(undeclared),
        )


if __name__ == "__main__":
    unittest.main()
