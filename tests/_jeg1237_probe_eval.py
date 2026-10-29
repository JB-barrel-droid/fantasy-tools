"""JEG-1237 scratch: full eval-render error lists, current code and the pre-fix layout (settings not folded)."""
from tests import _render_env
from tests.test_v2_finder_eval_render import run_checks

_render_env.ensure_built()
UNFOLD = ('el("div", {class: "v2-find-guardrails", id: "v2FindGuardrails"}, protectedField, backupField), advanced,', 'protectedField, backupField, advanced,')
for name, mutate in (("FIXED", None), ("BASELINE-LAYOUT", UNFOLD)):
    errs = run_checks(mutate)
    print(f"JEG1237EVAL {name} {len(errs)}")
    for e in errs:
        print(f"JEG1237EVAL {name} | {e}")
