#!/usr/bin/env python3
"""Completed Actions evidence, including runs which never reached checkout.

Read only trusted API JSON, never execute or download code from the observed run.
Cancellation alone does not establish replacement: preserve that uncertainty.
"""
import argparse
import json
from pathlib import Path
from pipelines.lib.timestamps import parse_iso_timestamp


def seconds(start, end):
    if not start or not end:
        return None
    return max(0, (parse_iso_timestamp(end) - parse_iso_timestamp(start)).total_seconds())


def report(run, jobs):
    rows = []
    for job in jobs:
        rows.append({
            "name": job["name"], "conclusion": job.get("conclusion"),
            "queue_seconds": seconds(run.get("created_at"), job.get("started_at")),
            "execution_seconds": seconds(job.get("started_at"), job.get("completed_at")),
            "steps": [{"name": step["name"], "conclusion": step.get("conclusion"),
                       "seconds": seconds(step.get("started_at"), step.get("completed_at"))}
                      for step in job.get("steps", [])],
        })
    return {
        "run_id": run["id"], "attempt": run.get("run_attempt"),
        "head_sha": run["head_sha"], "head_branch": run.get("head_branch"),
        "url": run.get("html_url"), "status": run["status"],
        "conclusion": run.get("conclusion"), "jobs": rows,
        "replacement": ("unknown: cancelled may mean pending replacement or manual cancellation; "
                        "Actions does not supply the cause" if run.get("conclusion") == "cancelled"
                        else "not indicated"),
        "timing_scope": "queue includes environment/runner/concurrency wait; step totals do not attribute API versus computation",
    }


def markdown(data):
    lines = [f"## Chain run {data['run_id']} (attempt {data['attempt']})",
             f"Head: `{data['head_sha']}`", f"Terminal status: {data['status']} / {data['conclusion']}",
             f"Replacement: {data['replacement']}", data["timing_scope"],
             "", "| Job / step | Conclusion | Seconds |", "| --- | --- | --- |"]
    for job in data["jobs"]:
        lines.append(f"| {job['name']} (queue) | | {job['queue_seconds']} |")
        lines.append(f"| {job['name']} (execution) | {job['conclusion']} | {job['execution_seconds']} |")
        for step in job["steps"]:
            name = step['name'].replace('|', '\\|').replace('\n', ' ')
            lines.append(f"| {name} | {step['conclusion']} | {step['seconds']} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--jobs', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    data = report(json.loads(Path(args.run).read_text()), json.loads(Path(args.jobs).read_text()))
    Path(args.output).write_text(json.dumps(data, indent=2) + '\n')
    print(markdown(data))


if __name__ == '__main__':
    main()
