"""JEG-1271: contract of the isolated Compare evidence view (app/v2/compare-evidence-view.js). No browser.

Runs the component's pure layers (adapt, tree, texts) in Node against the synthetic fixtures in
tests/fixtures/compare_evidence_view/cases.json and requires:

1. Fixtures are current outputs. Each case's verdict, evidence rows and againstKeys equal what the current
   trade.js (dealRead, compareTrade, tradeVerdict) returns for its synthetic give/receive rows, and the cases
   cover every verdict branch the brief names (reads, a split, both incomplete kinds) and every evidence state
   (complete, zero, missing, held, conflicting). trade.js is read here only; the component never loads it.
2. Nothing new on screen. Every text node the view renders is an input string, a number in the exact v2.js
   fmtGap/fmt format (checked against the functions extracted from v2.js), or one of the listed separators.
   Every net, total and label in the tree equals the input's.
3. Inputs stay unchanged. adapt and tree run on deep-frozen input in strict mode, and the JSON is identical after.
4. Source categories stay distinct (JEG-1212). Groups render in input order with the same markup; nothing totals
   across them and nothing marks a winner; a series named in two groups is refused.
5. Contract guards. Missing copy, an unlabelled synthetic input, a missing net shown as 0, a held row without a
   reason and duplicate ids are each refused, and the module reads no engine, storage, network, route or share API.
Discrimination: test_mutations_are_caught runs the same checks on broken copies of the module.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app" / "v2" / "compare-evidence-view.js"
TRADE = ROOT / "app" / "v2" / "trade.js"
V2 = ROOT / "app" / "v2" / "v2.js"
CASES = ROOT / "tests" / "fixtures" / "compare_evidence_view" / "cases.json"

CHECK = r"""
"use strict";
const [modulePath, tradePath, casesPath, fmtGapSrc, fmtSrc] = process.argv.slice(1);
const V = require(modulePath);
const TC = require(tradePath);
const data = require(casesPath);
const problems = [];
const bad = message => problems.push(message);
const deepFreeze = o => { if (o && typeof o === "object" && !Object.isFrozen(o)) { Object.values(o).forEach(deepFreeze); Object.freeze(o); } return o; };
const plain = x => JSON.parse(JSON.stringify(x));
const refGap = eval(`(${fmtGapSrc})`);
const refFmt = eval(`(${fmtSrc})`);
const EVIDENCE = ["usatoday", "fantasypros", "cbs", "fantasycalc", "espn", "cbsros", "razzball"];

// Formatting parity with v2.js.
[0, -0, 0.04, -0.04, 0.05, -0.05, 0.06, -0.06, 1, -1, 7.25, -7.25, 123.456, -0.000001, NaN, null, Infinity].forEach(n => {
  if (V.format.gap(n) !== refGap(n)) bad(`fmtGap(${n}) ${V.format.gap(n)} != v2.js ${refGap(n)}`);
  if (V.format.value(n) !== refFmt(n)) bad(`fmt(${n}) ${V.format.value(n)} != v2.js ${refFmt(n)}`);
});

function strings(o, out) {
  if (typeof o === "string") out.add(o);
  else if (o && typeof o === "object") Object.values(o).forEach(v => strings(v, out));
  return out;
}
function numbers(o, out) {
  if (typeof o === "number") { out.add(V.format.gap(o)); out.add(V.format.value(o)); }
  else if (o && typeof o === "object") Object.values(o).forEach(v => numbers(v, out));
  return out;
}
const find = (node, pred, out = []) => { if (!("text" in node)) { if (pred(node)) out.push(node); node.children.forEach(c => find(c, pred, out)); } return out; };
const text = node => V.texts(node).join("");
const cls = name => node => (node.attrs.class || "").split(" ").includes(name);

