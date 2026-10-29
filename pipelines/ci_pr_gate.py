"""Fail-closed PR state check for the expensive preview and render jobs.

The workflow event is only a snapshot. Query the current PR before spending a
runner on a build and again before reporting the required check as successful.
"""

import json
import os
import sys
from urllib.request import Request, urlopen


def current_pull(repo, number, token):
    if not repo or not token:
        raise ValueError("repository or GitHub token is unavailable")
    request = Request(
        f"https://api.github.com/repos/{repo}/pulls/{number}",
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": f"Bearer {token}",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def decide(event_name, event, live=None):
    """Return (run_expensive, reason); unknown/stale PR state never passes."""
    if event_name in ("push", "workflow_dispatch"):
        return True, f"{event_name}: full verification required"
    if event_name != "pull_request":
        raise ValueError(f"unsupported event: {event_name}")
    snapshot = event.get("pull_request") or {}
    if event.get("action") not in ("opened", "synchronize", "reopened",
                                   "ready_for_review", "converted_to_draft"):
        raise ValueError("unexpected pull_request action")
    if not snapshot.get("number") or live is None:
        raise ValueError("PR number or live PR state is unavailable")
    if live.get("number") != snapshot["number"]:
        raise ValueError("live PR number does not match event")
    if live.get("state") != "open":
        return False, "PR is no longer open; full verification cannot pass"
    if live.get("head", {}).get("sha") != snapshot.get("head", {}).get("sha"):
        return False, "PR head moved since this event; full verification cannot pass"
    if not isinstance(live.get("draft"), bool) or not isinstance(snapshot.get("draft"), bool):
        raise ValueError("PR draft state is unavailable")
    if live["draft"] != snapshot["draft"]:
        return False, "PR draft state changed since this event; full verification cannot pass"
    if live["draft"]:
        return False, "Full verification deferred while this PR is a draft; mark it ready for review"
    return True, "Current ready PR head: full verification required"


def run(phase, environ=None, fetch=current_pull):
    env = os.environ if environ is None else environ
    with open(env["GITHUB_EVENT_PATH"], encoding="utf-8") as source:
        event = json.load(source)
    name = env["GITHUB_EVENT_NAME"]
    live = None
    if name == "pull_request":
        number = (event.get("pull_request") or {}).get("number")
        if not isinstance(number, int):
            raise ValueError("PR number is unavailable")
        live = fetch(env.get("GITHUB_REPOSITORY"), number, env.get("GH_TOKEN"))
    allowed, reason = decide(name, event, live)
    with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(f"### Full verification: {'required' if allowed else 'deferred or stale'}\n\n{reason}.\n")
    if phase == "gate":
        with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"run_expensive={'true' if allowed else 'false'}\n")
        print(reason)
        return 0
    if phase != "verify":
        raise ValueError(f"unknown phase: {phase}")
    if not allowed:
        raise ValueError(reason)
    print(reason)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run(sys.argv[1]))
    except (KeyError, OSError, ValueError) as error:
        print(f"::error::PR state verification failed: {error}", file=sys.stderr)
        sys.exit(1)
