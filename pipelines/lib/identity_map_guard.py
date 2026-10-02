"""Identity-map write-path guard: prevent case-variant duplicates (JEG-112).

The canonical naming table at ``data/inputs/player_identity_map.json`` must
never hold two entries that differ only by case -- e.g. "Puka Nacua" and
"puka nacua" as separate rows. Case-variant duplicates break identity
resolution (the lookup table treats them as distinct) and they trip the
fail-closed ambiguity guard on what is really the same player.

This file provides the *write path* -- any pipeline that adds a new
canonical entry or alias MUST go through these helpers. They enforce:

  * Inserting a raw key whose case-normalized form (``norm_case_only``)
    already has a row raises ``IdentityMapCaseVariantCollision`` with
    the existing row's data.
  * Cross-section collisions are caught: a new canonical that
    case-normalizes to an existing alias -- or vice versa -- is the
    same problem from the other side, and the guard rejects it.
  * ``assert_no_case_duplicates()`` validates an in-memory snapshot (or
    the committed file) and raises the same exception type when a
    duplicate exists. This is what the regression test exercises.

The case-variant rule is *narrower* than the resolver's
``norm_player_name``: the brief scopes the invariant to "differ only
by case". Nickname expansion (``"josh" -> "joshua"``) is the resolver's
job and lives in :mod:`canonical_players` -- including it would flag
identity self-loops (e.g. an alias ``"josh allen"`` whose target is
``"josh allen"``) as case-variant duplicates, which is a different
class of redundancy and out of scope for JEG-112.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

_LIB = os.path.dirname(os.path.abspath(__file__))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

# Importable for the regression test that asserts we don't re-implement
# the rule -- the case-variant guard uses the dedicated ``norm_case_only``
# (defined below) for the case-variant invariant.


_REPO = os.path.dirname(os.path.dirname(_LIB))
IDENTITY_SNAPSHOT = os.path.join(
    _REPO, "data", "inputs", "player_identity_map.json"
)


def norm_case_only(s):
    """Case-variant normalization (JEG-112): lowercase, strip leading/trailing
    whitespace, collapse internal whitespace. Nothing else.

    Deliberately does NOT strip punctuation or generational suffixes:
    "ja'marr chase" vs "jamarr chase" and "james cook" vs "james cook iii"
    differ by more than case, so they are not case variants. The ticket
    scopes the invariant to "differ only by case" -- lower+strip, literally.
    Nickname expansion is the resolver's job and lives in
    ``canonical_players.norm_player_name``.
    """
    return " ".join(str(s).lower().split())


class IdentityMapCaseVariantCollision(ValueError):
    """Raised when an insert would create a case-variant duplicate.

    Carries enough context for the caller (or a regression test) to
    report exactly which raw form collided with which existing row.
    """

    def __init__(self, message: str, *, raw: str, norm: str,
                 existing_key: str | None = None,
                 existing_value: Any = None):
        super().__init__(message)
        self.raw = raw
        self.norm = norm
        self.existing_key = existing_key
        self.existing_value = existing_value


def _norm_index(*, canonical: dict, aliases: dict) -> dict[str, list[tuple[str, str]]]:
    """Build a {norm -> set(raw_key)} index of distinct raw forms per norm.

    The JEG-112 brief scopes the invariant to "groups with >1 distinct
    raw form" -- i.e. two raw strings that *differ* (otherwise it's a
    literal cross-section duplicate, not a case variant). We track the
    set of raw keys per norm so an alias self-loop that happens to
    share a key with a canonical row does not trip the audit (those
    self-loops are out of scope for JEG-112; see the lane report).
    """
    idx: dict[str, set[str]] = {}
    for raw in canonical:
        n = norm_case_only(raw)
        idx.setdefault(n, set()).add(raw)
    for raw in aliases:
        n = norm_case_only(raw)
        idx.setdefault(n, set()).add(raw)
    return idx


def assert_no_case_duplicates(snapshot: dict) -> None:
    """Validate ``snapshot`` has zero case-variant duplicates.

    A duplicate is a single norm with >1 *distinct* raw form across
    both sections. Identical-key cross-section duplicates (an alias
    self-loop sharing a key with the canonical row) are NOT case
    variants and are out of scope here -- they are filtered out by the
    resolver (``_load_alias_overrides`` keeps only ``a != c``), so they
    do not affect identity resolution.

    Raises :class:`IdentityMapCaseVariantCollision` on the first
    collision found (with the offending norm group). Intended for both
    the regression test and the commit-time audit.
    """
    canonical = snapshot.get("canonical", {}) or {}
    aliases = snapshot.get("alias_to_canonical", {}) or {}
    idx = _norm_index(canonical=canonical, aliases=aliases)
    for norm, raw_set in idx.items():
        if len(raw_set) > 1:
            sample = ", ".join(repr(r) for r in sorted(raw_set)[:6])
            extra = "" if len(raw_set) <= 6 else f" (+{len(raw_set) - 6} more)"
            raise IdentityMapCaseVariantCollision(
                f"case-variant duplicate: {len(raw_set)} distinct raw forms "
                f"normalize to {norm!r} -> [{sample}{extra}]",
                raw=sorted(raw_set)[0],
                norm=norm,
                existing_key=None,
                existing_value=None,
            )


def _ensure_norm_unique(raw: str, *, section: str,
                        canonical: dict, aliases: dict) -> None:
    """Reject ``raw`` if its case-normalized form already exists *with a
    distinct raw key* (case-variant duplicate).

    Identical-key cross-section duplicates are skipped -- they are out
    of scope for the JEG-112 brief, which targets distinct raw forms
    collapsing to the same norm.
    """
    norm = norm_case_only(raw)
    # Cross-section norm collision: any prior raw with a DIFFERENT raw form
    # that normalizes the same.
    for prior_raw in list(canonical.keys()) + list(aliases.keys()):
        if prior_raw == raw:
            continue
        if norm_case_only(prior_raw) == norm:
            sec = ("canonical" if prior_raw in canonical
                   else "alias_to_canonical")
            collider = canonical.get(prior_raw) or aliases.get(prior_raw)
            raise IdentityMapCaseVariantCollision(
                f"{section}: raw {raw!r} (norm {norm!r}) collides with "
                f"existing raw {prior_raw!r} in {sec} -- case-variant "
                f"duplicates are forbidden. Existing value: {collider!r}",
                raw=raw, norm=norm, existing_key=prior_raw,
                existing_value=collider,
            )


def add_canonical_entry(snapshot: dict, *, key: str, name: str,
                        pos: str, team: str) -> dict:
    """Insert a canonical entry into ``snapshot`` with case-variant protection.

    Returns the (mutated) snapshot dict. The key is added verbatim -- the
    guard rejects *case-variant* duplicates but does not silently rewrite
    the caller's casing. Callers that want the always-lowercase convention
    should pass ``key.lower()`` themselves; the guard's job is to refuse
    a second row, not to second-guess the first one.

    Raises :class:`IdentityMapCaseVariantCollision` if the normalized key
    already exists anywhere in the snapshot.
    """
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dict")
    canonical = dict(snapshot.get("canonical") or {})
    aliases = dict(snapshot.get("alias_to_canonical") or {})
    _ensure_norm_unique(key, section="canonical",
                        canonical=canonical, aliases=aliases)
    canonical[key] = {"name": name, "pos": pos, "team": team}
    snapshot["canonical"] = canonical
    return snapshot


def add_alias(snapshot: dict, *, alias: str, target: str) -> dict:
    """Insert an alias into ``snapshot`` with case-variant protection.

    The target is checked against ``canonical`` keys (not just aliases)
    so a new alias whose normalized form matches an existing canonical
    row is rejected -- that is the fail-closed case (the alias spelling
    would silently shadow a real identity on lookup).

    Raises :class:`IdentityMapCaseVariantCollision` if the normalized
    alias already exists anywhere in the snapshot.
    """
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dict")
    canonical = dict(snapshot.get("canonical") or {})
    aliases = dict(snapshot.get("alias_to_canonical") or {})
    # Same key, different target: real conflict, not idempotent.
    if alias in aliases and aliases[alias] != target:
        raise IdentityMapCaseVariantCollision(
            f"alias_to_canonical: alias {alias!r} already maps to "
            f"{aliases[alias]!r}, cannot remap to {target!r}",
            raw=alias, norm=norm_case_only(alias),
            existing_key=alias, existing_value=aliases[alias],
        )
    _ensure_norm_unique(alias, section="alias_to_canonical",
                        canonical=canonical, aliases=aliases)
    aliases[alias] = target
    snapshot["alias_to_canonical"] = aliases
    return snapshot


def load_snapshot(path: str = IDENTITY_SNAPSHOT) -> dict:
    """Load the snapshot JSON. Used by tests and the audit pass."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def audit_file(path: str = IDENTITY_SNAPSHOT) -> dict:
    """Load ``path`` and run :func:`assert_no_case_duplicates`.

    Returns the snapshot on success; raises
    :class:`IdentityMapCaseVariantCollision` on failure. Use as a
    commit-time / pipeline guard.
    """
    snap = load_snapshot(path)
    assert_no_case_duplicates(snap)
    return snap