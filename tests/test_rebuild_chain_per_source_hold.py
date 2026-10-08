"""Per-source promotion guards (decision per-source-promotion-001, 2026-10-07).

A review 'hold' in one published-chart source (usatoday, fantasycalc,
fantasypros, cbs) no longer fails the whole chain. The held source keeps its
last promoted fixture section, exactly, and the other sources publish. The
hold is never overridden, and everything else still fails closed.

Every guard here is negative-tested in the same file: each `*_is_caught`
test simulates the broken state the guard names (all-or-nothing chain, a held
section left half-promoted, a held candidate promoted anyway, an all-held run
published, a non-hold failure isolated as if it were a hold) and shows the
guard's check fires.

All stage scripts are faked; filesystem writes go to temp dirs.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "tests"))
import rebuild_comparison_chain as chain  # noqa: E402
import record_chain_holds as holds  # noqa: E402
from test_rebuild_chain_failclosed import WireFake, make_repo  # noqa: E402

FIXTURE_REL = Path("data/fixtures/current/comparison-sources-data.json")
GATED = ("usatoday", "fantasycalc", "fantasypros", "cbs")
OLD_BUILT_AT = "2026-10-03T00:00:00+00:00"


def seed_fixture(repo):
    """Last promoted state: every review-gated source at Week 4."""
    sources = {
        s: {"week_designated": "Week 4", "content_vintage": "Week 4",
            "combos": {"full_12": {"values": {"old player": 50.0}, "marker": "old"}}}
        for s in GATED
    }
    path = Path(repo) / FIXTURE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"built_at": OLD_BUILT_AT, "sources": sources}))
    return json.loads(path.read_text(encoding="utf-8"))


class PromotingFake(WireFake):
    """WireFake whose promoter really merges into the fixture, like the real one.

    Reference files carry the source name, so each section/review stem is
    "<source>-<a|b>-reference-section"; promote merges combo "<letter>_new"
    into sources[<source>], restamps the whole section Week 5 (the real
    promoter's whole-section vintage stamp), bumps built_at, and writes a
    promotion record. Every promote attempt is logged with its verdict.
    """

    def __init__(self, repo, verdicts=None):
        super().__init__(repo, verdicts)
        self.promote_attempts = []  # (stem, verdict)

    def __call__(self, cmd, **kwargs):
        script = Path(cmd[1]).name
        repo = self.repo
        if script == "build_source_reference.py":
            self.calls.append(script)
            matched = Path(cmd[cmd.index("--input") + 1])
            source = matched.relative_to(repo / "output" / "matched").parts[0]
            for letter in ("a", "b"):
                self._touch(repo / "output" / "references" / source / "2026-10-07"
                            / f"{source}-{letter}-reference.json", "{}")
            return True, ""
        if script == "promote_comparison_section.py":
            self.calls.append(script)
            review_path = Path(cmd[2])
            verdict = json.loads(review_path.read_text(encoding="utf-8")).get("verdict")
            stem = review_path.name.replace("-review.json", "")
            self.promote_attempts.append((stem, verdict))
            if verdict != "ready":  # faithful: the real promoter refuses
                return False, "promotion refused: review verdict is not 'ready'"
            source, letter = stem.split("-")[0], stem.split("-")[1]
            path = repo / FIXTURE_REL
            fixture = json.loads(path.read_text(encoding="utf-8"))
            section = fixture["sources"].setdefault(source, {"combos": {}})
            section["combos"][f"{letter}_new"] = {"values": {"new player": 60.0}, "marker": "new"}
            section["week_designated"] = "Week 5"
            section["content_vintage"] = "Week 5"
            fixture["built_at"] = f"2026-10-07T00:00:0{len(self.promote_attempts)}+00:00"
            path.write_text(json.dumps(fixture, separators=(",", ":")))
            self._touch(repo / "output" / "comparison-promotions"
                        / f"{source}-2026-10-07-{letter}-promotion.json", "{}")
            return True, ""
        if script == "build_cbsros_section_from_ddf_leg.py":
            # Parent fake overwrites the whole fixture; merge instead.
            path = repo / FIXTURE_REL
            keep = json.loads(path.read_text(encoding="utf-8"))
            ok, out = super().__call__(cmd, **kwargs)
            keep["sources"]["cbsros"] = json.loads(path.read_text(encoding="utf-8"))["sources"]["cbsros"]
            path.write_text(json.dumps(keep))
            return ok, out
        return super().__call__(cmd, **kwargs)


def run_chain(tmp, verdicts, nfl_week=5, run_fn_wrap=None):
    repo = make_repo(tmp, tuple(chain.SOURCES))
    before = seed_fixture(repo)
    fake = PromotingFake(repo, verdicts=verdicts)
    run_fn = run_fn_wrap(fake) if run_fn_wrap else fake
    status = chain.execute_chain(nfl_week=nfl_week, repo=repo, run_fn=run_fn)
    after = json.loads((repo / FIXTURE_REL).read_text(encoding="utf-8"))
    return status, before, after, fake, repo


# --- guard checks (each is negative-tested below) ----------------------------
def check_others_publish_despite_hold(status, after, held="fantasycalc"):
    assert status["success"] is True, status["failed"]
    assert status["outcome"] == "published_with_holds", status["outcome"]
    assert status["held"] == [held], status["held"]
    for s in GATED:
        if s != held:
            assert after["sources"][s]["week_designated"] == "Week 5", s
    assert status["fit"]["status"] == "ok" and status["adjusted_sections"]["status"] == "ok"


def check_held_section_kept_exactly(before, after, source="fantasycalc"):
    assert after["sources"][source] == before["sources"][source], after["sources"][source]


def check_held_candidate_never_promoted(fake):
    bad = [a for a in fake.promote_attempts if a[1] != "ready"]
    assert not bad, f"promote attempted on non-ready review(s): {bad}"


def check_fails_closed(status):
    assert status["success"] is False
    assert status["outcome"] == "failed"
    assert status["fit"]["status"] == "skipped"


class PerSourceHoldTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="per-source-hold-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _hold_fc_second_section(self, **kw):
        # Section a promotes (half-promotion), section b holds.
        return run_chain(self.tmp / "run", {"fantasycalc-b-reference-section": "hold"}, **kw)

    # --- positive behaviour --------------------------------------------------
    def test_one_held_source_does_not_block_the_others(self):
        status, before, after, fake, _ = self._hold_fc_second_section()
        check_others_publish_despite_hold(status, after)
        self.assertIn("HELD at stage 'review'", status["sources"]["fantasycalc"])

    def test_half_promoted_held_source_is_restored_exactly(self):
        status, before, after, fake, repo = self._hold_fc_second_section()
        # The first FantasyCalc section really was merged mid-run...
        self.assertIn(("fantasycalc-a-reference-section", "ready"), fake.promote_attempts)
        # ...and was rolled back: the published section is the pre-run one.
        check_held_section_kept_exactly(before, after)
        detail = status["held_detail"]["fantasycalc"]
        self.assertEqual(detail["rolled_back"], 1)
        self.assertEqual(detail["kept_section"]["week_designated"], "Week 4")
        # The rolled-back promotion record no longer reads as a promotion.
        promos = {p.name for p in (repo / "output" / "comparison-promotions").iterdir()}
        self.assertNotIn("fantasycalc-2026-10-07-a-promotion.json", promos)
        self.assertIn("fantasycalc-2026-10-07-a-promotion.rolled-back.json", promos)
        self.assertIn("usatoday-2026-10-07-a-promotion.json", promos)

    def test_held_candidate_is_never_promoted(self):
        status, before, after, fake, _ = self._hold_fc_second_section()
        check_held_candidate_never_promoted(fake)
        review = json.loads((fake.repo / "output" / "reviewed"
                             / "fantasycalc-b-reference-section-review.json").read_text(encoding="utf-8"))
        self.assertEqual(review["verdict"], "hold")  # never rewritten

    def test_one_week_hold_is_amber_two_weeks_is_red(self):
        status, *_ = self._hold_fc_second_section(nfl_week=5)
        self.assertEqual(status["held_detail"]["fantasycalc"]["hold_severity"], "amber")
        self.assertEqual(status["hold_severity"], "amber")
        shutil.rmtree(self.tmp / "run")
        status, *_ = self._hold_fc_second_section(nfl_week=6)
        self.assertEqual(status["held_detail"]["fantasycalc"]["weeks_behind"], 2)
        self.assertEqual(status["hold_severity"], "red")
        # Red still does not block the others from publishing.
        self.assertTrue(status["success"])

    def test_all_review_gated_sources_held_fails_closed(self):
        status, before, after, fake, _ = run_chain(self.tmp / "all", {"*": "hold"})
        check_fails_closed(status)
        self.assertIn("all_review_gated_sources_held", status["failed"])

    # Rule changed by Jeremy 2026-10-08 (source-resiliency-001): a non-hold
    # failure in one source, and an ESPN failure, are now isolated like a
    # hold (they used to fail the whole chain). Full coverage, with the
    # negative tests, is in tests/test_rebuild_chain_source_resiliency.py.
    def test_non_hold_failure_is_isolated(self):
        """A garbage verdict (not 'hold') in one source keeps its last section."""
        status, before, after, *_ = run_chain(
            self.tmp / "garbage", {"usatoday-a-reference-section": "banana"})
        self.assertTrue(status["success"], status["failed"])
        self.assertIn("usatoday", status["held"])
        check_held_section_kept_exactly(before, after, "usatoday")

    def test_espn_failure_is_isolated_alongside_a_hold(self):
        def wrap(fake):
            def run_fn(cmd, **kw):
                if Path(cmd[1]).name == "build_espn_section_from_ddf_leg.py":
                    return False, "espn section exploded"
                return fake(cmd, **kw)
            return run_fn
        status, before, after, *_ = run_chain(
            self.tmp / "espn", {"fantasycalc-b-reference-section": "hold"}, run_fn_wrap=wrap)
        self.assertTrue(status["success"], status["failed"])
        self.assertEqual(status["held"], ["espn", "fantasycalc"])
        check_held_section_kept_exactly(before, after)

    def test_unverifiable_restore_fails_closed(self):
        real_read = chain._read_fixture
        calls = {"n": 0}

        def flaky_read(repo):
            # Fail the post-restore verification read inside isolate_hold.
            data = real_read(repo)
            if calls.get("arm"):
                data["sources"]["fantasycalc"]["combos"]["tamper"] = {}
            return data

        orig_isolate = chain.isolate_hold

        def armed_isolate(*a, **k):
            calls["arm"] = True
            try:
                return orig_isolate(*a, **k)
            finally:
                calls["arm"] = False

        with mock.patch.object(chain, "_read_fixture", flaky_read), \
                mock.patch.object(chain, "isolate_hold", armed_isolate):
            status, *_ = self._hold_fc_second_section()
        check_fails_closed(status)
        self.assertIn("fantasycalc", status["failed"])

    def test_chain_exit_code_follows_success(self):
        for success, code in ((True, 0), (False, 1)):
            with mock.patch.object(chain, "execute_chain", return_value={"success": success}), \
                    mock.patch.object(sys, "argv", ["rebuild_comparison_chain.py"]):
                self.assertEqual(chain.main(), code)

    # --- negative tests: each guard catches the broken state it names --------
    def test_all_or_nothing_chain_is_caught(self):
        """Reverting to all-or-nothing (no isolated sources) fails the guard."""
        with mock.patch.object(chain, "HOLD_ISOLATED_SOURCES", ()), \
                mock.patch.object(chain, "FAILURE_ISOLATED_SOURCES", ()):
            status, before, after, *_ = self._hold_fc_second_section()
        with self.assertRaises(AssertionError):
            check_others_publish_despite_hold(status, after)

    def test_half_promoted_held_section_is_caught(self):
        """A hold that is marked held but NOT restored leaves FantasyCalc
        half-promoted (section a merged, whole section stamped Week 5)."""
        def no_restore(repo, source, before, result, nfl_week=None):
            result.update(status="held", hold_severity="amber", kept_section={}, weeks_behind=1)
            return result
        with mock.patch.object(chain, "isolate_hold", no_restore):
            status, before, after, *_ = self._hold_fc_second_section()
        self.assertTrue(status["success"])  # the broken chain would publish this
        with self.assertRaises(AssertionError):
            check_held_section_kept_exactly(before, after)

    def test_held_candidate_promoted_anyway_is_caught(self):
        """A chain that pushes a held review through promote is caught."""
        real = chain.process_section

        def override(section, repo, run_fn, nfl_week=None):
            try:
                return real(section, repo, run_fn, nfl_week=nfl_week)
            except chain.ReviewHold:
                review = Path(repo) / "output" / "reviewed" / f"{section.stem}-review.json"
                run_fn(["python3", "pipelines/promote_comparison_section.py", str(review), "--auto"])
                raise
        with mock.patch.object(chain, "process_section", override):
            status, before, after, fake, _ = self._hold_fc_second_section()
        with self.assertRaises(AssertionError):
            check_held_candidate_never_promoted(fake)

    def test_publishing_an_all_held_run_is_caught(self):
        with mock.patch.object(chain, "all_review_gated_held", return_value=False):
            status, *_ = run_chain(self.tmp / "allneg", {"*": "hold"})
        with self.assertRaises(AssertionError):
            check_fails_closed(status)

    def test_severity_that_never_goes_red_is_caught(self):
        status, *_ = self._hold_fc_second_section(nfl_week=6)
        self.assertEqual(status["hold_severity"], "red")
        shutil.rmtree(self.tmp / "run")
        with mock.patch.object(chain, "section_week", return_value=6):
            status, *_ = self._hold_fc_second_section(nfl_week=6)
        self.assertNotEqual(status["hold_severity"], "red")


class SectionWeekTest(unittest.TestCase):
    def test_week_sources(self):
        self.assertEqual(chain.section_week({"week_designated": "Week 4"}), 4)
        self.assertEqual(chain.section_week({"content_vintage": "Week 3"}), 3)
        self.assertEqual(chain.section_week({"content_vintage": "2026-09-29"}), 4)
        self.assertIsNone(chain.section_week({"week_designated": "rest of season"}))
        self.assertIsNone(chain.section_week(None))


class RecordChainHoldsTest(unittest.TestCase):
    def _status(self, held, severity="amber"):
        return {"held": held, "held_detail": {s: {"hold_severity": severity} for s in held}}

    def _ok(self, payloads):
        return {p["p_check_id"]: p["p_ok"] for p in payloads}

    def test_no_holds_records_both_ok(self):
        p = holds.build_payloads(self._status([]), "rebuild-chain.yml", "success")
        self.assertEqual(self._ok(p), {holds.CHECK_HELD: True, holds.CHECK_HELD_STALE: True})

    def test_one_week_hold_is_amber_only(self):
        p = holds.build_payloads(self._status(["fantasycalc"]), "rebuild-chain.yml", "success")
        self.assertEqual(self._ok(p), {holds.CHECK_HELD: False, holds.CHECK_HELD_STALE: True})
        self.assertEqual(p[0]["p_error_code"], "SOURCE_HELD:fantasycalc")

    def test_two_week_hold_is_red(self):
        p = holds.build_payloads(self._status(["cbs"], "red"), "rebuild-chain.yml", "success")
        self.assertEqual(self._ok(p), {holds.CHECK_HELD: False, holds.CHECK_HELD_STALE: False})

    def test_unreadable_status_after_a_run_is_not_ok(self):
        p = holds.build_payloads(None, "rebuild-chain.yml", "failure")
        self.assertEqual(self._ok(p), {holds.CHECK_HELD: False, holds.CHECK_HELD_STALE: False})

    def test_skipped_chain_records_nothing(self):
        self.assertEqual(holds.build_payloads(self._status(["cbs"]), "x", "skipped"), [])

    def test_recorder_that_reports_a_hold_as_ok_is_caught(self):
        """Negative: a recorder ignoring `held` would report a hold green."""
        broken = lambda status, owner, outcome: holds.build_payloads(  # noqa: E731
            {"held": [], "held_detail": {}}, owner, outcome)
        p = broken(self._status(["fantasycalc"]), "rebuild-chain.yml", "success")
        self.assertNotEqual(self._ok(p)[holds.CHECK_HELD],
                            self._ok(holds.build_payloads(self._status(["fantasycalc"]),
                                                          "rebuild-chain.yml", "success"))[holds.CHECK_HELD])

    def test_amber_hold_with_unknown_severity_counts_as_red(self):
        p = holds.build_payloads({"held": ["cbs"], "held_detail": {}}, "o", "success")
        self.assertFalse(self._ok(p)[holds.CHECK_HELD_STALE])


if __name__ == "__main__":
    unittest.main()
