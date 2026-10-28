#!/usr/bin/env python3
"""Conservatively isolate a source named by a failed post-rebuild validation.

The caller must run the whole `make validate` again after `isolate`. Only a
successful retry may call `confirm`; a failed retry must use
record_post_rebuild_validation.py and must not publish the fixture.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rebuild_comparison_chain as chain  # noqa: E402
import value_check  # noqa: E402

STATUS_RELS = ("output/comparison-chain-status.json", "dist/modules/comparison-chain-status.json")
FAIL_HEADER = re.compile(r"^(FAIL|ERROR): .+")
FAILED_SUMMARY = re.compile(r"^FAILED \(([^)]+)\)$")
EXCEPTION = re.compile(r"^[\w.]+(?:Error|Exception): .+")
SOURCE_NAMES = {
    "cbsros": ("CBS rest of season", "CBS ROS", "cbsros"),
    "fantasycalc": ("FantasyCalc", "fantasycalc"),
    "fantasypros": ("FantasyPros", "fantasypros"),
    "usatoday": ("USA Today", "usatoday"),
    "razzball": ("Razzball", "razzball"),
    "espn": ("ESPN", "espn"),
    "cbs": ("CBS", "cbs"),
}


def _git_bytes(repo: Path, rel: str) -> bytes | None:
    p = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=repo,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.stdout if p.returncode == 0 else None


def _published_leg_paths(repo: Path, root: str) -> list[str]:
    p = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD", str(chain.LEG_ROOT_REL)],
                       cwd=repo, capture_output=True, text=True)
    if p.returncode != 0:
        raise ValueError("published DDF leg list is unavailable")
    return [line for line in p.stdout.splitlines()
            if f"-{root}-" in line and line.endswith("/" + chain.LEG_FILES[root])]


def _json_bytes(data: bytes, label: str) -> dict:
    try:
        out = json.loads(data)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(out, dict) or not isinstance(out.get("sources"), dict):
        raise ValueError(f"{label} has no sources object")
    return out


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Replace one file completely; a failed write never truncates its target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                         delete=False) as tmp:
            name = tmp.name
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(name, path)
        name = None
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)


def changed_roots(current: dict, baseline: dict) -> set[str]:
    """A hold is a change too, but metadata alone cannot invent a culprit."""
    changed = set()
    for root in chain.SOURCES:
        now = current["sources"].get(root)
        old = baseline["sources"].get(root)
        if now != old:
            changed.add(root)
    return changed


def _named_roots(message: str) -> set[str]:
    # Longer aliases consume text first: "CBS ROS" cannot implicate CBS.
    remaining = message
    found = set()
    aliases = sorted(((alias, root) for root, names in SOURCE_NAMES.items()
                      for alias in names), key=lambda pair: len(pair[0]), reverse=True)
    aliases += sorted(((name, root) for name, root in
                       {**value_check.ROOT_OF, **value_check.DIAG_ROOT}.items()),
                      key=lambda pair: len(pair[0]), reverse=True)
    for alias, root in aliases:
        pattern = re.compile(r"(?<![\w])" + re.escape(alias) + r"(?![\w])", re.I)
        if pattern.search(remaining):
            found.add(root)
            remaining = pattern.sub(" ", remaining)
    return found


def failing_roots(log_text: str) -> set[str]:
    """Require every unittest failure's terminal error to name one root.

    Test IDs, traceback paths, passing-test output and generic make errors are
    never attribution. Multiple failing roots are deliberately declined.
    """
    lines = log_text.splitlines()
    headers = [i for i, line in enumerate(lines) if FAIL_HEADER.fullmatch(line)]
    if not headers:
        raise ValueError("no unittest FAIL/ERROR block to attribute")
    counts = []
    for line in lines:
        if not line.startswith("FAILED"):
            continue
        summary = FAILED_SUMMARY.fullmatch(line)
        if summary is None:
            raise ValueError("unrecognized unittest failure summary")
        fields = {}
        for part in summary.group(1).split(", "):
            match = re.fullmatch(r"([a-z ]+)=(\d+)", part)
            if match is None or match.group(1) not in (
                    "failures", "errors", "skipped", "expected failures", "unexpected successes"):
                raise ValueError("unrecognized unittest failure summary field")
            if match.group(1) in fields:
                raise ValueError("duplicate unittest failure summary field")
            fields[match.group(1)] = int(match.group(2))
        if not ("failures" in fields or "errors" in fields):
            raise ValueError("unrecognized unittest failure count")
        if fields.get("unexpected successes", 0):
            raise ValueError("unattributed unexpected unittest success")
        counts.append(fields.get("failures", 0) + fields.get("errors", 0))
    if not counts or sum(counts) != len(headers):
        raise ValueError("unittest failure count does not match attributed blocks")
    named = []
    for n, start in enumerate(headers):
        block = lines[start + 1:headers[n + 1] if n + 1 < len(headers) else len(lines)]
        # A block ends at the next unittest summary or make target.
        block = block[:next((i for i, line in enumerate(block)
                             if line.startswith(("Ran ", "FAILED (", "make: ***"))), len(block))]
        errors = [line for line in block if EXCEPTION.fullmatch(line)]
        if not errors:
            raise ValueError("a failing test has no terminal exception")
        roots = _named_roots(errors[-1])
        if len(roots) != 1:
            raise ValueError(f"failing assertion has {len(roots)} attributable sources")
        named.append(next(iter(roots)))
    if len(set(named)) != 1:
        raise ValueError("validation failures name multiple sources")
    return set(named)


def _status(repo: Path) -> dict:
    try:
        status = json.loads((repo / STATUS_RELS[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"chain status unreadable: {exc}") from exc
    if not isinstance(status, dict) or status.get("success") is not True:
        raise ValueError("chain has not succeeded before post-validation")
    for key in ("sources", "detail", "held_detail"):
        if not isinstance(status.get(key), dict):
            raise ValueError(f"chain status has malformed {key}")
    if not isinstance(status.get("held"), list):
        raise ValueError("chain status has malformed held list")
    return status


def isolate(repo: Path, log_text: str, week: int | None) -> str:
    repo = Path(repo)
    status = _status(repo)
    fixture_path = repo / chain.FIXTURE_REL
    current_bytes = fixture_path.read_bytes()
    current = _json_bytes(current_bytes, "current fixture")
    baseline = _json_bytes(_git_bytes(repo, str(chain.FIXTURE_REL)), "published fixture")
    roots = failing_roots(log_text)
    root = next(iter(roots))
    if root not in changed_roots(current, baseline):
        raise ValueError(f"{root} did not change from the published section")
    if root in (status.get("held") or []):
        raise ValueError(f"{root} was already held by the chain")
    if (status.get("detail") or {}).get(root, {}).get("status") != "ok":
        raise ValueError(f"{root} did not complete its source chain")
    # ESPN is the shared reindex anchor. Projection players.json is shared by
    # all three projection sources. A restored section with new shared inputs
    # can pass superficial checks yet publish inconsistent values.
    if root == "espn":
        raise ValueError("ESPN is the shared reindex anchor")
    if root in ("cbsros", "razzball"):
        players_rel = "data/fixtures/current/players.json"
        if _git_bytes(repo, players_rel) != (repo / players_rel).read_bytes():
            raise ValueError("projection players.json changed; source rollback is unsafe")
    old_section = baseline["sources"].get(root)
    if not isinstance(old_section, dict) or not old_section.get("combos"):
        raise ValueError(f"published {root} section is missing or empty")
    held = set(status.get("held") or []) | roots
    if set(chain.HOLD_ISOLATED_SOURCES) <= held:
        raise ValueError("all review-gated chart sources would be held")

    # A chart promotion record can drive the monitoring checkpoint. The
    # shared reindex stage changes the section hash after promotion, so match
    # the record by its source and promoted_at, which reindex leaves intact.
    # Never guess from a same-day filename alone.
    promo_dir = repo / chain.PROMOTIONS_REL
    promo_record = None
    if root in chain.HOLD_ISOLATED_SOURCES:
        current_section = copy.deepcopy(current["sources"].get(root))
        if not isinstance(current_section, dict):
            raise ValueError("current promoted section is malformed")
        promoted_at = current_section.get("promoted_at")
        if not promoted_at:
            raise ValueError("current promoted section lacks promoted_at")
        for path in sorted(promo_dir.glob(f"{root}-*-promotion.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError(f"promotion record unreadable: {path.name}: {exc}") from exc
            if (record.get("source_key") == root
                    and record.get("promoted_at") == promoted_at
                    and record.get("review_verdict") == "ready"
                    and re.fullmatch(r"[0-9a-f]{64}", str(record.get("section_after_sha256")))):
                promo_record = path
                break
        if status["detail"][root].get("promoted", 0) > 0 and promo_record is None:
            raise ValueError("current promotion record cannot be identified")

    # Preflight every source-specific file before changing anything. A missing
    # published leg declines recovery, rather than fabricating a value.
    old_legs = {}
    if root in chain.LEG_FILES:
        published_paths = _published_leg_paths(repo, root)
        if not published_paths:
            raise ValueError(f"published {root} DDF legs are missing")
        for rel in published_paths:
            data = _git_bytes(repo, rel)
            if data is None:
                raise ValueError(f"published DDF leg missing: {rel}")
            old_legs[rel] = data
    current_legs = chain._leg_files(repo, root)

    next_fixture = copy.deepcopy(current)
    kept = copy.deepcopy(old_section)
    reason = "chain hold: post-validate source failure"
    kept["validationHold"] = {"reason": reason, "root": root, "week": week,
                              "stage": "post_validate"}
    next_fixture["sources"][root] = kept
    old_validation = baseline.get("source_validation", {})
    validation = next_fixture.setdefault("source_validation", {})
    if not isinstance(old_validation, dict) or not isinstance(validation, dict):
        raise ValueError("source validation metadata is malformed")
    if root in old_validation:
        validation[root] = copy.deepcopy(old_validation[root])
    else:
        validation.pop(root, None)

    kept_week = chain.section_week(old_section)
    behind = week - kept_week if week is not None and kept_week is not None else None
    severity = "amber" if behind is not None and behind <= 1 else "red"
    result = status["detail"][root]
    promoted = result.get("promoted", 0)
    assertion = next((line for line in log_text.splitlines() if EXCEPTION.fullmatch(line)),
                     "source-specific validation failure")
    target = (promo_record.with_name(promo_record.stem + ".rolled-back.json")
              if promo_record is not None else None)
    if target is not None and (target.exists() or target.is_symlink()):
        raise ValueError("rolled-back promotion record already exists")
    rolled_back_records = [target.name] if target is not None else []
    result.update(status="held", held_reason="post-validate source failure",
                  failed_stage="post_validate", detail=f"make validate failed: {assertion[:300]}",
                  promoted=0, rolled_back=promoted, hold_severity=severity,
                  weeks_behind=behind, rolled_back_records=rolled_back_records,
                  kept_section={"present": True, "week_designated": old_section.get("week_designated"),
                                "content_vintage": old_section.get("content_vintage"),
                                "content_week": kept_week})
    status["held"] = sorted(held)
    status.setdefault("held_detail", {})[root] = {
        "reason": reason, "stage": "post_validate", "kept_section": result["kept_section"],
        "weeks_behind": behind, "hold_severity": severity,
    }
    status["sources"][root] = chain.describe_result(result)
    from week_state import source_weeks  # noqa: PLC0415
    index_path = repo / "data/history/index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = None
    status["source_weeks"] = source_weeks(next_fixture, index)
    status["hold_severity"] = ("red" if any(v.get("hold_severity") == "red"
                                             for v in status["held_detail"].values()) else "amber")
    status["success"] = False
    status["outcome"] = "validation_retry_pending"
    status["post_validate_isolation"] = {"root": root, "stage": "isolation_in_progress",
                                         "attributed_assertion": assertion[:300],
                                         "recorded_at": datetime.now(timezone.utc).isoformat(),
                                         "expected_section_sha256": chain._canonical_sha(kept),
                                         "expected_validation_present": root in validation,
                                         "expected_validation_sha256": chain._canonical_sha(validation.get(root)),
                                         "expected_legs_sha256": {
                                             rel: hashlib.sha256(data).hexdigest()
                                             for rel, data in old_legs.items()},
                                         "promotion_record": promo_record.name if promo_record else None,
                                         "rolled_back_record": target.name if target else None}
    # Publish the non-green state BEFORE touching the fixture or a leg. If
    # any later operation fails, even an incomplete rollback cannot be
    # mistaken for a successful chain. `confirm` rejects this in-progress
    # state; only a fully restored source advances to retry_pending.
    _write_status(repo, status)
    renamed = False
    try:
        _atomic_write_bytes(fixture_path, (json.dumps(next_fixture, indent=2) + "\n").encode())
        if chain._read_fixture(repo)["sources"][root] != kept:
            raise ValueError("restored section could not be verified")
        if old_legs:
            chain._restore_legs(repo, root, old_legs)
        if promo_record is not None:
            promo_record.rename(target)
            renamed = True
        status["post_validate_isolation"]["stage"] = "retry_pending"
        _write_status(repo, status)
    except Exception as exc:  # noqa: BLE001 -- retain non-green status even if rollback fails
        rollback_errors = []
        if renamed:
            try:
                target.rename(promo_record)
            except OSError as rollback_exc:
                rollback_errors.append(f"promotion record: {rollback_exc}")
        try:
            if old_legs:
                chain._restore_legs(repo, root, current_legs)
        except (OSError, ValueError) as rollback_exc:
            rollback_errors.append(f"DDF legs: {rollback_exc}")
        try:
            _atomic_write_bytes(fixture_path, current_bytes)
        except OSError as rollback_exc:
            rollback_errors.append(f"fixture: {rollback_exc}")
        suffix = f"; rollback incomplete: {'; '.join(rollback_errors)}" if rollback_errors else ""
        raise ValueError(f"source isolation failed: {exc}{suffix}") from exc
    return root


def _write_status(repo: Path, status: dict) -> None:
    data = (json.dumps(status, indent=2) + "\n").encode()
    # The output copy is authoritative. Write it last, so a status-copy
    # failure cannot make the chain appear green there before the dist copy.
    for rel in reversed(STATUS_RELS):
        path = repo / rel
        _atomic_write_bytes(path, data)


def confirm(repo: Path) -> str:
    repo = Path(repo)
    path = repo / STATUS_RELS[0]
    status = json.loads(path.read_text(encoding="utf-8"))
    recovery = status.get("post_validate_isolation") or {}
    root = recovery.get("root")
    if (status.get("outcome") != "validation_retry_pending"
            or status.get("success") is not False
            or recovery.get("stage") != "retry_pending" or root not in chain.SOURCES):
        raise ValueError("no pending post-validation isolation to confirm")
    fixture = _json_bytes((repo / chain.FIXTURE_REL).read_bytes(), "retried fixture")
    section = fixture["sources"].get(root)
    if not isinstance(section, dict):
        raise ValueError("isolated source section is missing")
    hold = section.get("validationHold") or {}
    if hold.get("reason") != "chain hold: post-validate source failure":
        raise ValueError("isolated source hold disappeared before confirmation")
    if chain._canonical_sha(section) != recovery.get("expected_section_sha256"):
        raise ValueError("isolated source section differs from verified rollback")
    validation = fixture.get("source_validation", {})
    if not isinstance(validation, dict) or (root in validation) != recovery.get("expected_validation_present"):
        raise ValueError("isolated source validation metadata changed")
    if chain._canonical_sha(validation.get(root)) != recovery.get("expected_validation_sha256"):
        raise ValueError("isolated source validation metadata differs from published")
    expected_legs = recovery.get("expected_legs_sha256")
    if not isinstance(expected_legs, dict) or {
            rel: hashlib.sha256(data).hexdigest()
            for rel, data in chain._leg_files(repo, root).items()} != expected_legs:
        raise ValueError("isolated source DDF legs differ from published")
    if root in chain.HOLD_ISOLATED_SOURCES:
        original = recovery.get("promotion_record")
        retired = recovery.get("rolled_back_record")
        if (not isinstance(original, str) or not original.startswith(root + "-")
                or not original.endswith("-promotion.json")
                or retired != original[:-5] + ".rolled-back.json"):
            raise ValueError("isolation promotion record evidence is malformed")
        promo_dir = repo / chain.PROMOTIONS_REL
        if (promo_dir / original).exists() or not (promo_dir / retired).is_file():
            raise ValueError("isolated promotion was not retired")
    if root not in (status.get("held") or []) or (status.get("detail") or {}).get(root, {}).get("status") != "held":
        raise ValueError("isolated source is not held in chain status")
    status["success"] = True
    status["outcome"] = "published_with_holds"
    recovery["stage"] = "retry_passed"
    _write_status(repo, status)
    return root


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("isolate", "confirm"))
    ap.add_argument("--repo", type=Path, default=chain.REPO)
    ap.add_argument("--log", type=Path)
    ap.add_argument("--week", type=int)
    args = ap.parse_args()
    try:
        if args.action == "isolate":
            if args.log is None or not args.log.is_file():
                raise ValueError("failed validation log is required")
            root = isolate(args.repo, args.log.read_text(encoding="utf-8", errors="replace"), args.week)
            print(f"post-validate: held {root}; run full make validate once more")
        else:
            root = confirm(args.repo)
            print(f"post-validate: retry passed; publishing with {root} held")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"post-validate: recovery declined: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
