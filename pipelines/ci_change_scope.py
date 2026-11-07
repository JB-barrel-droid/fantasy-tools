"""Is this PR docs-only? Then the required checks report success without the heavy build (JEG-1551).

`preview` and `v2-render` used to skip docs-only PRs with a `paths` filter
(JEG-1169). A required check that never runs stays pending, so once they are
required on main a docs-only PR could never merge. The filter moved here: the
workflows always run, and the cheap pr-state job decides. Same rule as the old
filter: every changed file is Markdown or under docs/, except the docs the
build reads; a rename counts by both names. Any doubt (not a PR, API error, a
list that may be cut off) means not docs-only, so the full check runs.

    python3 -m pipelines.ci_change_scope   # writes docs_only=true|false to $GITHUB_OUTPUT
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
from urllib.request import Request, urlopen

# Docs the site build reads; a change to one runs the full check.
BUILD_DOCS = ("docs/methodology.md", "docs/math-review-agenda.md",
              "docs/use-ddf-in-claude-chatgpt.md", "app/llm/*")
FILE_LIMIT = 3000


def is_doc(name):
    if any(fnmatch.fnmatch(name, p) for p in BUILD_DOCS):
        return False
    return name.endswith(".md") or name.startswith("docs/")


def docs_only(files):
    return bool(files) and all(is_doc(f) for f in files)


def names(batch):
    """Both names of a renamed file: moving the engine into docs/ is not a docs change."""
    out = []
    for f in batch:
        for key in ("filename", "previous_filename"):
            if f.get(key):
                out.append(f[key])
    return out


def _files(repo, number, token):
    out, page = [], 1
    while True:
        request = Request(
            f"https://api.github.com/repos/{repo}/pulls/{number}/files?per_page=100&page={page}",
            headers={"Accept": "application/vnd.github+json",
                     "Authorization": f"Bearer {token}",
                     "X-GitHub-Api-Version": "2022-11-28"},
        )
        with urlopen(request, timeout=20) as response:
            batch = json.load(response)
        out.extend(names(batch))
        if len(batch) < 100:
            return out
        page += 1


def decide(environ, list_files=_files):
    if environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return False, "not a pull_request event"
    try:
        with open(environ["GITHUB_EVENT_PATH"], encoding="utf-8") as handle:
            number = json.load(handle)["pull_request"]["number"]
        files = list_files(environ["GITHUB_REPOSITORY"], number, environ["GH_TOKEN"])
    except Exception as error:  # noqa: BLE001 - doubt runs the full check
        return False, f"changed files unavailable ({type(error).__name__})"
    if len(files) >= FILE_LIMIT:
        return False, "changed-file list may be cut off"
    if docs_only(files):
        return True, f"docs-only change ({len(files)} file(s))"
    return False, "code or build input changed"


def main(argv, environ=None):
    environ = os.environ if environ is None else environ
    only, reason = decide(environ)
    print(f"docs_only={'true' if only else 'false'}: {reason}")
    out = environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(f"docs_only={'true' if only else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
