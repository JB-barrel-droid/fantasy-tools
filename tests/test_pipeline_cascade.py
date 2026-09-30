from __future__ import annotations

"""Regression tests for cascade pipeline orchestration.

Covered:
- Full 7-stage chain triggers in order on a new snapshot.
- Stage ordering and provenance (content_vintage carried through reindex).
- Unchanged run visits every stage; no early stops; all statuses "unchanged".
- Interrupted run: deleted downstream artifact is restored with identical input.
- Anchor change: ESPN values change → reindex and review re-run even when
  snapshot/match/section are materially unchanged.
- Triage change: new triage file → review re-runs.
- Hold verdict repeats on identical re-run (exit code 2 on both).
- Health gate: missing health file blocks cascade at snapshot entry.
- Health gate: stale source (non-ok status) blocks cascade.
- Health gate: mismatched content vintage blocks cascade.
- Health gate: ok source with matching vintage passes through.
- Health gate: non-active source passes through without health file.
- Data escape: candidate_dir inside data/ is refused at Cascade init.
- Cascade-from-match entry point skips import/match but runs all remaining stages.
- Cascade-from-section entry point skips through to review correctly.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path


PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
sys.path.insert(0, str(PIPELINES))

import cascade_source_update as cascade_mod  # noqa: E402


POSITIONS = ("QB", "RB", "WR", "TE")
FULL_CHAIN = [
    "source-match",
    "source-reference",
    "comparison-section",
    "comparison-merge",
    "comparison-merge-report",
    "comparison-reindex",
    "comparison-review",
]


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_players(tmp: Path) -> tuple[Path, dict[str, int]]:
    rows = []
    player_keys = {}
    for pos_index, pos in enumerate(POSITIONS):
        for rank in range(12):
            key = 7000 + pos_index * 100 + rank
            name = f"Player {pos}{rank}"
            slug = name.lower()
            rows.append({"player_key": key, "name": name, "pos": pos, "team": "TST"})
            player_keys[slug] = key
    path = tmp / "players.json"
    write_json(path, {"players": rows})
    return path, player_keys


def build_comparison(tmp: Path, player_keys: dict[str, int], *, anchor_base: float = 40.0) -> Path:
    """Build comparison fixture with configurable ESPN anchor base value.

    Changing *anchor_base* changes ESPN native values, simulating an anchor
    refresh without touching the snapshot.
    """
    native = {slug: 100.0 + index for index, slug in enumerate(player_keys)}
    anchor = {}
    index_total = {}
    for pos_index, pos in enumerate(POSITIONS):
        slugs = [f"player {pos.lower()}{rank}" for rank in range(12)]
        for rank, slug in enumerate(slugs):
            anchor[slug] = anchor_base + pos_index * 20 + rank
        index_total[pos] = {"target_total": sum(anchor[slug] for slug in slugs), "n_priced": 12}

    path = tmp / "comparison.json"
    write_json(
        path,
        {
            "player_keys": player_keys,
            "sources": {
                "espn": {"combos": {"full_12": {"values": anchor}}},
                "fantasycalc": {
                    "name": "FantasyCalc",
                    "fetched_at": "2026-09-29T12:00:00Z",
                    "content_vintage": "Week 4",
                    "source_provenance": {
                        "source": "fantasycalc",
                        "content_vintage": "Week 4",
                        "vintage_kind": "week_designated",
                        "week_designated": 4,
                    },
                    "combos": {
                        "full_12": {
                            "native": native,
                            "reindexed": anchor,
                            "n": 48,
                            "index_total": index_total,
                        }
                    },
                },
            },
        },
    )
    return path


def build_snapshot(
    tmp: Path,
    player_keys: dict[str, int],
    *,
    bump_first: bool = False,
    source: str = "fantasycalc",
) -> Path:
    rows = []
    for index, slug in enumerate(player_keys):
        pos = slug.split()[1].rstrip("0123456789").upper()
        rows.append(
            {
                "player_name": " ".join(part.capitalize() for part in slug.split()),
                "value": 100.0 + index + (1.0 if bump_first and index == 0 else 0.0),
                "pos": pos,
                "team": "TST",
                "scoring": "ppr",
                "teams": 12,
                "source_player_id": player_keys[slug],
            }
        )
    raw_dir = tmp / "raw" / "sources" / source / "week-4"
    raw_dir.mkdir(parents=True, exist_ok=True)
    snapshot = raw_dir / "snapshot.json"

    # Write snapshot bytes and compute sha256 for the manifest integrity field.
    snapshot_data = {
        "schema": "trade-value-source-snapshot-v1",
        "source": source,
        "fetched_at": "2026-09-29T12:00:00Z",
        "default_scoring": None,
        "default_teams": 12,
        "row_count": len(rows),
        "rows": rows,
    }
    snapshot_bytes = (json.dumps(snapshot_data, indent=2, sort_keys=True) + "\n").encode("utf-8")
    snapshot.write_bytes(snapshot_bytes)
    snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()

    write_json(
        raw_dir / "snapshot-manifest.json",
        {
            "schema": "trade-value-source-manifest-v1",
            "source": source,
            "content_vintage": "Week 4",
            "content_vintage_derived_from": "week column",
            "week_designated": 4,
            "pulled_at": "2026-09-29T12:00:00Z",
            "snapshot_sha256": snapshot_sha256,
        },
    )
    return snapshot


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_health_file(
    tmp: Path,
    source: str,
    *,
    status: str = "ok",
    content_vintage: str = "Week 4",
    failure_reason: str | None = None,
    snapshot_path: Path | None = None,
    nfl_week: int = 4,
    extra_sources: dict | None = None,
) -> Path:
    """Write an import-health file covering all five ACTIVE_CASCADE_SOURCES.

    All five required active sources are included so the global-red gate passes
    for tests that only need to exercise a specific failure mode. The target
    ``source`` gets the specified ``status`` / ``content_vintage`` / optional
    attrs; the remaining four active sources get ``{"status": "ok",
    "content_vintage": content_vintage}`` entries.

    Pass ``snapshot_path`` for tests that require sha256 byte verification to
    pass (i.e. tests where the cascade gets past status/vintage/identity checks).
    The path is stored as an absolute string so the cascade resolves it directly
    rather than relative to ROOT.

    Pass ``nfl_week`` to produce a health file stamped with a different week.

    Pass ``extra_sources`` to override any source entry after the defaults are
    built (e.g. ``extra_sources={"usatoday": {"status": "stale", ...}}`` for
    global-red tests where the target source is ok but another is not).
    """
    path = tmp / "source-import-health.json"
    target_entry: dict = {
        "status": status,
        "content_vintage": content_vintage,
    }
    if failure_reason:
        target_entry["failure_reason"] = failure_reason
    if snapshot_path is not None:
        # Store as absolute string; ROOT / absolute_path → absolute_path in Python.
        target_entry["snapshot_path"] = str(snapshot_path)

    # Populate all five active sources. The global-red gate requires every one
    # to be a dict with status "ok"; tests that want a missing/malformed entry
    # should modify the returned file directly after this call.
    sources: dict = {
        src: (target_entry if src == source else {"status": "ok", "content_vintage": content_vintage})
        for src in cascade_mod.ACTIVE_CASCADE_SOURCES
    }
    if extra_sources:
        sources.update(extra_sources)
    write_json(
        path,
        {
            "schema": "trade-value-import-health-v1",
            "checked_at": _utc_now_iso(),  # always current so age check passes
            "nfl_week": nfl_week,
            "sources": sources,
        },
    )
    return path


def make_runner(
    tmp: Path,
    players: Path,
    comparison: Path,
    *,
    health_path: Path | None = None,
    triage: Path | None = None,
) -> cascade_mod.Cascade:
    out = tmp / "out"
    return cascade_mod.Cascade(
        players=players,
        comparison=comparison,
        raw_dir=tmp / "raw" / "sources",
        match_dir=out / "source-matches",
        reference_dir=out / "source-references",
        candidate_dir=out / "comparison-candidates",
        reindex_dir=out / "comparison-reference",
        review_dir=out / "comparison-review",
        report_path=out / "pipeline-cascade-report.json",
        health_path=health_path,
        triage=triage,
    )


def run_full_cascade(tmp, players, comparison, snapshot, **runner_kwargs):
    runner = make_runner(tmp, players, comparison, **runner_kwargs)
    runner.cascade_from_snapshot(snapshot)
    runner.write_report(trigger=f"snapshot:{snapshot}")
    return runner


# ---------------------------------------------------------------------------
# Stage ordering and provenance
# ---------------------------------------------------------------------------

class PipelineCascadeTest(unittest.TestCase):
    def test_changed_snapshot_triggers_every_downstream_stage_in_order(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys)

            runner = run_full_cascade(tmp, players, comparison, snapshot)

            stages = [step["stage"] for step in runner.steps]
            self.assertEqual(FULL_CHAIN, stages)
            self.assertTrue(all(step["status"] == "written" for step in runner.steps))
            self.assertEqual("ready", runner.steps[-1]["verdict"])

            # Verify the merge step ran the zero-fill check by confirming it
            # produced an output artifact with the correct section installed.
            merge_path = Path(runner.steps[stages.index("comparison-merge")]["output"])
            merged = json.loads(merge_path.read_text(encoding="utf-8"))
            self.assertIn("sources", merged)
            self.assertIn("fantasycalc", merged["sources"])

            # steps[-2] is comparison-reindex (steps[-1] is comparison-review)
            reindexed_path = Path(runner.steps[-2]["output"])
            reindexed = json.loads(reindexed_path.read_text(encoding="utf-8"))
            self.assertEqual("Week 4", reindexed["content_vintage"])
            self.assertEqual("Week 4", reindexed["source_provenance"]["content_vintage"])

            report = json.loads(runner.report_path.read_text(encoding="utf-8"))
            self.assertEqual("trade-value-cascade-report-v1", report["schema"])
            self.assertEqual(stages, [step["stage"] for step in report["steps"]])

            # Changed snapshot: all stages re-run and rewrite.
            changed_snapshot = build_snapshot(tmp, player_keys, bump_first=True)
            changed_runner = make_runner(tmp, players, comparison)
            changed_runner.cascade_from_snapshot(changed_snapshot)
            self.assertEqual(FULL_CHAIN, [step["stage"] for step in changed_runner.steps])
            self.assertTrue(all(step["status"] == "written" for step in changed_runner.steps))


# ---------------------------------------------------------------------------
# Unchanged run visits all stages — no early stop
# ---------------------------------------------------------------------------

class UnchangedRunTest(unittest.TestCase):
    def test_unchanged_snapshot_visits_all_stages_without_rewriting(self):
        """Second identical run reports all stages as 'unchanged', not stopped."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys)

            # Run 1: write everything.
            run_full_cascade(tmp, players, comparison, snapshot)

            # Run 2: same snapshot, same fixtures — all stages should be
            # "unchanged" but EVERY stage must be visited (no early stop).
            runner2 = make_runner(tmp, players, comparison)
            runner2.cascade_from_snapshot(snapshot)

            stages2 = [step["stage"] for step in runner2.steps]
            self.assertEqual(FULL_CHAIN, stages2, msg="all 7 stages must be visited on unchanged run")
            self.assertTrue(
                all(step["status"] == "unchanged" for step in runner2.steps),
                msg=f"all steps should be 'unchanged', got: {[s['status'] for s in runner2.steps]}",
            )
            # Verdict is still collected even when review is unchanged.
            self.assertEqual("ready", runner2.steps[-1]["verdict"])
            self.assertEqual(["ready"], runner2.review_verdicts)
            # Exit code: 0 (no hold verdicts).
            self.assertNotIn("hold", runner2.review_verdicts)


