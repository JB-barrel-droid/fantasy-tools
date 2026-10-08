"""Source resiliency guards (decision source-resiliency-001, Jeremy 2026-10-08).

"Have resiliency for when some of the sources fail": any single source
failing must not take the site down or corrupt it. The other sources
publish; the failed source keeps its last promoted section byte-for-byte
(so the page labels it with its own, older week); a failed ESPN refresh
keeps the last good ESPN section AND its DDF legs (the anchor).

Before this change only a review 'hold' in a published-chart source was
isolated (per-source-promotion-001). Every other single-source failure --
a failed import (no snapshot), a promote refusal, a malformed review, a
crashed stage script, any ESPN or CBS ROS failure -- failed the whole chain,
so nothing published. Each `test_*` below that simulates one of those
failure modes fails on origin/main 196906f.

Negative tests (`*_is_caught`) show each check fires on the broken state it
names. All stage scripts are faked; writes go to temp dirs.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "tests"))
import rebuild_comparison_chain as chain  # noqa: E402
from test_rebuild_chain_failclosed import make_repo  # noqa: E402
from test_rebuild_chain_per_source_hold import (  # noqa: E402
    FIXTURE_REL, GATED, PromotingFake, seed_fixture,
)
from test_rebuild_chain_workflow import find_step, script_of  # noqa: E402

WORKFLOW_PATH = ROOT / ".github/workflows/rebuild-chain.yml"
WORKFLOW = WORKFLOW_PATH.read_text()
IMPORT_STEP = "Import fresh snapshots from Supabase"
CHAIN_STEP = "Rebuild comparison chain (if fixture stale)"

OLD_ESPN_LEG = Path("data/ddf-two-tier/ddf-20260922-espn-ppr-12t-0p15/ddf_leg.json")
OLD_CBSROS_LEG = Path("data/ddf-two-tier/ddf-20260923-cbsros-ppr-12t-0p15/ddf_leg_cbsros.json")


def seed_all(repo):
    """Last good state: gated sources at Week 4, ESPN and CBS ROS sections
    plus one committed DDF leg each."""
    seed_fixture(repo)
    path = Path(repo) / FIXTURE_REL
    fixture = json.loads(path.read_text())
    fixture["sources"]["espn"] = {"espn_snapshot": "2026-09-22", "marker": "old-espn",
                                  "value_provenance": "modeled", "combos": {}}
    fixture["sources"]["cbsros"] = {"vintage": "2026-09-23", "marker": "old-cbsros", "combos": {}}
    fixture["source_validation"] = {s: "live" for s in fixture["sources"]}
    path.write_text(json.dumps(fixture, indent=2))
    for rel, body in ((OLD_ESPN_LEG, "OLD-ESPN-LEG"), (OLD_CBSROS_LEG, "OLD-CBSROS-LEG")):
        (Path(repo) / rel).parent.mkdir(parents=True, exist_ok=True)
        (Path(repo) / rel).write_text(body)
    return json.loads(path.read_text()), path.read_bytes()


def leg_tree(repo):
    root = Path(repo) / "data" / "ddf-two-tier"
    return {str(p.relative_to(repo)): p.read_text() for p in root.rglob("*") if p.is_file()}


def run_chain(tmp, verdicts=None, wrap=None, drop_snapshots=(), nfl_week=5):
    repo = make_repo(tmp, tuple(chain.SOURCES))
    for source in drop_snapshots:  # a failed import leaves no snapshot
        shutil.rmtree(repo / "data" / "raw" / "sources" / source)
    before, before_bytes = seed_all(repo)
    legs_before = leg_tree(repo)
    fake = PromotingFake(repo, verdicts=verdicts or {})
    status = chain.execute_chain(nfl_week=nfl_week, repo=repo,
                                 run_fn=wrap(fake) if wrap else fake)
    after = json.loads((repo / FIXTURE_REL).read_text())
    return dict(status=status, before=before, before_bytes=before_bytes, after=after,
                fake=fake, repo=repo, legs_before=legs_before, legs_after=leg_tree(repo))


def failing(script, after_calls=0, write=None, exc=False):
    """Wrap a fake so `script` fails (or raises) on call number after_calls+1."""
    def wrap(fake):
        seen = {"n": 0}

        def run_fn(cmd, **kw):
            if Path(cmd[1]).name == script:
                seen["n"] += 1
                if seen["n"] > after_calls:
                    if write:
                        write(fake.repo)
                    if exc:
                        raise RuntimeError(f"{script} crashed")
                    return False, f"{script} failed"
            return fake(cmd, **kw)
        return run_fn
    return wrap


# --- checks (each negative-tested below) -------------------------------------
def check_failed_source_kept_and_others_publish(run, failed):
    status, before, after = run["status"], run["before"], run["after"]
    assert status["success"] is True, status["failed"]
    assert failed in status["held"], (failed, status["held"])
    assert after["sources"][failed] == before["sources"][failed], f"{failed} section changed"
    for s in GATED:
        if s != failed:
            assert after["sources"][s]["week_designated"] == "Week 5", f"{s} did not publish"
    assert status["fit"]["status"] == "ok", status["fit"]
    assert status["adjusted_sections"]["status"] == "ok", status["adjusted_sections"]


def check_legs_kept(run, source="espn"):
    pick = lambda legs: {k: v for k, v in legs.items() if f"-{source}-" in k}  # noqa: E731
    after, before = pick(run["legs_after"]), pick(run["legs_before"])
    assert after == before, sorted(set(after) ^ set(before))


class SourceResiliencyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="source-resil-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    # --- one test per fixed failure mode ------------------------------------
    def test_failed_import_keeps_last_section_and_others_publish(self):
        """USA Today's page is down (402): its import wrote no snapshot."""
        run = run_chain(self.tmp / "imp", drop_snapshots=("usatoday",))
        check_failed_source_kept_and_others_publish(run, "usatoday")
        detail = run["status"]["held_detail"]["usatoday"]
        self.assertEqual(detail["stage"], "snapshot")
        self.assertEqual(detail["kept_section"]["week_designated"], "Week 4")
        self.assertIn("failed at stage 'snapshot'", run["status"]["sources"]["usatoday"])

    def test_promote_refusal_mid_source_is_rolled_back(self):
        """Promote refuses FantasyPros' second section (e.g. the L1 import
        gate) after the first was merged: the half-promotion is undone."""
        def wrap(fake):
            def run_fn(cmd, **kw):
                if (Path(cmd[1]).name == "promote_comparison_section.py"
                        and "fantasypros-b" in cmd[2]):
                    return False, "promotion refused: import health for 'fantasypros' is 'red'"
                return fake(cmd, **kw)
            return run_fn
        run = run_chain(self.tmp / "promo", wrap=wrap)
        check_failed_source_kept_and_others_publish(run, "fantasypros")
        self.assertIn(("fantasypros-a-reference-section", "ready"), run["fake"].promote_attempts)
        self.assertEqual(run["status"]["held_detail"]["fantasypros"]["rolled_back"], 1)

    def test_malformed_review_is_isolated(self):
        """A reviewer that returns a garbage verdict (malformed rows upstream)."""
        run = run_chain(self.tmp / "garbage", verdicts={"cbs-a-reference-section": "banana"})
        check_failed_source_kept_and_others_publish(run, "cbs")
        self.assertNotIn(("cbs-a-reference-section", "banana"), run["fake"].promote_attempts)

    def test_crashed_stage_script_is_isolated(self):
        """A scraper/matcher crash (exception, not an exit code) in FantasyCalc."""
        def wrap(fake):
            def run_fn(cmd, **kw):
                if Path(cmd[1]).name == "match_source_snapshot.py" and "fantasycalc" in cmd[3]:
                    raise RuntimeError("identity resolution collapsed")
                return fake(cmd, **kw)
            return run_fn
        run = run_chain(self.tmp / "crash", wrap=wrap)
        check_failed_source_kept_and_others_publish(run, "fantasycalc")
        self.assertEqual(run["status"]["held_detail"]["fantasycalc"]["stage"], "error")

    def test_failed_espn_refresh_keeps_last_good_anchor(self):
        """ESPN's section build fails after all 12 new legs were written: the
        ESPN section and the legs go back to the last good anchor, and the
        other sources still publish (and the fit runs on the kept anchor)."""
        run = run_chain(self.tmp / "espn", wrap=failing("build_espn_section_from_ddf_leg.py"))
        self.assertTrue(run["status"]["success"], run["status"]["failed"])
        self.assertIn("espn", run["status"]["held"])
        self.assertEqual(run["after"]["sources"]["espn"], run["before"]["sources"]["espn"])
        check_legs_kept(run)
        for s in GATED:
            self.assertEqual(run["after"]["sources"][s]["week_designated"], "Week 5", s)
        self.assertEqual(run["status"]["fit"]["status"], "ok")

    def test_espn_builder_that_corrupts_the_fixture_is_restored(self):
        """ESPN's builder dies after writing a truncated fixture."""
        def corrupt(repo):
            (repo / FIXTURE_REL).write_text('{"sources": {"espn": ')
        run = run_chain(self.tmp / "espn-corrupt",
                        wrap=failing("build_espn_section_from_ddf_leg.py", write=corrupt))
        self.assertTrue(run["status"]["success"], run["status"]["failed"])
        self.assertEqual(run["after"]["sources"]["espn"], run["before"]["sources"]["espn"])
        check_legs_kept(run)

    def test_failed_cbsros_leg_build_restores_partial_legs(self):
        """CBS ROS leg 4 of 12 fails after legs 1-3 were written."""
        def wrap(fake):
            seen = {"n": 0}

            def run_fn(cmd, **kw):
                if Path(cmd[1]).name == "build_cbsros_ddf_leg.py":
                    seen["n"] += 1
                    if seen["n"] > 3:
                        return False, "leg exploded"
                    leg = (fake.repo / "data" / "ddf-two-tier"
                           / f"ddf-20261007-cbsros-x-{seen['n']}t-0p15" / "ddf_leg_cbsros.json")
                    leg.parent.mkdir(parents=True, exist_ok=True)
                    leg.write_text("NEW")
                    return True, ""
                return fake(cmd, **kw)
            return run_fn
        run = run_chain(self.tmp / "cbsros", wrap=wrap)
        self.assertTrue(run["status"]["success"], run["status"]["failed"])
        self.assertIn("cbsros", run["status"]["held"])
        self.assertEqual(run["after"]["sources"]["cbsros"], run["before"]["sources"]["cbsros"])
        check_legs_kept(run, "cbsros")

    def test_week_ten_snapshot_beats_week_nine_and_committed_week_four(self):
        """`week-10` sorted before `week-4` by name: from Week 10 the chain
        would rebuild FantasyCalc/CBS from the committed Week 4 snapshot."""
        repo = self.tmp / "sort"
        for d in ("week-4", "week-9", "week-10", "_archived"):
            p = repo / "data" / "raw" / "sources" / "fantasycalc" / d
            p.mkdir(parents=True)
            (p / "snapshot.json").write_text("{}")
        self.assertEqual(chain.find_latest_snapshot(repo, "fantasycalc").parent.name, "week-10")
        for d in ("2026-09-29", "2026-10-06", "2026-12-01"):
            p = repo / "data" / "raw" / "sources" / "usatoday" / d
            p.mkdir(parents=True)
            (p / "snapshot.json").write_text("{}")
        self.assertEqual(chain.find_latest_snapshot(repo, "usatoday").parent.name, "2026-12-01")

    # --- still fail-closed -----------------------------------------------------
    def test_supabase_outage_for_every_chart_still_fails_closed(self):
        """Nothing new to publish: every review-gated source failed."""
        run = run_chain(self.tmp / "outage", drop_snapshots=GATED)
        self.assertFalse(run["status"]["success"])
        self.assertIn("all_review_gated_sources_held", run["status"]["failed"])
        for s in GATED:
            self.assertEqual(run["after"]["sources"][s], run["before"]["sources"][s])

    def test_unverifiable_leg_restore_fails_closed(self):
        def bad_restore(repo, source, before_legs):
            raise ValueError("disk full")
        with mock.patch.object(chain, "_restore_legs", bad_restore):
            run = run_chain(self.tmp / "legfail", wrap=failing("build_espn_section_from_ddf_leg.py"))
        self.assertFalse(run["status"]["success"])
        self.assertIn("espn", run["status"]["failed"])

    # --- negative tests ----------------------------------------------------------
    def test_all_or_nothing_on_failures_is_caught(self):
        with mock.patch.object(chain, "FAILURE_ISOLATED_SOURCES", ()):
            run = run_chain(self.tmp / "neg1", drop_snapshots=("usatoday",))
        with self.assertRaises(AssertionError):
            check_failed_source_kept_and_others_publish(run, "usatoday")

    def test_section_only_restore_is_caught(self):
        """Restoring the ESPN section but not its legs leaves a fresh, half
        anchor beside the kept section."""
        with mock.patch.object(chain, "_restore_legs", lambda *a, **k: None):
            run = run_chain(self.tmp / "neg2", wrap=failing("build_espn_section_from_ddf_leg.py"))
        self.assertTrue(run["status"]["success"])  # the broken chain would publish this
        with self.assertRaises(AssertionError):
            check_legs_kept(run)

    def test_name_sorted_snapshots_are_caught(self):
        with mock.patch.object(chain, "snapshot_sort_key", lambda p: p.name):
            repo = self.tmp / "neg3"
            for d in ("week-4", "week-10"):
                p = repo / "data" / "raw" / "sources" / "cbs" / d
                p.mkdir(parents=True)
                (p / "snapshot.json").write_text("{}")
            self.assertEqual(chain.find_latest_snapshot(repo, "cbs").parent.name, "week-4")


