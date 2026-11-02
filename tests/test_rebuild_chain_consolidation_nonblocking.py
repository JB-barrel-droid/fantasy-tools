#!/usr/bin/env python3
"""Decision consol-nonblocking-001 (Jeremy 2026-10-07): a failed
consolidated_values write must not hold the Pages deploy, and must be recorded
red on its own monitored check (consolidated_values_write).

Rebuild run 37641559947 is the broken state: the consolidation step failed,
the job failed, and the Pages dispatch (implicit success()) was skipped while
the fixture had already been pushed. JEG-1441 changes the transport: an App
push now triggers Pages directly. The regression boundary is therefore the
publication step, which must still run after a failed consolidation write.

The workflow is stdlib-parsed (no pyyaml in CI). A small evaluator runs the
job's steps in order the way GitHub does: a step whose `if:` has no status
function gets an implicit success(); a failed step without continue-on-error
fails the job; `steps.<id>.outcome` is the raw result. Each guard is
negative-tested on a mutated copy of the real workflow.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import record_monitor_check as rec  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "rebuild-chain.yml"
CONSOLIDATE = "Build consolidation layer (JEG-324)"
RECORD = "Record consolidated_values check"
PUBLISH = "Commit and push if changed"


def parse_steps(text):
    """[{name, id, if, continue_on_error, run}] for the job's steps."""
    header = re.search(r"\n    steps:(?:[ \t]+&[A-Za-z0-9_-]+)?[ \t]*\n", text)
    if header is None:
        raise ValueError("Main job steps header missing")
    # Anchors do not change the step sequence. Do not consume later jobs.
    body = re.split(r"\n  [A-Za-z0-9_-]+:[ \t]*\n", text[header.start():], maxsplit=1)[0]
    chunks = re.split(r"\n      - (?=name:|uses:)", body)[1:]
    out = []
    for c in chunks:
        lines = c.split("\n")
        first = lines[0]
        name = first[len("name:"):].strip() if first.startswith("name:") else first
        fields = {"name": name, "id": None, "if": None, "continue_on_error": False, "run": ""}
        for ln in lines[1:]:
            m = re.match(r"^        (id|if|continue-on-error|run):\s*(.*)$", ln)
            if not m:
                continue
            key, val = m.group(1), m.group(2).strip()
            if key == "id":
                fields["id"] = val
            elif key == "if":
                fields["if"] = val
            elif key == "continue-on-error":
                fields["continue_on_error"] = val == "true"
            elif key == "run":
                fields["run"] = val
        fields["run"] = fields["run"] or c
        out.append(fields)
    return out


def evaluate(expr, ctx, job_failed):
    """GitHub `if:` semantics for the subset this workflow uses."""
    if expr is None:
        return not job_failed
    e = expr.strip()
    if e.startswith("${{") and e.endswith("}}"):
        e = e[3:-2].strip()
    has_status = re.search(r"\b(always|cancelled|success|failure)\(\)", e)
    py = e.replace("&&", " and ").replace("||", " or ")
    py = re.sub(r"!(?!=)", " not ", py)
    py = py.replace("always()", "True").replace("cancelled()", "False")
    py = py.replace("success()", str(not job_failed)).replace("failure()", str(job_failed))

    def lookup(m):
        return repr(ctx.get(m.group(0), ""))
    py = re.sub(r"\b(steps|github)\.[A-Za-z0-9_.-]+", lookup, py)
    value = bool(eval(py, {"__builtins__": {}}, {}))  # noqa: S307 - test-only, fixed workflow text
    return value if has_status else (value and not job_failed)


def simulate(text, outcomes):
    """Run the job. outcomes: {step name: 'success'|'failure'} (default success).
    Returns {step name: ran?}, the record step's --outcome value, job status."""
    ctx = {"github.ref": "refs/heads/main", "github.event_name": "workflow_dispatch"}
    job_failed, ran, recorded = False, {}, None
    for s in parse_steps(text):
        go = evaluate(s["if"], ctx, job_failed)
        ran[s["name"]] = go
        outcome = outcomes.get(s["name"], "success") if go else "skipped"
        if s["id"]:
            ctx[f"steps.{s['id']}.outcome"] = outcome
            ctx[f"steps.{s['id']}.conclusion"] = ("success" if s["continue_on_error"] and outcome == "failure"
                                                  else outcome)
        if s["id"] == "push" and go:
            ctx["steps.push.outputs.pushed"] = "true"
        if go and s["name"] == RECORD:
            m = re.search(r'--outcome "\$\{\{ ([^}]+) \}\}"', s["run"])
            src = m.group(1).strip() if m else ""
            recorded = ("failure" if job_failed else "success") if src == "job.status" else ctx.get(src)
        if go and outcome == "failure" and not s["continue_on_error"]:
            job_failed = True
    return ran, recorded, ("failure" if job_failed else "success")


FAILED_WRITE = {CONSOLIDATE: "failure"}


