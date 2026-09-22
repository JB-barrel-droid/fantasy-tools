"""Preseason (draft) ECR rank annotation for the trade-value chart.

Repo-owned port of trade-value/annotate_preseason_ecr_rank.py (2026-09-22).
The chart's "lock order" control needs a stable preseason anchor per player.

SEMANTICS: the rank is POSITIONAL. The draft source
(data/inputs/ecr_draft.json, captured from FantasyPros draft ECR) carries
only per-position ranks -- QB1 -> 1, RB24 -> 24, WR137 -> 137. There is no
trustworthy overall (cross-position) rank in the source, and we do not
invent one. Consumers that need a single row order should sort within
position groups, i.e. by (pos, preseason_ecr_rank). Null means the player
has no preseason rank (breakouts, late additions, K/DST) -- never zero.

Identity (hard user rule): every draft name resolves through
lib/canonical_players to a numeric player_key. Ambiguous or unmatched
names resolve to nothing -- no rank is invented for them, ever.
"""

import json
import os
import sys

_LIB = os.path.dirname(os.path.abspath(__file__))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
from canonical_players import load_registry, resolve  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(_LIB))
DRAFT_ECR_JSON = os.path.join(_REPO, "data", "inputs", "ecr_draft.json")

FIELD = "preseason_ecr_rank"
META_KEY = "preseason_ecr"
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")


def provenance_note():
    """Provenance/semantics note for meta.preseason_ecr (shared with the bake)."""
    return {
        "source": "FantasyPros draft ECR (preseason)",
        "source_file": "data/inputs/ecr_draft.json",
        "semantics": ("POSITIONAL draft ECR rank (1 = best at the position). "
                      "The source carries no overall cross-position rank and "
                      "none is invented. Sort within position groups, e.g. "
                      "by (pos, preseason_ecr_rank). Null = no preseason "
                      "rank (breakout, late addition, K/DST), never zero."),
    }


def load_preseason_ecr_ranks(registry=None, draft_path=None):
    """Draft ECR positional rank keyed by canonical player_key.

    Returns (ranks, report) where ranks maps int player_key -> int
    positional rank, and report carries counts for logging/QA.
    Fail-closed: ambiguous/unmatched names are skipped (no invented ranks).
    On duplicate resolution to one key, the best (lowest) rank wins.
    """
    reg = registry or load_registry()
    with open(draft_path or DRAFT_ECR_JSON) as f:
        draft = json.load(f)

    ranks = {}
    report = {"draft_entries": len(draft), "skill_entries": 0,
              "resolved": 0, "unmatched": 0, "collisions": 0,
              "bad_ranks": 0}
    for _norm, entry in draft.items():
        pos = (entry.get("pos") or "").upper()
        if pos not in SKILL_POSITIONS:
            continue
        report["skill_entries"] += 1
        rank = entry.get("rank_ecr")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            report["bad_ranks"] += 1
            continue
        key = resolve(entry.get("name"), position=pos, registry=reg)
        if key is None:
            report["unmatched"] += 1
            continue
        key = int(key)
        if key in ranks:
            report["collisions"] += 1
            ranks[key] = min(ranks[key], rank)
        else:
            ranks[key] = rank
        report["resolved"] += 1
    return ranks, report


def annotate_rows(rows, ranks):
    """Pure annotation: set FIELD on each row from ranks (None where absent)."""
    for row in rows:
        key = row.get("player_key")
        row[FIELD] = ranks.get(int(key)) if key is not None else None
    return rows
