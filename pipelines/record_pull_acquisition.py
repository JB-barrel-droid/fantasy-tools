#!/usr/bin/env python3
"""Record pull acquisition results to pipeline-checkpoints.json artifact.

CLI:
  python3 pipelines/record_pull_acquisition.py --source <src> --status acquired|unchanged|failed --rows N --vintage V [--reason TEXT]

Importable:
  from pipelines.record_pull_acquisition import record_acquisition
  record_acquisition(source, status, rows, vintage, reason=None)

Reads dist/modules/pipeline-checkpoints.json, writes/updates the acquisition.<source>
block as {status, rows, vintage, recorded_at, reason}, preserving all other keys.
"""

import argparse
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ARTIFACT_PATH = REPO / "dist" / "modules" / "pipeline-checkpoints.json"


class AcquisitionError(Exception):
    """Structured error for acquisition recording failures."""
    pass


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def load_artifact(path):
    """Load the pipeline-checkpoints.json artifact."""
    path = Path(path)
    if not path.exists():
        raise AcquisitionError(f"Artifact not found: {path}")

    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise AcquisitionError(f"Artifact unparseable: {path}: {e}")


def save_artifact(path, data):
    """Save the pipeline-checkpoints.json artifact."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def record_acquisition(source, status, rows, vintage, reason=None):
    """Record acquisition result for a source.

    Args:
        source: Source name (e.g., 'espn', 'cbs')
        status: One of 'acquired', 'unchanged', 'failed'
        rows: Number of rows (int) - ignored if status is 'unchanged'
        vintage: Vintage string (e.g., '2026-10-02')
        reason: Optional reason text

    Returns:
        dict: The updated acquisition block

    Raises:
        AcquisitionError: If artifact is missing or unparseable
    """
    if status not in ("acquired", "unchanged", "failed"):
        raise AcquisitionError(f"Invalid status: {status}. Must be 'acquired', 'unchanged', or 'failed'")

    data = load_artifact(ARTIFACT_PATH)

    # Initialize acquisition block if needed
    if "acquisition" not in data:
        data["acquisition"] = {}

    # Build the acquisition record
    record = {
        "status": status,
        "vintage": vintage,
        "recorded_at": iso_now(),
    }

    # Only include rows when relevant
    if status in ("acquired", "failed"):
        record["rows"] = rows

    if reason:
        record["reason"] = reason

    # Update the source-specific block
    data["acquisition"][source] = record

    # Save preserving other keys
    save_artifact(ARTIFACT_PATH, data)

    return record


def record_acquisition_to_file(path, source, status, rows, vintage, reason=None):
    """Record acquisition result to a specific file (for testing with temp copies).

    Args:
        path: Path to the artifact file
        source: Source name (e.g., 'espn', 'cbs')
        status: One of 'acquired', 'unchanged', 'failed'
        rows: Number of rows (int) - ignored if status is 'unchanged'
        vintage: Vintage string (e.g., '2026-10-02')
        reason: Optional reason text

    Returns:
        dict: The updated acquisition block
    """
    if status not in ("acquired", "unchanged", "failed"):
        raise AcquisitionError(f"Invalid status: {status}. Must be 'acquired', 'unchanged', or 'failed'")

    path = Path(path)
    if not path.exists():
        raise AcquisitionError(f"Artifact not found: {path}")

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise AcquisitionError(f"Artifact unparseable: {path}: {e}")

    # Initialize acquisition block if needed
    if "acquisition" not in data:
        data["acquisition"] = {}

    # Build the acquisition record
    record = {
        "status": status,
        "vintage": vintage,
        "recorded_at": iso_now(),
    }

    # Only include rows when relevant
    if status in ("acquired", "failed"):
        record["rows"] = rows

    if reason:
        record["reason"] = reason

    # Update the source-specific block
    data["acquisition"][source] = record

    # Save preserving other keys
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    return record


def main():
    parser = argparse.ArgumentParser(
        description="Record pull acquisition to pipeline-checkpoints.json"
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source name (e.g., espn, cbs)"
    )
    parser.add_argument(
        "--status",
        required=True,
        choices=["acquired", "unchanged", "failed"],
        help="Acquisition status"
    )
    parser.add_argument(
        "--rows",
        type=int,
        required=True,
        help="Number of rows acquired (ignored for unchanged)"
    )
    parser.add_argument(
        "--vintage",
        required=True,
        help="Vintage string (e.g., 2026-10-02)"
    )
    parser.add_argument(
        "--reason",
        default=None,
        help="Optional reason text"
    )

    args = parser.parse_args()

    # For 'unchanged', rows should be 0 or ignored
    if args.status == "unchanged":
        rows = 0
    else:
        rows = args.rows

    try:
        record_acquisition(
            source=args.source,
            status=args.status,
            rows=rows,
            vintage=args.vintage,
            reason=args.reason
        )
        print(f"Recorded acquisition: {args.source} -> {args.status}")
        sys.exit(0)
    except AcquisitionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
