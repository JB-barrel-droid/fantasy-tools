"""JEG-1099: click an opportunity and both teams' lineups open below the table.

20-team league: click row 1; the panel names both teams, shows each side's gives and gets, the starting lineup by position
before and after in DDF Value, the starters value change equal to the table's own arithmetic, the row is highlighted, the
address carries the pick, the selection survives "Show all" and "Show top 10 only", Escape closes it and returns focus,
and the link reopens the same trade after a reload. The viability slot now carries the fit label and the viability (JEG-1108), for example "Natural fit · High viability".

Discrimination: test_guard_fails_on_broken_builds serves league.js with the click ignored, with the Escape key ignored,
and with the pick dropped on re-render, and requires the checks to fail on each.
"""
from __future__ import annotations

import re
import unittest

from tests._league_render import browser_on_build, open_page, seed, source, wait_opps

PANEL = """() => { const p = document.getElementById('v2LgOppPanel'); if (!p) return null;
  const side = s => { const n = p.querySelector(`[data-side="${s}"]`); if (!n) return null;
    const t = n.querySelector('table[data-view="DDF Value"]');
    return {head: n.querySelector('h4').textContent, text: n.querySelector('p').textContent,
      slots: t ? [...t.querySelectorAll('tbody tr[data-slot]')].map(tr => [...tr.children].map(c => c.textContent)) : [],
      starters: t ? [...[...t.querySelectorAll('tbody tr')].find(tr => tr.firstChild.textContent === 'Starters').children].map(c => c.textContent) : null}; };
  return {title: p.querySelector('h3').textContent, mine: side('Your team'), theirs: side('Their team'),
    viability: (document.getElementById('v2LgOppPanelViability') || {}).textContent || '', hash: location.hash,
    selected: [...document.querySelectorAll('#v2LgOppsTable tr.v2-lg-opp.is-selected')].map(tr => tr.dataset.oppId)}; }"""
FIRST_ROW = "#v2LgOppsTable tbody tr.v2-lg-opp >> nth=0"


def check(browser, base, overrides=None):
    errors = []
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[panel] ")
    seed(page, "20team")
    wait_opps(page, timeout=90000)
    if page.evaluate("() => document.getElementById('v2LgOppPanel')"):
        errors.append("a panel is open before any click")
    first_id = page.evaluate("() => document.querySelector('#v2LgOppsTable tr.v2-lg-opp').dataset.oppId")
    page.click(FIRST_ROW + " >> td >> nth=0")
    page.wait_for_selector("#v2LgOppPanel")
    s = page.evaluate(PANEL)
    if not s["mine"] or not s["theirs"]:
        errors.append(f"panel lacks a side: {s}")
        page.close()
        return errors
    for who in ("mine", "theirs"):
        side = s[who]
        if "Gives:" not in side["text"] or "Gets:" not in side["text"] or not side["slots"]:
            errors.append(f"{who}: gives/gets or lineup missing: {side}")
        for slot in side["slots"]:
            if len(slot) != 4 or not re.fullmatch(r"[+−-]?\d+\.\d|0\.0|[+-]\d+\.\d", slot[3].replace("−", "-")):
                errors.append(f"{who}: slot row malformed {slot}")
        if not side["starters"] or len(side["starters"]) != 4:
            errors.append(f"{who}: no starters total row")
    # The change shown on each side is after minus before, to the shown precision.
    for who in ("mine", "theirs"):
        b, a, d = (float(x.replace("−", "-")) for x in s[who]["starters"][1:])
        if abs((a - b) - d) > 0.11:
            errors.append(f"{who}: starters {b} -> {a} but change {d}")
    if not page.evaluate("() => Boolean(document.querySelector('#v2LgOppPanel button#v2LgOppPanelClose'))"):
        errors.append("Close button missing from the panel")
    if not re.fullmatch(r"(Natural fit|Market supported|Force fit) · (High|Medium-high|Medium) viability", s["viability"]):
        errors.append(f"viability slot does not carry '<fit> · <level> viability' (JEG-1108): {s['viability']!r}")
    if s["selected"] != [first_id] or f"trade=" not in s["hash"]:
        errors.append(f"row not highlighted or address has no pick: {s['selected']} {s['hash']}")
    # The pick survives Show all and Show top 10 only.
    page.click("#v2LgOppsAll")
    page.wait_for_timeout(200)
    if not page.evaluate("() => Boolean(document.getElementById('v2LgOppPanel'))"):
        errors.append("the panel closed on Show all")
    page.click("#v2LgOppsLess")
    page.wait_for_timeout(200)
    if page.evaluate("() => (document.getElementById('v2LgOppPanel') || {dataset: {}}).dataset.oppId") != first_id:
        errors.append("the pick did not survive Show top 10 only")
    # The link reopens the same trade.
    url = page.evaluate("() => location.href")
    page.reload(wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=30000)
    wait_opps(page, timeout=90000)
    page.wait_for_timeout(300)
    if (page.evaluate("() => (document.getElementById('v2LgOppPanel') || {dataset: {}}).dataset.oppId") or "").split("|")[1:] != first_id.split("|")[1:]:
        errors.append(f"the link {url} did not reopen the same trade")
    # Escape closes it and returns focus to the row's button.
    page.focus("#v2LgOppPanelLink")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    if page.evaluate("() => Boolean(document.getElementById('v2LgOppPanel'))") or "trade=" in page.evaluate("() => location.hash"):
        errors.append("Escape did not close the panel and clear the address")
    if not page.evaluate("() => (document.activeElement.dataset || {}).pickFor"):
        errors.append("focus did not return to the Both teams button")
    page.close()
    return errors


def run_checks(overrides=None):
    with browser_on_build() as (browser, base):
        return check(browser, base, overrides)


class LeagueOppPanelRenderTest(unittest.TestCase):
    def test_panel(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        league = source("league.js")
        broken = {
            "row click ignored": league.replace('if (!tr || event.target.closest("button, a, select, input")) return;', "return;", 1),
            "escape ignored": league.replace('if (event.key !== "Escape" || !UI.selectedOpp) return;', "return;", 1),
            "pick dropped on re-render": league.replace("const chosen = UI.selectedOpp ? sorted.find(r => r.id === UI.selectedOpp) : null;", "const chosen = null;", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, league, f"mutation anchor for {name!r} is stale")
                try:
                    caught = run_checks({"league.js": body})
                except Exception as exc:   # a build where the panel never opens times out: that is a catch
                    caught = [f"raised {type(exc).__name__}"]
                self.assertNotEqual(caught, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