# --- workflow: the import loop and the ESPN bake ---------------------------------
FAKE_PY = """#!/bin/bash
if [ "$1" = "-c" ]; then exec "{real}" "$@"; fi
echo "$@" >> "$CALLS"
case "$1" in
  pipelines/import_supabase_references.py)
    [ "$3" = "$FAIL_SOURCE" ] && {{ echo "Fail closed: zero rows" >&2; exit 1; }}; exit 0;;
  pipelines/rebuild_comparison_chain.py)
    mkdir -p output
    echo "{{\\"held\\": [$HELD], \\"success\\": true}}" > output/comparison-chain-status.json
    exit 0;;
esac
exit 0
"""
FAKE_MAKE = """#!/bin/bash
cat data/inputs/espn_projections.csv >> "$VALIDATED_ANCHOR"
exit 0
"""


def run_step(text, step, cwd, env):
    script = script_of(find_step(text, step))
    script = script.replace("${{ steps.week.outputs.nfl_week }}", "6")
    return subprocess.run(["bash", "-e", "-c", script], cwd=cwd, env=env,
                          capture_output=True, text=True)


def workflow_env(td, **extra):
    bindir = td / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "python3").write_text(FAKE_PY.format(real=sys.executable))
    (bindir / "make").write_text(FAKE_MAKE)
    for f in ("python3", "make"):
        os.chmod(bindir / f, 0o755)
    return {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(td), "CALLS": str(td / "calls"),
            "VALIDATED_ANCHOR": str(td / "validated"), "HELD": "", "FAIL_SOURCE": "", **extra}


