"""JEG-438 stage 3a: the Supabase reference savers resolve names through the one
player resolver, and the migration changed nothing it should not.

Three guards, each negative-tested against the broken state it names:

1. Stored labels are byte-identical. ``player_norm`` is part of the
   source_trade_values upsert grain and is joined on downstream, so a migrated
   writer must keep writing the exact strings the retired normalizers wrote.
   ``legacy_label`` is compared with frozen copies of those normalizers over
   every real name we hold (registry + committed source snapshots).
2. Same keys on real names. The pre-migration saver matcher (frozen copy of
   save_espn_cbs_references.build_name_index/resolve_name with the hand-kept
   ALIASES) and the migrated saver path are run over every name in the
   committed source snapshots. No key may change and no name may be lost; the
   only names allowed to start resolving are pinned (verified aliases).
3. A fuzzy (provisional) match is never written by a saver: it goes to review
   and to the pending list for the nightly reconcile.
"""
import json
import re
import sys
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import player_resolver as pr  # noqa: E402
import save_espn_cbs_references as espn_cbs  # noqa: E402
import save_cbsros_references as cbsros  # noqa: E402

SNAPSHOTS = (
    ("cbsros", ROOT / "data/raw/sources/cbsros/2026-09-30/snapshot.json"),
    ("fantasycalc", ROOT / "data/raw/sources/fantasycalc/week-4/snapshot.json"),
)
ESPN_PAGE = ROOT / "data/raw/sources/espn/live_page_projections_2026-09-30.json"


# ---------------------------------------------------------------------------
# Frozen copies of the retired code (verbatim, 2026-10-07, before migration).
# ---------------------------------------------------------------------------

def old_source_label(value):  # match_source_snapshot.normalize_name
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_OLD_SUFFIX_RE = re.compile(r"\s+(jr|sr|ii|iii|iv|v)$")


def old_plain_label(name):  # canonical_players.norm_plain
    s = (name or "").lower()
    for ch in ("’", "'", ".", "-"):
        s = s.replace(ch, "")
    s = _OLD_SUFFIX_RE.sub("", s)
    return " ".join(s.split())


def old_lower_label(name):  # refresh_fantasycalc_supabase.normalize_name
    return name.lower().strip()


OLD_ALIASES = {  # build_ddf_two_tier_leg.ALIASES
    "cameron ward": "cam ward",
    "cameron skattebo": "cam skattebo",
    "travis etienne jr": "travis etienne",
    "michael pittman jr": "michael pittman",
}


def old_index(players):
    index = {}
    for record in players:
        key = record.get("player_key")
        name = str(record.get("full_name") or "").strip()
        if not isinstance(key, int) or not name:
            continue
        index.setdefault(old_source_label(name), []).append(
            {"player_key": key, "position": str(record.get("position") or "").strip().upper() or None})
    return index


