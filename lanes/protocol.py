#!/usr/bin/env python3
"""
Lane outbox/inbox protocol — JEG-94.

Goal
----
Allow one lane to write a brief to another lane's outbox, have a CLI connector
pick it up and (in the live case) execute it, then write a signed result into
the destination lane's inbox. The reviewer verifies the signature against the
brief assignment before trusting the result.

Design constraints (from lanes/LANES.md and lanes/ROUTING.md):

  * Fail closed: every step refuses a malformed/missing field.
  * Worker lanes cannot run tests or the Linear CLI (sandbox is sealed). The
    protocol must not assume workers can self-verify; the REVIEWER verifies
    against the brief assignment that was last placed in the outbox.
  * Lanes never merge/push/deploy. The connector is process tooling only;
    methodology/values/copy stay with Jeremy.

Data model
----------
A brief is a JSON object with at least these fields:

    {
        "issue":        "JEG-94",                    # Linear issue key
        "lane":         "minimax",                   # destination lane
        "from":         "minimax",                   # origin lane
        "subject":      "short text",
        "context":      "long-form text",
        "created_at":   "2026-10-02T20:15:00Z",      # ISO-8601 UTC
        "signature":    "<lane>|<issue>|<ts-sig>"    # signing triple
    }

The signature is deterministic: `lane:issue:created_at` joined with the lane
name. The reviewer rebuilds it from the brief fields it has on file and
compares. There is no shared secret; identity is the lane name and the
timestamp that the brief was placed. (Phase 1 — cheap version. Phase 2 will
add HMAC over the brief body when a secrets layer is approved.)

A result is also a JSON object with the same shape but with the lane name
set to the WORKER lane (the lane that produced the result) and an extra
`result_of` field pointing at the issue key it answers:

    {
        "issue":        "JEG-94",
        "lane":         "minimax",                   # the worker that produced this
        "result_of":    "JEG-94",                    # the brief it answers
        "subject":      "summary line",
        "context":      "long-form text",
        "created_at":   "2026-10-02T20:30:00Z",      # worker timestamp
        "signature":    "minimax|JEG-94|<ts-sig>"    # lane name + issue + ts
    }

The reviewer's check (`verify_signature`) takes a result and the brief it was
supposed to answer, and:

  1. Refuses if the result is malformed, including a signature that does
     not recompute from the result's own (lane, issue, created_at).
  2. Refuses if the brief itself is malformed (missing lane/issue).
  3. Refuses if the result's `lane` (worker) does not match the brief's
     destination lane.
  4. Refuses if the result's `issue` does not match the brief's issue.
  5. Refuses if the result's `result_of` does not match the brief's issue.
  6. Passes otherwise.

Note: the result's timestamp is the worker's own and is not required to
equal the brief's — the gate checks the signature's lane/issue parts
against the assignment, not timestamp equality (a worker can only sign
its own moment).

Adapter interface
-----------------
`LaneAdapter` is the abstract base every per-lane connector implements. Only
the minimax adapter is shipped today (claude and chatgpt adapters are
deliberately not built — see lanes/ROUTING.md). A future adapter should
subclass `LaneAdapter` and implement `dispatch(brief, dry_run)` plus
`self_test()`.

Public surface
--------------
  * `LANES_DIR`, `OUTBOX_DIR`, `INBOX_DIR` — workspace layout
  * `KNOWN_LANES` — set of lane names that the protocol accepts
  * `sign(lane, issue, ts)` — build the signature string
  * `make_brief(...)` / `make_result(...)` — produce signed JSON
  * `write_brief(brief, outbox_dir)` / `write_result(result, inbox_dir)`
  * `load_brief(path)` / `load_result(path)`
  * `validate_brief(brief)` / `validate_result(result)`
  * `verify_signature(result, brief)` — the reviewer's gate
  * `LaneAdapter` — abstract base class for per-lane connectors
  * `MiniMaxAdapter` — the minimax connector (dry-run + live)
"""

from __future__ import annotations

import json
import os
import re
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

LANES_DIR = Path(__file__).resolve().parent
REPO_ROOT = LANES_DIR.parent

# Outbox: where a dispatcher writes briefs addressed to another lane.
# Layout: outbox/<destination_lane>/<issue>-<epoch>.json
OUTBOX_DIR = LANES_DIR / "outbox"

# Inbox: where the worker writes signed result files.
# Layout: inbox/<worker_lane>/<issue>-<epoch>.json
INBOX_DIR = LANES_DIR / "inbox"