def import_problems(text):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        env = workflow_env(td, FAIL_SOURCE="usatoday")
        proc = run_step(text, IMPORT_STEP, td, env)
        calls = (td / "calls").read_text() if (td / "calls").exists() else ""
        imported = [line.split()[-1] for line in calls.splitlines()]
        problems = []
        if proc.returncode != 0:
            problems.append(f"one failed import ended the step (exit {proc.returncode})")
        for src in ("fantasypros", "espn", "cbs", "cbsros", "razzball"):
            if src not in imported:
                problems.append(f"{src} was never imported after usatoday failed")
        return problems


def bake_revert_problems(text):
    problems = []
    for held, bake, want in (('"espn"', "success", "OLD"), ('"cbs"', "success", "NEW"),
                             ('"espn"', "skipped", "NEW")):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            work = td / "w"
            work.mkdir()
            git = lambda *a: subprocess.run(["git", *a], cwd=work, check=True,  # noqa: E731
                                            capture_output=True)
            git("init", "-q")
            for rel in ("data/inputs/espn_projections.csv", "data/fixtures/current/players.json",
                        "data/fixtures/current/players.naming-manifest.json"):
                (work / rel).parent.mkdir(parents=True, exist_ok=True)
                (work / rel).write_text("OLD")
            git("add", "-A")
            git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
            # What the bake step leaves on disk.
            (work / "data/inputs/espn_projections.csv").write_text("NEW")
            env = workflow_env(td, HELD=held, BAKE_OUTCOME=bake)
            proc = run_step(text, CHAIN_STEP, work, env)
            got = (td / "validated").read_text() if (td / "validated").exists() else None
            if proc.returncode != 0:
                problems.append(f"chain step exited {proc.returncode} (held={held}, bake={bake}): "
                                f"{proc.stderr[-200:]}")
            elif got != want:
                problems.append(f"held={held} bake={bake}: validate saw anchor {got!r}, want {want!r}")
    return problems


