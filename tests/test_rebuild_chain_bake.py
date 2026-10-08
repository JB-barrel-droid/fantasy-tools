"""The daily ESPN anchor bake in rebuild-chain.yml (bake_players=true).

players.json (the ESPN anchor every other chart indexes to) and the ESPN CSV
behind it only moved on a manual refresh, while the scrape saved fresh ESPN
rows to Supabase every day (2026-10-07: anchor 2026-10-03, Supabase 2026-10-07).
The bake now rides inside the comparison-chain run, which pins these rules:

  - the bake runs only when dispatched with bake_players=true, before the chain;
  - the bake step never commits or pushes: the baked files reach main only
    through the commit step's success branch, i.e. after the chain step's
    `make validate` passed on them (validate-before-push, main-only-on-green);
  - a red chain pushes none of the baked files;
  - a failed bake restores the committed anchor, so a half-written bake can
    never ride along with a green chain;
  - the ESPN scrape uploads the CSV the bake downloads.

Like tests/test_rebuild_chain_workflow.py these execute the real `run:`
scripts against throwaway git repos, and every rule is negative-tested against
a mutated copy of the real workflow.
"""
import re
import tempfile
import unittest
from pathlib import Path

from tests.test_rebuild_chain_workflow import (
    BASELINE, CHAIN, COMMIT, FAIL, PUBLISH_RED, SYNC_OK, find_step, git,
    run_script, script_of, write,
)

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github/workflows/rebuild-chain.yml").read_text(encoding="utf-8")
ESPN_WORKFLOW = (ROOT / ".github/workflows/espn-supabase-sync.yml").read_text(encoding="utf-8")

BAKE = "Refresh ESPN anchor and bake players.json"
DECIDE = "Decide whether to bake players.json"
IMPORT = "Import fresh snapshots from Supabase"
RESTORE = "Restore committed ESPN anchor (bake failed)"
UPLOAD = "Upload saved ESPN CSV for the anchor bake"
CSV = "data/inputs/espn_projections.csv"
PLAYERS = "data/fixtures/current/players.json"
MANIFEST = "data/fixtures/current/players.naming-manifest.json"
BAKED = (CSV, PLAYERS, MANIFEST)
FIXTURE = "data/fixtures/current/comparison-sources-data.json"


def static_problems(text, espn_text=ESPN_WORKFLOW):
    problems = []
    if not re.search(r"^      bake_players:\s*$", text, re.M):
        problems.append("workflow_dispatch input bake_players is not declared "
                        "(the pg_cron dispatch would get HTTP 422)")
    bake = find_step(text, BAKE)
    if bake is None:
        return problems + ["bake step missing"]
    # GAP-BAKE-ON-CHANGE (2026-10-08): the rule changed from "only when
    # bake_players == 'true'" to "when the decide step says so", which is
    # bake_players == 'true' OR a projection input that differs from the one
    # players.json was baked from (pipelines/projection_identity.py decide).
    if "if: steps.decide.outputs.bake == 'true'" not in bake:
        problems.append("bake step must run only when the decide step says bake")
    decide = find_step(text, DECIDE)
    decide_script = script_of(decide or "") or ""
    if decide is None or "id: decide" not in decide:
        problems.append("decide step missing (id: decide)")
    elif "projection_identity.py decide" not in decide_script:
        problems.append("decide step does not run projection_identity.py decide")
    elif "--force" not in decide_script or "github.event.inputs.bake_players" not in decide:
        problems.append("decide step ignores bake_players (the daily forced bake)")
    if "check_espn_bake_csv.py" not in decide_script:
        problems.append("decide step does not check the ESPN scrape CSV (check_espn_bake_csv.py)")
    if "id: bake" not in bake:
        problems.append("bake step must have id: bake (restore and commit read its outcome)")
    script = script_of(bake) or ""
    for forbidden in ("git commit", "git push"):
        if forbidden in script:
            problems.append(f"bake step runs `{forbidden}`: baked files must reach main "
                            "only through the commit step, after validate")
    for needed in ("bake_players.py", "pin_naming_manifest.py",
                   "--cbsros-snapshot", "--razzball-snapshot"):
        if needed not in script:
            problems.append(f"bake step does not run {needed}")
    restore = find_step(text, RESTORE)
    if restore is None or "if: steps.bake.outcome == 'failure'" not in restore:
        problems.append("a failed bake must restore the committed anchor")
    chain = find_step(text, CHAIN) or ""
    if "make validate" not in (script_of(chain) or ""):
        problems.append("chain step no longer runs make validate before the commit")
    order = [text.find(f"name: {n}") for n in (IMPORT, DECIDE, BAKE, RESTORE, CHAIN, COMMIT)]
    if -1 in order or order != sorted(order):
        problems.append("steps are not in the order import, decide, bake, restore, chain, commit")
    upload = find_step(espn_text, UPLOAD)
    if upload is None or "name: espn-projections" not in upload \
            or "/tmp/espn_projections.csv" not in upload:
        problems.append("espn-supabase-sync.yml does not upload the espn-projections CSV")
    return problems