const seen = {kinds: new Set(), states: new Set(), split: false, tooFew: false, valueMissing: false, cells: new Set()};
data.cases.forEach(c => {
  const tag = `[${c.id}]`;
  if (c.input.synthetic !== true || !c.input.syntheticLabel) bad(`${tag} fixture is not visibly synthetic`);
  // 1. The fixture's outputs are what the current trade.js returns.
  const deal = plain(TC.dealRead(c.give, c.receive, c.chartKeys));
  if (JSON.stringify(deal) !== JSON.stringify(c.input.verdict)) bad(`${tag} verdict differs from trade.js dealRead`);
  const rows = TC.compareTrade(c.give, c.receive, ["ddf_value"].concat(EVIDENCE)).rows;
  const against = TC.tradeVerdict(rows, "ddf_value").againstKeys || [];
  if (JSON.stringify(against) !== JSON.stringify(c.input.againstKeys)) bad(`${tag} againstKeys differ from trade.js tradeVerdict`);
  c.input.groups.forEach(g => g.rows.forEach(r => {
    const ref = rows.find(x => x.key === r.key);
    if (r.held) { if (r.net !== null || !c.heldKeys.includes(r.key)) bad(`${tag} held ${r.key} carries a net or is not a held key`); return; }
    if (ref.net !== r.net || ref.give !== r.give || ref.receive !== r.receive) bad(`${tag} ${r.key} totals differ from trade.js compareTrade`);
    if (JSON.stringify(ref.missing.map(m => m.row.name)) !== JSON.stringify(r.missing.map(m => m.row.name))) bad(`${tag} ${r.key} missing players differ`);
  }));

  // 3. Frozen input: strict-mode adapt/tree would throw on any write; JSON must be unchanged too.
  const before = JSON.stringify(c.input);
  const frozen = deepFreeze(plain(c.input));
  let model, tree;
  try { model = V.adapt(frozen); tree = V.tree(model, {open: new Set(c.input.disclosures.map(d => d.id))}); }
  catch (e) { bad(`${tag} adapt/tree threw on frozen input: ${e.message}`); return; }
  if (JSON.stringify(frozen) !== before) bad(`${tag} input changed`);

  // 2. Every text node is an input string, a formatted input number or a separator.
  const allowed = new Set([...strings(c.input, new Set()), ...numbers(c.input, new Set()), ...V.SEPARATORS]);
  V.texts(tree).forEach(t => { if (!allowed.has(t)) bad(`${tag} new text on screen: ${JSON.stringify(t)}`); });
  if (!V.texts(tree).includes(c.input.syntheticLabel)) bad(`${tag} synthetic label not rendered`);

  // Verdict reads the same as v2.js renderDeal.
  const v = c.input.verdict;
  seen.kinds.add(v.kind);
  if (v.kind === "read") seen.cells.add(v.cell);
  const titleNode = find(tree, cls("cev-verdict-title"))[0];
  if (v.kind === "read") {
    const want = v.title.toLowerCase().includes(v.action.toLowerCase()) ? v.title : `${v.title}: ${v.action}`;
    if (!titleNode || text(titleNode) !== want) bad(`${tag} verdict title ${titleNode && text(titleNode)} != ${want}`);
  } else if (titleNode) bad(`${tag} incomplete verdict shows a title`);
  const vText = find(tree, cls("cev-verdict-text"))[0];
  if (!vText || text(vText) !== v.text) bad(`${tag} verdict text changed`);
  const prod = find(tree, cls("cev-verdict-production"))[0];
  if ((v.production || null) !== (prod ? text(prod) : null)) bad(`${tag} production line changed`);
  const words = c.input.copy.sideWords;
  c.input.nets.forEach(spec => {
    const n = v[spec.id];
    const li = find(tree, node => node.attrs["data-net"] === spec.id)[0];
    const shown = text(find(li, cls("cev-net-value"))[0]);
    const want = n.net === null ? (n.tooFew ? c.input.copy.tooFewCharts : c.input.copy.missingValue)
      : n.split ? `${refGap(n.net)} · ${c.input.copy.chartsSplit} (${refGap(n.charts.min)} ${c.input.copy.rangeJoin} ${refGap(n.charts.max)})`
        : `${refGap(n.net)} · ${words[n.side]}`;
    if (shown !== want) bad(`${tag} net ${spec.id} shows ${shown}, want ${want}`);
    if (text(find(li, cls("cev-net-name"))[0]) !== spec.name) bad(`${tag} net ${spec.id} name changed`);
    if (n.split) seen.split = true;
    if (n.tooFew) seen.tooFew = true;
    if (spec.id === "value" && n.net === null) seen.valueMissing = true;
  });

  // Evidence rows: state, number and labels equal the input.
  const groups = find(tree, cls("cev-group"));
  if (JSON.stringify(groups.map(g => g.attrs["data-group"])) !== JSON.stringify(c.input.groups.map(g => g.id))) bad(`${tag} group order changed`);
  groups.forEach(g => {
    const attrs = Object.keys(g.attrs).sort().join(",");
    if (attrs !== "aria-labelledby,class,data-group" || g.attrs.class !== "cev-group") bad(`${tag} group ${g.attrs["data-group"]} is styled differently (${attrs} ${g.attrs.class})`);
  });
  c.input.groups.forEach(group => {
    const g = groups.find(x => x.attrs["data-group"] === group.id);
    if (!g) { bad(`${tag} group ${group.id} not rendered`); return; }
    if (text(find(g, cls("cev-group-label"))[0]) !== group.label) bad(`${tag} group ${group.id} label changed`);
    group.rows.forEach(r => {
      const li = find(g, node => node.attrs["data-series"] === r.key)[0];
      if (!li) { bad(`${tag} ${r.key} not rendered in ${group.id}`); return; }
      const state = li.attrs["data-state"];
      const want = r.held ? "held" : r.net === null ? "missing" : r.net === 0 ? "zero" : "complete";
      if (state !== want) bad(`${tag} ${r.key} state ${state}, want ${want}`);
      seen.states.add(state);
      const conflicting = li.attrs["data-conflicting"] === "true";
      if (conflicting !== (want === "complete" && c.input.againstKeys.includes(r.key))) bad(`${tag} ${r.key} conflicting flag wrong`);
      if (conflicting) seen.states.add("conflicting");
      if (text(find(li, cls("cev-row-name"))[0]) !== r.label) bad(`${tag} ${r.key} label changed`);
      const value = text(find(li, cls("cev-row-value"))[0]);
      const wantValue = r.held ? c.input.copy.held : r.net === null ? c.input.copy.missingValue : refGap(r.net);
      if (value !== wantValue) bad(`${tag} ${r.key} shows ${value}, want ${wantValue}`);
      const detail = text(find(li, cls("cev-row-detail"))[0]);
      if (r.held && detail !== r.held.reason) bad(`${tag} ${r.key} hold reason changed`);
      if (!r.held && r.net === null && detail !== r.missing.map(m => `${m.row.name} ${c.input.copy.noValue}`).join(", ")) bad(`${tag} ${r.key} missing players not named`);
      if (r.net !== null && detail !== `${c.input.copy.give} ${refFmt(r.give)} · ${c.input.copy.receive} ${refFmt(r.receive)}`) bad(`${tag} ${r.key} totals changed: ${detail}`);
      if (r.net === 0 && value !== "0.0") bad(`${tag} real zero not shown as 0.0`);
      // By position: each label comes from its own copy key (JEG-1294), not merely from some input string.
      const dirNode = find(li, cls("cev-row-direction"))[0];
      if (r.net !== null && !r.held) {
        const dir = refGap(r.net) === "0.0" ? "even" : r.net > 0 ? "up" : "down";
        if (!dirNode || text(dirNode) !== c.input.copy.directions[dir]) bad(`${tag} ${r.key} direction label is not copy.directions.${dir}`);
      } else if (dirNode) bad(`${tag} ${r.key} has a direction label without a number`);
      const flag = find(li, cls("cev-row-flag"))[0];
      if (conflicting ? !flag || text(flag) !== c.input.copy.conflicting : Boolean(flag)) bad(`${tag} ${r.key} conflicting label is not copy.conflicting`);
    });
  });
  // 4. No aggregate across groups and no winner mark anywhere.
  if (find(tree, node => /winner|best|preferred|recommend|primary/i.test(node.attrs.class || "") || Object.keys(node.attrs).some(a => /winner|best|preferred|rank/i.test(a))).length) bad(`${tag} a node is marked as a winner`);

  // Disclosures: button + controlled region, ids line up.
  c.input.disclosures.forEach(d => {
    const box = find(tree, node => node.attrs["data-disclosure"] === d.id)[0];
    const [button, panel] = box.children;
    if (button.tag !== "button" || button.attrs["aria-controls"] !== panel.attrs.id || panel.attrs["aria-labelledby"] !== button.attrs.id) bad(`${tag} disclosure ${d.id} ARIA wiring`);
    if (text(button) !== d.summary || V.texts(panel).join("|") !== d.lines.join("|")) bad(`${tag} disclosure ${d.id} text changed`);
  });
  const closed = V.tree(model, {open: new Set()});
  find(closed, cls("cev-disclosure-toggle")).forEach(b => { if (b.attrs["aria-expanded"] !== "false") bad(`${tag} closed disclosure says expanded`); });
  find(closed, cls("cev-disclosure-panel")).forEach(p => { if (p.attrs.hidden !== "") bad(`${tag} closed panel not hidden`); });
  const slot = find(tree, node => node.attrs["data-cev-slot"] === "readout");
  if (slot.length !== 1 || slot[0].children.length) bad(`${tag} readout slot must be one empty opaque slot`);
});
["read", "incomplete"].forEach(k => { if (!seen.kinds.has(k)) bad(`no fixture for verdict kind ${k}`); });
["complete", "zero", "missing", "held", "conflicting"].forEach(s => { if (!seen.states.has(s)) bad(`no fixture for evidence state ${s}`); });
if (!seen.split) bad("no split-charts fixture");
if (!seen.tooFew) bad("no too-few-charts fixture");
if (!seen.valueMissing) bad("no missing DDF Value fixture");
if (seen.cells.size < 5) bad(`only ${seen.cells.size} deal-read cells covered`);