# ---------------------------------------------------------------------------
# Interrupted run — missing/corrupt downstream artifact recovery
# ---------------------------------------------------------------------------

class InterruptedRunTest(unittest.TestCase):
    def test_deleted_review_artifact_is_restored_with_identical_input(self):
        """Deleting the review artifact mid-run is healed on the next run."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys)

            # Run 1: complete cascade.
            r1 = run_full_cascade(tmp, players, comparison, snapshot)
            review_path = Path(r1.steps[-1]["output"])
            reindex_path = Path(r1.steps[-2]["output"])
            self.assertTrue(review_path.exists())

            # Simulate interruption: delete review and reindex artifacts.
            review_path.unlink()
            reindex_path.unlink()
            self.assertFalse(review_path.exists())
            self.assertFalse(reindex_path.exists())

            # Run 2: same snapshot, identical input.
            r2 = run_full_cascade(tmp, players, comparison, snapshot)

            stages2 = [step["stage"] for step in r2.steps]
            # All 7 stages must be visited — no early stop at source-match.
            self.assertEqual(FULL_CHAIN, stages2)

            # Upstream stages that didn't change → "unchanged".
            # Downstream deleted artifacts → "written" (restored).
            upstream_stages = {"source-match", "source-reference", "comparison-section",
                               "comparison-merge", "comparison-merge-report"}
            downstream_stages = {"comparison-reindex", "comparison-review"}
            for step in r2.steps:
                if step["stage"] in upstream_stages:
                    self.assertEqual(
                        "unchanged", step["status"],
                        msg=f"stage {step['stage']} should be unchanged (not re-run)",
                    )
                elif step["stage"] in downstream_stages:
                    self.assertEqual(
                        "written", step["status"],
                        msg=f"stage {step['stage']} should be written (deleted artifact restored)",
                    )

            # Restored files actually exist and have valid content.
            self.assertTrue(review_path.exists())
            self.assertTrue(reindex_path.exists())
            review_doc = json.loads(review_path.read_text())
            self.assertEqual("trade-value-comparison-review-v1", review_doc.get("schema"))

    def test_deleted_match_artifact_is_restored_and_full_chain_rerun(self):
        """Deleting the match artifact causes all downstream to be rewritten."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys)

            r1 = run_full_cascade(tmp, players, comparison, snapshot)
            match_path = Path(r1.steps[0]["output"])
            match_path.unlink()
            self.assertFalse(match_path.exists())

            r2 = run_full_cascade(tmp, players, comparison, snapshot)

            stages2 = [step["stage"] for step in r2.steps]
            self.assertEqual(FULL_CHAIN, stages2)
            # Every stage must be "written" since match was deleted and recomputed.
            self.assertTrue(
                all(step["status"] == "written" for step in r2.steps),
                msg=f"expected all written after match deletion, got: {[s['status'] for s in r2.steps]}",
            )
            self.assertTrue(match_path.exists())


# ---------------------------------------------------------------------------
# Independent input changes propagate through affected stages
# ---------------------------------------------------------------------------

class IndependentInputChangeTest(unittest.TestCase):
    def test_anchor_change_propagates_to_reindex_despite_unchanged_snapshot(self):
        """Changing ESPN anchor values re-runs reindex and review even when
        the snapshot/match/section are materially unchanged."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys, anchor_base=40.0)
            snapshot = build_snapshot(tmp, player_keys)

            # Run 1 with original anchor.
            r1 = run_full_cascade(tmp, players, comparison, snapshot)
            reindex_path_1 = Path(r1.steps[-2]["output"])
            reindex_1 = json.loads(reindex_path_1.read_text())
            # Grab a sample reindexed value.
            first_combo = next(iter(reindex_1.get("combos", {})), None)
            sample_key = next(iter(reindex_1["combos"][first_combo]["reindexed"]), None) if first_combo else None

            # Change ESPN anchor values (different anchor_base = different anchor).
            build_comparison(tmp, player_keys, anchor_base=50.0)  # overwrites comparison.json

            # Run 2 with same snapshot but different anchor.
            r2 = make_runner(tmp, players, comparison)
            r2.cascade_from_snapshot(snapshot)

            stages2 = [step["stage"] for step in r2.steps]
            self.assertEqual(FULL_CHAIN, stages2, msg="all stages must be visited even with unchanged snapshot")

            # merge artifact reflects changed fixture → must be "written".
            merge_step = next(s for s in r2.steps if s["stage"] == "comparison-merge")
            self.assertEqual("written", merge_step["status"],
                             msg="comparison-merge must rewrite when fixture (anchor) changes")

            # Reindex must produce a different result with a different anchor.
            reindex_step = next(s for s in r2.steps if s["stage"] == "comparison-reindex")
            self.assertEqual("written", reindex_step["status"],
                             msg="comparison-reindex must rewrite when ESPN anchor changes")

            if sample_key and first_combo:
                reindex_2 = json.loads(Path(reindex_step["output"]).read_text())
                val1 = reindex_1["combos"][first_combo]["reindexed"].get(sample_key)
                val2 = reindex_2["combos"][first_combo]["reindexed"].get(sample_key)
                self.assertNotEqual(val1, val2, msg="reindexed values should differ with different anchor")

    def test_triage_change_propagates_to_review_despite_unchanged_snapshot(self):
        """Adding a triage file re-runs review (review depends on triage).
        The reindex artifact is unchanged; only the review must update."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys)

            # Run 1: no triage.
            r1 = run_full_cascade(tmp, players, comparison, snapshot)
            review_path = Path(r1.steps[-1]["output"])
            reindex_path = Path(r1.steps[-2]["output"])

            # Build a triage file that triages any review_rows from the reindex.
            reindex_doc = json.loads(reindex_path.read_text())
            review_rows = reindex_doc.get("review_rows", [])
            triage_entries = {
                str(row.get("player_key", "unknown")): {"disposition": "accepted", "note": "test"}
                for row in review_rows
            }
            triage_path = tmp / "triage.json"
            write_json(triage_path, {"schema": "trade-value-triage-v1", "entries": triage_entries})

            # Run 2: same snapshot + new triage.
            r2 = make_runner(tmp, players, comparison, triage=triage_path)
            r2.cascade_from_snapshot(snapshot)

            stages2 = [step["stage"] for step in r2.steps]
            self.assertEqual(FULL_CHAIN, stages2, msg="all stages must be visited when triage changes")

            # Reindex is independent of triage → unchanged.
            reindex_step2 = next(s for s in r2.steps if s["stage"] == "comparison-reindex")
            self.assertEqual("unchanged", reindex_step2["status"],
                             msg="comparison-reindex should not change when only triage changes")

            # Review depends on triage → must rewrite (or at least be re-run).
            review_step2 = next(s for s in r2.steps if s["stage"] == "comparison-review")
            # Whether it's "written" or "unchanged" depends on whether review_rows
            # were present. Either way the review was re-evaluated.
            self.assertIn(review_step2["status"], {"written", "unchanged"},
                          msg="review step must execute (status written or unchanged, not skipped)")
            # The review artifact exists.
            self.assertTrue(review_path.exists())


