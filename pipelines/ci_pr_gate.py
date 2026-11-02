"""Fail-closed PR state check for the expensive preview and render jobs.

The workflow event is only a snapshot. Query the current PR before spending a
runner on a build and again before reporting the required check as successful.

An idle ready PR gets no further event, so a check that fails on one API blip
stays red until someone re-runs it. Reads are retried a bounded number of times
(JEG-1292) and still fail closed after the last attempt.
"""

import json
import os
import sys
import time
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# Seconds slept before the second and third reads: three reads over about 30 s.
RETRY_DELAYS = (10, 20)


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


def transient(error):
    """Network errors, 5xx, 429 and rate-limit 403s are retried; 404 and other 4xx are not."""
    if not isinstance(error, HTTPError):
        return True
    if error.code >= 500 or error.code == 429:
        return True
    if error.code != 403:
        return False
    if error.headers and (error.headers.get("x-ratelimit-remaining") == "0"
                          or error.headers.get("retry-after")):
        return True
    try:
        return "rate limit" in error.read().decode("utf-8", "replace").lower()
    except (OSError, ValueError):
        return False


def draft_lags(snapshot, live):
    """True when only the draft flag differs, as it can right after ready_for_review."""
    return (isinstance(live, dict) and live.get("state") == "open"
            and live.get("head", {}).get("sha") == snapshot.get("head", {}).get("sha")
            and isinstance(live.get("draft"), bool) and isinstance(snapshot.get("draft"), bool)
            and live["draft"] != snapshot["draft"])


def live_pull(fetch, repo, snapshot, token):
    """Read the live PR, retrying transient errors and a draft flag that has not caught up."""
    for delay in (*RETRY_DELAYS, None):
        try:
            live = fetch(repo, snapshot["number"], token)
        except (OSError, HTTPException) as error:
            if delay is None or not transient(error):
                raise
            reason = f"PR state read failed ({error})"
        else:
            if delay is None or not draft_lags(snapshot, live):
                return live
            reason = "live draft flag differs from the event"
        print(f"::warning::{reason}; reading again in {delay}s", file=sys.stderr)
        time.sleep(delay)


def decide(event_name, event, live=None):
    """Return (run_expensive, reason); unknown/stale PR state never passes."""
    if event_name in ("push", "workflow_dispatch", "merge_group"):
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
        snapshot = event.get("pull_request") or {}
        if not isinstance(snapshot.get("number"), int):
            raise ValueError("PR number is unavailable")
        live = live_pull(fetch, env.get("GITHUB_REPOSITORY"), snapshot, env.get("GH_TOKEN"))
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


def main(argv, environ=None, fetch=current_pull):
    try:
        return run(argv[0], environ, fetch)
    except (KeyError, OSError, ValueError, HTTPException) as error:
        print(f"::error::PR state verification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