// 2b. Altered copy (JEG-1294): prefix every caller-supplied word and require each rendered word to follow,
// node by node. A literal equal to today's copy, or a word taken from another key, does not follow.
const ALT = "\u00abalt\u00bb ";
const alterAll = o => typeof o === "string" ? (o ? ALT + o : o) : Array.isArray(o) ? o.map(alterAll)
  : o && typeof o === "object" ? Object.fromEntries(Object.entries(o).map(([k, v]) => [k, alterAll(v)])) : o;
const WORDS = ["copy", "syntheticLabel", "nets", "explanation", "disclosures"];
data.cases.forEach(c => {
  const tag = `[${c.id} altered]`;
  const alt = plain(c.input);
  WORDS.forEach(k => { alt[k] = alterAll(alt[k]); });
  ["id"].forEach(() => { alt.nets = alt.nets.map((n, i) => ({...n, id: c.input.nets[i].id})); alt.disclosures = alt.disclosures.map((d, i) => ({...d, id: c.input.disclosures[i].id})); });
  alt.groups = alt.groups.map(g => ({...g, label: ALT + g.label, rows: g.rows.map(r => ({...r, label: ALT + r.label,
    held: r.held ? {reason: ALT + r.held.reason} : r.held, missing: r.missing.map(m => ({...m, row: {...m.row, name: ALT + m.row.name}}))}))}));
  ["title", "action", "text", "production"].forEach(k => { if (typeof alt.verdict[k] === "string" && alt.verdict[k]) alt.verdict[k] = ALT + alt.verdict[k]; });
  let a, b;
  try { a = V.texts(V.tree(V.adapt(deepFreeze(plain(c.input))), {open: new Set(), idBase: "x"})); b = V.texts(V.tree(V.adapt(deepFreeze(alt)), {open: new Set(), idBase: "x"})); }
  catch (e) { bad(`${tag} threw: ${e.message}`); return; }
  if (a.length !== b.length) { bad(`${tag} structure changed with the words (${a.length} vs ${b.length} text nodes)`); return; }
  const fixed = new Set([...numbers(c.input, new Set()), ...V.SEPARATORS]);
  a.forEach((t, i) => {
    const follows = b[i] === ALT + t || (b[i] === t && fixed.has(t));
    if (!follows) bad(`${tag} text node ${i} ${JSON.stringify(t)} did not follow its input (got ${JSON.stringify(b[i])})`);
  });
});