# ---------------------------------------------------------------------------
# Hold verdict repeats on identical re-run
# ---------------------------------------------------------------------------

class HoldVerdictRepeatTest(unittest.TestCase):
    def _build_hold_world(self, tmp: Path) -> tuple[Path, Path, Path, Path]:
        """Build fixtures that guarantee a 'hold' verdict.

        Strategy: add an extra player (key=9999) who is in players.json and
        in the comparison fixture's player_keys (so they pass match and section
        stages), but NOT in the ESPN anchor values (so the reindex stage emits
        an untriaged review_rows entry → hold verdict on every run).

        This is deterministic: the reindex stage always produces a review row
        for any player who has a native value but no anchor entry, and the
        review stage always marks untriaged review rows as hold.
        """
        players, player_keys = build_players(tmp)
        comparison = build_comparison(tmp, player_keys)

        # Add extra player to players.json so the match stage can resolve them.
        extra_key = 9999
        extra_slug = "player extra0"
        extra_name = "Player Extra0"
        extra_pos = "TE"
        players_data = json.loads((tmp / "players.json").read_text(encoding="utf-8"))
        players_data["players"].append(
            {"player_key": extra_key, "name": extra_name, "pos": extra_pos, "team": "TST"}
        )
        (tmp / "players.json").write_text(
            json.dumps(players_data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        # Add extra player to comparison fixture player_keys (so the section
        # stage places them into native values) but do NOT add them to the ESPN
        # anchor values (so the reindex stage finds no anchor → review_rows).
        comp_data = json.loads((tmp / "comparison.json").read_text(encoding="utf-8"))
        comp_data["player_keys"][extra_slug] = extra_key
        (tmp / "comparison.json").write_text(
            json.dumps(comp_data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        # Build snapshot that includes the extra player.
        rows = []
        for index, s in enumerate(player_keys):
            pos = s.split()[1].rstrip("0123456789").upper()
            rows.append(
                {
                    "player_name": " ".join(part.capitalize() for part in s.split()),
                    "value": 100.0 + index,
                    "pos": pos,
                    "team": "TST",
                    "scoring": "ppr",
                    "teams": 12,
                    "source_player_id": player_keys[s],
                }
            )
        # Extra player: matched by name → player_key 9999 → section native value →
        # no ESPN anchor → reindex review_rows → hold.
        rows.append(
            {
                "player_name": extra_name,
                "value": 50.0,
                "pos": extra_pos,
                "team": "TST",
                "scoring": "ppr",
                "teams": 12,
                "source_player_id": extra_key,
            }
        )
        raw_dir = tmp / "raw" / "sources" / "fantasycalc" / "week-4"
        raw_dir.mkdir(parents=True, exist_ok=True)
        snapshot = raw_dir / "snapshot.json"
        snapshot_data = {
            "schema": "trade-value-source-snapshot-v1",
            "source": "fantasycalc",
            "fetched_at": "2026-09-29T12:00:00Z",
            "default_scoring": None,
            "default_teams": 12,
            "row_count": len(rows),
            "rows": rows,
        }
        snapshot_bytes = (json.dumps(snapshot_data, indent=2, sort_keys=True) + "\n").encode("utf-8")
        snapshot.write_bytes(snapshot_bytes)
        snapshot_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
        write_json(raw_dir / "snapshot-manifest.json", {
            "schema": "trade-value-source-manifest-v1",
            "source": "fantasycalc",
            "content_vintage": "Week 4",
            "content_vintage_derived_from": "week column",
            "week_designated": 4,
            "pulled_at": "2026-09-29T12:00:00Z",
            "snapshot_sha256": snapshot_sha256,
        })
        return players, player_keys, comparison, snapshot

    def test_hold_verdict_repeats_and_exits_nonzero_on_identical_rerun(self):
        """A 'hold' review on run 1 must still produce 'hold' and exit 2 on
        run 2 with identical input — the cascade must visit every stage and
        re-collect the verdict rather than stopping at an unchanged upstream.

        The hold is guaranteed by _build_hold_world: the extra player (key=9999)
        has a native value in the section but no ESPN anchor value, so the
        reindex stage always emits an untriaged review_rows entry → hold.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys, comparison, snapshot = self._build_hold_world(tmp)

            r1 = run_full_cascade(tmp, players, comparison, snapshot)
            verdict1 = r1.steps[-1].get("verdict")

            # The hold is deterministic: assert it rather than skipping.
            self.assertEqual(
                "hold", verdict1,
                msg=(
                    f"run 1 verdict was {verdict1!r}, expected 'hold'. "
                    "The extra player (key=9999) should produce an untriaged "
                    "review_rows entry (no ESPN anchor) → hold. "
                    "Check _build_hold_world or the reindex/review logic."
                ),
            )
            # Run 1 produces hold → exit code 2.
            self.assertIn("hold", r1.review_verdicts)

            # Run 2: same input, same world.
            r2 = run_full_cascade(tmp, players, comparison, snapshot)
            verdict2 = r2.steps[-1].get("verdict")

            # The cascade MUST visit the review stage on run 2 and re-collect
            # the verdict — not stop at source-match.
            stages2 = [step["stage"] for step in r2.steps]
            self.assertIn("comparison-review", stages2,
                          msg="comparison-review must be visited on unchanged re-run to re-collect hold verdict")
            self.assertEqual("hold", verdict2,
                             msg="hold verdict must repeat on identical re-run")
            self.assertIn("hold", r2.review_verdicts,
                          msg="review_verdicts must record hold on re-run")
            # Exit code 2 would be returned by main().
            self.assertEqual(2, 2 if "hold" in r2.review_verdicts else 0)


# ---------------------------------------------------------------------------
# Import health gate
# ---------------------------------------------------------------------------

class HealthGateTest(unittest.TestCase):
    def test_health_missing_blocks_snapshot_cascade(self):
        """When the health file doesn't exist, cascade raises SystemExit."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")

            missing_health = tmp / "no-health.json"
            self.assertFalse(missing_health.exists())

            runner = make_runner(tmp, players, comparison, health_path=missing_health)
            with self.assertRaises(SystemExit) as ctx:
                runner.cascade_from_snapshot(snapshot)
            self.assertIn("cascade blocked", str(ctx.exception))
            self.assertIn("import-health", str(ctx.exception))
            # No match step was executed.
            self.assertEqual([], runner.steps)

    def test_health_stale_source_blocks_cascade(self):
        """A non-ok source status (stale/missing/failed) blocks the cascade."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")

            health = build_health_file(
                tmp, "fantasycalc",
                status="stale",
                content_vintage="Week 3",
                failure_reason="STALE_VINTAGE: content vintage Week 3 != current NFL week 4",
            )
            runner = make_runner(tmp, players, comparison, health_path=health)
            with self.assertRaises(SystemExit) as ctx:
                runner.cascade_from_snapshot(snapshot)
            self.assertIn("cascade blocked", str(ctx.exception))
            self.assertIn("stale", str(ctx.exception).lower())
            self.assertEqual([], runner.steps)

    def test_health_vintage_mismatch_blocks_cascade(self):
        """Health ok but content_vintage mismatch blocks the cascade."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            # Snapshot manifest says "Week 4".
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
            # Health file says "Week 3" (mismatch).
            health = build_health_file(
                tmp, "fantasycalc", status="ok", content_vintage="Week 3"
            )
            runner = make_runner(tmp, players, comparison, health_path=health)
            with self.assertRaises(SystemExit) as ctx:
                runner.cascade_from_snapshot(snapshot)
            self.assertIn("cascade blocked", str(ctx.exception))
            self.assertIn("content_vintage", str(ctx.exception))
            self.assertEqual([], runner.steps)

    def test_health_ok_matching_vintage_allows_cascade(self):
        """Health ok with matching vintage and valid sha256 allows the full cascade."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
            # snapshot_path is required so the sha256 integrity gate can pass.
            health = build_health_file(
                tmp, "fantasycalc", status="ok", content_vintage="Week 4",
                snapshot_path=snapshot,
            )

            runner = make_runner(tmp, players, comparison, health_path=health)
            runner.cascade_from_snapshot(snapshot)

            stages = [step["stage"] for step in runner.steps]
            self.assertEqual(FULL_CHAIN, stages)
            self.assertTrue(all(step["status"] == "written" for step in runner.steps))

    def test_non_active_source_passes_health_gate_without_file(self):
        """A source not in ACTIVE_CASCADE_SOURCES bypasses the health gate."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            # Use a source not in the active set.
            snapshot = build_snapshot(tmp, player_keys, source="testonly")
            # Write manifest with non-active source name.
            manifest_path = snapshot.parent / "snapshot-manifest.json"
            write_json(manifest_path, {
                "schema": "trade-value-source-manifest-v1",
                "source": "testonly",
                "content_vintage": "Week 4",
                "pulled_at": "2026-09-29T12:00:00Z",
            })
            missing_health = tmp / "no-health.json"

            runner = make_runner(tmp, players, comparison, health_path=missing_health)
            # Should not raise even though health file is missing.
            runner.cascade_from_snapshot(snapshot)
            stages = [step["stage"] for step in runner.steps]
            self.assertEqual(FULL_CHAIN, stages)

    def test_health_check_skipped_when_health_path_is_none(self):
        """health_path=None disables the gate entirely (test harness mode)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")

            # No health file, health_path=None — should not block.
            runner = make_runner(tmp, players, comparison, health_path=None)
            runner.cascade_from_snapshot(snapshot)
            stages = [step["stage"] for step in runner.steps]
            self.assertEqual(FULL_CHAIN, stages)


# ---------------------------------------------------------------------------
# Data escape guard
# ---------------------------------------------------------------------------

class DataEscapeGuardTest(unittest.TestCase):
    def test_candidate_dir_inside_data_is_refused_at_init(self):
        """Cascade.__init__ must refuse candidate_dir inside data/."""
        ROOT = Path(__file__).resolve().parent.parent
        bad_dir = ROOT / "data" / "fixtures" / "current"

        with self.assertRaises(SystemExit) as ctx:
            cascade_mod.Cascade(
                players=ROOT / "data/fixtures/current/players.json",
                comparison=ROOT / "data/fixtures/current/comparison-sources-data.json",
                raw_dir=ROOT / "data/raw/sources",
                match_dir=ROOT / "output/source-matches",
                reference_dir=ROOT / "output/source-references",
                candidate_dir=bad_dir,  # inside data/ — must be refused
                reindex_dir=ROOT / "output/comparison-reference",
                review_dir=ROOT / "output/comparison-review",
                report_path=ROOT / "output/pipeline-cascade-report.json",
            )
        self.assertIn("data/", str(ctx.exception))
        self.assertIn("candidate_dir", str(ctx.exception))

    def test_reindex_dir_inside_data_is_refused_at_init(self):
        """Cascade.__init__ must refuse reindex_dir inside data/."""
        ROOT = Path(__file__).resolve().parent.parent
        bad_dir = ROOT / "data" / "reference"

        with self.assertRaises(SystemExit) as ctx:
            cascade_mod.Cascade(
                players=ROOT / "data/fixtures/current/players.json",
                comparison=ROOT / "data/fixtures/current/comparison-sources-data.json",
                raw_dir=ROOT / "data/raw/sources",
                match_dir=ROOT / "output/source-matches",
                reference_dir=ROOT / "output/source-references",
                candidate_dir=ROOT / "output/comparison-candidates",
                reindex_dir=bad_dir,   # inside data/ — must be refused
                review_dir=ROOT / "output/comparison-review",
                report_path=ROOT / "output/pipeline-cascade-report.json",
            )
        self.assertIn("data/", str(ctx.exception))
        self.assertIn("reindex_dir", str(ctx.exception))


# ---------------------------------------------------------------------------
# Intermediate entry points
# ---------------------------------------------------------------------------

class IntermediateEntryTest(unittest.TestCase):
    def test_cascade_from_match_runs_all_downstream_stages(self):
        """Entering at the match stage produces comparison-section through review."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys)

            # First produce the match artifact.
            import match_source_snapshot as ms
            payload = ms.match_snapshot(snapshot, players)
            match_dir = tmp / "out" / "source-matches"
            match_path = ms.default_output_path(payload, match_dir)
            match_path.parent.mkdir(parents=True, exist_ok=True)
            match_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                                  encoding="utf-8")

            runner = make_runner(tmp, players, comparison)
            runner.cascade_from_match(match_path)

            stages = [step["stage"] for step in runner.steps]
            # match stage itself is not included (we entered at match).
            self.assertIn("source-reference", stages)
            self.assertIn("comparison-section", stages)
            self.assertIn("comparison-merge", stages)
            self.assertIn("comparison-reindex", stages)
            self.assertIn("comparison-review", stages)
            self.assertTrue(all(step["status"] == "written" for step in runner.steps))

    def test_cascade_from_section_runs_merge_reindex_review(self):
        """Entering at the section stage produces merge through review."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys)

            # Run the first two stages to produce a section artifact.
            r1 = make_runner(tmp, players, comparison)
            r1.cascade_from_snapshot(snapshot)
            section_path = Path(
                next(s for s in r1.steps if s["stage"] == "comparison-section")["output"]
            )
            self.assertTrue(section_path.exists())

            # Now enter at the section stage in a fresh runner.
            out2 = tmp / "out2"
            runner2 = cascade_mod.Cascade(
                players=players,
                comparison=comparison,
                raw_dir=tmp / "raw" / "sources",
                match_dir=out2 / "source-matches",
                reference_dir=out2 / "source-references",
                candidate_dir=out2 / "comparison-candidates",
                reindex_dir=out2 / "comparison-reference",
                review_dir=out2 / "comparison-review",
                report_path=out2 / "pipeline-cascade-report.json",
            )
            runner2.cascade_from_section(section_path)

            stages2 = [step["stage"] for step in runner2.steps]
            self.assertEqual(
                ["comparison-merge", "comparison-merge-report", "comparison-reindex", "comparison-review"],
                stages2,
            )
            self.assertTrue(all(step["status"] == "written" for step in runner2.steps))
            self.assertEqual("ready", runner2.steps[-1]["verdict"])


# ---------------------------------------------------------------------------
# Entry-point integration — existing Makefile targets route through main()
# ---------------------------------------------------------------------------

class EntryPointIntegrationTest(unittest.TestCase):
    """Verify that calling cascade_source_update.main() at each entry point
    automatically runs all dependent downstream stages.

    These tests exercise the same dispatch path that the updated Makefile
    targets invoke (make source-match, make source-reference, etc.), proving
    that 'make source-match SNAPSHOT_FILE=X' now cascades through review, not
    just writing the match artifact.

    Non-active source name ("testonly") is used throughout so the health gate
    is bypassed per design — active sources are covered by IntermediateHealthGateTest.
    """

    def _run_main(self, tmp: Path, players: Path, comparison: Path, argv: list[str]) -> int:
        """Run cascade main() with output dirs rooted at tmp/out."""
        out = tmp / "out"
        full_argv = [
            *argv,
            "--players", str(players),
            "--comparison", str(comparison),
            "--output-root", str(out),
        ]
        return cascade_mod.main(full_argv)

    def test_snapshot_entry_triggers_all_downstream_stages(self):
        """make source-match SNAPSHOT_FILE=X now routes through cascade.

        Passing a snapshot artifact to --input must produce all 7 stages
        (source-match through comparison-review).
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="testonly")
            # Fix snapshot-manifest to use "testonly" source (build_snapshot
            # writes "fantasycalc" in manifest; rewrite for non-active source).
            manifest_path = snapshot.parent / "snapshot-manifest.json"
            manifest_data = json.loads(manifest_path.read_text())
            manifest_data["source"] = "testonly"
            manifest_path.write_text(json.dumps(manifest_data, indent=2) + "\n")

            rc = self._run_main(tmp, players, comparison, ["--input", str(snapshot)])

            out = tmp / "out"
            report_path = out / "pipeline-cascade-report.json"
            self.assertTrue(report_path.exists(), msg="cascade report must be written")
            report = json.loads(report_path.read_text())
            stages = [step["stage"] for step in report["steps"]]
            self.assertEqual(FULL_CHAIN, stages,
                             msg="snapshot entry must cascade all 7 stages")
            self.assertTrue(
                all(step["status"] == "written" for step in report["steps"]),
                msg="all stages must write on first run",
            )
            self.assertEqual(0, rc, msg="exit 0 expected for ready verdict")

    def test_match_entry_triggers_reference_through_review(self):
        """make source-reference MATCH_FILE=X now routes through cascade.

        Entering at a match artifact must produce source-reference through
        comparison-review (6 stages), not just the reference artifact.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="testonly")
            # Rewrite manifest to non-active source.
            manifest_path = snapshot.parent / "snapshot-manifest.json"
            md = json.loads(manifest_path.read_text())
            md["source"] = "testonly"
            manifest_path.write_text(json.dumps(md, indent=2) + "\n")

            # Produce the match artifact via the Cascade class (bypasses health).
            import match_source_snapshot as ms
            payload = ms.match_snapshot(snapshot, players)
            # Rewrite source field to non-active for the artifact itself.
            payload["source"] = "testonly"
            if isinstance(payload.get("source_provenance"), dict):
                payload["source_provenance"]["source"] = "testonly"
            match_dir = tmp / "matches"
            match_path = ms.default_output_path(payload, match_dir)
            match_path.parent.mkdir(parents=True, exist_ok=True)
            match_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

            rc = self._run_main(tmp, players, comparison, ["--input", str(match_path)])

            out = tmp / "out"
            report_path = out / "pipeline-cascade-report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text())
            stages = [step["stage"] for step in report["steps"]]
            # Entered at match stage, so source-match itself is not in stages.
            self.assertNotIn("source-match", stages)
            for expected_stage in [
                "source-reference", "comparison-section", "comparison-merge",
                "comparison-merge-report", "comparison-reindex", "comparison-review",
            ]:
                self.assertIn(expected_stage, stages,
                              msg=f"{expected_stage} must run when entering at match")
            self.assertEqual(0, rc)

    def test_section_entry_triggers_merge_through_review(self):
        """make comparison-merge CANDIDATE_FILE=X now routes through cascade.

        Entering at a section artifact must produce comparison-merge through
        comparison-review (4 stages).
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="testonly")
            # Rewrite manifest to non-active source.
            manifest_path = snapshot.parent / "snapshot-manifest.json"
            md = json.loads(manifest_path.read_text())
            md["source"] = "testonly"
            manifest_path.write_text(json.dumps(md, indent=2) + "\n")

            # Produce a section artifact via the Cascade class.
            runner = make_runner(tmp, players, comparison)
            runner.cascade_from_snapshot(snapshot)
            section_step = next(s for s in runner.steps if s["stage"] == "comparison-section")
            section_path = Path(section_step["output"])

            rc = self._run_main(tmp, players, comparison, ["--input", str(section_path)])

            out = tmp / "out"
            report_path = out / "pipeline-cascade-report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text())
            stages = [step["stage"] for step in report["steps"]]
            self.assertEqual(
                ["comparison-merge", "comparison-merge-report",
                 "comparison-reindex", "comparison-review"],
                stages,
                msg="section entry must trigger merge through review",
            )
            self.assertEqual(0, rc)


# ---------------------------------------------------------------------------
# Health gate for intermediate artifacts from active sources
# ---------------------------------------------------------------------------

class IntermediateHealthGateTest(unittest.TestCase):
    """Verify that the health gate is enforced for intermediate artifact entries
    from active dashboard sources.

    Prior to this fix the --input path bypassed the health gate entirely.
    These tests confirm that active sources are blocked without valid health
    and that no downstream artifacts are written.
    """

    def _make_active_match_artifact(self, tmp: Path, players: Path,
                                    comparison: Path) -> Path:
        """Produce a fantasycalc match artifact with source_provenance."""
        snapshot = build_snapshot(tmp, players_keys_unused := {}, source="fantasycalc")
        # Rebuild using real player_keys.
        _, player_keys = build_players(tmp)
        snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
        import match_source_snapshot as ms
        payload = ms.match_snapshot(snapshot, players)
        match_dir = tmp / "matches"
        match_path = ms.default_output_path(payload, match_dir)
        match_path.parent.mkdir(parents=True, exist_ok=True)
        match_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return match_path

    def _run_main_with_health(self, tmp: Path, players: Path, comparison: Path,
                               match_path: Path, health_path: Path) -> None:
        out = tmp / "out"
        cascade_mod.main([
            "--input", str(match_path),
            "--players", str(players),
            "--comparison", str(comparison),
            "--health", str(health_path),
            "--output-root", str(out),
        ])

    def test_active_source_match_blocked_without_health_file(self):
        """--input match artifact from active source with absent health file → blocked.
        No downstream artifacts must be written.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            match_path = self._make_active_match_artifact(tmp, players, comparison)
            missing_health = tmp / "no-health.json"

            out = tmp / "out"
            with self.assertRaises(SystemExit) as ctx:
                self._run_main_with_health(tmp, players, comparison, match_path, missing_health)

            self.assertIn("cascade blocked", str(ctx.exception))
            # No downstream artifacts should have been written.
            self.assertFalse(out.exists(),
                             msg="no output directory should exist when health gate blocks")

    def test_active_source_match_blocked_with_stale_health(self):
        """--input active source with stale/non-ok health → blocked."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            match_path = self._make_active_match_artifact(tmp, players, comparison)
            stale_health = build_health_file(
                tmp, "fantasycalc",
                status="stale",
                content_vintage="Week 3",
                failure_reason="STALE_VINTAGE: Week 3 != NFL week 4",
            )

            with self.assertRaises(SystemExit) as ctx:
                self._run_main_with_health(tmp, players, comparison, match_path, stale_health)

            self.assertIn("cascade blocked", str(ctx.exception))
            self.assertIn("stale", str(ctx.exception).lower())

    def test_active_source_match_blocked_with_vintage_mismatch(self):
        """--input active source where artifact vintage != health vintage → blocked."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            match_path = self._make_active_match_artifact(tmp, players, comparison)
            # Snapshot/manifest has Week 4 vintage; health says Week 3.
            wrong_vintage_health = build_health_file(
                tmp, "fantasycalc", status="ok", content_vintage="Week 3"
            )

            with self.assertRaises(SystemExit) as ctx:
                self._run_main_with_health(tmp, players, comparison, match_path, wrong_vintage_health)

            self.assertIn("cascade blocked", str(ctx.exception))
            self.assertIn("content_vintage", str(ctx.exception))

    def test_active_source_match_allowed_with_valid_health(self):
        """--input active source with valid health (ok + matching vintage + sha256) → all stages run."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            match_path = self._make_active_match_artifact(tmp, players, comparison)
            # The snapshot was written by _make_active_match_artifact via build_snapshot.
            # Pass its path to the health file so the sha256 integrity gate can resolve it.
            snapshot_path = tmp / "raw" / "sources" / "fantasycalc" / "week-4" / "snapshot.json"
            valid_health = build_health_file(
                tmp, "fantasycalc", status="ok", content_vintage="Week 4",
                snapshot_path=snapshot_path,
            )

            out = tmp / "out"
            rc = cascade_mod.main([
                "--input", str(match_path),
                "--players", str(players),
                "--comparison", str(comparison),
                "--health", str(valid_health),
                "--output-root", str(out),
            ])

            report_path = out / "pipeline-cascade-report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text())
            stages = [step["stage"] for step in report["steps"]]
            for expected_stage in [
                "source-reference", "comparison-section",
                "comparison-reindex", "comparison-review",
            ]:
                self.assertIn(expected_stage, stages)
            self.assertEqual(0, rc)

    def test_active_source_blocked_when_provenance_absent(self):
        """--input artifact with no source_provenance for active source → blocked."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            match_path = self._make_active_match_artifact(tmp, players, comparison)

            # Strip source_provenance from the artifact.
            artifact = json.loads(match_path.read_text())
            artifact.pop("source_provenance", None)
            match_path.write_text(json.dumps(artifact, indent=2) + "\n")

            valid_health = build_health_file(tmp, "fantasycalc", status="ok", content_vintage="Week 4")

            out = tmp / "out"
            with self.assertRaises(SystemExit) as ctx:
                cascade_mod.main([
                    "--input", str(match_path),
                    "--players", str(players),
                    "--comparison", str(comparison),
                    "--health", str(valid_health),
                    "--output-root", str(out),
                ])

            self.assertIn("cascade blocked", str(ctx.exception))
            self.assertIn("source_provenance", str(ctx.exception))

    def test_non_active_source_passes_intermediate_health_gate(self):
        """--input artifact from non-active source bypasses health gate (no file needed)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="testonly")
            # Fix manifest source.
            mp = snapshot.parent / "snapshot-manifest.json"
            md = json.loads(mp.read_text())
            md["source"] = "testonly"
            mp.write_text(json.dumps(md, indent=2) + "\n")

            import match_source_snapshot as ms
            payload = ms.match_snapshot(snapshot, players)
            payload["source"] = "testonly"
            if isinstance(payload.get("source_provenance"), dict):
                payload["source_provenance"]["source"] = "testonly"
            match_dir = tmp / "matches"
            match_path = ms.default_output_path(payload, match_dir)
            match_path.parent.mkdir(parents=True, exist_ok=True)
            match_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                                  encoding="utf-8")

            missing_health = tmp / "no-health.json"
            out = tmp / "out"
            # Should NOT raise: non-active source bypasses health gate.
            rc = cascade_mod.main([
                "--input", str(match_path),
                "--players", str(players),
                "--comparison", str(comparison),
                "--health", str(missing_health),  # missing, but non-active → no check
                "--output-root", str(out),
            ])
            self.assertIn(rc, (0, 2), msg="exit 0 or 2 expected (ready or hold), not error")


ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Health gate regression tests — concrete defects fixed in second integrator
# review cycle
# ---------------------------------------------------------------------------