# Known lanes. The protocol refuses unknown names (fail closed).
KNOWN_LANES = ("minimax",)

# Lane name pattern: lower-case ascii letters, digits, dash, underscore.
_LANE_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

# Linear issue key pattern: PREFIX-NUMBER (e.g. JEG-94, DATA-12).
# The prefix is upper-case ascii letters; the number is decimal.
_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{0,15}-[0-9]{1,6}$")

# ISO-8601 UTC timestamp pattern. Accepts both "...Z" and "+00:00" trailing.
_TS_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LaneProtocolError(Exception):
    """Base error for lane protocol failures (fail closed)."""


class InvalidLaneNameError(LaneProtocolError):
    """A lane name is malformed or not in KNOWN_LANES."""


class InvalidIssueKeyError(LaneProtocolError):
    """An issue key is malformed."""


class InvalidTimestampError(LaneProtocolError):
    """A timestamp is missing or not ISO-8601 UTC."""


class MissingFieldError(LaneProtocolError):
    """A required field is absent."""


class SignatureMismatchError(LaneProtocolError):
    """A result's signature does not match the brief it claims to answer."""


# ---------------------------------------------------------------------------
# Field validation helpers
# ---------------------------------------------------------------------------


def _check_lane(lane: Any, *, role: str = "lane") -> str:
    if not isinstance(lane, str):
        raise InvalidLaneNameError(f"{role!r} must be a string, got {type(lane).__name__}")
    if lane not in KNOWN_LANES:
        raise InvalidLaneNameError(
            f"{role!r} {lane!r} is not a known lane. Known lanes: {sorted(KNOWN_LANES)}"
        )
    if not _LANE_NAME_RE.match(lane):
        raise InvalidLaneNameError(f"{role!r} {lane!r} fails name pattern {_LANE_NAME_RE.pattern}")
    return lane


def _check_issue(issue: Any, *, role: str = "issue") -> str:
    if not isinstance(issue, str):
        raise InvalidIssueKeyError(f"{role!r} must be a string, got {type(issue).__name__}")
    if not _ISSUE_KEY_RE.match(issue):
        raise InvalidIssueKeyError(
            f"{role!r} {issue!r} is not a valid Linear issue key (e.g. JEG-94)"
        )
    return issue


def _check_ts(ts: Any, *, role: str = "created_at") -> str:
    if not isinstance(ts, str):
        raise InvalidTimestampError(f"{role!r} must be a string, got {type(ts).__name__}")
    if not _TS_RE.match(ts):
        raise InvalidTimestampError(
            f"{role!r} {ts!r} must be ISO-8601 UTC (e.g. 2026-10-02T20:15:00Z)"
        )
    # Round-trip parse to catch timezone-naive strings that happen to match.
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidTimestampError(f"{role!r} {ts!r} failed parse: {exc}") from exc
    if parsed.tzinfo is None:
        raise InvalidTimestampError(f"{role!r} {ts!r} must include a UTC offset")
    return ts


def _check_required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MissingFieldError(f"{field!r} must be a non-empty string")
    return value


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string ending in 'Z'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Signature
# ---------------------------------------------------------------------------


def sign(lane: str, issue: str, ts: str) -> str:
    """
    Build a deterministic signature string from the lane name, issue key,
    and timestamp. The triple is the worker's claim of identity at a
    specific moment — the reviewer rebuilds the same triple from the brief
    it has on file and compares.
    """
    _check_lane(lane, role="sign.lane")
    _check_issue(issue, role="sign.issue")
    _check_ts(ts, role="sign.ts")
    return f"{lane}|{issue}|{ts}"


def parse_signature(sig: str) -> Tuple[str, str, str]:
    """Parse a signature string back into (lane, issue, ts). Refuses if malformed."""
    if not isinstance(sig, str) or "|" not in sig:
        raise SignatureMismatchError(f"signature {sig!r} is not a '|'-joined string")
    parts = sig.split("|")
    if len(parts) != 3:
        raise SignatureMismatchError(
            f"signature {sig!r} must have exactly 3 parts (lane|issue|ts), got {len(parts)}"
        )
    lane, issue, ts = parts
    _check_lane(lane, role="signature.lane")
    _check_issue(issue, role="signature.issue")
    _check_ts(ts, role="signature.ts")
    return lane, issue, ts


# ---------------------------------------------------------------------------
# Brief / result construction
# ---------------------------------------------------------------------------


