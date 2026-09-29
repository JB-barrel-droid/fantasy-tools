#!/usr/bin/env python3
"""Cascade trade-value source updates through dependent pipeline stages.

The individual stage scripts remain the source of truth for each transform.
This runner wires them together after any earlier-stage update:

snapshot -> match -> source reference -> comparison section -> reindex -> review

Promotion is intentionally not automatic; it still requires the existing
human approval path.
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


SCHEMA_STAGE = {
    file_import_stage.SCHEMA: "snapshot",
    match_stage.OUTPUT_SCHEMA: "match",
    reference_stage.OUTPUT_SCHEMA: "reference",
    section_stage.OUTPUT_SCHEMA: "section",
    reindex_stage.SCHEMA: "reindexed",
    review_stage.SCHEMA: "review",
}


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


def stop_after_unchanged(stage: str, steps: list[dict[str, Any]], *, force: bool) -> bool:
    """True when the cascade can stop because this stage had no material delta."""
    if force or not steps or steps[-1]["stage"] != stage:
        return False
    if steps[-1]["status"] != "unchanged":
        return False
    steps.append(
        {
            "stage": "cascade-stop",
            "inputs": [steps[-1]["output"]],
            "output": None,
            "status": "skipped",
            "reason": f"{stage} output is materially unchanged",
        }
    )
    return True


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


class Cascade:
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
    ) -> None:
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
        self.steps: list[dict[str, Any]] = []
        self.review_verdicts: list[str] = []

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
        write_if_changed(
            output,
            snapshot,
            stage="source-import",
            inputs=[path],
            steps=self.steps,
            force=self.force,
        )
        return output

    def import_supabase_source(self, source: str) -> Path:
        result = supabase_import_stage.import_source(source, output_dir=self.raw_dir)
        snapshot_path = Path(result["snapshot_path"])
        self.steps.append(
            {
                "stage": "supabase-import",
                "inputs": [source],
                "output": str(snapshot_path),
                "status": "unchanged" if result["already_stamped"] else "written",
                "content_vintage": result["content_vintage"],
                "row_count": result["row_count"],
                "review_count": result["review_count"],
            }
        )
        return snapshot_path

    def cascade_from_snapshot(self, snapshot_path: Path) -> None:
        payload = match_stage.match_snapshot(snapshot_path, self.players)
        output = match_stage.default_output_path(payload, self.match_dir)
        write_if_changed(
            output,
            payload,
            stage="source-match",
            inputs=[snapshot_path],
            steps=self.steps,
            force=self.force,
        )
        if stop_after_unchanged("source-match", self.steps, force=self.force):
            return
        self.cascade_from_match(output)

    def cascade_from_match(self, match_path: Path) -> None:
        artifacts = reference_stage.build_references(match_path)
        output_paths: list[Path] = []
        for artifact in artifacts:
            output = reference_stage.default_output_path(artifact, self.reference_dir)
            write_if_changed(
                output,
                artifact,
                stage="source-reference",
                inputs=[match_path],
                steps=self.steps,
                force=self.force,
            )
            output_paths.append(output)
        if all(step["status"] == "unchanged" for step in self.steps[-len(output_paths):]):
            self.steps.append(
                {
                    "stage": "cascade-stop",
                    "inputs": [str(path) for path in output_paths],
                    "output": None,
                    "status": "skipped",
                    "reason": "all source-reference outputs are materially unchanged",
                }
            )
            return
        self.cascade_from_references(output_paths)

    def cascade_from_references(self, reference_paths: list[Path]) -> None:
        section = section_stage.build_section(
            reference_paths,
            self.comparison,
            section_key=None,
            meta={},
        )
        output = section_stage.default_output_path(section, self.candidate_dir)
        write_if_changed(
            output,
            section,
            stage="comparison-section",
            inputs=reference_paths,
            steps=self.steps,
            force=self.force,
        )
        if stop_after_unchanged("comparison-section", self.steps, force=self.force):
            return
        self.cascade_from_section(output)

    def cascade_from_section(self, section_path: Path) -> None:
        """Run merge (with fail-closed zero-fill check), then reindex, then review.

        The merge stage is required by pipeline-rules §3: the zero-fill check
        must pass before reference-compute reindexing can proceed.  The merged
        candidate artifact and candidate report are written under candidate_dir
        alongside the section artifact.  Promotion is never automatic; it still
        requires ``promote_comparison_section.py --approve``.
        """
        section = load_json(section_path)
        # merge_candidate performs the fail-closed zero-fill check (raises
        # SystemExit if any native value is null/non-numeric or placed_count
        # mismatches).  It never writes under data/.
        merged, report = merge_stage.merge_candidate(section_path, self.comparison)

        merged_out = default_merge_candidate_path(section, self.candidate_dir)
        write_if_changed(
            merged_out,
            merged,
            stage="comparison-merge",
            inputs=[section_path],
            steps=self.steps,
            force=self.force,
        )

        report_out = default_merge_report_path(section, self.candidate_dir)
        write_if_changed(
            report_out,
            report,
            stage="comparison-merge-report",
            inputs=[section_path],
            steps=self.steps,
            force=self.force,
        )

        # Stop if both merge artifacts are materially unchanged — meaning the
        # candidate section AND the comparison fixture haven't changed, so
        # reindex would produce the same output.
        merge_steps = [s for s in self.steps[-2:] if s["stage"] in {"comparison-merge", "comparison-merge-report"}]
        if not self.force and len(merge_steps) == 2 and all(s["status"] == "unchanged" for s in merge_steps):
            self.steps.append(
                {
                    "stage": "cascade-stop",
                    "inputs": [str(section_path)],
                    "output": None,
                    "status": "skipped",
                    "reason": "comparison-merge output is materially unchanged",
                }
            )
            return

        self._run_reindex(section_path)

    def _run_reindex(self, section_path: Path) -> None:
        """Reindex a candidate section and cascade into review."""
        section, review_rows = reindex_stage.reindex_section(
            str(section_path),
            fixture_path=str(self.comparison),
            players_path=str(self.players),
        )
        output = default_reindexed_path(section, self.reindex_dir)
        write_if_changed(
            output,
            section,
            stage="comparison-reindex",
            inputs=[section_path],
            steps=self.steps,
            force=self.force,
            indent=1,
            sort_keys=False,
        )
        if review_rows:
            self.steps[-1]["review_rows"] = len(review_rows)
        if stop_after_unchanged("comparison-reindex", self.steps, force=self.force):
            return
        self.cascade_from_reindexed(output)

    def cascade_from_reindexed(self, reindexed_path: Path) -> None:
        report = review_stage.review_candidate(
            str(reindexed_path),
            triage_path=str(self.triage) if self.triage else None,
            fixture_path=str(self.comparison),
            players_path=str(self.players),
        )
        output = default_review_path(report_source(report, reindexed_path), self.review_dir)
        write_if_changed(
            output,
            report,
            stage="comparison-review",
            inputs=[reindexed_path],
            steps=self.steps,
            force=self.force,
            indent=1,
            sort_keys=False,
        )
        self.steps[-1]["verdict"] = report["verdict"]
        self.review_verdicts.append(str(report["verdict"]))

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


def output_dirs(args: argparse.Namespace) -> dict[str, Path]:
    if args.output_root:
        base = args.output_root
        return {
            "raw_dir": base / "raw" / "sources",
            "match_dir": base / "source-matches",
            "reference_dir": base / "source-references",
            "candidate_dir": base / "comparison-candidates",
            "reindex_dir": base / "comparison-reference",
            "review_dir": base / "comparison-review",
            "report_path": args.report or base / "pipeline-cascade-report.json",
        }
    return {
        "raw_dir": args.raw_dir,
        "match_dir": args.match_dir,
        "reference_dir": args.reference_dir,
        "candidate_dir": args.candidate_dir,
        "reindex_dir": args.reindex_dir,
        "review_dir": args.review_dir,
        "report_path": args.report or ROOT / "output" / "pipeline-cascade-report.json",
    }


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
    parser.add_argument("--raw-dir", type=Path, default=supabase_import_stage.DEFAULT_OUTPUT_DIR)
    parser.add_argument("--match-dir", type=Path, default=match_stage.DEFAULT_OUTPUT_DIR)
    parser.add_argument("--reference-dir", type=Path, default=reference_stage.DEFAULT_OUTPUT_DIR)
    parser.add_argument("--candidate-dir", type=Path, default=section_stage.DEFAULT_OUTPUT_DIR)
    parser.add_argument("--reindex-dir", type=Path, default=ROOT / "output" / "comparison-reference")
    parser.add_argument("--review-dir", type=Path, default=ROOT / "output" / "comparison-review")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--triage", type=Path)
    parser.add_argument("--force", action="store_true", help="rewrite downstream artifacts even if material content is unchanged")
    args = parser.parse_args(argv)

    dirs = output_dirs(args)
    cascade = Cascade(
        players=args.players,
        comparison=args.comparison,
        triage=args.triage,
        force=args.force,
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
