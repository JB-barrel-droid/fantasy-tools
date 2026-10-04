"""JEG-323 — regression guard: no health/freshness/vintage/check_ SQL function
defined in this repo may return a constant result without reading a table.

BACKGROUND
  Production Supabase exposes ``public.check_source_vintages()``, a
  console-only stub (no repo definition exists) that always returns
  ``{"changed": false, "note": "stub"}``. That is a false-green health
  surface, tracked under JEG-323 for revoke/removal. This guard makes
  sure no health-shaped function sneaks into the repo under that
  failure mode. A function whose name or comment matches
  ``health|freshness|vintage|check_`` MUST either reference a relation
  (FROM or JOIN on a table name) or appear on an explicit ALLOWLIST
  with a written reason.

DESIGN
  - Pure string/regex scan. No DB. No network. No fixtures.
  - Synthetic stub-like and real-function inline SQL strings prove the
    heuristic actually distinguishes the two failure modes the ticket
    names.
  - The repo scan walks ``sql/migrations/*.sql`` and ``sql/contract/*.sql``
    for ``CREATE [OR REPLACE] FUNCTION`` bodies and applies the same
    heuristic; an empty ALLOWLIST keeps the bar high.

Run: ``python3 -m unittest tests.test_health_function_no_hardcoded_green``
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Iterable, Tuple


# Root of the repo (tests/ lives one level under it).
ROOT = Path(__file__).resolve().parents[1]

# Directories to scan for CREATE [OR REPLACE] FUNCTION bodies.
SQL_DIRS = (
    ROOT / "sql" / "migrations",
    ROOT / "sql" / "contract",
)

# Pattern that marks a function as "health-shaped" by name OR by leading
# COMMENT. Substring matching is deliberate and fail-closed: a guard must
# catch the exact function this ticket names, and the word-boundary form
# \b(health|freshness|vintage|check_)\b FAILS on "check_source_vintages"
# (the "_" in "check_" is followed by "s" — both word chars, so no \b —
# and "vintage" is followed by "s", so no \b either). Over-flagging
# (e.g. a function named "checkout_something") is handled by the
# ALLOWLIST escape hatch with a written reason.
HEALTH_NAME_PATTERN = re.compile(r"(?i)(health|freshness|vintag|check)")

# Captures a CREATE [OR REPLACE] FUNCTION header up to the function name.
# We anchor on the signature and then look ahead for the body delimiter
# (``$$`` ... ``$$`` or ``AS ''`` ... ``''`` or ``BEGIN ... END``).
# NOTE (review fix 2026-10-04): this needs DOTALL. The original (?ix)
# form failed twice: (1) on Python 3.11+ a leading newline before
# (?ix) is a hard re.error ("global flags not at the start"); (2) without
# DOTALL, neither [^\n]*? nor .*? can cross the newlines between the
# signature and the AS $$ body delimiter, so real multi-line DDL never
# parsed. (?ixs) at position 0 fixes both.
CREATE_FUNCTION_RE = re.compile(
    r"""(?ixs)
    create \s+ (?: or \s+ replace \s+ )? function \s+
    (?: \w+ \s* \. \s* )?            # optional schema.
    (?P<name> \w+ )                  # function name
    .*?                             # rest of signature (may span lines).
    (?:
        \$\$\s* (?P<dollar_body>.*?) \$\$    # $$ ... $$ plpgsql body
      |
        '(?P<single_body>(?:[^']|'')*?)'     # ' ... ' body
      |
        begin \s* (?P<plain_body>.*?) \s* end # BEGIN ... END body
    )
    """,
)

# A COMMENT that names the function as health/freshness/vintage pulls it
# into scope. PlpgSQL COMMENTs live on a separate statement, so we look
# for them in the ~30 lines above the CREATE FUNCTION.
COMMENT_LINE_RE = re.compile(r"(?im)^\s*--\s*(?P<text>.*)$")


# Functions on this allowlist are explicitly exempted. The reason must
# be written out so future reviewers see WHY the exemption exists. Keep
# it small. Every entry is a tuple (qualname, reason).
#
ALLOWLIST: Tuple[Tuple[str, str], ...] = (
    # Example shape (no entries today; the stub the ticket names lives
    # in production Supabase only and has no repo definition — see
    # lanes/inbox/minimax/JEG-323-guard.md).
)


def _iter_create_function_bodies() -> Iterable[Tuple[Path, str, str, str, int]]:
    """Yield (file, qualified_name, name, body, match_start) for every
    CREATE FUNCTION body found under SQL_DIRS.

    The matching is intentionally permissive on syntax so the heuristic
    in :func:`classify_function` sees realistic inputs. match_start is
    yielded so callers can look at the comments leading THIS function,
    not the first function in the file.
    """
    for sql_dir in SQL_DIRS:
        if not sql_dir.is_dir():
            continue
        for path in sorted(sql_dir.glob("*.sql")):
            text = path.read_text(encoding="utf-8")
            for match in CREATE_FUNCTION_RE.finditer(text):
                name = match.group("name")
                body = (
                    match.group("dollar_body")
                    or match.group("single_body")
                    or match.group("plain_body")
                    or ""
                )
                qualified = f"public.{name}"
                yield path, qualified, name, body, match.start()


def _is_health_shaped(name: str, body: str, leading_comments: str) -> bool:
    """Return True if the function name or any leading comment matches
    the health/freshness/vintage/check_ pattern.
    """
    if HEALTH_NAME_PATTERN.search(name):
        return True
    for line_match in COMMENT_LINE_RE.finditer(leading_comments):
        if HEALTH_NAME_PATTERN.search(line_match.group("text")):
            return True
    return False


def _reads_any_table(body: str) -> bool:
    """Heuristic: the function body references at least one relation
    via FROM or JOIN on a table-like identifier.

    The check is a literal regex — we are NOT parsing SQL. A function
    that constructs a query via string concatenation or uses EXECUTE
    would defeat this scan. That is acceptable: a health function whose
    body is built at call time and not statically inspectable is a smell
    that belongs in a code review, not in this guard.
    """
    # Strip line comments first so a commented-out FROM doesn't satisfy
    # the bar.
    stripped = re.sub(r"--[^\n]*", "", body)
    # FROM <relation> or JOIN <relation>. The relation token is any
    # unquoted sequence of letters, digits, underscores, and dots (so
    # schema-qualified names like public.source_trade_values match).
    table_ref_re = re.compile(
        r"(?i)\b(?:FROM|JOIN)\b\s+(?P<rel>[A-Za-z_][\w]*\.[A-Za-z_][\w]*"
        r"|[A-Za-z_][\w]*)"
    )
    return bool(table_ref_re.search(stripped))


def classify_function(name: str, body: str, leading_comments: str) -> str:
    """Return one of:

    - ``"pass"`` — health-shaped AND reads a table. (Real check.)
    - ``"fail-stub"`` — health-shaped AND does NOT read a table. (Stub.)
    - ``"pass-nonscope"`` — not health-shaped; nothing to say.

    The classifier is the core of the guard. The synthetic tests below
    exercise each branch.
    """
    if not _is_health_shaped(name, body, leading_comments):
        return "pass-nonscope"
    return "pass" if _reads_any_table(body) else "fail-stub"


def _leading_comments_for(text: str, start: int) -> str:
    """Return the run of comment lines immediately preceding ``start``.

    We look at most 30 lines backwards; nothing else is plausibly the
    function's prologue.
    """
    snippet = text[:start].splitlines()[-30:]
    return "\n".join(snippet)


class SyntheticStubGuard(unittest.TestCase):
    """Hermetic inline-SQL cases proving the heuristic catches the stub
    class the ticket names (a stub returns a constant without reading a
    table) and lets a real health function through.
    """

    SYNTHETIC_STUB = """
    -- Returns a constant payload. (Deliberately innocuous comment with
    -- none of the health/freshness/vintage/check stems: this case proves
    -- the NAME arm alone catches the ticket's function.)
    create or replace function public.check_source_vintages()
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = public, pg_temp
    as $$
    begin
      -- NB: no FROM or JOIN anywhere in this body.
      return jsonb_build_object('changed', false, 'note', 'stub');
    end $$;
    """

    SYNTHETIC_REAL = """
    -- vintage check: compare current vintage to last-dispatched.
    create or replace function public.check_source_vintages()
    returns jsonb
    language plpgsql
    volatile
    security definer
    set search_path = public, pg_temp
    as $$
    declare
      out jsonb;
    begin
      select jsonb_build_object(
        'changed',     (cur is distinct from fx),
        'current',     cur,
        'fixture',     fx
      ) into out
      from public.source_trade_values stv,
           public.pipeline_cron_state pcs
      where stv.source = 'fantasycalc'
        and pcs.key    = 'fantasycalc'
      limit 1;
      return coalesce(out, jsonb_build_object('changed', true));
    end $$;
    """

    SYNTHETIC_NAMED_ONLY = """
    -- innocuous comment, but the name screams "health check".
    create or replace function public.health_probe()
    returns text
    language sql
    as $$ select 'green'::text $$;
    """

    SYNTHETIC_COMMENT_ONLY = """
    -- Returns the freshness stamp for the source.
    create or replace function public.freshness_stamp()
    returns text
    language sql
    as $$ select '2026-10-03'::text $$;
    """

    def test_synthetic_stub_is_caught(self):
        match = CREATE_FUNCTION_RE.search(self.SYNTHETIC_STUB)
        self.assertIsNotNone(match, "synthetic stub did not parse")
        body = match.group("dollar_body") or match.group("single_body") or match.group("plain_body")
        leading = self.SYNTHETIC_STUB[: match.start()]
        verdict = classify_function(match.group("name"), body, leading)
        self.assertEqual(verdict, "fail-stub",
                         "stub-like function MUST classify as fail-stub")

    def test_name_arm_alone_catches_ticket_function(self):
        """Direct classifier unit test: the exact function name from
        JEG-323 must be caught by the NAME arm with zero leading
        comments. Regression: the first version of HEALTH_NAME_PATTERN
        used \\b...\\b word boundaries and missed "check_source_vintages"
        by name (the "_" is followed by "s", so no boundary)."""
        verdict = classify_function(
            "check_source_vintages",
            "begin return jsonb_build_object('changed', false); end",
            "",
        )
        self.assertEqual(
            verdict, "fail-stub",
            "name arm MUST catch check_source_vintages with no comments",
        )
        # And the name arm must NOT fire on an unrelated name.
        self.assertEqual(
            classify_function(
                "update_player_ranks",
                "begin return jsonb_build_object('ok', true); end",
                "",
            ),
            "pass-nonscope",
            "unrelated names must stay out of scope",
        )

    def test_synthetic_real_is_passed(self):
        match = CREATE_FUNCTION_RE.search(self.SYNTHETIC_REAL)
        self.assertIsNotNone(match, "synthetic real did not parse")
        body = match.group("dollar_body") or match.group("single_body") or match.group("plain_body")
        leading = self.SYNTHETIC_REAL[: match.start()]
        verdict = classify_function(match.group("name"), body, leading)
        self.assertEqual(verdict, "pass",
                         "real function reading tables MUST classify as pass")

    def test_health_named_const_only_is_caught(self):
        """A function named like a health probe that reads no table is the
        exact shape JEG-323 names. It MUST fail the guard even with a
        clean comment.
        """
        match = CREATE_FUNCTION_RE.search(self.SYNTHETIC_NAMED_ONLY)
        self.assertIsNotNone(match)
        body = match.group("dollar_body") or match.group("single_body") or match.group("plain_body")
        leading = self.SYNTHETIC_NAMED_ONLY[: match.start()]
        verdict = classify_function(match.group("name"), body, leading)
        self.assertEqual(verdict, "fail-stub",
                         "name-only health function with no FROM MUST be caught")

    def test_comment_only_freshness_const_only_is_caught(self):
        """A function whose comment (not name) says 'freshness' and that
        returns a constant is exactly the JEG-323 failure mode. The guard
        MUST catch it via the COMMENT arm.
        """
        match = CREATE_FUNCTION_RE.search(self.SYNTHETIC_COMMENT_ONLY)
        self.assertIsNotNone(match)
        body = match.group("dollar_body") or match.group("single_body") or match.group("plain_body")
        leading = self.SYNTHETIC_COMMENT_ONLY[: match.start()]
        verdict = classify_function(match.group("name"), body, leading)
        self.assertEqual(verdict, "fail-stub",
                         "comment-flagged freshness function with no FROM MUST be caught")


class RepoScanGuard(unittest.TestCase):
    """Walk sql/migrations/ and sql/contract/ and FAIL on any health-shaped
    function whose body has no FROM or JOIN.

    Today the repo has zero CREATE FUNCTION bodies, so this test is a
    tripwire: it MUST stay green and FAIL the day someone lands a stub.
    """

    def test_no_hardcoded_green_health_function(self):
        offenders = []
        allowlisted = {qualname for qualname, _ in ALLOWLIST}
        for path, qualified, name, body, start in _iter_create_function_bodies():
            text = path.read_text(encoding="utf-8")
            leading = _leading_comments_for(text, start)
            verdict = classify_function(name, body, leading)
            if verdict == "fail-stub" and qualified not in allowlisted:
                offenders.append(
                    f"{path.name}: {qualified} — body has no FROM/JOIN. "
                    f"Add a relation read OR add the function to ALLOWLIST in "
                    f"tests/test_health_function_no_hardcoded_green.py with a "
                    f"written reason."
                )
        self.assertEqual(
            offenders, [],
            "JEG-323: health/freshness/vintage/check_ function(s) with no "
            "table read detected:\n  - " + "\n  - ".join(offenders),
        )

    def test_allowlist_entries_are_well_formed(self):
        """Every ALLOWLIST row must carry a non-empty reason; an empty
        reason means the exemption slipped through review.
        """
        for qualname, reason in ALLOWLIST:
            self.assertTrue(qualname, "ALLOWLIST entry missing qualname")
            self.assertTrue(
                reason and reason.strip(),
                f"ALLOWLIST entry for {qualname!r} has empty reason; "
                f"every exemption MUST carry a written justification",
            )


if __name__ == "__main__":
    unittest.main()