def make_brief(
    *,
    issue: str,
    lane: str,
    sender: str,
    subject: str,
    context: str,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Construct a signed brief addressed to `lane` from `sender`. Returns a plain
    dict; the caller writes it to the outbox via `write_brief`.
    """
    _check_issue(issue)
    _check_lane(lane)
    _check_lane(sender, role="from")
    _check_required_text(subject, "subject")
    _check_required_text(context, "context")
    ts = created_at or now_iso()
    brief = {
        "issue": issue,
        "lane": lane,
        "from": sender,
        "subject": subject,
        "context": context,
        "created_at": ts,
        "signature": sign(lane, issue, ts),
    }
    return brief


def make_result(
    *,
    issue: str,
    lane: str,
    subject: str,
    context: str,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Construct a signed result. The worker lane is `lane` (the lane that
    produced the result); `result_of` echoes the issue key.
    """
    _check_issue(issue)
    _check_lane(lane, role="result.lane")
    _check_required_text(subject, "subject")
    _check_required_text(context, "context")
    ts = created_at or now_iso()
    return {
        "issue": issue,
        "lane": lane,
        "result_of": issue,
        "subject": subject,
        "context": context,
        "created_at": ts,
        "signature": sign(lane, issue, ts),
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_brief(brief: Any) -> Dict[str, Any]:
    """Refuse if `brief` is missing a required field or has a bad type. Returns the brief."""
    if not isinstance(brief, dict):
        raise LaneProtocolError(f"brief must be a dict, got {type(brief).__name__}")
    for field in ("issue", "lane", "from", "subject", "context", "created_at", "signature"):
        if field not in brief:
            raise MissingFieldError(f"brief is missing required field {field!r}")
    _check_issue(brief["issue"])
    _check_lane(brief["lane"], role="brief.lane")
    _check_lane(brief["from"], role="brief.from")
    _check_required_text(brief["subject"], "subject")
    _check_required_text(brief["context"], "context")
    _check_ts(brief["created_at"], role="brief.created_at")
    expected = sign(brief["lane"], brief["issue"], brief["created_at"])
    if brief["signature"] != expected:
        raise SignatureMismatchError(
            f"brief.signature {brief['signature']!r} does not match "
            f"recomputed {expected!r}"
        )
    return brief


def validate_result(result: Any) -> Dict[str, Any]:
    """Refuse if `result` is missing a required field or has a bad type. Returns the result."""
    if not isinstance(result, dict):
        raise LaneProtocolError(f"result must be a dict, got {type(result).__name__}")
    for field in ("issue", "lane", "result_of", "subject", "context", "created_at", "signature"):
        if field not in result:
            raise MissingFieldError(f"result is missing required field {field!r}")
    _check_issue(result["issue"])
    _check_lane(result["lane"], role="result.lane")
    _check_issue(result["result_of"], role="result.result_of")
    _check_required_text(result["subject"], "subject")
    _check_required_text(result["context"], "context")
    _check_ts(result["created_at"], role="result.created_at")
    expected = sign(result["lane"], result["issue"], result["created_at"])
    if result["signature"] != expected:
        raise SignatureMismatchError(
            f"result.signature {result['signature']!r} does not match "
            f"recomputed {expected!r}"
        )
    return result


# ---------------------------------------------------------------------------
# Reviewer verification
# ---------------------------------------------------------------------------


def verify_signature(result: Any, brief: Any) -> None:
    """
    The reviewer's gate. Refuses if the result does not credibly answer the
    brief assignment. Raises a LaneProtocolError subclass on every failure.

    Checks, in order:
      1. Result is a valid result shape. This includes the signature
         recomputing from the result's OWN (lane, issue, created_at) —
         the signature proves internal consistency of the worker's claim.
      2. Brief is a valid brief shape.
      3. Result's `lane` (worker) matches brief's `lane` (destination).
      4. Result's `issue` matches brief's `issue`.
      5. Result's `result_of` matches brief's `issue`.

    NOTE: the result's `created_at` is the WORKER's timestamp and is NOT
    required to equal the brief's `created_at`. Requiring that would make
    every genuine result fail the gate, since a worker can only sign its
    own moment. "Verifies the signature against the brief assignment"
    (JEG-96 Phase 1) means the signature's lane/issue parts match the
    assignment — which steps 1+3+4+5 enforce — not timestamp equality.
    """
    validate_result(result)
    validate_brief(brief)

    if result["lane"] != brief["lane"]:
        raise SignatureMismatchError(
            f"result.lane {result['lane']!r} does not match brief.lane {brief['lane']!r}"
        )
    if result["issue"] != brief["issue"]:
        raise SignatureMismatchError(
            f"result.issue {result['issue']!r} does not match brief.issue {brief['issue']!r}"
        )
    if result["result_of"] != brief["issue"]:
        raise SignatureMismatchError(
            f"result.result_of {result['result_of']!r} does not match brief.issue {brief['issue']!r}"
        )


# ---------------------------------------------------------------------------
# Outbox / inbox IO
# ---------------------------------------------------------------------------


def _lane_subdir(parent: Path, lane: str, *, kind: str) -> Path:
    _check_lane(lane, role=kind + ".lane")
    subdir = parent / lane
    return subdir


def write_brief(brief: Dict[str, Any], outbox_dir: Optional[Path] = None) -> Path:
    """Validate and write a brief into the destination lane's outbox subdir."""
    validate_brief(brief)
    base = Path(outbox_dir) if outbox_dir is not None else OUTBOX_DIR
    subdir = _lane_subdir(base, brief["lane"], kind="outbox")
    subdir.mkdir(parents=True, exist_ok=True)
    epoch = int(datetime.fromisoformat(brief["created_at"].replace("Z", "+00:00")).timestamp())
    path = subdir / f"{brief['issue']}-{epoch}.json"
    if path.exists():
        # Refuse to clobber; brief dispatch is idempotent only at the connector
        # layer, not the IO layer. Fail closed.
        raise LaneProtocolError(f"brief already exists at {path}")
    path.write_text(json.dumps(brief, indent=2, sort_keys=True) + "\n")
    return path


def write_result(result: Dict[str, Any], inbox_dir: Optional[Path] = None) -> Path:
    """Validate and write a result into the worker lane's inbox subdir."""
    validate_result(result)
    base = Path(inbox_dir) if inbox_dir is not None else INBOX_DIR
    subdir = _lane_subdir(base, result["lane"], kind="inbox")
    subdir.mkdir(parents=True, exist_ok=True)
    epoch = int(datetime.fromisoformat(result["created_at"].replace("Z", "+00:00")).timestamp())
    path = subdir / f"{result['issue']}-{epoch}.json"
    if path.exists():
        raise LaneProtocolError(f"result already exists at {path}")
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return path


def load_brief(path: Path) -> Dict[str, Any]:
    """Load a brief file from disk and validate it. Refuses if malformed."""
    p = Path(path)
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise LaneProtocolError(f"brief file {p} is not valid JSON: {exc}") from exc
    return validate_brief(data)


def load_result(path: Path) -> Dict[str, Any]:
    """Load a result file from disk and validate it. Refuses if malformed."""
    p = Path(path)
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise LaneProtocolError(f"result file {p} is not valid JSON: {exc}") from exc
    return validate_result(data)


def list_briefs(outbox_dir: Optional[Path] = None, lane: Optional[str] = None) -> List[Path]:
    """List brief JSON files in an outbox. Optionally filtered by destination lane."""
    base = Path(outbox_dir) if outbox_dir is not None else OUTBOX_DIR
    if lane is not None:
        _check_lane(lane)
        base = base / lane
    if not base.exists():
        return []
    return sorted(base.glob("*.json"))


def list_results(inbox_dir: Optional[Path] = None, lane: Optional[str] = None) -> List[Path]:
    """List result JSON files in an inbox. Optionally filtered by worker lane."""
    base = Path(inbox_dir) if inbox_dir is not None else INBOX_DIR
    if lane is not None:
        _check_lane(lane)
        base = base / lane
    if not base.exists():
        return []
    return sorted(base.glob("*.json"))


# ---------------------------------------------------------------------------
# Adapter interface
# ---------------------------------------------------------------------------


class LaneAdapter(ABC):
    """
    Per-lane connector interface. Each lane adapter knows how to take a brief
    addressed to its lane and (in live mode) dispatch it, then write a signed
    result back to its inbox.

    Today, only `MiniMaxAdapter` is shipped. The interface exists so a future
    claude/chatgpt adapter can be added without changing this protocol.
    """

    name: str  # lane name, e.g. "minimax"

    @abstractmethod
    def dispatch(self, brief: Dict[str, Any], *, dry_run: bool = False) -> Dict[str, Any]:
        """
        Take a validated brief and return a signed result. If `dry_run` is
        True, the adapter MUST NOT write to the inbox or trigger any side
        effects beyond returning the result (so callers can inspect what
        would happen). Implementations MAY still record the dispatch to
        `lanes/dispatch_ledger.jsonl` for usage tracking; the smoke test
        exercises both paths.

        Implementations are responsible for:
          - calling `validate_brief(brief)` defensively (no trust in caller);
          - constructing a result via `make_result(...)` so the signature is
            built correctly;
          - writing the result via `write_result(result)` UNLESS `dry_run`;
          - raising `LaneProtocolError` subclasses on any refusal.
        """

    def self_test(self) -> Tuple[bool, str]:
        """Default self-test: round-trip a dry-run brief. Returns (ok, message)."""
        try:
            brief = make_brief(
                issue="JEG-94",
                lane=self.name,
                sender="minimax",
                subject="self-test",
                context="self-test dispatch",
            )
            self.dispatch(brief, dry_run=True)
            return True, f"{self.name} adapter self-test passed"
        except Exception as exc:  # noqa: BLE001
            return False, f"{self.name} adapter self-test failed: {exc}"


# ---------------------------------------------------------------------------
# MiniMax adapter
# ---------------------------------------------------------------------------


class MiniMaxAdapter(LaneAdapter):
    """
    The MiniMax lane connector. The minimax sandbox blocks test execution and
    the Linear CLI for workers, so the dispatch path here is intentionally
    cheap:

      - In dry-run mode (the default for `mmcode dispatch --dry-run`), the
        adapter builds the would-be result and returns it WITHOUT writing
        to the inbox or invoking any external system.
      - In live mode, the adapter writes the signed result to
        `lanes/inbox/minimax/<issue>-<epoch>.json` so the reviewer (Jeremy
        or the orchestrator lane) can pick it up and verify the signature
        against the brief.

    No external CLI is invoked. A future implementation that needs to call
    the minimax CLI should do so behind this same interface.
    """

    name = "minimax"

    def __init__(self, inbox_dir: Optional[Path] = None):
        self.inbox_dir = Path(inbox_dir) if inbox_dir is not None else INBOX_DIR

    def dispatch(self, brief: Dict[str, Any], *, dry_run: bool = False) -> Dict[str, Any]:
        # Defensive re-validation; refuse anything not shaped like a brief.
        validate_brief(brief)
        if brief["lane"] != self.name:
            raise InvalidLaneNameError(
                f"MiniMaxAdapter cannot dispatch brief addressed to lane {brief['lane']!r}"
            )
        # Build a deterministic, signed result. The worker lane is `self.name`.
        result = make_result(
            issue=brief["issue"],
            lane=self.name,
            subject=f"Dry-run echo: {brief['subject']}"
            if dry_run
            else f"Executed: {brief['subject']}",
            context=(
                f"DRY RUN\n\nBrief subject: {brief['subject']}\n"
                f"Brief from: {brief['from']}\n"
                f"Brief created_at: {brief['created_at']}\n\n"
                f"Brief context. Body:\n{brief['context']}"
            ),
        )
        if dry_run:
            return result
        # Live path: write the signed result to the worker inbox.
        write_result(result, inbox_dir=self.inbox_dir)
        return result


# ---------------------------------------------------------------------------
# CLI surface (also reachable from bin/mmcode)
# ---------------------------------------------------------------------------


def _print_brief(brief: Dict[str, Any]) -> None:
    print(json.dumps(brief, indent=2, sort_keys=True))


def _print_result(result: Dict[str, Any]) -> None:
    print(json.dumps(result, indent=2, sort_keys=True))


def _print_verdict(ok: bool, message: str) -> None:
    print(("PASS" if ok else "FAIL") + ": " + message)


def main(argv: Optional[List[str]] = None) -> int:
    """
    Minimal CLI so `python3 -m lanes.protocol ...` and `bin/mmcode ...` share
    the same surface. Subcommands:

        make-brief  --issue I --lane L --from F --subject S --context C
                     [--outbox DIR] [--ts ISO]
        make-result --issue I --lane L --subject S --context C
                     [--inbox DIR] [--ts ISO]
        verify      --brief PATH --result PATH
        adapter-self-test [--inbox DIR]
        dispatch    --issue I --lane L --from F --subject S --context C
                     [--inbox DIR] [--ts ISO] [--dry-run]
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__.split("Goal")[0].strip(), file=sys.stderr)
        return 2

    cmd, args = argv[0], argv[1:]

    if cmd == "make-brief":
        kwargs: Dict[str, Any] = {}
        outbox: Optional[Path] = None
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("--issue", "--lane", "--from", "--subject", "--context", "--ts"):
                if i + 1 >= len(args):
                    print(f"missing value after {a}", file=sys.stderr)
                    return 2
                key = a[2:].replace("-", "_")
                if key == "from":
                    # --from is the origin lane; make_brief takes it as
                    # `sender` (from is a Python keyword).
                    key = "sender"
                if key == "ts":
                    kwargs["created_at"] = args[i + 1]
                else:
                    kwargs[key] = args[i + 1]
                i += 2
                continue
            if a == "--outbox":
                outbox = Path(args[i + 1])
                i += 2
                continue
            print(f"unknown flag {a}", file=sys.stderr)
            return 2
        try:
            brief = make_brief(**kwargs)
        except LaneProtocolError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        path = write_brief(brief, outbox_dir=outbox)
        _print_brief(brief)
        print(f"wrote: {path}")
        return 0

    if cmd == "make-result":
        kwargs = {}
        inbox: Optional[Path] = None
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("--issue", "--lane", "--subject", "--context", "--ts"):
                if i + 1 >= len(args):
                    print(f"missing value after {a}", file=sys.stderr)
                    return 2
                key = a[2:].replace("-", "_")
                if key == "ts":
                    kwargs["created_at"] = args[i + 1]
                else:
                    kwargs[key] = args[i + 1]
                i += 2
                continue
            if a == "--inbox":
                inbox = Path(args[i + 1])
                i += 2
                continue
            print(f"unknown flag {a}", file=sys.stderr)
            return 2
        try:
            result = make_result(**kwargs)
        except LaneProtocolError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        path = write_result(result, inbox_dir=inbox)
        _print_result(result)
        print(f"wrote: {path}")
        return 0

    if cmd == "verify":
        brief_path = None
        result_path = None
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--brief":
                brief_path = Path(args[i + 1])
                i += 2
                continue
            if a == "--result":
                result_path = Path(args[i + 1])
                i += 2
                continue
            print(f"unknown flag {a}", file=sys.stderr)
            return 2
        if brief_path is None or result_path is None:
            print("--brief and --result are required", file=sys.stderr)
            return 2
        try:
            brief = load_brief(brief_path)
            result = load_result(result_path)
            verify_signature(result, brief)
        except LaneProtocolError as exc:
            _print_verdict(False, str(exc))
            return 1
        _print_verdict(True, f"signature verified for {result['issue']}")
        return 0

    if cmd == "adapter-self-test":
        inbox: Optional[Path] = None
        i = 0
        while i < len(args):
            if args[i] == "--inbox":
                inbox = Path(args[i + 1])
                i += 2
                continue
            print(f"unknown flag {args[i]}", file=sys.stderr)
            return 2
        adapter = MiniMaxAdapter(inbox_dir=inbox)
        ok, message = adapter.self_test()
        _print_verdict(ok, message)
        return 0 if ok else 1

    if cmd == "dispatch":
        # Build a brief and dispatch via the named adapter. Default adapter
        # is the only one shipped today (minimax).
        kwargs = {}
        inbox = None
        dry_run = False
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("--issue", "--lane", "--from", "--subject", "--context", "--ts"):
                if i + 1 >= len(args):
                    print(f"missing value after {a}", file=sys.stderr)
                    return 2
                key = a[2:].replace("-", "_")
                if key == "from":
                    # --from is the origin lane; make_brief takes it as
                    # `sender` (from is a Python keyword).
                    key = "sender"
                if key == "ts":
                    kwargs["created_at"] = args[i + 1]
                else:
                    kwargs[key] = args[i + 1]
                i += 2
                continue
            if a == "--inbox":
                inbox = Path(args[i + 1])
                i += 2
                continue
            if a == "--dry-run":
                dry_run = True
                i += 1
                continue
            print(f"unknown flag {a}", file=sys.stderr)
            return 2
        try:
            brief = make_brief(**kwargs)
        except LaneProtocolError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        adapter = MiniMaxAdapter(inbox_dir=inbox)
        try:
            result = adapter.dispatch(brief, dry_run=dry_run)
        except LaneProtocolError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        _print_result(result)
        print(
            f"dispatched (dry_run={dry_run}) {brief['issue']} -> {brief['lane']}: "
            f"result {'NOT written' if dry_run else 'written'}"
        )
        return 0

    print(f"unknown subcommand {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())