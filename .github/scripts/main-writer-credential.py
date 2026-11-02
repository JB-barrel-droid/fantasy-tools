#!/usr/bin/env python3
"""Ephemeral Git credential IPC for JEG-1441 publication steps.

Git invokes this helper with get/store/erase. Only get can return a credential,
only to Git's private pipe, for this repository over HTTPS. Nothing is stored.
The GitHub environment policy, not this source code, protects the App key.
"""
import os
import sys

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipelines"))
from lib.repository import WRITER_REPOSITORIES


def credential(request, environment):
    """Select an existing step token or refuse without echoing input values."""
    path = request.get("path", "").strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if (request.get("protocol") != "https"
            or request.get("host", "").lower() != "github.com"
            or path.lower() not in WRITER_REPOSITORIES
            or environment.get("GITHUB_REPOSITORY", "").lower() != path.lower()):
        raise ValueError("Credential destination is outside the writer repository")
    ref = environment.get("GITHUB_REF", "")
    if ref == "refs/heads/main":
        # Never fall back to the default token if main's App mint failed.
        token = environment.get("MAIN_WRITER_TOKEN", "")
    elif ref.startswith("refs/heads/") and ref != "refs/heads/":
        token = environment.get("BRANCH_WRITER_TOKEN", "")
    else:
        raise ValueError("Only branch workflow refs may publish")
    if not token or any(ch in token for ch in "\r\n\0"):
        raise ValueError("No valid step-scoped writer token is available")
    return {"username": "x-access-token", "password": token}


def main():
    operation = sys.argv[1] if len(sys.argv) == 2 else ""
    if operation in ("store", "erase"):
        return 0  # Deliberately no disk, Keychain, credential store or log.
    if operation != "get":
        return 1
    request = {}
    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line:
            break
        key, separator, value = line.partition("=")
        if separator:
            request[key] = value
    try:
        selected = credential(request, os.environ)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)  # Fixed messages, no values/snippets.
        return 1
    # This is Git's credential-helper protocol, never a job log or artifact.
    sys.stdout.write("username=" + selected["username"] + "\npassword=" + selected["password"] + "\n\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