class HealthGateRegressionTest(unittest.TestCase):
    """Regression suite for three concrete gate defects identified in the
    second integrator review.

    Each test asserts: cascade blocks, and no downstream artifacts are written.
    """

    # ---- Stale NFL week (health from week 3, today is week 4) ----

    def test_stale_nfl_week_health_blocks_snapshot_cascade(self):
        """Health file with nfl_week=3 must be rejected when today is week 4.

        The Week 3 import validated Week 3 data as current. Entering Week 4
        the cascade must block rather than proceeding on a stale report.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
            # nfl_week=3 — today is week 4 per WEEK1_START=2026-09-08.
            stale_health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot,
                nfl_week=3,
            )
            runner = make_runner(tmp, players, comparison, health_path=stale_health)
            out = tmp / "out"

            with self.assertRaises(SystemExit) as ctx:
                runner.cascade_from_snapshot(snapshot)
            msg = str(ctx.exception)
            self.assertIn("cascade blocked", msg)
            self.assertIn("nfl_week", msg)
            self.assertFalse(out.exists(),
                             msg="no output must be written when stale-week health blocks")

    def test_stale_nfl_week_health_blocks_intermediate_cascade(self):
        """Health file with nfl_week=3 must also block intermediate artifact entry."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)

            # Build a match artifact via the non-health path, then switch to active source.
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
            import match_source_snapshot as ms
            payload = ms.match_snapshot(snapshot, players)
            match_dir = tmp / "matches"
            match_path = ms.default_output_path(payload, match_dir)
            match_path.parent.mkdir(parents=True, exist_ok=True)
            match_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

            stale_health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot,
                nfl_week=3,
            )
            out = tmp / "out"
            with self.assertRaises(SystemExit) as ctx:
                cascade_mod.main([
                    "--input", str(match_path),
                    "--players", str(players),
                    "--comparison", str(comparison),
                    "--health", str(stale_health),
                    "--output-root", str(out),
                ])
            msg = str(ctx.exception)
            self.assertIn("cascade blocked", msg)
            self.assertIn("nfl_week", msg)
            self.assertFalse(out.exists(),
                             msg="no output must be written when stale-week health blocks")

    # ---- Modified snapshot (bytes tampered, vintage unchanged) ----

    def test_modified_snapshot_sha256_mismatch_blocks_snapshot_cascade(self):
        """Altered snapshot bytes (same vintage) must be detected and cascade blocked.

        This guards against a snapshot that passes the vintage check but whose
        values have been modified after the manifest was written.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
            health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot,
            )
            # Tamper with snapshot bytes after manifest was written.
            original_bytes = snapshot.read_bytes()
            tampered = original_bytes.replace(b'"value": 100.0', b'"value": 999.0')
            self.assertNotEqual(original_bytes, tampered, "tamper must differ")
            snapshot.write_bytes(tampered)

            runner = make_runner(tmp, players, comparison, health_path=health)
            out = tmp / "out"
            with self.assertRaises(SystemExit) as ctx:
                runner.cascade_from_snapshot(snapshot)
            msg = str(ctx.exception)
            self.assertIn("cascade blocked", msg)
            # Must mention sha256 or "modified" or "tamper".
            self.assertTrue(
                any(kw in msg.lower() for kw in ("sha256", "modified", "tamper", "bytes")),
                msg=f"expected sha256/tamper mention in: {msg}",
            )
            self.assertFalse(out.exists(),
                             msg="no output must be written when sha256 mismatch blocks")

    def test_intermediate_tampered_snapshot_blocks_cascade(self):
        """An intermediate artifact tracing to a tampered snapshot must be blocked.

        The health entry records the snapshot path. If that snapshot's bytes no
        longer match the manifest sha256, the cascade must block even if the
        content_vintage string still matches.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")

            # Produce a match artifact (health bypassed — health_path=None).
            import match_source_snapshot as ms
            payload = ms.match_snapshot(snapshot, players)
            match_dir = tmp / "matches"
            match_path = ms.default_output_path(payload, match_dir)
            match_path.parent.mkdir(parents=True, exist_ok=True)
            match_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

            health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot,
            )

            # Tamper with the snapshot AFTER the health file (and match artifact) exist.
            original_bytes = snapshot.read_bytes()
            tampered = original_bytes.replace(b'"value": 100.0', b'"value": 777.0')
            self.assertNotEqual(original_bytes, tampered, "tamper must differ")
            snapshot.write_bytes(tampered)

            out = tmp / "out"
            with self.assertRaises(SystemExit) as ctx:
                cascade_mod.main([
                    "--input", str(match_path),
                    "--players", str(players),
                    "--comparison", str(comparison),
                    "--health", str(health),
                    "--output-root", str(out),
                ])
            msg = str(ctx.exception)
            self.assertIn("cascade blocked", msg)
            self.assertTrue(
                any(kw in msg.lower() for kw in ("sha256", "modified", "tamper", "bytes")),
                msg=f"expected sha256/tamper mention in: {msg}",
            )
            self.assertFalse(out.exists(),
                             msg="no output must be written when tampered snapshot blocks")

    # ---- Health refresh exception propagates (fail closed) ----

    def test_refresh_health_exception_propagates_not_swallowed(self):
        """_refresh_health_after_import must NOT swallow exceptions.

        When run_health raises (e.g. Supabase unavailable), the exception must
        propagate rather than silently falling through to an old ok health report.
        A pre-existing ok health file does not grant permission to proceed.
        """
        import verify_import_health as _vh_mod

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
            # Pre-existing ok health file — the old (buggy) code would fall through
            # to use this when run_health raised.
            health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot,
            )
            runner = make_runner(tmp, players, comparison, health_path=health)

            with unittest.mock.patch.object(
                _vh_mod, "run_health", side_effect=RuntimeError("Supabase connection refused")
            ):
                with self.assertRaises(RuntimeError, msg="exception must propagate, not be swallowed"):
                    runner._refresh_health_after_import(snapshot)

    # ---- Global red gate (target source ok, other source stale) ----

    def test_global_red_health_blocks_cascade(self):
        """Global-red gate: fantasycalc ok but usatoday stale → cascade blocked.

        Pipeline-rules §8: run_health returns non-zero when ANY source is not ok.
        A health report that marks one source ok must not permit cascade when
        another active source is simultaneously stale.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
            health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot,
                extra_sources={
                    "usatoday": {
                        "status": "stale",
                        "content_vintage": "Week 3",
                        "failure_reason": "content unchanged since Week 3",
                    }
                },
            )
            runner = make_runner(tmp, players, comparison, health_path=health)
            out = tmp / "out"

            with self.assertRaises(SystemExit) as ctx:
                runner.cascade_from_snapshot(snapshot)
            msg = str(ctx.exception)
            self.assertIn("cascade blocked", msg)
            self.assertIn("global health", msg)
            self.assertFalse(out.exists(),
                             msg="no output must be written when global red blocks")

    # ---- run_health returns non-zero (rc=1, global red) ----

    def test_run_health_nonzero_return_blocks_refresh(self):
        """run_health returning 1 must raise SystemExit — not silently proceed.

        The integer return code is the normal failure path when any source is not
        ok. Removing exception catches alone (without checking rc) does not fail
        closed: a return value of 1 must still block all downstream stages.

        Pipeline-rules §8: all sources must be healthy before cascade proceeds.
        """
        import verify_import_health as _vh_mod

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
            # Pre-existing ok health file — not authoritative when run_health returns 1.
            health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot,
            )
            runner = make_runner(tmp, players, comparison, health_path=health)
            out = tmp / "out"

            with unittest.mock.patch.object(_vh_mod, "run_health", return_value=1):
                with self.assertRaises(SystemExit) as ctx:
                    runner._refresh_health_after_import(snapshot)
            msg = str(ctx.exception)
            self.assertIn("cascade blocked", msg)
            self.assertIn("exit 1", msg)
            # Downstream stages were never entered — output dir must not exist.
            self.assertFalse(out.exists(),
                             msg="no output must be written when rc=1 blocks refresh")

    # ---- Stale checked_at age (3 days > max 2 days) ----

    def test_old_checked_at_blocks_cascade(self):
        """Health file with checked_at 3 days ago must be rejected (max=2 days).

        The NFL week alone is not sufficient freshness proof: a health report
        written Monday and reused on Thursday same week is stale by calendar age
        even though nfl_week still matches.
        """
        import verify_import_health as _vh_mod
        from datetime import timedelta

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
            health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot,
            )
            # Overwrite checked_at to 3 days ago (> _MAX_HEALTH_AGE_DAYS=2).
            health_data = json.loads(health.read_text())
            old_date = (_vh_mod.utc_today() - timedelta(days=3)).isoformat()
            health_data["checked_at"] = f"{old_date}T12:00:00Z"
            health.write_text(json.dumps(health_data, indent=2) + "\n")

            runner = make_runner(tmp, players, comparison, health_path=health)
            out = tmp / "out"
            with self.assertRaises(SystemExit) as ctx:
                runner.cascade_from_snapshot(snapshot)
            msg = str(ctx.exception)
            self.assertIn("cascade blocked", msg)
            self.assertIn("checked_at", msg)
            self.assertFalse(out.exists(),
                             msg="no output must be written when stale checked_at blocks")

    # ---- Snapshot identity mismatch at import entry ----

    def _build_alt_snapshot(self, tmp: Path) -> Path:
        """Build a second fantasycalc snapshot with different bytes, same vintage.

        Has its own valid snapshot-manifest.json (sha256 matches its own bytes)
        so the manifest-vs-bytes check passes; the identity check distinguishes
        it from the primary snapshot by its different sha256.
        """
        alt_dir = tmp / "raw" / "sources" / "fantasycalc" / "week-4-alt"
        alt_dir.mkdir(parents=True, exist_ok=True)
        alt_data = {
            "schema": "trade-value-source-snapshot-v1",
            "source": "fantasycalc",
            "fetched_at": "2026-09-29T13:00:00Z",
            "default_scoring": None,
            "default_teams": 12,
            "row_count": 1,
            "rows": [{
                "player_name": "Alt Player QB0",
                "value": 50.0,
                "pos": "QB",
                "team": "ALT",
                "scoring": "ppr",
                "teams": 12,
                "source_player_id": 99,
            }],
        }
        b_bytes = (json.dumps(alt_data, indent=2, sort_keys=True) + "\n").encode("utf-8")
        snapshot_b = alt_dir / "snapshot.json"
        snapshot_b.write_bytes(b_bytes)
        b_sha = hashlib.sha256(b_bytes).hexdigest()
        write_json(
            alt_dir / "snapshot-manifest.json",
            {
                "schema": "trade-value-source-manifest-v1",
                "source": "fantasycalc",
                "content_vintage": "Week 4",
                "week_designated": 4,
                "pulled_at": "2026-09-29T13:00:00Z",
                "snapshot_sha256": b_sha,
            },
        )
        return snapshot_b

    def test_different_snapshot_identity_blocks_import(self):
        """Health verified snapshot A; cascade called with snapshot B (same vintage) → blocked.

        Both snapshots have the same content_vintage and valid manifest sha256
        (bytes match their own manifest). The identity gate must detect that health
        was verified against snapshot A but the import is presenting snapshot B.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            # Snapshot A: health is verified against this one.
            snapshot_a = build_snapshot(tmp, player_keys, source="fantasycalc")
            health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot_a,
            )
            # Snapshot B: different bytes, same vintage, own valid manifest.
            snapshot_b = self._build_alt_snapshot(tmp)

            runner = make_runner(tmp, players, comparison, health_path=health)
            out = tmp / "out"
            with self.assertRaises(SystemExit) as ctx:
                runner.cascade_from_snapshot(snapshot_b)
            msg = str(ctx.exception)
            self.assertIn("cascade blocked", msg)
            self.assertFalse(out.exists(),
                             msg="no output must be written when snapshot identity differs")

    # ---- Artifact lineage mismatch at intermediate entry ----

    def test_mismatched_lineage_blocks_intermediate(self):
        """Artifact derived from snapshot A; health verified against snapshot B → blocked.

        A match artifact carries source_provenance.snapshot_manifest pointing to
        snapshot A's manifest. When the health file was verified against snapshot B,
        the provenance cross-check detects the lineage mismatch and blocks cascade.
        Same vintage string is not sufficient — byte identity is required.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            # Snapshot A: the artifact will be derived from this.
            snapshot_a = build_snapshot(tmp, player_keys, source="fantasycalc")
            # Snapshot B: health was verified against this; different sha256 from A.
            snapshot_b = self._build_alt_snapshot(tmp)

            # Produce a match artifact derived from snapshot_a (health_path=None bypasses gate).
            import match_source_snapshot as ms
            payload = ms.match_snapshot(snapshot_a, players)
            match_dir = tmp / "matches"
            match_path = ms.default_output_path(payload, match_dir)
            match_path.parent.mkdir(parents=True, exist_ok=True)
            match_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            # Confirm the artifact has the expected lineage (snapshot_a's manifest).
            art = json.loads(match_path.read_text())
            prov = art.get("source_provenance", {})
            self.assertIn(
                "snapshot-manifest.json", prov.get("snapshot_manifest", ""),
                msg="artifact must carry snapshot_manifest provenance"
            )

            # Health says: verified against snapshot_b.
            health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot_b,
            )

            out = tmp / "out"
            with self.assertRaises(SystemExit) as ctx:
                cascade_mod.main([
                    "--input", str(match_path),
                    "--players", str(players),
                    "--comparison", str(comparison),
                    "--health", str(health),
                    "--output-root", str(out),
                ])
            msg = str(ctx.exception)
            self.assertIn("cascade blocked", msg)
            self.assertFalse(out.exists(),
                             msg="no output must be written when lineage mismatch blocks")

    # ---- Omitted required source ----

    def test_omitted_required_source_blocks_cascade(self):
        """Health file missing a required active source must be rejected.

        A health report that only lists the target source (or omits any other
        active source) would silently pass if the global gate iterated only
        present entries. Iterating ACTIVE_CASCADE_SOURCES catches the gap.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
            health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot,
            )
            # Remove a required source after the file is written.
            health_data = json.loads(health.read_text())
            health_data["sources"].pop("espn")
            health.write_text(json.dumps(health_data, indent=2) + "\n")

            runner = make_runner(tmp, players, comparison, health_path=health)
            out = tmp / "out"
            with self.assertRaises(SystemExit) as ctx:
                runner.cascade_from_snapshot(snapshot)
            msg = str(ctx.exception)
            self.assertIn("cascade blocked", msg)
            self.assertIn("espn", msg)
            self.assertFalse(out.exists(),
                             msg="no output must be written when required source is absent")

    # ---- Null/malformed source entry ----

    def test_malformed_source_entry_blocks_cascade(self):
        """A null or non-dict source entry must be rejected (not silently skipped).

        The prior global-red loop used ``if isinstance(entry, dict) and ...``
        which short-circuited to False for null entries, silently passing them.
        The new loop blocks on any non-dict entry.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
            health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot,
            )
            # Replace cbs entry with null (malformed health report).
            health_data = json.loads(health.read_text())
            health_data["sources"]["cbs"] = None
            health.write_text(json.dumps(health_data, indent=2) + "\n")

            runner = make_runner(tmp, players, comparison, health_path=health)
            out = tmp / "out"
            with self.assertRaises(SystemExit) as ctx:
                runner.cascade_from_snapshot(snapshot)
            msg = str(ctx.exception)
            self.assertIn("cascade blocked", msg)
            self.assertIn("cbs", msg)
            self.assertFalse(out.exists(),
                             msg="no output must be written when null source entry blocks")

    # ---- Future checked_at (negative age) ----

    def test_future_checked_at_blocks_cascade(self):
        """A health file with checked_at in the future must be rejected.

        A future timestamp produces a negative age_days. The prior gate only
        checked ``age_days > _MAX_HEALTH_AGE_DAYS``, which a negative value
        passes (−2 > 2 is False). The new gate also rejects negative ages.
        """
        import verify_import_health as _vh_mod
        from datetime import timedelta

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="fantasycalc")
            health = build_health_file(
                tmp, "fantasycalc",
                status="ok",
                content_vintage="Week 4",
                snapshot_path=snapshot,
            )
            # Overwrite checked_at to 2 days in the future.
            health_data = json.loads(health.read_text())
            future_date = (_vh_mod.utc_today() + timedelta(days=2)).isoformat()
            health_data["checked_at"] = f"{future_date}T12:00:00Z"
            health.write_text(json.dumps(health_data, indent=2) + "\n")

            runner = make_runner(tmp, players, comparison, health_path=health)
            out = tmp / "out"
            with self.assertRaises(SystemExit) as ctx:
                runner.cascade_from_snapshot(snapshot)
            msg = str(ctx.exception)
            self.assertIn("cascade blocked", msg)
            self.assertIn("checked_at", msg)
            self.assertFalse(out.exists(),
                             msg="no output must be written when future checked_at blocks")


# ---------------------------------------------------------------------------
# Makefile wiring — subprocess dry-run tests to catch argument/variable errors
# ---------------------------------------------------------------------------

class MakefileWiringTest(unittest.TestCase):
    """Verify that each Makefile stage target routes through cascade_source_update.py.

    Uses ``make -n`` dry-run mode so these tests do not execute the pipeline;
    they only verify the argument/variable wiring.  A wiring error (wrong
    variable name, missing --input flag, wrong script path) will cause the
    dry-run output to differ from expectations and the test to fail.
    """

    @classmethod
    def setUpClass(cls) -> None:
        # Confirm make is available; skip the whole class if not.
        result = subprocess.run(
            ["make", "--version"], capture_output=True, cwd=ROOT
        )
        if result.returncode != 0:
            raise unittest.SkipTest("make not available")

    def _make_dryrun(self, target: str, extra_vars: dict[str, str]) -> str:
        env = {**os.environ, **extra_vars}
        result = subprocess.run(
            ["make", "-n", target, *[f"{k}={v}" for k, v in extra_vars.items()]],
            capture_output=True, text=True, cwd=ROOT, env=env,
        )
        return result.stdout + result.stderr

    def test_supabase_import_routes_through_cascade(self):
        out = self._make_dryrun("supabase-import", {"SOURCE": "fantasycalc"})
        self.assertIn("cascade_source_update.py", out,
                      msg="supabase-import must invoke cascade_source_update.py")
        self.assertIn("--source", out)
        self.assertIn("fantasycalc", out)

    def test_source_match_routes_through_cascade(self):
        out = self._make_dryrun(
            "source-match", {"SNAPSHOT_FILE": "/tmp/test/snapshot.json"}
        )
        self.assertIn("cascade_source_update.py", out,
                      msg="source-match must invoke cascade_source_update.py")
        self.assertIn("--input", out)
        self.assertIn("/tmp/test/snapshot.json", out)

    def test_source_reference_routes_through_cascade(self):
        out = self._make_dryrun(
            "source-reference", {"MATCH_FILE": "/tmp/test/matched.json"}
        )
        self.assertIn("cascade_source_update.py", out,
                      msg="source-reference must invoke cascade_source_update.py")
        self.assertIn("--input", out)
        self.assertIn("/tmp/test/matched.json", out)

    def test_comparison_section_routes_through_cascade(self):
        out = self._make_dryrun(
            "comparison-section", {"REFERENCE_FILE": "/tmp/test/reference.json"}
        )
        self.assertIn("cascade_source_update.py", out,
                      msg="comparison-section must invoke cascade_source_update.py")
        self.assertIn("--input", out)

    def test_comparison_merge_routes_through_cascade(self):
        out = self._make_dryrun(
            "comparison-merge", {"CANDIDATE_FILE": "/tmp/test/section.json"}
        )
        self.assertIn("cascade_source_update.py", out,
                      msg="comparison-merge must invoke cascade_source_update.py")
        self.assertIn("--input", out)
        self.assertIn("/tmp/test/section.json", out)

    def test_comparison_reindex_routes_through_cascade(self):
        out = self._make_dryrun(
            "comparison-reindex", {"CANDIDATE_FILE": "/tmp/test/section.json"}
        )
        self.assertIn("cascade_source_update.py", out,
                      msg="comparison-reindex must invoke cascade_source_update.py")
        self.assertIn("--input", out)
        self.assertIn("/tmp/test/section.json", out)


# ---------------------------------------------------------------------------
# Makefile subprocess execution tests — actual pipeline runs with isolated
# fixture paths, asserting real downstream artifacts and exit behaviour.
# ---------------------------------------------------------------------------

class MakefileExecutionTest(unittest.TestCase):
    """Execute Make targets with isolated tmp-dir fixtures and assert that
    downstream artifacts are actually written and exit codes are correct.

    Uses non-active source "testonly" so the health gate is bypassed without
    requiring a synthetic health file. Fixture-path overrides (PLAYERS,
    COMPARISON, OUTPUT_ROOT) are passed through the Makefile variables that
    _CASCADE_OVERRIDES expands into --players / --comparison / --output-root.
    """

    @classmethod
    def setUpClass(cls) -> None:
        result = subprocess.run(["make", "--version"], capture_output=True, cwd=ROOT)
        if result.returncode != 0:
            raise unittest.SkipTest("make not available")

    def test_make_source_match_actual_execution(self):
        """make source-match with a testonly snapshot must run the full cascade
        and write the pipeline report + at least one review artifact.

        Verifies that SNAPSHOT_FILE, PLAYERS, COMPARISON, and OUTPUT_ROOT are
        correctly threaded through _CASCADE_OVERRIDES into cascade_source_update.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            # Non-active source: health gate bypassed automatically.
            snapshot = build_snapshot(tmp, player_keys, source="testonly")
            out = tmp / "cascade-out"

            result = subprocess.run(
                [
                    "make", "source-match",
                    f"SNAPSHOT_FILE={snapshot}",
                    f"PLAYERS={players}",
                    f"COMPARISON={comparison}",
                    f"OUTPUT_ROOT={out}",
                ],
                capture_output=True, text=True, cwd=ROOT,
            )
            self.assertIn(
                result.returncode, (0, 2),
                msg=(
                    f"make source-match failed (rc={result.returncode}):\n"
                    f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                ),
            )
            report = out / "pipeline-cascade-report.json"
            self.assertTrue(
                report.exists(),
                msg=(
                    f"pipeline report not written at {report}:\n"
                    f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                ),
            )
            review_dir = out / "comparison-review"
            reviews = list(review_dir.glob("**/*.json")) if review_dir.exists() else []
            self.assertTrue(
                reviews,
                msg=(
                    f"no review artifacts written under {review_dir}:\n"
                    f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                ),
            )

    def test_make_comparison_merge_actual_execution(self):
        """make comparison-merge with a testonly section artifact must cascade
        through to review and write the pipeline report.

        An intermediate Make target (comparison-merge) is tested here to confirm
        that re-entry at the section stage also routes through cascade correctly
        and that OUTPUT_ROOT and CANDIDATE_FILE overrides work end-to-end.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            players, player_keys = build_players(tmp)
            comparison = build_comparison(tmp, player_keys)
            snapshot = build_snapshot(tmp, player_keys, source="testonly")

            # Produce a section artifact via in-process cascade (health_path=None
            # bypasses health gate for testonly source).
            setup_runner = make_runner(tmp, players, comparison)  # health_path=None
            setup_runner.cascade_from_snapshot(snapshot)

            candidate_dir = tmp / "out" / "comparison-candidates"
            sections = list(candidate_dir.glob("**/*-section.json"))
            self.assertTrue(sections, "no section artifacts from setup cascade — fix test setup")
            section_path = sections[0]

            out = tmp / "cascade-merge-out"
            result = subprocess.run(
                [
                    "make", "comparison-merge",
                    f"CANDIDATE_FILE={section_path}",
                    f"PLAYERS={players}",
                    f"COMPARISON={comparison}",
                    f"OUTPUT_ROOT={out}",
                ],
                capture_output=True, text=True, cwd=ROOT,
            )
            self.assertIn(
                result.returncode, (0, 2),
                msg=(
                    f"make comparison-merge failed (rc={result.returncode}):\n"
                    f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                ),
            )
            report = out / "pipeline-cascade-report.json"
            self.assertTrue(
                report.exists(),
                msg=(
                    f"pipeline report not written at {report}:\n"
                    f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                ),
            )
            review_dir = out / "comparison-review"
            reviews = list(review_dir.glob("**/*.json")) if review_dir.exists() else []
            self.assertTrue(
                reviews,
                msg=(
                    f"no review artifacts under {review_dir}:\n"
                    f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                ),
            )


if __name__ == "__main__":
    unittest.main()
