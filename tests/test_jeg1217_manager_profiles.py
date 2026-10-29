"""Manager profiles (JEG-1217 stages 1-2): capture, exclusion, identity, persistence and import/export.

The checks live in tests/manager_profiles_harness.cjs (pure Node, no browser). Every guard is proven:
test_checks_fail_on_broken_builds copies the modules, breaks one rule at a time, and requires the harness to name the
check that catches it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "v2"
HARNESS = ROOT / "tests" / "manager_profiles_harness.cjs"
MODULES = ["manager-profiles.js", "workspace.js"]

REQUIRED = [
    "test_unknown_profile_is_default", "test_no_numeric_weights", "test_describe_single_mixed_none", "test_exclusion_toggle",
    "test_my_team_never_eligible", "test_duplicate_names_keep_separate_profiles", "test_rename_keeps_profile", "test_removal_drops_profile",
    "test_profiles_are_per_league", "test_unchanged_write_returns_same_book", "test_tags_fixed_list_no_free_text", "test_store_reload",
    "test_store_debounce", "test_store_corrupt_and_version_not_overwritten", "test_store_unavailable", "test_store_other_tab",
    "test_legacy_and_partial_state", "test_profiles_do_not_touch_workspace", "test_export_import_round_trip",
    "test_import_matches_by_unique_name_only", "test_import_rejects_bad_files", "test_legacy_note_round_trip",
    "test_store_save_failure_reported_and_recovers", "test_legacy_note_starting_with_tag_label",
    "test_store_pending_edit_survives_other_tab", "test_store_pending_edit_merges_same_manager",
    "test_store_reload_without_pending_edit_takes_other_tab",
]


def run_harness(modules_dir: Path) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", str(HARNESS), str(modules_dir)], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise AssertionError(f"harness crashed: {out.stderr[-1500:]}")
    return json.loads(out.stdout)


def mutated(old: str, new: str) -> tempfile.TemporaryDirectory:
    """A temp dir with the modules, manager-profiles.js edited once; a stale anchor fails loudly."""
    tmp = tempfile.TemporaryDirectory()
    for name in MODULES:
        shutil.copy2(APP / name, Path(tmp.name) / name)
    path = Path(tmp.name) / "manager-profiles.js"
    text = path.read_text(encoding="utf-8")
    if old not in text:
        tmp.cleanup()
        raise AssertionError(f"mutation anchor is stale: {old[:70]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return tmp


# (rule broken, anchor, replacement, a check that must fail)
MUTATIONS = [
    ("excluded managers stay eligible", "eligible: !mine && !profile.excluded", "eligible: !mine", "test_exclusion_toggle"),
    ("my team becomes a counterparty", "eligible: !mine && !profile.excluded", "eligible: !profile.excluded", "test_my_team_never_eligible"),
    ("profiles keyed by name", "const saved = book.leagues[ws.id] && book.leagues[ws.id][String(teamId)];",
     "const t = (ws.teams || []).find(x => String(x.id) === String(teamId)); const byName = t && Object.values(book.leagues[ws.id] || {}).find(p => (ws.teams.find(x => x.id === p.teamId) || {}).name === t.name); const saved = byName;",
     "test_duplicate_names_keep_separate_profiles"),
    ("removed teams keep profiles", "const dropped = Object.keys(league).filter(id => !ids.has(id));", "const dropped = [];", "test_removal_drops_profile"),
    ("writes to unknown teams accepted", "if (!teamIds(ws).has(id)) return book;", "", "test_removal_drops_profile"),
    ("numbers accepted as levels", "const pick = (value, allowed) => (allowed.includes(value) ? value : allowed[0]);",
     "const pick = (value, allowed) => (allowed.includes(value) || typeof value === \"number\" ? value : allowed[0]);", "test_legacy_and_partial_state"),
    ("numbers accepted by setAnchor", "ANCHORS.includes(anchor) && LEVELS.includes(level)", "ANCHORS.includes(anchor)", "test_no_numeric_weights"),
    ("truthy strings exclude", "excluded: raw.excluded === true", "excluded: Boolean(raw.excluded)", "test_legacy_and_partial_state"),
    ("corrupt value overwritten on load", "setState(loadStatus === \"unavailable\"", "dirty = loadStatus !== \"ok\"; write(); setState(loadStatus === \"unavailable\"",
     "test_store_corrupt_and_version_not_overwritten"),
    ("nothing persisted", "storage.setItem(STORAGE_KEY, serialize(book));", "void 0;", "test_store_reload"),
    ("duplicate names match on import", "count(leagueNames, name) === 1 && count(fileNames, name) === 1", "true", "test_import_matches_by_unique_name_only"),
    ("unversioned import accepted", "if (data.v !== VERSION) return {book, matched: 0, unmatched: [], error: \"Those manager profiles were saved by a newer version of this page.\"};",
     "", "test_import_rejects_bad_files"),
    ("blank profiles kept", "if (isBlank(profile)) delete league[id];", "if (!profile) delete league[id];", "test_exclusion_toggle"),
    ("mixed not detected", "active.length === 1 ? \"single\" : \"mixed\"", "\"single\"", "test_describe_single_mixed_none"),
    ("free text accepted as a tag", "const cleanTags = list => (Array.isArray(list) ? TAGS.filter(tag => list.includes(tag)) : []);",
     "const cleanTags = list => (Array.isArray(list) ? [...new Set(list)] : []);", "test_tags_fixed_list_no_free_text"),
    ("tags start ticked", "excluded: false, tags: [],", "excluded: false, tags: [\"rookies\"],", "test_unknown_profile_is_default"),
    ("ticked tags not saved", "!p.excluded && !p.tags.length &&", "!p.excluded &&", "test_tags_fixed_list_no_free_text"),
    ("earlier note dropped on load", "...(note ? {note} : {}),", "", "test_legacy_note_round_trip"),
    ("earlier Other preferences dropped on load", "...(kept !== \"unknown\" ? {[LEGACY_ANCHOR]: kept} : {})", "", "test_legacy_note_round_trip"),
    ("note-only profile saved as nothing", "&& !legacyOf(p).note && !legacyOf(p).subjective);", ");", "test_legacy_note_round_trip"),
    ("tag-label prefix of an earlier note read as ticked", "tags: cleanTags(raw.tags),",
     "tags: cleanTags([...(Array.isArray(raw.tags) ? raw.tags : []), ...TAGS.filter(t => cleanNote(raw.note).startsWith(TAG_LABELS[t]))]),",
     "test_legacy_note_starting_with_tag_label"),
    ("tag-label prefix stripped from an earlier note", "const note = cleanNote(raw.note);",
     "const note = TAGS.reduce((n, t) => (n.startsWith(TAG_LABELS[t]) ? n.slice(TAG_LABELS[t].length).replace(/^[;,.\\s]+/, \"\") : n), cleanNote(raw.note));",
     "test_legacy_note_starting_with_tag_label"),
    ("failed delayed save not announced", "statusListeners.forEach(fn =>", "[].forEach(fn =>", "test_store_save_failure_reported_and_recovers"),
    ("failed save not retried", "storage.setItem(STORAGE_KEY, serialize(book));\n        dirty = false;", "dirty = false;\n        storage.setItem(STORAGE_KEY, serialize(book));",
     "test_store_save_failure_reported_and_recovers"),
    # JEG-1318: another tab saves inside this tab's write delay.
    ("pending edit dropped by another tab's save", "const next = dirty ? normalizeBook(merge3(shared, book, parsed.book)) || parsed.book : parsed.book;", "const next = parsed.book;",
     "test_store_pending_edit_survives_other_tab"),
    ("pending edit overwrites another tab's save", "const next = dirty ? normalizeBook(merge3(shared, book, parsed.book)) || parsed.book : parsed.book;", "const next = dirty ? book : parsed.book;",
     "test_store_pending_edit_survives_other_tab"),
    ("merge base not moved on save", "        shared = book;\n        setState(\"saved\");", "        setState(\"saved\");",
     "test_store_pending_edit_survives_other_tab"),
    ("ticked boxes not combined", "return [...new Set(mine.concat(theirs))]", "return mine; void [...new Set(mine.concat(theirs))]",
     "test_store_pending_edit_merges_same_manager"),
    ("a field both tabs set goes to the other tab", "    return mine;\n  }\n\n  // ---------- the store", "    return theirs;\n  }\n\n  // ---------- the store",
     "test_store_pending_edit_merges_same_manager"),
    ("save still owed once storage holds the edit", "if (dirty && serialize(next) === serialize(shared)) {", "if (false) {",
     "test_store_reload_without_pending_edit_takes_other_tab"),
]


class ManagerProfiles(unittest.TestCase):
    def test_all_checks_pass(self):
        result = run_harness(APP)
        self.assertEqual(result["failures"], [])
        missing = [name for name in REQUIRED if name not in result["ran"]]
        self.assertEqual(missing, [], "required checks did not run")

    def test_checks_fail_on_broken_builds(self):
        for label, old, new, expect in MUTATIONS:
            with self.subTest(label):
                tmp = mutated(old, new)
                try:
                    result = run_harness(Path(tmp.name))
                finally:
                    tmp.cleanup()
                failed = {f["name"] for f in result["failures"]}
                self.assertIn(expect, failed, f"{label}: {expect} did not catch it (failed: {sorted(failed)})")

    def test_module_has_no_dom_or_engine_dependency(self):
        text = (APP / "manager-profiles.js").read_text(encoding="utf-8")
        for token in ("document.", "TradeValueFinder", "TradeValueEngine", "fetch("):
            self.assertNotIn(token, text, token)


if __name__ == "__main__":
    unittest.main()
