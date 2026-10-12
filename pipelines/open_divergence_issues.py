"""JEG-610: open one Linear sub-issue per source-week that the divergence check
flags warn or investigate (and nobody has resolved).

Reads the built report (`dist/modules/source-divergence.json`), builds an issue
for each unresolved flagged source, skips any whose key is already a child of
the parent issue, and creates the rest through the Linear GraphQL API.

The token comes from the LINEAR_API_KEY environment variable only (a GitHub
Actions secret). With no token the script prints what it would open and exits 0,
so it is safe to run anywhere. `--dry-run` never calls the network.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPORT = REPO / "dist" / "modules" / "source-divergence.json"
API = "https://api.linear.app/graphql"
PARENT = "JEG-460"
FLAGGED = ("warn", "investigate")


def issue_key(source: str, week) -> str:
    return f"divergence:{source}:w{week}"


def pending_issues(report: dict) -> list[dict]:
    """One entry per source-week that is flagged and has no recorded resolution."""
    out = []
    for source, row in sorted((report.get("sources") or {}).items()):
        status = row.get("status")
        if status not in FLAGGED:
            continue  # ok, n/a, or reviewed (a resolution is recorded)
        week = row.get("week", report.get("week"))
        key = issue_key(source, week)
        reasons = row.get("reasons") or []
        label = row.get("label", source)
        body = [
            f"Automatic: the source divergence check marked **{label}** "
            f"`{status}` for week {week}.",
            "",
            row.get("message", ""),
            "",
        ]
        if reasons:
            body += ["Why it was flagged:"] + [f"- {r}" for r in reasons] + [""]
        body += ["Checklist:"] + [f"- [ ] {item}" for item in report.get("checklist") or []]
        body += ["", f"Key: `{key}` (used to avoid opening a duplicate)."]
        out.append({
            "key": key,
            "title": f"Divergence {status}: {label}, week {week} [{key}]",
            "description": "\n".join(body),
        })
    return out


def _graphql(token: str, query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        API, data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Content-Type": "application/json", "Authorization": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise RuntimeError(f"Linear API error: {payload['errors']}")
    return payload["data"]


def existing_titles(token: str, parent: str) -> tuple[str, str, list[str]]:
    """(parent uuid, team uuid, titles of the parent's children, archived included)."""
    data = _graphql(token, """query($id:String!){issue(id:$id){id team{id}
        children(first:250, includeArchived:true){nodes{title}}}}""", {"id": parent})["issue"]
    return data["id"], data["team"]["id"], [n["title"] for n in data["children"]["nodes"]]


def create(token: str, team_id: str, parent_id: str, item: dict) -> str:
    data = _graphql(token, """mutation($i:IssueCreateInput!){issueCreate(input:$i){
        success issue{identifier}}}""",
        {"i": {"teamId": team_id, "parentId": parent_id,
               "title": item["title"], "description": item["description"]}})
    return data["issueCreate"]["issue"]["identifier"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path, default=REPORT)
    ap.add_argument("--parent", default=PARENT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    report = json.loads(args.report.read_text())
    items = pending_issues(report)
    token = os.environ.get("LINEAR_API_KEY", "").strip()
    if args.dry_run or not token:
        why = "dry run" if args.dry_run else "LINEAR_API_KEY not set"
        print(f"{why}: {len(items)} issue(s) would be considered")
        for it in items:
            print(f"  {it['title']}")
        return 0
    if not items:
        print("nothing flagged")
        return 0
    parent_id, team_id, titles = existing_titles(token, args.parent)
    for it in items:
        if any(it["key"] in t for t in titles):
            print(f"exists, skipped: {it['key']}")
            continue
        print(f"opened {create(token, team_id, parent_id, it)} for {it['key']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
