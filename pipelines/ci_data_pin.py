"""Run PR and merge-queue tests on known-good data, not on whatever data main has now (JEG-1551).

Bots commit fresh data to main dozens of times a day. PR checks used to build
`dist/` from the data on the PR's checkout, so one bad rebuild turned every
open PR red at once (JEG-1550, 2026-11-06). Code PRs now test against the data
from the newest main commit whose own data check passed: the newest successful
`v2 render test` run on a push to main. That run is the data check. A red one
holds the data, not the code PRs.

Paths a PR changes itself are left alone, so a PR that edits data or
fixtures still tests its own version. Any doubt (no token, API error, a file
list that may be cut off, a pin commit that cannot be fetched) leaves the
checkout as it is: the old behaviour, never a silent half-pin.

    python3 -m pipelines.ci_data_pin apply      # in CI, before `make sync`
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from urllib.request import Request, urlopen

# Paths the data bots commit to main (git log of the rebuild, bake, pulse,
# health and status commits, 2026-11-05 to 2026-11-07).
DATA_PATHS = (
    "data/fixtures/current",
    "data/ddf-two-tier",
    "data/inputs",
    "data/history",
    "dist/modules",
    "output",
)
DATA_CHECK_WORKFLOW = "v2-render-test.yml"
PINNED_EVENTS = ("pull_request", "merge_group")
# The compare API returns at most 300 files; a list that long may be cut off.
COMPARE_FILE_LIMIT = 300


def _api(path, token):
    request = Request(
        f"https://api.github.com/{path}",
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": f"Bearer {token}",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def known_good_sha(runs_payload):
    """Head SHA of the newest successful push run on main, or None."""
    for run in runs_payload.get("workflow_runs") or []:
        if (run.get("event") == "push" and run.get("head_branch") == "main"
                and run.get("conclusion") == "success" and run.get("head_sha")):
            return run["head_sha"]
    return None


def event_range(event_name, payload):
    """(base_sha, head_sha) the change is measured against, or (None, None)."""
    if event_name == "pull_request":
        pr = payload.get("pull_request") or {}
        return (pr.get("base") or {}).get("sha"), (pr.get("head") or {}).get("sha")
    if event_name == "merge_group":
        group = payload.get("merge_group") or {}
        return group.get("base_sha"), group.get("head_sha")
    return None, None


def changed_files(compare_payload):
    """File names the change touches, or None when the list may be incomplete."""
    files = compare_payload.get("files")
    if files is None or len(files) >= COMPARE_FILE_LIMIT:
        return None
    return [f["filename"] for f in files if f.get("filename")]


def paths_to_pin(changed, data_paths=DATA_PATHS):
    """Data paths the change leaves alone; those are the ones safe to pin."""
    def touched(root):
        return any(name == root or name.startswith(root + "/") for name in changed)
    return [p for p in data_paths if not touched(p)]


def plan(event_name, payload, fetch_api):
    """Return (pin_sha, paths, reason). pin_sha None means leave the checkout as it is."""
    if event_name not in PINNED_EVENTS:
        return None, [], f"{event_name or 'unknown'} event tests the data it has"
    base, head = event_range(event_name, payload)
    if not base or not head:
        return None, [], "event has no base and head commit"
    try:
        compare = fetch_api(f"compare/{base}...{head}")
        runs = fetch_api(f"actions/workflows/{DATA_CHECK_WORKFLOW}/runs"
                         "?branch=main&event=push&status=success&per_page=5")
    except Exception as error:  # noqa: BLE001 - any API doubt keeps the old behaviour
        return None, [], f"GitHub API unavailable ({type(error).__name__})"
    changed = changed_files(compare)
    if changed is None:
        return None, [], "changed-file list may be incomplete"
    pin = known_good_sha(runs)
    if not pin:
        return None, [], "no passing data check on main yet"
    paths = paths_to_pin(changed)
    if not paths:
        return None, [], "the change edits every data path"
    return pin, paths, "ok"


def _git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True)


def apply(environ=None, fetch_api=None, git=_git):
    environ = os.environ if environ is None else environ
    event_name = environ.get("GITHUB_EVENT_NAME", "")
    payload = {}
    event_path = environ.get("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        with open(event_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    if fetch_api is None:
        repo, token = environ.get("GITHUB_REPOSITORY"), environ.get("GH_TOKEN")

        def fetch_api(path):
            if not repo or not token:
                raise ValueError("repository or token unavailable")
            return _api(f"repos/{repo}/{path}", token)

    pin, paths, reason = plan(event_name, payload, fetch_api)
    if pin:
        try:
            git("fetch", "--no-tags", "--depth=1", "origin", pin)
            present = []
            for path in paths:  # a path the pin lacks keeps the checkout's version
                try:
                    git("cat-file", "-e", f"{pin}:{path}")
                    present.append(path)
                except subprocess.CalledProcessError:
                    pass
            paths = present
            if not paths:
                raise subprocess.CalledProcessError(1, "restore", "no data path in the pin")
            git("restore", f"--source={pin}", "--worktree", "--", *paths)
        except subprocess.CalledProcessError as error:
            # A partial restore would mix two data states; put the checkout back.
            if paths:
                git("restore", "--source=HEAD", "--worktree", "--", *paths)
            pin, reason = None, f"could not restore pinned data ({error.returncode})"
    if pin:
        line = f"Tests use known-good data from main {pin[:12]} for: {', '.join(paths)}"
    else:
        line = f"Tests use this checkout's own data ({reason})"
    print(line)
    summary = environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return pin, paths, reason


def main(argv):
    if argv[1:] != ["apply"]:
        print("usage: python3 -m pipelines.ci_data_pin apply", file=sys.stderr)
        return 2
    apply()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