def old_resolve(name, pos, index):
    norm = old_source_label(name)
    norm = OLD_ALIASES.get(norm, norm)
    candidates = index.get(norm, [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]["player_key"]
    wanted = (pos or "").strip().upper()
    if wanted:
        filtered = [c for c in candidates if c.get("position") == wanted]
        if len(filtered) == 1:
            return filtered[0]["player_key"]
    return None


# ---------------------------------------------------------------------------
# Corpus: every real name we hold in the repo.
# ---------------------------------------------------------------------------

def registry_players():
    payload = pr.load_registry_payload()
    return [dict(zip(payload["columns"], row)) for row in payload["players"]]


def source_names():
    out = []
    for source, path in SNAPSHOTS:
        data = json.loads(path.read_text(encoding="utf-8"))
        for r in data["rows"] + data.get("review_rows", []):
            name = r.get("player_name") or r.get("player") or r.get("name")
            if name:
                out.append((source, name, r.get("pos")))
    for p in json.loads(ESPN_PAGE.read_text(encoding="utf-8"))["players"]:
        name = p.get("name") or p.get("player_name")
        if name:
            out.append(("espn", name, p.get("pos") or p.get("position")))
    return out


def label_corpus():
    payload = pr.load_registry_payload()
    names = {p["full_name"] for p in registry_players()}
    names |= {a["source_player_name"] for a in payload["aliases"]}
    names |= {n for _, n, _ in source_names()}
    return sorted(names)


class LabelConventionTest(unittest.TestCase):
    CONVENTIONS = {"source": old_source_label, "plain": old_plain_label, "lower": old_lower_label}

    def mismatches(self, convention, new_fn, corpus):
        old = self.CONVENTIONS[convention]
        return [n for n in corpus if new_fn(n) != old(n)]

    def test_labels_are_byte_identical_to_the_retired_normalizers(self):
        corpus = label_corpus()
        self.assertGreater(len(corpus), 4000)
        for convention in self.CONVENTIONS:
            bad = self.mismatches(convention, lambda n, c=convention: pr.legacy_label(n, c), corpus)
            self.assertEqual(bad[:10], [], f"{convention} label drifted")

    def test_corpus_catches_a_drifted_label(self):
        # Broken states: plausible "cleanups" that would silently re-key stored rows.
        corpus = label_corpus()
        broken = {
            "source": lambda n: pr.norm_key(n),                          # unify to the resolver key
            "plain": lambda n: old_plain_label(n.replace("-", " ")),     # hyphen to space, not deleted
            "lower": lambda n: n.lower(),                                # forget the strip
        }
        for convention, fn in broken.items():
            self.assertTrue(self.mismatches(convention, fn, corpus + [" Padded Name "]),
                            f"corpus cannot tell a drifted {convention} label apart")

    def test_unknown_convention_fails(self):
        with self.assertRaises(ValueError):
            pr.legacy_label("x", "nickname")


class SaverEquivalenceTest(unittest.TestCase):
    # Names that resolve now and did not before the migration (verified rows in
    # public.player_name_aliases). Anything else starting to resolve is a change
    # in matching and must be reviewed, not absorbed.
    NEWLY_RESOLVED = {"Kenny Gainwell"}

    def compare(self, new_players=None, extra_aliases=()):
        players = registry_players()
        oidx = old_index(players)
        nidx = pr.resolver_for_players(new_players(players) if new_players else players)
        for a in extra_aliases:
            nidx.add_alias(a)
        changed, lost, gained = [], [], set()
        for source, name, pos in source_names():
            old = old_resolve(name, pos, oidx)
            new, _rec, _pos = espn_cbs.resolve_player(name, pos, nidx, source)
            if old is not None and new is not None and old != new:
                changed.append((source, name, pos, old, new))
            elif old is not None and new is None:
                lost.append((source, name, pos, old))
            elif old is None and new is not None:
                gained.add(name)
        return changed, lost, gained

    def test_no_key_changes_or_losses_on_real_names(self):
        changed, lost, gained = self.compare()
        self.assertEqual(changed, [])
        self.assertEqual(lost, [])
        self.assertEqual(gained, self.NEWLY_RESOLVED)

    def test_comparison_catches_a_bad_alias_row(self):
        # Broken state: a wrong verified row in player_name_aliases re-points a
        # real name (the risk the alias table adds). Ja'Marr Chase -> Puka Nacua.
        r = pr.get_resolver()
        chase = r.key("Ja'Marr Chase", source="x", pos="WR", record=False)
        puka = r.key("Puka Nacua", source="x", pos="WR", record=False)
        self.assertNotEqual(chase, puka)
        bad = {"source": "*", "source_player_name": "Ja'Marr Chase", "position": "WR",
               "player_key": puka, "status": "verified"}
        changed, lost, _gained = self.compare(extra_aliases=[bad])
        # Re-pointed (changed) or, beside an existing verified alias, ambiguous (lost).
        hit = [c for c in changed + lost if c[1].lower().startswith("ja") and "chase" in c[1].lower()]
        self.assertTrue(hit, (changed[:3], lost[:3]))

    def test_comparison_catches_players_read_without_positions(self):
        # Broken state: the saver's live players read loses the position column.
        strip = lambda rows: [{k: v for k, v in p.items() if k != "position"} for p in rows]  # noqa: E731
        _changed, lost, _gained = self.compare(new_players=strip)
        self.assertGreater(len(lost), 100)


class ProvisionalNeverWrittenTest(unittest.TestCase):
    # Fictional names: the committed alias map must not already know them.
    PLAYERS = [
        {"player_key": 91001, "full_name": "Quentavious Zzyzxfake", "position": "WR", "active": True},
        {"player_key": 7, "full_name": "Ja'Marr Chase", "position": "WR", "active": True},
    ]
    FUZZY = "Quent Zzyzxfake"

    def check(self, lookup):
        r = pr.PlayerResolver(self.PLAYERS)
        key, reason = lookup(r, self.FUZZY, source="cbsros", pos="WR")
        self.assertIsNone(key, "a fuzzy match was handed to the writer")
        self.assertEqual(reason, "no_match")
        pending = r.pending_rows()
        self.assertEqual([(p["status"], p["player_key"]) for p in pending], [("provisional", 91001)])

    def test_saver_lookup_declines_fuzzy_and_records_it(self):
        self.check(pr.lookup_for_saver)
        self.assertEqual(pr.lookup_for_saver(pr.PlayerResolver(self.PLAYERS), "Ja’Marr Chase",
                                             source="cbs", pos="WR"), (7, None))

    def test_broken_state_accepting_fuzzy_is_caught(self):
        def accepting(r, name, *, source, pos=None, **_):
            res = r.resolve(name, source=source, pos=pos, allow_provisional=True)
            return res.player_key, None if res.player_key else "no_match"

        with self.assertRaises(AssertionError):
            self.check(accepting)

    def test_cbsros_rows_send_fuzzy_names_to_review(self):
        snap = {"vintage_date": "2026-10-01", "rows": [
            {"player_name": "Quent Zzyzxfake", "player_norm": "quent zzyzxfake", "pos": "WR"},
            {"player_name": "Ja’Marr Chase", "player_norm": "jamarr chase", "pos": "WR"}]}
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cbsros, "fetch_players", lambda: self.PLAYERS):
            path = Path(tmp) / "snapshot.json"
            path.write_text(json.dumps(snap), encoding="utf-8")
            clean, review, _ = cbsros.build_cbsros_rows(path)
        self.assertEqual([r["player_key"] for r in clean], [7])
        self.assertEqual([(r["player_name"], r["reason"]) for r in review], [("Quent Zzyzxfake", "no_match")])
        self.assertEqual(cbsros.RESOLVERS[-1].pending_rows()[0]["status"], "provisional")


if __name__ == "__main__":
    unittest.main()
