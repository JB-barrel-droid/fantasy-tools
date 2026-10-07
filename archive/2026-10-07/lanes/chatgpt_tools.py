#!/usr/bin/env python3
"""Agentic ChatGPT lane: repo access via OpenAI function calling.

The old lane (chatgpt_adapter.py) was text-in/text-out: ChatGPT only saw the
brief. This loop gives it full working access to its OWN lane branch through
tools: it reads the real code, writes/edits files, and commits — all inside a
dedicated worktree, never the shared checkout.

Standing boundary: ChatGPT gets hands on its branch, never on main. Tools are
read-only plus file-write and commit; there are NO push/merge/deploy/shell
tools. It cannot touch main, cannot push to GitHub, cannot deploy. Roman
reviews every diff and integrates through the gated merge sweep.

Usage:
    python3 chatgpt_tools.py <brief.md> [--model gpt-5] [--max-iters 20]
The brief's "Branch:" line selects the lane branch (created as a worktree
under ~/workspace/worktrees/ if missing). Result goes to
lanes/inbox/chatgpt/<stem>-result.md like the old lane.
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

API_URL = "https://api.openai.com/v1/chat/completions"
ALLOWED = ("api.openai.com",)
DEFAULT_MODEL = "gpt-5"
MAIN_REPO = "/home/hatch/workspace/fantasy-tools"
WORKTREES = "/home/hatch/workspace/worktrees"
LANES_DIR = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(LANES_DIR, "inbox", "chatgpt")
MAX_ITERS = 40

# Set per-run by setup_worktree(); all tools operate inside it.
WORKDIR = MAIN_REPO


def _repo_path(path):
    """Resolve a worktree-relative path, rejecting escapes."""
    full = os.path.normpath(os.path.join(WORKDIR, path))
    if not full.startswith(WORKDIR + os.sep) and full != WORKDIR:
        raise ValueError(f"path escapes worktree: {path}")
    if "/.git/" in full or full.endswith("/.git"):
        raise ValueError("direct .git access is not allowed")
    return full


def setup_worktree(branch):
    """Ensure a dedicated worktree for the lane branch; return its path."""
    global WORKDIR
    slug = branch.replace("/", "-")
    wt = os.path.join(WORKTREES, slug)
    if os.path.exists(os.path.join(wt, ".git")):
        # reuse: in a worktree .git is a file, not a dir — use exists()
        subprocess.run(["git", "checkout", branch], cwd=wt,
                       capture_output=True, check=False)
    else:
        os.makedirs(WORKTREES, exist_ok=True)
        # base the branch on origin/main so it starts current
        subprocess.run(["git", "fetch", "origin", "main", "--quiet"],
                       cwd=MAIN_REPO, capture_output=True, check=False)
        r = subprocess.run(
            ["git", "worktree", "add", "-B", branch, wt, "origin/main"],
            cwd=MAIN_REPO, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"worktree setup failed: {r.stderr[:300]}")
    WORKDIR = wt
    print(f"worktree: {wt} on {branch}", flush=True)
    return wt


def tool_read_file(path, offset=0, limit=200):
    full = _repo_path(path)
    if os.path.isdir(full):
        raise ValueError(f"{path} is a directory, use list_dir")
    with open(full, "r", errors="replace") as f:
        lines = f.readlines()
    total = len(lines)
    chunk = lines[offset:offset + limit]
    return {"path": path, "total_lines": total,
            "shown": f"{offset + 1}-{offset + len(chunk)}",
            "content": "".join(chunk)}


def tool_list_dir(path="."):
    full = _repo_path(path)
    entries = sorted(os.listdir(full))
    out = []
    for e in entries:
        if e.startswith(".git"):
            continue
        p = os.path.join(full, e)
        out.append((e + "/") if os.path.isdir(p) else e)
    return {"path": path, "entries": out[:200],
            "truncated": len(out) > 200}


def tool_git(args):
    """Run a read-only git command. Only whitelisted subcommands."""
    allowed = {"log", "diff", "show", "status", "rev-parse", "ls-files",
               "for-each-ref", "blame"}
    if not args or args[0] not in allowed:
        raise ValueError(f"git subcommand not allowed: {args[:1]}")
    r = subprocess.run(["git"] + args, cwd=WORKDIR, capture_output=True,
                       text=True, timeout=60)
    out = (r.stdout + r.stderr)[-12000:]
    return {"exit": r.returncode, "output": out}


def tool_grep(pattern, path=".", include="*.py"):
    r = subprocess.run(
        ["grep", "-rn", "--include=" + include, pattern, _repo_path(path)],
        cwd=WORKDIR, capture_output=True, text=True, timeout=30)
    out = r.stdout[-8000:]
    return {"matches": out.count("\n"), "output": out}


# --- Supabase: read-only. Eyes on live data, never writes. ---

def _sb():
    import sys as _sys
    _sys.path.insert(0, "/home/hatch/workspace/skills/supabase-football-signal/bin")
    import sbclient
    return sbclient


def tool_db_tables():
    """List tables/views exposed by PostgREST."""
    sb = _sb()
    spec = sb.openapi_spec()
    paths = spec.get("paths", {})
    tables = sorted({p[1:] for p in paths
                     if p.startswith("/") and p not in ("/",)
                     and "/" not in p[1:] and p[1:] != "rpc"})
    return {"tables": tables}


def tool_db_describe(table):
    """Column names and types for one table/view."""
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table):
        raise ValueError("bad table name")
    sb = _sb()
    spec = sb.openapi_spec()
    defs = spec.get("definitions", {})
    d = defs.get(table, {})
    props = d.get("properties", {})
    return {"table": table,
            "columns": {k: v.get("type", "?") for k, v in props.items()}}


def tool_db_select(table, select="*", filters="", limit=25, order=""):
    """Read rows from a table/view. Read-only. Limit capped at 100."""
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table):
        raise ValueError("bad table name")
    limit = max(1, min(int(limit), 100))
    params = f"?select={select}&limit={limit}"
    if filters:
        params += "&" + filters.lstrip("&")
    if order:
        params += f"&order={order}"
    sb = _sb()
    rows = sb.get(table, params=params)
    if isinstance(rows, list):
        return {"table": table, "n": len(rows), "rows": rows}
    return {"table": table, "result": str(rows)[:4000]}


def tool_http_get(url):
    """Fetch a public https URL (e.g. the live Pages site). No credentials sent."""
    if not url.startswith("https://"):
        raise ValueError("only https URLs")
    req = urllib.request.Request(url, headers={"User-Agent": "lane-review/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return {"url": url, "status": e.code, "error": e.read().decode()[:500]}
    return {"url": url, "status": 200, "chars": len(body),
            "body": body[:15000]}

def tool_write_file(path, content):
    """Create or overwrite a file in the worktree. Directories created as needed."""
    full = _repo_path(path)
    if os.path.isdir(full):
        raise ValueError(f"{path} is a directory")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)
    return {"path": path, "bytes": len(content.encode())}


def tool_edit_file(path, old_text, new_text):
    """Surgical edit: replace first exact occurrence of old_text."""
    full = _repo_path(path)
    with open(full, "r", errors="replace") as f:
        content = f.read()
    if old_text not in content:
        # report nearby candidates to help the model fix the match
        return {"path": path, "replaced": False,
                "error": "old_text not found verbatim"}
    content = content.replace(old_text, new_text, 1)
    with open(full, "w") as f:
        f.write(content)
    return {"path": path, "replaced": True}


def tool_run_validation(checks):
    """Run allowlisted validation checks inside the lane worktree.

    checks: [{"name": <allowlist name>, "files": [<worktree-relative paths>]}].
    Commands come ONLY from lanes/validation_allowlist.yaml (loaded from the
    main repo, never the worktree). No shell, no network, scrubbed env,
    per-check timeout. Use after writing/editing files to catch static
    breakage before Roman reviews.
    """
    import yaml as _yaml
    with open(os.path.join(MAIN_REPO, "lanes", "validation_allowlist.yaml")) as f:
        allow = _yaml.safe_load(f)["checks"]
    safe_env = {"PATH": "/usr/bin:/bin:/usr/local/bin",
                "HOME": WORKDIR, "LANG": "C.UTF-8"}
    results = []
    for c in checks or []:
        name = c.get("name", "")
        spec = allow.get(name)
        if spec is None:
            results.append({"check": name, "ok": False,
                            "error": f"not allowlisted (available: {sorted(allow)})"})
            continue
        argv = list(spec["argv"])
        if spec.get("append_files"):
            try:
                files = [_repo_path(p) for p in c.get("files", [])]
            except ValueError as e:
                results.append({"check": name, "ok": False, "error": str(e)})
                continue
            if not files:
                results.append({"check": name, "ok": False,
                                "error": "no files given"})
                continue
            argv += files
        try:
            r = subprocess.run(argv, cwd=WORKDIR, env=safe_env,
                               capture_output=True, text=True,
                               timeout=int(spec.get("timeout", 60)))
            out = (r.stdout + r.stderr)[-8000:]
            results.append({"check": name, "ok": r.returncode == 0,
                            "returncode": r.returncode, "output": out})
        except subprocess.TimeoutExpired:
            results.append({"check": name, "ok": False, "error": "timeout"})
        except Exception as e:
            results.append({"check": name, "ok": False, "error": str(e)[:200]})
    return {"results": results}


def tool_git_commit(message):
    """Stage all worktree changes and commit on the lane branch. Never pushes."""
    r = subprocess.run(["git", "add", "-A"], cwd=WORKDIR, capture_output=True,
                       text=True, timeout=60)
    if r.returncode != 0:
        return {"committed": False, "error": r.stderr[:300]}
    r = subprocess.run(
        ["git", "-c", "user.name=chatgpt-lane", "-c", "user.email=lane@local",
         "commit", "-m", message],
        cwd=WORKDIR, capture_output=True, text=True, timeout=60)
    out = (r.stdout + r.stderr)[-2000:]
    if "nothing to commit" in out:
        return {"committed": False, "note": "nothing to commit"}
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WORKDIR,
                         capture_output=True, text=True).stdout.strip()[:12]
    return {"committed": r.returncode == 0, "sha": sha, "output": out}


def _tool(name, description, properties, required):
    return {"type": "function",
            "function": {"name": name, "description": description,
                         "parameters": {"type": "object",
                                        "properties": properties,
                                        "required": required}}}


TOOLS = [
    _tool("read_file",
          "Read a repo-relative file (paged). Use for code under review.",
          {"path": {"type": "string"},
           "offset": {"type": "integer", "default": 0},
           "limit": {"type": "integer", "default": 200}},
          ["path"]),
    _tool("list_dir",
          "List a repo-relative directory.",
          {"path": {"type": "string", "default": "."}},
          []),
    _tool("git",
          "Read-only git: log, diff, show, status, rev-parse, ls-files, blame.",
          {"args": {"type": "array", "items": {"type": "string"}}},
          ["args"]),
    _tool("grep",
          "Search file contents with grep.",
          {"pattern": {"type": "string"},
           "path": {"type": "string", "default": "."},
           "include": {"type": "string", "default": "*.py"}},
          ["pattern"]),
    _tool("write_file",
          "Create or overwrite a file in the worktree. Use for new files.",
          {"path": {"type": "string"},
           "content": {"type": "string"}},
          ["path", "content"]),
    _tool("edit_file",
          "Surgical edit: replace first exact occurrence of old_text with new_text.",
          {"path": {"type": "string"},
           "old_text": {"type": "string"},
           "new_text": {"type": "string"}},
          ["path", "old_text", "new_text"]),
    _tool("git_commit",
          "Stage all worktree changes and commit on the lane branch. Never pushes.",
          {"message": {"type": "string"}},
          ["message"]),
    _tool("run_validation",
          "Run allowlisted validation checks (py_compile, node_check, "
          "json_lint, git_diff_check) inside the lane worktree. Use after "
          "writing/editing files.",
          {"checks": {"type": "array", "items": {"type": "object"}}},
          ["checks"]),
    _tool("db_tables",
          "List tables/views in Supabase (read-only).",
          {}, []),
    _tool("db_describe",
          "Column names and types for one Supabase table/view.",
          {"table": {"type": "string"}},
          ["table"]),
    _tool("db_select",
          "Read rows from a Supabase table/view. Read-only, max 100 rows.",
          {"table": {"type": "string"},
           "select": {"type": "string", "default": "*"},
           "filters": {"type": "string", "default": ""},
           "limit": {"type": "integer", "default": 25},
           "order": {"type": "string", "default": ""}},
          ["table"]),
    _tool("http_get",
          "Fetch a public https URL (e.g. the live Pages site). No credentials sent.",
          {"url": {"type": "string"}},
          ["url"]),
]

DISPATCH = {"read_file": lambda a: tool_read_file(**a),
            "list_dir": lambda a: tool_list_dir(**a),
            "git": lambda a: tool_git(a["args"]),
            "grep": lambda a: tool_grep(**a),
            "write_file": lambda a: tool_write_file(**a),
            "edit_file": lambda a: tool_edit_file(**a),
            "git_commit": lambda a: tool_git_commit(**a),
            "run_validation": lambda a: tool_run_validation(**a),
            "db_tables": lambda a: tool_db_tables(**a),
            "db_describe": lambda a: tool_db_describe(**a),
            "db_select": lambda a: tool_db_select(**a),
            "http_get": lambda a: tool_http_get(**a)}

SYSTEM = ("You are a senior staff engineer working on your OWN lane branch in "
          "a dedicated worktree. Be direct, specific, and adversarial where "
          "warranted. No vague praise. Every finding names the exact file and "
          "line it touches and proposes a concrete fix. You READ the files "
          "before opining, you WRITE the fix (write_file for new files, "
          "edit_file for surgical changes), and you COMMIT coherent slices "
          "with git_commit. Respect the brief's file boundaries: stay inside "
          "'May touch', never touch 'Must not touch'. Never touch main, never "
          "push, never merge, never deploy — there are no tools for that and "
          "you must not ask for them. Quote the lines you base each finding "
          "on. End with a summary of files changed and commit SHAs.")


def _post(messages, model, max_tokens=32000):
    from dynamic_credentials import dynamic_credential_entry, \
        DynamicCredentialError
    try:
        entry = dynamic_credential_entry("custom.openai", "access_token")
    except DynamicCredentialError as exc:
        raise RuntimeError(f"custom.openai unavailable: {exc}")
    surr = str(entry.get("surrogate", "")).strip()
    if not surr.startswith("hsurr:"):
        raise RuntimeError("authd did not return a usable surrogate")
    payload = {"model": model, "messages": messages, "tools": TOOLS,
               "tool_choice": "auto"}
    if model.startswith("gpt-5") or model.startswith("o"):
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["max_tokens"] = max_tokens
    data = json.dumps(payload).encode()
    req = urllib.request.Request(API_URL, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    add_surrogate_to_request(req, "custom.openai", allowed_hosts=ALLOWED)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return read_json_response(resp)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenAI API {e.code}: {e.read().decode()[:400]}")


def run(brief_path, model=DEFAULT_MODEL, max_iters=MAX_ITERS):
    with open(brief_path) as f:
        brief = f.read()
    # Lane branch -> dedicated worktree. Falls back to read-only on main repo
    # if the brief names no branch.
    m = re.search(r"^Branch:\s*(\S+)", brief, re.M)
    branch = m.group(1) if m else None
    if branch:
        setup_worktree(branch)
        branch_note = (f"\n\nYou are working on lane branch {branch} in your "
                       f"own worktree. Commit your work with git_commit.")
    else:
        branch_note = ("\n\nNo lane branch was assigned: READ-ONLY mode. "
                       "Do not attempt write_file/edit_file/git_commit.")
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": brief + branch_note}]
    tool_roundtrips = 0
    warn_at = max(1, max_iters - 6)
    for i in range(max_iters):
        body = _post(messages, model)
        msg = body["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            answer = msg.get("content", "")
            return answer, tool_roundtrips
        # Budget guardrail: force convergence before the cap hits.
        if i == warn_at:
            messages.append({
                "role": "user",
                "content": (f"BUDGET: you have {max_iters - 1 - i} tool rounds "
                            "left. STOP exploring. Write your deliverable file "
                            "with write_file NOW, commit it with git_commit, "
                            "then end your turn with the required closing line. "
                            "Do not make more exploratory tool calls.")})
            continue
        messages.append({"role": "assistant", "content": msg.get("content"),
                         "tool_calls": tool_calls})
        for tc in tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"].get("arguments") or "{}")
            try:
                result = DISPATCH[name](args)
                content = json.dumps(result)[:12000]
            except Exception as e:
                content = json.dumps({"error": str(e)[:300]})
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": content})
        tool_roundtrips += 1
        print(f"  iter {i + 1}: {len(tool_calls)} tool call(s)", flush=True)
    return ("[stopped after max iterations without final answer]",
            tool_roundtrips)


def main():
    brief = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL
    max_iters = int(sys.argv[3]) if len(sys.argv) > 3 else MAX_ITERS
    print(f"agentic dispatch: {os.path.basename(brief)} -> {model} ...",
          flush=True)
    answer, rounds = run(brief, model, max_iters)
    base = os.path.basename(brief)
    m = re.match(r"(.+)-brief\.md$", base)
    stem = m.group(1) if m else os.path.splitext(base)[0]
    os.makedirs(INBOX, exist_ok=True)
    out_path = os.path.join(INBOX, f"{stem}-result.md")
    header = (f"# ChatGPT lane result — {stem}\n\n"
              f"_Model: {model} (agentic, repo tools incl. write+commit on its "
              f"lane branch, {rounds} tool round-trips). Roman reviews the "
              f"diff and integrates; ChatGPT never merges/pushes/deploys._\n\n"
              f"_Worktree: {WORKDIR}_\n\n---\n\n")
    with open(out_path, "w") as f:
        f.write(header + answer)
    print(f"result written: {out_path} ({len(answer)} chars)")
    return out_path


if __name__ == "__main__":
    main()