def run_bake_scenario(text, chain_outcome, bake_outcome):
    """Simulate a run after the bake: real restore/sync/publish/commit/fail scripts."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        remote, work = td / "remote.git", td / "work"
        git(td, "init", "-q", "--bare", "-b", "main", str(remote))
        git(td, "clone", "-q", str(remote), str(work))
        git(work, "checkout", "-q", "-b", "main")
        for rel, content in {**BASELINE, **{b: "OLD-ANCHOR" for b in BAKED}}.items():
            write(work, rel, content)
        git(work, "add", "-A")
        git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "baseline")
        git(work, "push", "-q", "-u", "origin", "main")
        base = git(work, "rev-parse", "HEAD")

        # What the bake step leaves on disk: a full bake, or a half-written one.
        for rel in BAKED:
            write(work, rel, "NEW-ANCHOR" if bake_outcome == "success" else "PARTIAL-BAKE")
        steps = [RESTORE] if bake_outcome == "failure" else []
        if chain_outcome == "success":
            write(work, FIXTURE, "NEW")
            steps += [SYNC_OK, COMMIT]
        else:
            write(work, FIXTURE, "PARTIAL")
            steps += [PUBLISH_RED, COMMIT, FAIL]
        env = {"CHAIN_OUTCOME": chain_outcome, "BAKE_OUTCOME": bake_outcome,
               "GITHUB_OUTPUT": str(td / "gh_out.txt")}
        rcs = {}
        for step in steps:
            if find_step(text, step) is None:
                rcs[step] = None
                continue
            rcs[step] = run_script(text, step, work, env).returncode
        verify = td / "verify"
        git(td, "clone", "-q", str(remote), str(verify))
        changed = set(git(verify, "diff", "--name-only", base, "HEAD").splitlines())
        return {"changed": changed,
                "remote": {rel: (verify / rel).read_text(encoding="utf-8") for rel in BAKED},
                "rcs": rcs}


def behaviour_problems(text):
    problems = []
    green = run_bake_scenario(text, "success", "success")
    for rel in BAKED:
        if green["remote"][rel] != "NEW-ANCHOR":
            problems.append(f"a green chain after a good bake did not push {rel}")
    red = run_bake_scenario(text, "failure", "success")
    for rel in BAKED:
        if rel in red["changed"]:
            problems.append(f"a red chain (validate failed) pushed baked {rel}")
    if red["rcs"].get(FAIL) in (None, 0):
        problems.append("the job does not fail loudly after a red chain")
    broken_bake = run_bake_scenario(text, "success", "failure")
    for rel in BAKED:
        if broken_bake["remote"][rel] != "OLD-ANCHOR":
            problems.append(f"a failed bake's partial {rel} reached main with a green chain")
    if broken_bake["rcs"].get(RESTORE) not in (0,):
        problems.append("the restore step did not run cleanly after a failed bake")
    return problems


class RebuildChainBakeTest(unittest.TestCase):
    def test_real_workflow_static_rules(self):
        self.assertEqual([], static_problems(WORKFLOW))

    def test_real_workflow_behaviour(self):
        self.assertEqual([], behaviour_problems(WORKFLOW))

    # --- each rule caught against a simulated broken workflow ---

    def test_catches_bake_that_pushes_itself(self):
        broken = WORKFLOW.replace(
            '          python3 pipelines/pin_naming_manifest.py --source-label "supabase:players"\n',
            '          python3 pipelines/pin_naming_manifest.py --source-label "supabase:players"\n'
            '          git commit -am bake && git push origin HEAD:main\n', 1)
        self.assertNotEqual(broken, WORKFLOW)
        self.assertTrue(any("git push" in p for p in static_problems(broken)))

    def test_catches_baked_files_pushed_on_a_red_chain(self):
        # Stage the baked anchor in the failure (status-only) branch too.
        marker = "            # Chain failed: stage ONLY the status and health files, never the fixture.\n"
        broken = WORKFLOW.replace(marker, marker + f"            git add {PLAYERS} {CSV}\n", 1)
        self.assertNotEqual(broken, WORKFLOW)
        self.assertTrue(any("red chain" in p and PLAYERS in p
                            for p in behaviour_problems(broken)))

    def test_catches_green_chain_not_shipping_the_bake(self):
        broken = WORKFLOW.replace(
            "            git add data/inputs/espn_projections.csv \\\n"
            "                    data/fixtures/current/players.json \\\n"
            "                    data/fixtures/current/players.naming-manifest.json || true\n",
            "", 1)
        self.assertNotEqual(broken, WORKFLOW)
        self.assertTrue(any("did not push" in p for p in behaviour_problems(broken)))

    def test_catches_missing_restore_after_failed_bake(self):
        block = find_step(WORKFLOW, RESTORE)
        broken = WORKFLOW.replace(block + "\n", "", 1)
        self.assertNotEqual(broken, WORKFLOW)
        self.assertTrue(any("partial" in p for p in behaviour_problems(broken)))
        self.assertTrue(any("restore" in p for p in static_problems(broken)))

    def test_catches_bake_after_the_chain(self):
        bake = find_step(WORKFLOW, BAKE)
        moved = WORKFLOW.replace(bake + "\n", "", 1)
        commit = find_step(moved, COMMIT)
        moved = moved.replace(commit, bake + "\n" + commit, 1)
        self.assertTrue(any("order" in p for p in static_problems(moved)))

    def test_catches_validate_removed_from_the_chain(self):
        broken = WORKFLOW.replace(
            "env -u SUPABASE_URL -u SUPABASE_SERVICE_KEY make validate",
            "env -u SUPABASE_URL -u SUPABASE_SERVICE_KEY true", 1)
        self.assertNotEqual(broken, WORKFLOW)
        self.assertTrue(any("make validate" in p for p in static_problems(broken)))

    def test_catches_unconditional_bake(self):
        broken = WORKFLOW.replace(
            "        if: steps.decide.outputs.bake == 'true'\n", "", 1)
        self.assertNotEqual(broken, WORKFLOW)
        self.assertTrue(any("decide step says bake" in p for p in static_problems(broken)))

    def test_catches_bake_that_ignores_the_daily_forced_input(self):
        broken = WORKFLOW.replace('decide --force "${FORCE:-false}"', "decide", 1)
        self.assertNotEqual(broken, WORKFLOW)
        self.assertTrue(any("ignores bake_players" in p for p in static_problems(broken)))

    def test_catches_bake_before_the_import(self):
        # The bake must read the snapshots the import step just wrote (the
        # ones the chain builds the sections from), so it runs after it.
        imp = find_step(WORKFLOW, IMPORT)
        moved = WORKFLOW.replace(imp + "\n", "", 1)
        commit = find_step(moved, COMMIT)
        moved = moved.replace(commit, imp + "\n" + commit, 1)
        self.assertTrue(any("order" in p for p in static_problems(moved)))

    def test_catches_missing_espn_artifact_upload(self):
        broken_espn = ESPN_WORKFLOW.replace("name: espn-projections", "name: something-else", 1)
        self.assertNotEqual(broken_espn, ESPN_WORKFLOW)
        self.assertTrue(any("espn-projections" in p
                            for p in static_problems(WORKFLOW, broken_espn)))


class CheckEspnBakeCsvTest(unittest.TestCase):
    """pipelines/check_espn_bake_csv.py: refuse a CSV that is not Supabase's latest."""

    def setUp(self):
        from pipelines import check_espn_bake_csv as mod
        self.mod = mod
        self.header = list(mod.REQUIRED_COLUMNS)
        self.rows = [{**{c: "1" for c in self.header}, "eligible": "True",
                      "espn_snapshot_date": "2026-10-07"} for _ in range(120)]

    def test_clean_csv_passes(self):
        self.assertEqual([], self.mod.csv_problems(self.header, self.rows, "2026-10-07"))

    def test_older_artifact_than_supabase_is_refused(self):
        # The 2026-10-07 state: committed anchor 2026-10-03, Supabase 2026-10-07.
        rows = [{**r, "espn_snapshot_date": "2026-10-03"} for r in self.rows]
        self.assertTrue(any("!= Supabase latest" in p
                            for p in self.mod.csv_problems(self.header, rows, "2026-10-07")))

    def test_short_or_mixed_or_misshapen_csv_is_refused(self):
        self.assertTrue(self.mod.csv_problems(self.header, self.rows[:50], "2026-10-07"))
        mixed = self.rows[:-1] + [{**self.rows[0], "espn_snapshot_date": "2026-10-06"}]
        self.assertTrue(self.mod.csv_problems(self.header, mixed, "2026-10-07"))
        self.assertTrue(self.mod.csv_problems(self.header[:-3], self.rows, "2026-10-07"))
        self.assertTrue(self.mod.csv_problems(self.header, self.rows, None))


if __name__ == "__main__":
    unittest.main()
