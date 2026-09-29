#!/usr/bin/env python3
"""Cascade trade-value source updates through dependent pipeline stages.

The individual stage scripts remain the source of truth for each transform.
This runner wires them together after any earlier-stage update:

  supabase-import / source-import
    -> source-match
    -> source-reference
    -> comparison-section
    -> comparison-merge + comparison-merge-report
    -> comparison-reindex
    -> comparison-review

Promotion is intentionally not automatic; it still requires the existing
human approval path (``promote_comparison_section.py --approve``).

Automatic wiring
----------------
``make cascade SOURCE=<source>`` runs the full chain from a fresh Supabase
import. ``make cascade-from INPUT=<artifact>`` re-enters the chain at the
artifact's schema stage. Individual ``make source-match / source-reference /
...`` targets remain available for debugging individual stages.

Import health gate (pipeline-rules §8)
---------------------------------------
For the five active dashboard sources (espn, usatoday, fantasycalc,
fantasypros, cbs), the cascade reads ``output/source-import-health.json``
before proceeding to match. It verifies the source's L1 status is ``"ok"``
and the health file's recorded ``content_vintage`` matches the snapshot
manifest's ``content_vintage``. Any mismatch fails closed with a clear
message. Pass ``--skip-health-check`` or leave ``--health`` unset to bypass
the gate (tests, intermediate-artifact entry, non-active sources).

Stage freshness and recovery
-----------------------------
Every stage is ALWAYS visited. ``write_if_changed`` skips rewriting when the
computed output is materially identical to what is already on disk, but the
cascade never short-circuits past a stage based on an upstream artifact being
unchanged. This means:

- Missing or corrupt downstream artifacts are always restored in a single run.
- A changed comparison fixture (ESPN anchor) or triage file propagates to the
  affected stages automatically.
- A ``hold`` review verdict is re-collected on every run, so repeated identical
  runs correctly exit 2 rather than silently going green.

Candidate writes are fail-closed against data/
------------------------------------------------
All output directories except ``raw_dir`` are checked against ``data/`` at
startup. Passing ``--candidate-dir data/fixtures/current`` or any other data/
subtree is refused. The merge stage's ``require_output_path`` provides a second
guard at write time.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "pipelines"
if str(PIPELINES) not in sys.path:
    sys.path.insert(0, str(PIPELINES))

import build_comparison_source_section as section_stage  # noqa: E402
import build_source_reference as reference_stage  # noqa: E402
import import_source_snapshot as file_import_stage  # noqa: E402
import import_supabase_references as supabase_import_stage  # noqa: E402
import match_source_snapshot as match_stage  # noqa: E402
import merge_comparison_candidate as merge_stage  # noqa: E402
import reindex_comparison_section as reindex_stage  # noqa: E402
import review_comparison_candidate as review_stage  # noqa: E402


# Active dashboard sources that require an import-health gate before cascade.
ACTIVE_CASCADE_SOURCES = frozenset({"espn", "usatoday", "fantasycalc", "fantasypros", "cbs"})
DEFAULT_HEALTH_PATH = ROOT / "output" / "source-import-health.json"

# data/ root used for the output-dir escape guard.
_DATA_ROOT = (ROOT / "data").resolve()

SCHEMA_STAGE = {
    file_import_stage.SCHEMA: "snapshot",
    match_stage.OUTPUT_SCHEMA: "match",
    reference_stage.OUTPUT_SCHEMA: "reference",
    section_stage.OUTPUT_SCHEMA: "section",
    reindex_stage.SCHEMA: "reindexed",
    review_stage.SCHEMA: "review",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_outside_data(path: Path, param_name: str) -> None:
    """Fail closed when *path* resolves inside data/.

    raw_dir is intentionally exempt (raw snapshots live under data/raw/).
    All other output dirs must be under output/ or a custom working dir.
    """
    resolved = path.resolve()
    if resolved == _DATA_ROOT or _DATA_ROOT in resolved.parents:
        raise SystemExit(
            f"cascade refuses to write inside data/ for {param_name!r}: {path}.\n"
            "All output dirs (except raw_dir) must be outside data/. "
            "Pass --output-root or explicit --*-dir pointing to output/ or a tmp dir."
        )


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return payload


def dump_json(payload: dict[str, Any], *, indent: int = 2, sort_keys: bool = True) -> str:
    return json.dumps(payload, indent=indent, sort_keys=sort_keys) + "\n"


_VOLATILE_KEYS = frozenset({"generated_at", "built_at"})


def strip_volatile(value: Any) -> Any:
    """Return a comparison copy with processing timestamps removed.

    Strips keys that are pure processing/acquisition timestamps:
    ``generated_at`` (pipeline run time) and ``built_at`` (fixture write time).
    These must never drive freshness gates (pipeline-rules §5), but stripping
    them here is only for idempotency comparison — the written files still
    carry the full, unmodified payload.
    """
    if isinstance(value, dict):
        return {
            key: strip_volatile(child)
            for key, child in value.items()
            if key not in _VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [strip_volatile(child) for child in value]
    return value


def materially_same(path: Path, payload: dict[str, Any]) -> bool:
    if not path.exists():
        return False
    try:
        existing = load_json(path)
    except (OSError, json.JSONDecodeError):
        return False
    return strip_volatile(existing) == strip_volatile(payload)


def write_if_changed(
    path: Path,
    payload: dict[str, Any],
    *,
    stage: str,
    inputs: list[Path],
    steps: list[dict[str, Any]],
    force: bool = False,
    indent: int = 2,
    sort_keys: bool = True,
) -> bool:
    changed = force or not materially_same(path, payload)
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_json(payload, indent=indent, sort_keys=sort_keys), encoding="utf-8")
    steps.append(
        {
            "stage": stage,
            "inputs": [str(path_arg) for path_arg in inputs],
            "output": str(path),
            "status": "written" if changed else "unchanged",
        }
    )
    return changed


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def first_combo_slug(section: dict[str, Any]) -> str:
    first = next(iter(section.get("combos", {})), "mixed")
    return section_stage.slug(str(first))


def default_merge_candidate_path(section: dict[str, Any], output_dir: Path) -> Path:
    fetched = str(section.get("fetched_at") or date.today().isoformat())[:10]
    source = section_stage.slug(str(section.get("source_key") or section.get("section_key") or "source"))
    return output_dir / source / fetched / f"{source}-candidate.json"


def default_merge_report_path(section: dict[str, Any], output_dir: Path) -> Path:
    fetched = str(section.get("fetched_at") or date.today().isoformat())[:10]
    source = section_stage.slug(str(section.get("source_key") or section.get("section_key") or "source"))
    return output_dir / source / fetched / f"{source}-candidate-report.json"


def default_reindexed_path(section: dict[str, Any], output_dir: Path) -> Path:
    fetched = str(section.get("fetched_at") or date.today().isoformat())[:10]
    source = section_stage.slug(str(section.get("source_key") or section.get("section_key") or "source"))
    combo = first_combo_slug(section)
    return output_dir / source / fetched / f"{source}-{combo}-reindexed.json"


def default_review_path(reindexed: dict[str, Any], output_dir: Path) -> Path:
    fetched = str(reindexed.get("fetched_at") or date.today().isoformat())[:10]
    source = section_stage.slug(str(reindexed.get("source_key") or "source"))
    combo = first_combo_slug(reindexed)
    return output_dir / source / fetched / f"{source}-{combo}-review.json"


# ---------------------------------------------------------------------------
# Cascade class
# ---------------------------------------------------------------------------

class Cascade:
    """Orchestrate the full trade-value pipeline for one source.

    Every stage is always visited; ``write_if_changed`` skips rewriting only
    when the computed result is materially identical to what is already on disk.
    This ensures missing or corrupt downstream artifacts are always restored and
    that changes to independent inputs (comparison fixture, triage, players)
    propagate to the affected stages even when the upstream snapshot is
    unchanged.
    """

    def __init__(
        self,
        *,
        players: Path,
        comparison: Path,
        raw_dir: Path,
        match_dir: Path,
        reference_dir: Path,
        candidate_dir: Path,
        reindex_dir: Path,
        review_dir: Path,
        report_path: Path,
        triage: Path | None = None,
        force: bool = False,
        health_path: Path | None = None,
    ) -> None:
        # Guard: output dirs (except raw_dir) must not write inside data/.
        for name, path in (
            ("match_dir", match_dir),
            ("reference_dir", reference_dir),
            ("candidate_dir", candidate_dir),
            ("reindex_dir", reindex_dir),
            ("review_dir", review_dir),
        ):
            _require_outside_data(path, name)

        self.players = players
        self.comparison = comparison
        self.raw_dir = raw_dir
        self.match_dir = match_dir
        self.reference_dir = reference_dir
        self.candidate_dir = candidate_dir
        self.reindex_dir = reindex_dir
        self.review_dir = review_dir
        self.report_path = report_path
        self.triage = triage
        self.force = force
        self.health_path = health_path
        self.steps: list[dict[str, Any]] = []
        self.review_verdicts: list[str] = []
        # Becomes True the first time any stage is newly written.  Once set,
        # all subsequent downstream stages are forced even when their computed
        # content is materially unchanged — provenance requires that every
        # artifact downstream of a rebuilt stage was computed from the same
        # rebuilt input, not from a cached prior run.
        self._downstream_force: bool = force

    # ------------------------------------------------------------------
    # Internal write helper — propagates downstream force
    # ------------------------------------------------------------------

    def _write(
        self,
        path: Path,
        payload: dict[str, Any],
        *,
        stage: str,
        inputs: list[Path],
        indent: int = 2,
        sort_keys: bool = True,
    ) -> bool:
        """Write if changed and escalate ``_downstream_force`` on first write."""
        changed = write_if_changed(
            path,
            payload,
            stage=stage,
            inputs=inputs,
            steps=self.steps,
            force=self._downstream_force,
            indent=indent,
            sort_keys=sort_keys,
        )
        if changed:
            self._downstream_force = True
        return changed

    # ------------------------------------------------------------------
    # Import health gate (pipeline-rules §8)
    # ------------------------------------------------------------------

    def _check_import_health(self, snapshot_path: Path) -> None:
        """Fail closed if the snapshot's source has non-ok import health.

        Applies only to the five active dashboard sources; non-active or test
        sources pass through without a check. Requires the snapshot directory
        to contain a ``snapshot-manifest.json`` sidecar with ``content_vintage``
        provenance. Health is verified against ``self.health_path`` (or skipped
        when ``health_path`` is None).
        """
        if self.health_path is None:
            return  # health gate disabled: test harness, intermediate entry, or non-active source

        snapshot = load_json(snapshot_path)
        source = snapshot.get("source")
        if source not in ACTIVE_CASCADE_SOURCES:
            return  # not a gateable source

        manifest_path = snapshot_path.parent / "snapshot-manifest.json"
        if not manifest_path.is_file():
            raise SystemExit(
                f"cascade blocked: no snapshot-manifest.json alongside {snapshot_path}. "
                f"Run: make supabase-import SOURCE={source}"
            )
        manifest = load_json(manifest_path)
        content_vintage = manifest.get("content_vintage")
        if not content_vintage:
            raise SystemExit(
                f"cascade blocked: snapshot manifest for {source!r} has no content_vintage. "
                "Provenance is required. Re-import via: make supabase-import SOURCE={source}"
            )

        hp = self.health_path
        if not hp.is_file():
            raise SystemExit(
                f"cascade blocked: import health file {hp} not found. "
                f"Run: make import-health NFL_WEEK=<current_week>"
            )
        health = load_json(hp)
        if health.get("schema") != "trade-value-import-health-v1":
            raise SystemExit(
                f"cascade blocked: {hp} has unexpected schema {health.get('schema')!r}"
            )
        entry = (health.get("sources") or {}).get(source)
        if not isinstance(entry, dict):
            raise SystemExit(
                f"cascade blocked: health file has no entry for source {source!r}"
            )
        status = entry.get("status")
        if status != "ok":
            failure_reason = entry.get("failure_reason") or "unknown reason"
            raise SystemExit(
                f"cascade blocked: import health for {source!r} is {status!r} "
                f"({failure_reason}). "
                f"Fix the import and re-run: make import-health NFL_WEEK=<n>"
            )
        health_vintage = str(entry.get("content_vintage") or "")
        if str(content_vintage) != health_vintage:
            raise SystemExit(
                f"cascade blocked: snapshot content_vintage {content_vintage!r} does not "
                f"match health content_vintage {health_vintage!r}. "
                f"Re-import via: make supabase-import SOURCE={source}"
            )

    # ------------------------------------------------------------------
    # Import entry points
    # ------------------------------------------------------------------

    def import_raw_file(
        self,
        path: Path,
        *,
        source: str | None,
        scoring: str | None,
        teams: int | None,
        fetched_at: str | None,
        source_url: str | None,
    ) -> Path:
        snapshot = file_import_stage.build_snapshot(
            path,
            source=source,
            scoring=scoring,
            teams=teams,
            fetched_at=fetched_at,
            source_url=source_url,
        )
        output = file_import_stage.default_output_path(snapshot, self.raw_dir)
        self._write(output, snapshot, stage="source-import", inputs=[path])
        return output

    def import_supabase_source(self, source: str) -> Path:
        result = supabase_import_stage.import_source(source, output_dir=self.raw_dir)
        snapshot_path = Path(result["snapshot_path"])
        written = not result["already_stamped"]
        self.steps.append(
            {
                "stage": "supabase-import",
                "inputs": [source],
                "output": str(snapshot_path),
                "status": "written" if written else "unchanged",
                "content_vintage": result["content_vintage"],
                "row_count": result["row_count"],
                "review_count": result["review_count"],
            }
        )
        if written:
            self._downstream_force = True
        return snapshot_path

    # ------------------------------------------------------------------
    # Cascade entry points — each always visits all downstream stages
    # ------------------------------------------------------------------

    def cascade_from_snapshot(self, snapshot_path: Path) -> None:
        """Run the import health gate then cascade from a raw snapshot.

        This is the primary automated entry point. The health gate enforces
        pipeline-rules §8: no match/reference/section/reindex/review step runs
        on a red gate for active dashboard sources.
        """
        self._check_import_health(snapshot_path)
        payload = match_stage.match_snapshot(snapshot_path, self.players)
        output = match_stage.default_output_path(payload, self.match_dir)
        self._write(output, payload, stage="source-match", inputs=[snapshot_path])
        self.cascade_from_match(output)

    def cascade_from_match(self, match_path: Path) -> None:
        artifacts = reference_stage.build_references(match_path)
        output_paths: list[Path] = []
        for artifact in artifacts:
            output = reference_stage.default_output_path(artifact, self.reference_dir)
            self._write(output, artifact, stage="source-reference", inputs=[match_path])
            output_paths.append(output)
        self.cascade_from_references(output_paths)

    def cascade_from_references(self, reference_paths: list[Path]) -> None:
        section = section_stage.build_section(
            reference_paths,
            self.comparison,
            section_key=None,
            meta={},
        )
        output = section_stage.default_output_path(section, self.candidate_dir)
        self._write(output, section, stage="comparison-section", inputs=reference_paths)
        self.cascade_from_section(output)

    def cascade_from_section(self, section_path: Path) -> None:
        """Run merge (fail-closed zero-fill check), reindex, and review.

        The merge stage is required by pipeline-rules §3: the zero-fill check
        must pass before reference-compute reindexing can proceed. The merged
        candidate artifact and candidate report are written under candidate_dir
        alongside the section artifact. Promotion is never automatic; it still
        requires ``promote_comparison_section.py --approve``.

        Note: every stage is always visited — no early stop on unchanged
        outputs. This ensures that a deleted reindexed/review artifact is
        always restored, and that a changed comparison fixture (ESPN anchor)
        or triage file propagates to the affected stage even when the section
        itself is unchanged.
        """
        section = load_json(section_path)
        # merge_candidate performs the fail-closed zero-fill check (raises
        # SystemExit if any native value is null/non-numeric or placed_count
        # mismatches). It never writes under data/.
        merged, report = merge_stage.merge_candidate(section_path, self.comparison)

        merged_out = default_merge_candidate_path(section, self.candidate_dir)
        self._write(merged_out, merged, stage="comparison-merge", inputs=[section_path])

        report_out = default_merge_report_path(section, self.candidate_dir)
        self._write(report_out, report, stage="comparison-merge-report", inputs=[section_path])

        self._run_reindex(section_path)

    def _run_reindex(self, section_path: Path) -> None:
        """Reindex a candidate section and cascade into review."""
        section, review_rows = reindex_stage.reindex_section(
            str(section_path),
            fixture_path=str(self.comparison),
            players_path=str(self.players),
        )
        output = default_reindexed_path(section, self.reindex_dir)
        self._write(output, section, stage="comparison-reindex", inputs=[section_path], indent=1, sort_keys=False)
        if review_rows:
            self.steps[-1]["review_rows"] = len(review_rows)
        self.cascade_from_reindexed(output)

    def cascade_from_reindexed(self, reindexed_path: Path) -> None:
        report = review_stage.review_candidate(
            str(reindexed_path),
            triage_path=str(self.triage) if self.triage else None,
            fixture_path=str(self.comparison),
            players_path=str(self.players),
        )
        output = default_review_path(report_source(report, reindexed_path), self.review_dir)
        self._write(output, report, stage="comparison-review", inputs=[reindexed_path], indent=1, sort_keys=False)
        self.steps[-1]["verdict"] = report["verdict"]
        self.review_verdicts.append(str(report["verdict"]))

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def write_report(self, *, trigger: str) -> None:
        report = {
            "schema": "trade-value-cascade-report-v1",
            "trigger": trigger,
            "chain": [
                "supabase-import/source-import",
                "source-match",
                "source-reference",
                "comparison-section",
                "comparison-merge + comparison-merge-report",
                "comparison-reindex",
                "comparison-review",
            ],
            "promotion": "not automatic; use comparison-promote with APPROVE after a ready review",
            "steps": self.steps,
        }
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(dump_json(report), encoding="utf-8")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def report_source(report: dict[str, Any], reindexed_path: Path) -> dict[str, Any]:
    """Build a tiny reindexed-like shape for the review output path."""
    try:
        reindexed = load_json(reindexed_path)
    except (OSError, json.JSONDecodeError):
        reindexed = {}
    return {
        "source_key": report.get("source_key") or reindexed.get("source_key"),
        "fetched_at": reindexed.get("fetched_at"),
        "combos": reindexed.get("combos", {}),
    }


def infer_stage(paths: list[Path]) -> str:
    if len(paths) > 1:
        stages = {infer_stage([path]) for path in paths}
        if stages != {"reference"}:
            raise SystemExit(f"Multiple inputs are only supported for reference artifacts; got {sorted(stages)}")
        return "reference"
    payload = load_json(paths[0])
    stage = SCHEMA_STAGE.get(payload.get("schema"))
    if stage is None:
        raise SystemExit(f"Cannot cascade from unsupported schema {payload.get('schema')!r} in {paths[0]}")
    return stage


def output_dirs(args: argparse.Namespace) -> dict[str, Any]:
    if args.output_root:
        base = Path(args.output_root)
        dirs = {
            "raw_dir": base / "raw" / "sources",
            "match_dir": base / "source-matches",
            "reference_dir": base / "source-references",
            "candidate_dir": base / "comparison-candidates",
            "reindex_dir": base / "comparison-reference",
            "review_dir": base / "comparison-review",
            "report_path": args.report or base / "pipeline-cascade-report.json",
        }
    else:
        dirs = {
            "raw_dir": Path(args.raw_dir) if args.raw_dir else supabase_import_stage.DEFAULT_OUTPUT_DIR,
            "match_dir": Path(args.match_dir) if args.match_dir else match_stage.DEFAULT_OUTPUT_DIR,
            "reference_dir": Path(args.reference_dir) if args.reference_dir else reference_stage.DEFAULT_OUTPUT_DIR,
            "candidate_dir": Path(args.candidate_dir) if args.candidate_dir else section_stage.DEFAULT_OUTPUT_DIR,
            "reindex_dir": Path(args.reindex_dir) if args.reindex_dir else ROOT / "output" / "comparison-reference",
            "review_dir": Path(args.review_dir) if args.review_dir else ROOT / "output" / "comparison-review",
            "report_path": args.report or ROOT / "output" / "pipeline-cascade-report.json",
        }
    return dirs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source", help="run the DB import for this dashboard source, then cascade")
    source_group.add_argument("--raw-input", type=Path, help="import this CSV/JSON raw source file, then cascade")
    source_group.add_argument("--input", type=Path, nargs="+", help="existing artifact(s) to cascade from")
    parser.add_argument("--scoring")
    parser.add_argument("--raw-source", help="source name for --raw-input")
    parser.add_argument("--teams", type=int)
    parser.add_argument("--fetched-at")
    parser.add_argument("--source-url")
    parser.add_argument("--players", type=Path, default=match_stage.DEFAULT_PLAYERS)
    parser.add_argument("--comparison", type=Path, default=section_stage.DEFAULT_COMPARISON)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--raw-dir", type=Path, default=None)
    parser.add_argument("--match-dir", type=Path, default=None)
    parser.add_argument("--reference-dir", type=Path, default=None)
    parser.add_argument("--candidate-dir", type=Path, default=None)
    parser.add_argument("--reindex-dir", type=Path, default=None)
    parser.add_argument("--review-dir", type=Path, default=None)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--triage", type=Path)
    parser.add_argument("--health", type=Path, default=None,
                        help="import health JSON (default: output/source-import-health.json for "
                             "--source/--raw-input; skipped for --input intermediate artifacts)")
    parser.add_argument("--skip-health-check", action="store_true",
                        help="bypass the import health gate (use only for tests or non-active sources)")
    parser.add_argument("--force", action="store_true",
                        help="rewrite downstream artifacts even if material content is unchanged")
    args = parser.parse_args(argv)

    dirs = output_dirs(args)

    # Determine health path: applies to --source and --raw-input (primary automated
    # entry points). Intermediate --input artifacts bypass the gate by default.
    if args.skip_health_check:
        health_path: Path | None = None
    elif args.health:
        health_path = args.health
    elif args.source or args.raw_input:
        # Automated entry: enforce health gate using the default health file.
        health_path = DEFAULT_HEALTH_PATH
    else:
        # Intermediate artifact entry (--input): gate bypass is documented
        # in the module docstring — the human explicitly chose this artifact.
        health_path = None

    cascade = Cascade(
        players=args.players,
        comparison=args.comparison,
        triage=args.triage,
        force=args.force,
        health_path=health_path,
        **dirs,
    )

    trigger = ""
    if args.source:
        snapshot = cascade.import_supabase_source(args.source)
        trigger = f"supabase-import:{args.source}"
        cascade.cascade_from_snapshot(snapshot)
    elif args.raw_input:
        snapshot = cascade.import_raw_file(
            args.raw_input,
            source=args.raw_source,
            scoring=args.scoring,
            teams=args.teams,
            fetched_at=args.fetched_at,
            source_url=args.source_url,
        )
        trigger = f"source-import:{args.raw_input}"
        cascade.cascade_from_snapshot(snapshot)
    else:
        inputs = [Path(path) for path in args.input or []]
        stage = infer_stage(inputs)
        trigger = f"{stage}:{','.join(str(path) for path in inputs)}"
        if stage == "snapshot":
            cascade.cascade_from_snapshot(inputs[0])
        elif stage == "match":
            cascade.cascade_from_match(inputs[0])
        elif stage == "reference":
            cascade.cascade_from_references(inputs)
        elif stage == "section":
            cascade.cascade_from_section(inputs[0])
        elif stage == "reindexed":
            cascade.cascade_from_reindexed(inputs[0])
        elif stage == "review":
            cascade.steps.append(
                {
                    "stage": "comparison-review",
                    "inputs": [str(inputs[0])],
                    "output": str(inputs[0]),
                    "status": "already-terminal",
                    "verdict": load_json(inputs[0]).get("verdict"),
                }
            )

    cascade.write_report(trigger=trigger)

    print(f"cascade report -> {cascade.report_path}")
    for step in cascade.steps:
        extra = f" ({step['verdict']})" if step.get("verdict") else ""
        print(f"{step['stage']}: {step['status']}{extra} -> {step['output']}")

    return 2 if any(verdict == "hold" for verdict in cascade.review_verdicts) else 0


if __name__ == "__main__":
    raise SystemExit(main())