// Two direct tree() calls (the JEG-1274 reuse path) never share an id.
{
  const m = V.adapt(deepFreeze(plain(data.cases[0].input)));
  const ids = t => find(t, n => Boolean(n.attrs.id)).map(n => n.attrs.id);
  const one = ids(V.tree(m)), two = ids(V.tree(m));
  if (!one.length || one.some(id => two.includes(id))) bad("two tree() calls without idBase share ids");
}

// 5. Contract guards.
const base = data.cases[0].input;
const refuse = (label, mutate) => {
  const copy = plain(base);
  mutate(copy);
  try { V.adapt(deepFreeze(copy)); bad(`accepted: ${label}`); } catch (e) { /* refused, as required */ }
};
refuse("missing copy key", i => { delete i.copy.held; });
refuse("synthetic without a label", i => { i.syntheticLabel = ""; });
refuse("synthetic left unstated", i => { delete i.synthetic; });
refuse("missing net shown without missing players", i => { i.groups[0].rows[0].net = null; i.groups[0].rows[0].missing = []; });
refuse("held row without a reason", i => { i.groups[0].rows[0].held = {}; });
refuse("series in two groups", i => { i.groups[1].rows.push(plain(i.groups[0].rows[0])); });
refuse("duplicate group id", i => { i.groups[1].id = i.groups[0].id; });
refuse("duplicate disclosure id", i => { i.disclosures[1].id = i.disclosures[0].id; });
refuse("unknown verdict kind", i => { i.verdict.kind = "maybe"; });
refuse("net as text", i => { i.verdict.value.net = "4"; });
refuse("copy string null", i => { i.copy.noValue = null; });
refuse("copy string empty", i => { i.copy.conflicting = ""; });
refuse("sideWords not an object", i => { i.copy.sideWords = "You win"; });
refuse("null group", i => { i.groups[1] = null; });
refuse("null row", i => { i.groups[0].rows[0] = null; });
refuse("group id not a slug", i => { i.groups[0].id = "a b"; });
refuse("null disclosure", i => { i.disclosures[0] = null; });
console.log(JSON.stringify(problems));
"""


def node_available() -> bool:
    return shutil.which("node") is not None


def _fn_source(text: str, name: str) -> str:
    """The arrow function `const name = x => { ... };` from v2.js, as source (braces matched)."""
    head = f"  const {name} = "
    at = text.find(head)
    if at < 0:
        raise AssertionError(f"{name} not found in v2.js")
    begin = at + len(head)
    depth, i = 0, text.index("{", begin)
    while True:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[begin:i + 1]
        i += 1


def run_checks(module_text: str | None = None) -> list[str]:
    v2 = V2.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        module = MODULE
        if module_text is not None:
            module = Path(tmp) / "compare-evidence-view.js"
            module.write_text(module_text, encoding="utf-8")
        proc = subprocess.run(["node", "-e", CHECK, str(module), str(TRADE), str(CASES), _fn_source(v2, "fmtGap"), _fn_source(v2, "fmt")],
                              capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        return [f"node failed: {proc.stderr.strip()[-2000:]}"]
    return json.loads(proc.stdout.strip().splitlines()[-1])


@unittest.skipUnless(node_available(), "node is required")
class CompareEvidenceViewContractTest(unittest.TestCase):
    def test_contract(self):
        self.assertEqual([], run_checks())

    def test_module_reads_no_engine_storage_network_route_or_share_api(self):
        src = MODULE.read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/|//[^\n]*", "", src, flags=re.S)
        for banned in ("TradeValueTrade", "TradeValueCurveControls", "TradeValueFinder", "TradeValueLeague", "TradeValueTargets",
                       "DDFSourceViews", "localStorage", "sessionStorage", "fetch(", "XMLHttpRequest", "location", "history.",
                       "require(", "import ", "ddf-state", "DDFState", "dealRead", "compareTrade", "tradeVerdict"):
            self.assertFalse(banned in code, f"compare-evidence-view.js uses {banned}")

    def test_fixtures_are_visibly_synthetic(self):
        data = json.loads(CASES.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["cases"]), 8)
        for case in data["cases"]:
            self.assertIs(case["input"]["synthetic"], True, case["id"])
            self.assertTrue(case["input"]["syntheticLabel"].startswith("Synthetic"), case["id"])
            for side in ("give", "receive"):
                for player in case[side]:
                    self.assertTrue(player["name"].startswith("Synthetic"), (case["id"], player["name"]))

    def test_mutations_are_caught(self):
        src = MODULE.read_text(encoding="utf-8")
        mutants = {
            "missing net shown as zero": ('return [tx(n.tooFew ? copy.tooFewCharts : copy.missingValue)];', 'return [tx(n.tooFew ? copy.tooFewCharts : "0.0")];'),
            "new copy in a row": ('[tx(copy.held)]', '[tx("Held back")]'),
            "rounded differently": ('const text = Math.abs(gap).toFixed(1);', 'const text = Math.abs(gap).toFixed(2);'),
            "input written": ('need(Array.isArray(input.groups) && input.groups.length > 0, "groups are required");',
                              'need(Array.isArray(input.groups) && input.groups.length > 0, "groups are required"); input.groups.reverse();'),
            "zero treated as missing": ('if (row.net === null) {\n      need(missing.length > 0', 'if (!row.net) {\n      need(true'),
            "groups merged": ('model.groups.map(g => evidenceGroupTree(g, copy, idBase))', '[evidenceGroupTree({id: "all", label: model.groups[0].label, note: null, rows: model.groups.flatMap(g => g.rows)}, copy, idBase)]'),
            # JEG-1294 reviewer mutants: a literal equal to today's copy, and another key's word.
            "hard-coded conflicting label": ('[tx(copy.conflicting)]', '[tx("Sees the trade the other way")]'),
            "even label from another key": ('return {cls: "even", label: copy.directions.even};', 'return {cls: "even", label: "Even"};'),
            "even label from the wrong copy key": ('return {cls: "even", label: copy.directions.even};', 'return {cls: "even", label: copy.sideWords.even};'),
            "title rule changed": ('? [deal.title] : [deal.title, deal.action]', '? [deal.title, deal.action] : [deal.title]'),
        }
        for label, (old, new) in mutants.items():
            with self.subTest(label):
                self.assertTrue(old in src, f"anchor missing for {label}")
                self.assertNotEqual([], run_checks(src.replace(old, new, 1)), label)


if __name__ == "__main__":
    unittest.main()
