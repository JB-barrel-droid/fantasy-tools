"""Find a bash that can run the workflow step scripts the tests execute.

On Windows `bash` on PATH is often C:\\Windows\\System32\\bash.exe (WSL) or the
WindowsApps stub, which cannot see the Windows temp dir the tests use. Git for
Windows ships a bash that can, so look for it next to git. Returns None when no
usable bash exists; callers skip only then (Linux CI always has one).
"""
from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _windows_candidates():
    if os.environ.get("FT_BASH"):
        yield Path(os.environ["FT_BASH"])
    git = shutil.which("git")
    if git:
        # Git\cmd\git.exe or Git\mingw64\bin\git.exe -> Git\bin\bash.exe
        for root in Path(git).resolve().parents:
            yield root / "bin" / "bash.exe"
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")):
        if base:
            yield Path(base) / "Git" / "bin" / "bash.exe"
    found = shutil.which("bash")
    if found and not any(part.lower() in ("system32", "windowsapps") for part in Path(found).parts):
        yield Path(found)


def _works(bash: str) -> bool:
    try:
        r = subprocess.run([bash, "-c", "echo ok"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and r.stdout.strip() == "ok"


@functools.lru_cache(maxsize=None)
def usable_bash() -> str | None:
    if sys.platform != "win32":
        return shutil.which("bash")
    for candidate in _windows_candidates():
        if candidate.is_file() and _works(str(candidate)):
            return str(candidate)
    return None
