"""Lossless validation-breach/1 transport shared by checks and status consumers.

One JSON object per line in the log is the authoritative sink. Human summaries
are derived from the same object; no rows or numeric precision are discarded.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import TextIO

SCHEMA = "validation-breach/1"
PREFIX = "VALIDATION_BREACH_JSON "
RUNBOOK = "runbooks/validation-failures.md#band-line"
POLICY = "docs/exemption-decision-policy.md"


@dataclass
class PerturbationResult:
    worst: float
    flipped: bool
    record: dict

    def __iter__(self):
        # Preserve the two-value interface used by mutation/cache workers.
        return iter((self.worst, self.flipped))


def render(record: dict) -> str:
    p, a = record["perturbed"], record["argmax"]
    bound = record["bound"]
    return (f"[BREACH] {record['check_id']} schema={record['schema']} "
            f"status={record['status']} role={record['blocking_role']} "
            f"perturbed={p['name']} [{p['player_key']}, {p['pos']}] "
            f"affected={a['name']} [{a['player_key']}] "
            f"before={a['before']!r} after={a['after']!r} signed={a['signed']!r}; "
            f"observed={a['absolute']!r} > bound={bound['value']!r} {bound['units']} "
            f"excess={a['excess']!r}; mechanism={record['mechanism']['name']}; "
            f"setting={record['setting']}; causal_inputs={record['perturbation']}; "
            f"affected_count={len(record['affected'])}; "
            f"runbook={record['runbook']} policy={record['policy']}; "
            f"reproduce={record['reproduce']}")


def emit(record: dict, stream: TextIO | None = None) -> str:
    stream = stream or sys.stdout
    summary = render(record)
    print(summary, file=stream)
    print(PREFIX + json.dumps(record, sort_keys=True, allow_nan=False), file=stream)
    return summary


def records_from_log(log_text: str) -> list[dict]:
    records = []
    for line in log_text.splitlines():
        if line.startswith(PREFIX):
            record = json.loads(line[len(PREFIX):])
            if record.get("schema") != SCHEMA:
                raise ValueError("unsupported validation breach schema")
            records.append(record)
    return records