def guard_problems(text):
    """Every way the workflow breaks the decision; empty = compliant."""
    problems = []
    names = [s["name"] for s in parse_steps(text)]
    for n in (CONSOLIDATE, RECORD, PUBLISH):
        if n not in names:
            problems.append(f"missing step {n!r}")
    if problems:
        return problems
    ran, recorded, _job = simulate(text, FAILED_WRITE)
    if not ran[PUBLISH]:
        problems.append("a failed consolidation write skips publication")
    if not ran[RECORD]:
        problems.append("a failed consolidation write is not recorded")
    else:
        payload = rec.build_payload("consolidated_values_write", "rebuild-chain.yml", recorded)
        if payload is None or payload["p_ok"]:
            problems.append(f"a failed consolidation write is recorded as {recorded!r}, not red")
    ran_ok, recorded_ok, _ = simulate(text, {})
    if not ran_ok[RECORD] or rec.build_payload("consolidated_values_write", "rebuild-chain.yml",
                                               recorded_ok)["p_ok"] is not True:
        problems.append("a successful consolidation write is not recorded green")
    record = next(s for s in parse_steps(text) if s["name"] == RECORD)
    if "always()" not in (record["if"] or ""):
        problems.append("the record step must run if: always() (an earlier failure must still be recorded)")
    publish = next(s for s in parse_steps(text) if s["name"] == PUBLISH)
    if publish["if"] and "consolidate" in publish["if"]:
        problems.append("publication depends on the consolidation step")
    return problems


class NonBlockingConsolidationTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_anchor_preserves_every_guarded_step(self):
        anchored = self.text
        plain = anchored.replace("steps: &writer-steps", "steps:", 1)
        self.assertNotEqual(anchored, plain)
        self.assertEqual(parse_steps(anchored), parse_steps(plain))
        names = [step["name"] for step in parse_steps(anchored)]
        for name in (CONSOLIDATE, RECORD, PUBLISH):
            self.assertIn(name, names)

    def test_real_workflow_complies(self):
        self.assertEqual(guard_problems(self.text), [])

    def test_failed_write_still_publishes_and_records_red(self):
        ran, recorded, _ = simulate(self.text, FAILED_WRITE)
        self.assertTrue(ran[CONSOLIDATE])
        self.assertTrue(ran[PUBLISH])
        self.assertEqual(recorded, "failure")
        self.assertFalse(rec.build_payload("consolidated_values_write", "rebuild-chain.yml", recorded)["p_ok"])

    # -- negative tests: each mutation is the broken state the guard names ----

    def mutate(self, old, new):
        self.assertIn(old, self.text)
        return self.text.replace(old, new, 1)

    def mutate_step_field(self, text, name, field, value):
        """Change exactly one named step field, independent of its env entries."""
        pattern = (r"(      - name: " + re.escape(name) + r"\n"
                   r"(?:(?!^      - |^  [A-Za-z0-9_-]+:).)*?)"
                   r"^        " + re.escape(field) + r": [^\n]*\n")
        replacement = "" if value is None else f"        {field}: {value}\n"
        changed, count = re.subn(pattern, lambda m: m[1] + replacement,
                                 text, count=1, flags=re.DOTALL | re.MULTILINE)
        self.assertEqual(count, 1, (name, field))
        self.assertNotEqual(changed, text)
        return changed

    def test_run_37641559947_shape_is_caught(self):
        # The live broken state: no continue-on-error on the write, and the
        # publication on its implicit success().
        broken = self.mutate_step_field(self.text, CONSOLIDATE, "continue-on-error", None)
        broken = self.mutate_step_field(broken, PUBLISH, "if", None)
        self.assertIn("a failed consolidation write skips publication", guard_problems(broken))

    def test_either_safeguard_alone_keeps_publication_running(self):
        # Defence in depth: dropping only one of continue-on-error / always()
        # still reaches publication, which triggers Pages through the App push.
        no_coe = self.mutate_step_field(self.text, CONSOLIDATE, "continue-on-error", None)
        self.assertTrue(simulate(no_coe, FAILED_WRITE)[0][PUBLISH])
        no_always = self.mutate_step_field(self.text, PUBLISH, "if", None)
        self.assertTrue(simulate(no_always, FAILED_WRITE)[0][PUBLISH])

    def test_record_from_job_status_is_caught(self):
        # continue-on-error keeps job.status green: recording it would hide the red.
        broken = self.mutate('--outcome "${{ steps.consolidate.outcome }}"', '--outcome "${{ job.status }}"')
        self.assertTrue(any("not red" in p for p in guard_problems(broken)), guard_problems(broken))

    def test_record_that_only_runs_on_success_is_caught(self):
        broken = self.mutate("if: always() && steps.consolidate.outcome != 'skipped'",
                             "if: steps.consolidate.outcome != 'skipped'")
        self.assertIn("the record step must run if: always() (an earlier failure must still be recorded)",
                      guard_problems(broken))
        # and without continue-on-error it is actually skipped on a failed write
        broken = self.mutate_step_field(broken, CONSOLIDATE, "continue-on-error", None)
        self.assertIn("a failed consolidation write is not recorded", guard_problems(broken))

    def test_publication_gated_on_the_write_is_caught(self):
        broken = self.mutate_step_field(self.text, PUBLISH, "if",
                                        "${{ steps.consolidate.outcome == 'success' }}")
        problems = guard_problems(broken)
        self.assertIn("a failed consolidation write skips publication", problems)
        self.assertIn("publication depends on the consolidation step", problems)

    def test_evaluator_matches_github_implicit_success(self):
        self.assertFalse(evaluate("steps.push.outputs.pushed == 'true'",
                                  {"steps.push.outputs.pushed": "true"}, job_failed=True))
        self.assertTrue(evaluate("always() && github.ref == 'refs/heads/main'",
                                 {"github.ref": "refs/heads/main"}, job_failed=True))
        self.assertTrue(evaluate("${{ !cancelled() && steps.push.outputs.pushed == 'true' }}",
                                 {"steps.push.outputs.pushed": "true"}, job_failed=True))
        self.assertFalse(evaluate("steps.chain.outcome != 'success'",
                                  {"steps.chain.outcome": "success"}, job_failed=False))


if __name__ == "__main__":
    unittest.main()
