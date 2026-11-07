"""Run PR and merge-queue tests on known-good data, not on whatever data main has now (JEG-1551).

Bots commit fresh data to main dozens of times a day. PR checks used to build
`dist/` from the data on the PR's checkout, so one bad rebuild turned every
open PR red at once (JEG-1550, 2026-11-06). Code PRs now test against the data
from the newest main commit whose own data check passed: the newest successful
`v2 render test` run on a push to main. That run is the data check. A red one
holds the data, not the code PRs.

Paths a PR changes itself (renames count by both names) are left alone, so a
PR that edits data or fixtures still tests its own version. Any doubt (no
token, API error, a file list that may be cut off, a pin commit that cannot be
fetched or lacks one of the paths) leaves the checkout as it is: the old
behaviour, never a silent half-pin. A failed restore is undone in full,
including files the pin added.

One run uses one pin: the pr-state job resolves it once (`plan`, written to
$GITHUB_OUTPUT as `data_pin`) and every build, shard and render job applies
that same answer through the DATA_PIN environment variable.

    python3 -m pipelines.ci_data_pin plan       # pr-state: writes data_pin=...
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
    """File names the change touches (both names of a rename), or None when the list may be incomplete."""
    files = compare_payload.get("files")
    if files is None or len(files) >= COMPARE_FILE_LIMIT:
        return None
    out = []
    for f in files:
        for key in ("filename", "previous_filename"):
            if f.get(key):
                out.append(f[key])
    return out


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


def encode(pin, paths, reason):
    """One line for $GITHUB_OUTPUT: `sha:path,path` or `none:reason`."""
    if pin:
        return f"{pin}:{','.join(paths)}"
    return "none:" + " ".join(str(reason).split())


def decode(value):
    """Inverse of encode; anything unreadable means leave the checkout."""
    value = (value or "").strip()
    head, sep, rest = value.partition(":")
    if not sep or head == "none" or not head:
        return None, [], rest or "no pin resolved for this run"
    paths = [p for p in rest.split(",") if p]
    if not paths or any(p not in DATA_PATHS for p in paths):
        return None, [], "unreadable pin for this run"
    return head, paths, "ok"


def _untracked(git, paths):
    out = git("ls-files", "--others", "-z", "--", *paths).stdout
    return {name for name in out.split("\0") if name}


def _event_plan(environ, fetch_api):
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

    return plan(event_name, payload, fetch_api)


def _report(environ, line):
    print(line)
    summary = environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def write_plan(environ=None, fetch_api=None):
    """pr-state: resolve the pin once for the whole run."""
    environ = os.environ if environ is None else environ
    pin, paths, reason = _event_plan(environ, fetch_api)
    value = encode(pin, paths, reason)
    out = environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(f"data_pin={value}\n")
    _report(environ, f"Data pin for this run: {value}")
    return pin, paths, reason


def apply(environ=None, fetch_api=None, git=_git):
    environ = os.environ if environ is None else environ
    if "DATA_PIN" in environ:
        pin, paths, reason = decode(environ["DATA_PIN"])
    else:
        pin, paths, reason = _event_plan(environ, fetch_api)
    if pin:
        before = None
        try:
            git("fetch", "--no-tags", "--depth=1", "origin", pin)
            for path in paths:  # a pin that lacks a path is not a complete snapshot
                try:
                    git("cat-file", "-e", f"{pin}:{path}")
                except subprocess.CalledProcessError:
                    raise subprocess.CalledProcessError(1, "cat-file", f"pin lacks {path}")
            before = _untracked(git, paths)
            git("restore", f"--source={pin}", "--worktree", "--", *paths)
        except subprocess.CalledProcessError as error:
            if before is not None:
                # A partial restore would mix two data states; put the checkout
                # back, including any file the pin added.
                git("restore", "--source=HEAD", "--worktree", "--", *paths)
                root = git("rev-parse", "--show-toplevel").stdout.strip()
                for name in sorted(_untracked(git, paths) - before):
                    try:
                        os.remove(os.path.join(root, name))
                    except FileNotFoundError:
                        pass
            pin, reason = None, f"could not restore pinned data ({error.returncode})"
    if pin:
        line = f"Tests use known-good data from main {pin[:12]} for: {', '.join(paths)}"
    else:
        line = f"Tests use this checkout's own data ({reason})"
    _report(environ, line)
    return pin, paths, reason


def main(argv):
    if argv[1:] == ["apply"]:
        apply()
        return 0
    if argv[1:] == ["plan"]:
        write_plan()
        return 0
    print("usage: python3 -m pipelines.ci_data_pin plan|apply", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
