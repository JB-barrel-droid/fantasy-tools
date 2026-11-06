"""Optional local swap-request boundary. No pricing, fetching or persistence.

The request supplies league context and an explicit gain policy. The one Node
bridge calls app/v2/waiver-board-swaps.js, which calls Waivers/finder; neither
this module nor the board validator implements another roster decision path.
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUEST_KEYS = {"setting", "roster_keys", "wire_keys", "wire_overrides", "context", "gain_policy"}
POSITIONS = {"QB", "RB", "WR", "TE"}
SHAPE_REQUIRED = POSITIONS | {"FLEX", "SUPERFLEX", "BENCH"}
SHAPE_ALLOWED = SHAPE_REQUIRED | {"K", "DST"}
BLOCK_KEYS = {"available", "missing_reason", "request", "rows", "unresolved_wire_keys"}
MAX_KEY = 2**53 - 1  # exact identities across the Python / JavaScript boundary


def _number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_KEY


def _keys(value):
    return isinstance(value, list) and all(_integer(k) for k in value) and len(set(value)) == len(value)


def validate_request(request, setting) -> list[str]:
    """Refuse ambiguous inputs; return deterministic field errors, never defaults."""
    if not isinstance(request, dict) or set(request) != REQUEST_KEYS:
        return ["needs exactly " + ", ".join(sorted(REQUEST_KEYS))]
    out = []
    if json.dumps(request["setting"], sort_keys=True) != json.dumps(setting, sort_keys=True):
        out.append("setting must equal the board setting")
    for field in ("roster_keys", "wire_keys"):
        if not _keys(request[field]):
            out.append(f"{field} must be unique resolved integer player keys")
    overrides = request["wire_overrides"]
    if not isinstance(overrides, dict) or set(overrides) != {"add", "remove"}:
        out.append("wire_overrides needs exactly add and remove")
    elif not all(_keys(overrides[k]) for k in ("add", "remove")):
        out.append("wire_overrides must contain unique resolved integer player keys")
    elif set(overrides["add"]) & set(overrides["remove"]):
        out.append("wire_overrides cannot add and remove the same player")
    policy = request["gain_policy"]
    if (not isinstance(policy, dict) or set(policy) != {"minimum", "comparison"}
            or not _number(policy["minimum"]) or policy["comparison"] not in ("gt", "gte")):
        out.append("gain_policy requires a finite minimum and explicit comparison gt or gte")
    ctx = request["context"]
    if (not isinstance(ctx, dict) or not {"shape", "expected", "weights"} <= set(ctx)
            or set(ctx) - {"shape", "expected", "weights", "rosterSize"}):
        return out + ["context needs shape, expected and weights, with optional rosterSize only"]
    shape = ctx["shape"]
    if (not isinstance(shape, dict) or not SHAPE_REQUIRED <= set(shape) or set(shape) - SHAPE_ALLOWED
            or not all(_integer(n) for n in shape.values())
            or not sum(shape[k] for k in SHAPE_REQUIRED - {"BENCH"})):
        out.append("context.shape needs nonnegative integer league slots and at least one starter")
    expected = ctx["expected"]
    if not isinstance(expected, dict) or set(expected) != POSITIONS:
        out.append("context.expected needs QB, RB, WR and TE depth bands")
    else:
        for pos, band in sorted(expected.items()):
            if (not isinstance(band, dict) or not {"lo", "hi"} <= set(band)
                    or set(band) - {"lo", "hi", "starters", "bench", "expected"}
                    or not all(_number(n) and n >= 0 for n in band.values())
                    or not _integer(band["lo"]) or not _integer(band["hi"]) or band["lo"] > band["hi"]):
                out.append(f"context.expected.{pos} needs the engine's nonnegative lo/hi depth band")
    weights = ctx["weights"]
    if (not isinstance(weights, dict) or set(weights) - (POSITIONS | {"overall"})
            or not (POSITIONS <= set(weights) or "overall" in weights)
            or not all(_number(n) and n >= 0 for n in weights.values())):
        out.append("context.weights needs engine bench weights for every position or overall")
    if "rosterSize" in ctx and not _integer(ctx["rosterSize"]):
        out.append("context.rosterSize must be a nonnegative integer")
    return out


def evaluate_swaps(board: dict, request: dict) -> dict:
    """Replay the shared JS rules. Fail closed if Node or the bridge is unavailable."""
    errors = validate_request(request, board["setting"])
    if errors:
        raise ValueError("swap request: " + "; ".join(errors))
    try:
        result = subprocess.run(
            ["node", str(ROOT / "pipelines" / "waiver_board_swaps.cjs")],
            input=json.dumps({"board": board, "request": request}, allow_nan=False),
            capture_output=True, text=True, timeout=30, cwd=ROOT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"swap rules could not run: {exc}") from exc
    if result.returncode:
        raise ValueError("swap rules refused: " + result.stderr.strip()[-500:])
    try:
        return json.loads(result.stdout)
    except (TypeError, ValueError) as exc:
        raise ValueError("swap rules returned invalid JSON") from exc


def validate_block(block, board) -> list[str]:
    """Check shape, then replay the SAME rules to pin gain, identity and depth."""
    if not isinstance(block, dict) or set(block) != BLOCK_KEYS:
        return ["needs exactly " + ", ".join(sorted(BLOCK_KEYS))]
    errors = validate_request(block["request"], board["setting"])
    if type(block["available"]) is not bool:
        errors.append("available must be boolean")
    elif block["available"]:
        if block["missing_reason"] is not None:
            errors.append("available swaps must have a null missing_reason")
    elif not isinstance(block["missing_reason"], str) or not block["missing_reason"].strip():
        errors.append("unavailable swaps need a missing_reason")
    if not isinstance(block["rows"], list):
        errors.append("rows must be a list")
    else:
        for row in block["rows"]:
            if (not isinstance(row, dict) or set(row) != {"add", "drop", "gain"}
                    or not _integer(row["add"]) or not (row["drop"] is None or _integer(row["drop"]))
                    or not _number(row["gain"])):
                errors.append("each row needs integer add, integer-or-null drop and finite gain")
    if not _keys(block["unresolved_wire_keys"]):
        errors.append("unresolved_wire_keys must be unique integer player keys")
    if not errors:
        try:
            expected = evaluate_swaps(board, block["request"])
            if block != expected:
                errors.append("does not match the shared Waivers/finder replay (gain, identities, order or depth)")
        except ValueError as exc:
            errors.append(str(exc))
    return errors