class WorkflowResiliencyTest(unittest.TestCase):
    def test_one_failed_import_does_not_end_the_job(self):
        self.assertEqual(import_problems(WORKFLOW), [])

    def test_fail_fast_import_loop_is_caught(self):
        old = WORKFLOW.split("          failed_imports=\"\"\n")[0] + (
            "          for src in fantasycalc usatoday fantasypros espn cbs cbsros razzball; do\n"
            "            python3 pipelines/import_supabase_references.py --source \"$src\"\n"
            "          done\n") + WORKFLOW.split("Imports failed:$failed_imports\"; fi\n")[1]
        self.assertNotEqual(old, WORKFLOW)
        self.assertTrue(import_problems(old))

    def test_failed_espn_chain_keeps_the_committed_anchor(self):
        self.assertEqual(bake_revert_problems(WORKFLOW), [])

    def test_shipping_a_fresh_bake_beside_a_kept_espn_section_is_caught(self):
        start = WORKFLOW.index('          if [ "${BAKE_OUTCOME:-}" = "success" ] && python3 -c')
        end = WORKFLOW.index("          mkdir -p output\n", start)
        broken = WORKFLOW[:start] + WORKFLOW[end:]
        self.assertTrue(bake_revert_problems(broken))


if __name__ == "__main__":
    unittest.main()
