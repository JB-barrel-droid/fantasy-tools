"""Trade target answer card (JEG-1274): the contract in docs/design/target-answer-card-contract.md, checked in pure Node.

States come only from the supplied output, every value shows exactly as supplied, a real zero stays "0", a missing
value is never 0, identity is stable, input is never mutated, text is escaped, and the module reads no storage, makes
no request and imports no engine. Every guard is proven: test_checks_fail_on_broken_builds copies the module, breaks
one rule at a time, and requires the harness to name the check that catches it.

Run: python3 -m unittest tests.test_target_answer_card_contract
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app" / "v2" / "target-answer-card.js"
CASES = ROOT / "tests" / "fixtures" / "target_answer_card" / "cases.json"

# Pure Node, no browser and no DOM: viewModel() and markup() are pure; mount() is covered by the render test.
HARNESS = r"""
"use strict";
const fs = require("fs");
const C = require(process.argv[2]);
const SRC = fs.readFileSync(process.argv[2], "utf8");
const DATA = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const clone = x => JSON.parse(JSON.stringify(x));
const freeze = x => { if (x && typeof x === "object") { Object.values(x).forEach(freeze); Object.freeze(x); } return x; };
const input = (name, edit) => { const c = Object.assign({fixture: clone(DATA.fixture)}, JSON.parse(JSON.stringify(DATA.cases[name]), (k, v) => v)); if (edit) edit(c); return freeze(c); };
// JSON.stringify turns -0 into 0, so the zero case is re-read from the file to keep its -0.
const raw = name => { const c = JSON.parse(fs.readFileSync(process.argv[3], "utf8")).cases[name]; c.fixture = clone(DATA.fixture); return freeze(c); };
function eq(a, b, what) { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(`${what}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`); }
function ok(v, what) { if (!v) throw new Error(what); }
const html = (vm, open) => C.markup(vm, {uid: "t", open: open || {}});
const ddText = (h, key) => { const m = h.match(new RegExp(`data-key="${key}"><dt>[^<]*</dt><dd[^>]*>([^<]*)</dd>`)); return m ? m[1] : null; };
const supplied = item => typeof item.display === "string" && item.display.trim() ? item.display : (Object.is(item.value, -0) ? "0" : String(item.value));

const checks = {
  test_states_from_supplied_output() {
    const want = {buy: "buy", sell: "sell", fair: "fair", empty: "empty", missing: "missing", unavailable: "unavailable", zero: "sell", long_name: "buy"};
    eq(Object.keys(DATA.cases).sort(), Object.keys(want).sort(), "fixture cases");
    Object.entries(want).forEach(([name, state]) => {
      const vm = C.viewModel(raw(name));
      eq(vm.state, state, `state for ${name}`);
      ok(html(vm).includes(`data-state="${state}"`), `${name} markup carries its state`);
    });
    eq(C.STATES, ["buy", "sell", "fair", "empty", "missing", "unavailable"], "the six states");
    eq(C.viewModel(null).state, "empty", "no input is empty");
    eq(C.viewModel(raw("buy")).sideWord, "Buy", "buy word");
    eq(C.viewModel(raw("sell")).sideWord, "Sell", "sell word");
    eq(C.viewModel(raw("fair")).sideWord, "Fair price", "fair word");
    eq(C.viewModel(raw("unavailable")).message, DATA.cases.unavailable.reason, "unavailable says the supplied reason");
  },
  test_values_exact() {
    ["buy", "sell", "fair", "missing", "zero", "long_name"].forEach(name => {
      const vm = C.viewModel(raw(name));
      const h = html(vm);
      DATA.cases[name].values.forEach((item, i) => {
        if (item.value === null) return;
        eq(vm.values[i].text, supplied(item), `${name}/${item.key} text`);
        eq(ddText(h, item.key), supplied(item), `${name}/${item.key} in the markup`);
        eq(vm.values[i].label, item.label, `${name}/${item.key} label`);
      });
      eq(vm.values.map(v => v.key), DATA.cases[name].values.map(v => v.key), `${name} value order`);
    });
    eq(C.viewModel(raw("buy")).values[2].text, "-4.45", "display string shown verbatim");
    eq(C.viewModel(raw("long_name")).values[0].text, "123.456789", "a number is never rounded");
    eq(C.viewModel(raw("sell")).values[2].text, "+4.75", "a signed display string keeps its sign");
  },
  test_real_zero_stays_zero() {
    const vm = C.viewModel(raw("zero"));
    eq(vm.values.map(v => v.text), ["0", "5.5", "0"], "0 and -0 show as 0");
    ok(vm.values.every(v => !v.isMissing), "a real zero is not missing");
    eq(vm.sources[0].text, "0", "a source at its waiver line shows its 0");
    eq(C.viewModel(raw("fair")).values[2].text, "0", "a zero gap shows 0");
    const h = html(vm, {sources: true});
    eq(ddText(h, "ours"), "0", "zero in the markup");
    ok(h.includes('data-value="0"'), "zero kept as the raw value");
    eq(C.valueText({value: 0}), "0", "valueText(0)");
    eq(C.valueText({value: 0, display: "0.0"}), "0.0", "display 0.0 verbatim");
  },
  test_missing_never_zero() {
    const vm = C.viewModel(raw("missing"));
    eq(vm.values[0].text, "No value", "missing value says No value");
    ok(vm.values[0].isMissing, "missing flag");
    eq(vm.values[0].reason, DATA.cases.missing.values[0].reason, "missing reason passed through");
    eq(vm.missing, DATA.cases.missing.missing, "missing reasons passed through");
    eq(C.valueText({value: null}), null, "null has no text");
    eq(C.valueText({value: NaN}), null, "NaN has no text");
    eq(C.valueText({}), null, "absent has no text");
    const bad = C.viewModel(input("buy", c => { c.values[0].value = "12"; }));
    eq(bad.values[0].text, "No value", "a non-number is never shown as a number");
    ok(bad.problems.length > 0, "a non-number is reported");
    const src = C.viewModel(raw("buy")).sources;
    eq(src.map(s => s.text), ["10.4", "9.1", null, null], "unpriced sources show no number");
    eq(src[2].reason, "Not on Synthetic Chart C's chart", "missing source reason");
    eq(src[3].reason, "held this week (data check)", "unavailable source reason");
  },
  test_identity_stable() {
    ["buy", "sell", "fair", "missing", "zero", "long_name"].forEach(name => {
      const p = DATA.cases[name].player;
      const vm = C.viewModel(raw(name));
      eq(vm.player, {id: p.id, name: p.name, pos: p.pos, team: p.team}, `${name} identity`);
      ok(html(vm).includes(`data-player-id="${p.id}"`), `${name} carries its id`);
    });
    const long = DATA.cases.long_name.player.name;
    ok(html(C.viewModel(raw("long_name"))).includes(`>${long}</h3>`), "a long name is shown whole");
    const renamed = C.viewModel(input("buy", c => { c.player.name = "Synthetic Receiver Alpha Renamed"; }));
    eq(renamed.player.id, DATA.cases.buy.player.id, "the id, not the name, is the identity");
  },
  test_no_identity_is_missing() {
    eq(C.viewModel(input("buy", c => { c.player = {name: "No Id"}; })).state, "missing", "no id");
    eq(C.viewModel(input("buy", c => { c.player = {id: "syn-x"}; })).state, "missing", "no name");
    eq(C.viewModel(input("buy", c => { c.player = null; })).state, "missing", "no player");
  },
  test_unknown_answer_is_missing() {
    eq(C.viewModel(input("buy", c => { c.answer.side = "hold"; })).state, "missing", "unknown side");
    eq(C.viewModel(input("buy", c => { c.status = "maybe"; })).state, "missing", "unknown status");
    eq(C.viewModel(input("buy", c => { c.sources[0].status = "guess"; })).sources[0].status, "missing", "unknown source status is not priced");
  },
  test_reasons_and_sources_pass_through() {
    ["buy", "sell", "fair", "zero", "long_name"].forEach(name => {
      const vm = C.viewModel(raw(name));
      eq(vm.reasons, DATA.cases[name].answer.reasons, `${name} reasons, in order`);
      eq(vm.sources.map(s => [s.key, s.name, s.status]), DATA.cases[name].sources.map(s => [s.key, s.name, s.status]), `${name} sources, in order`);
    });
  },
  test_input_not_mutated() {
    Object.keys(DATA.cases).forEach(name => {
      const c = Object.assign({fixture: clone(DATA.fixture)}, clone(DATA.cases[name]));
      const before = JSON.stringify(c);
      const vm = C.viewModel(c);
      C.markup(vm, {uid: "t", open: {sources: true, detail: true}});
      eq(JSON.stringify(c), before, `${name} input unchanged`);
      C.markup(C.viewModel(raw(name)), {uid: "t", open: {sources: true, detail: true}});   // frozen: a write would throw
    });
    const d = raw("buy");
    eq(C.viewModel(d).detail === d.detail, true, "the detail is handed to the slot as supplied, not copied or changed");
  },
  test_escaping() {
    const h = html(C.viewModel(input("buy", c => { c.player.name = '<img src=x onerror="alert(1)">'; c.answer.reasons = ["a & b <b>"]; })));
    ok(!h.includes("<img"), "markup in a name is escaped");
    ok(h.includes("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"), "escaped name shown");
    ok(h.includes("a &amp; b &lt;b&gt;"), "escaped reason shown");
    // Every other supplied string reaches innerHTML through esc() too.
    const X = "<i>x</i>", EX = "&lt;i&gt;x&lt;/i&gt;";
    const every = input("buy", c => {
      c.player.pos = X; c.player.team = X; c.fixture.label = X;
      c.values[0].label = X; c.values[1].display = X; c.values.push({key: "nil", label: "Nil", value: null, reason: X});
      c.sources[0].name = X; c.sources[2].reason = X; c.sources[0].display = X;
    });
    const all = C.markup(C.viewModel(every), {uid: "t", open: {sources: true}});
    ok(!all.includes("<i>"), "no supplied markup survives: " + all.slice(0, 200));
    eq((all.match(/&lt;i&gt;x&lt;\/i&gt;/g) || []).length, 9, "every probed field shown escaped");
    ["empty", "unavailable", "missing"].forEach(name => {
      const m = C.markup(C.viewModel(input(name, c => { c.message = X; c.reason = X; c.missing = [X]; })), {uid: "t"});
      ok(!m.includes("<i>") && m.includes(EX), `${name} message and reasons escaped`);
    });
    const lab = C.markup(C.viewModel(raw("buy"), {buy: X, sources: X}), {uid: "t", labels: {sources: X}});
    ok(!lab.includes("<i>") && lab.includes(EX), "caller labels escaped");
  },
  test_disclosures_closed_by_default() {
    const h = html(C.viewModel(raw("buy")));
    eq((h.match(/aria-expanded="false"/g) || []).length, 2, "two closed toggles");
    eq((h.match(/class="tac-panel" id="[^"]+" hidden/g) || []).length, 2, "two hidden panels");
    const o = html(C.viewModel(raw("buy")), {sources: true, detail: true});
    eq((o.match(/aria-expanded="true"/g) || []).length, 2, "open toggles");
    ok(!/ hidden>/.test(o), "open panels are not hidden");
    ok(h.includes('aria-controls="t-sources"') && h.includes('id="t-sources"'), "toggle controls its panel");
    ok(h.includes('class="tac-detail-slot"'), "the detail slot is present");
    ok(!html(C.viewModel(raw("fair"))).includes("tac-detail-slot"), "no detail supplied, no slot");
    ok(!html(C.viewModel(raw("missing"))).includes('data-tac-toggle="detail"'), "missing case has no detail toggle");
  },
  test_fixture_labelled() {
    Object.keys(DATA.cases).forEach(name => ok(html(C.viewModel(raw(name))).includes(`<p class="tac-fixture">${DATA.fixture.label}</p>`), `${name} shows the synthetic label`));
    ok(/synthetic/i.test(DATA.fixture.label), "the label says synthetic");
    const json = JSON.stringify(DATA.cases);
    ok(!/"name":"(?!Synthetic)/.test(json), "every name in the fixture is synthetic");
  },
  test_labels_injectable() {
    const vm = C.viewModel(raw("buy"), {buy: "Target"});
    eq(vm.sideWord, "Target", "a caller's word replaces the placeholder");
    eq(C.viewModel(raw("buy")).sideWord, "Buy", "default unchanged");
    ok(Object.isFrozen(C.LABELS), "defaults are frozen");
  },
  test_no_storage_network_engine() {
    const code = SRC.replace(/\/\/[^\n]*/g, "");
    ["localStorage", "sessionStorage", "indexedDB", "fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "import(", "require(",
     "TradeValueTargets", "TradeValueCurve", "Math."].forEach(word => ok(!code.includes(word), `module uses ${word}`));
  },
};

const result = {};
for (const [name, fn] of Object.entries(checks)) {
  try { fn(); result[name] = true; } catch (e) { result[name] = String(e && e.message || e); }
}
process.stdout.write(JSON.stringify(result));
"""

REQUIRED = [
    "test_states_from_supplied_output", "test_values_exact", "test_real_zero_stays_zero", "test_missing_never_zero",
    "test_identity_stable", "test_no_identity_is_missing", "test_unknown_answer_is_missing",
    "test_reasons_and_sources_pass_through", "test_input_not_mutated", "test_escaping", "test_disclosures_closed_by_default",
    "test_fixture_labelled", "test_labels_injectable", "test_no_storage_network_engine",
]

# (what is broken, old text, new text, the check that must catch it)
MUTATIONS = [
    ("zero dropped", 'if (finite(item.value)) return Object.is(item.value, -0) ? "0" : String(item.value);',
     'if (item.value) return String(item.value);', "test_real_zero_stays_zero"),
    ("missing shown as zero", "text: text === null ? labels.noValue : text,", 'text: text === null ? "0" : text,', "test_missing_never_zero"),
    ("numbers rounded", 'Object.is(item.value, -0) ? "0" : String(item.value)', 'item.value.toFixed(1)', "test_values_exact"),
    ("display ignored", "if (str(item.display)) return item.display;", "", "test_values_exact"),
    ("identity not required", 'if (!player || problems.includes("unknown status")', 'if (problems.includes("unknown status")', "test_no_identity_is_missing"),
    ("unknown side accepted", '|| !SIDES.includes(side)) {', ') {', "test_unknown_answer_is_missing"),
    ("input reordered", "vm.reasons = (Array.isArray(c.answer.reasons) ? c.answer.reasons : [])",
     "vm.reasons = (Array.isArray(c.answer.reasons) ? c.answer.reasons.reverse() : [])", "test_input_not_mutated"),
    ("sources re-sorted", "return (Array.isArray(list) ? list : []).map((item, i) => {\n      const key = str(item && item.key) || `source-",
     "return (Array.isArray(list) ? list.slice().sort((a, b) => String(a.name).localeCompare(String(b.name))) : []).map((item, i) => {\n      const key = str(item && item.key) || `source-",
     "test_reasons_and_sources_pass_through"),
    ("escaping removed", "const esc = v => String(v).replace(", "const esc = v => String(v); const _unused = v => String(v).replace(", "test_escaping"),
    ("value label unescaped", "<dt>${esc(v.label)}</dt>", "<dt>${v.label}</dt>", "test_escaping"),
    ("message unescaped", '<p class="tac-message">${esc(vm.message)}</p>', '<p class="tac-message">${vm.message}</p>', "test_escaping"),
    ("source reason unescaped", '(s.reason ? `<span class="tac-reason">${esc(s.reason)}</span>` : "")', '(s.reason ? `<span class="tac-reason">${s.reason}</span>` : "")', "test_escaping"),
    ("panels open by default", '${open ? "" : " hidden"}', "", "test_disclosures_closed_by_default"),
    ("fixture label dropped", "if (vm.fixture) out.push(", "if (false) out.push(", "test_fixture_labelled"),
    ("storage read", "function render() {", 'function render() { try { localStorage.getItem("tac"); } catch (e) {}', "test_no_storage_network_engine"),
]


def run_harness(module: Path) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "harness.cjs"
        script.write_text(HARNESS, encoding="utf-8")
        out = subprocess.run(["node", str(script), str(module), str(CASES)], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise AssertionError(f"harness crashed: {out.stderr[-1500:]}")
    return json.loads(out.stdout)


class TargetAnswerCardContractTest(unittest.TestCase):
    def test_every_check_passes(self):
        result = run_harness(MODULE)
        self.assertEqual(sorted(result), sorted(REQUIRED), "harness checks and REQUIRED drifted")
        failed = {k: v for k, v in result.items() if v is not True}
        self.assertEqual(failed, {})

    def test_checks_fail_on_broken_builds(self):
        source = MODULE.read_text(encoding="utf-8")
        for what, old, new, check in MUTATIONS:
            with self.subTest(what):
                self.assertEqual(source.count(old), 1, f"mutation anchor for {what!r} must appear exactly once")
                with tempfile.TemporaryDirectory() as tmp:
                    broken = Path(tmp) / "target-answer-card.js"
                    broken.write_text(source.replace(old, new), encoding="utf-8")
                    result = run_harness(broken)
                self.assertIsNot(result.get(check), True, f"{check} did not catch: {what}")

    def test_fixture_cases_cover_every_state(self):
        data = json.loads(CASES.read_text(encoding="utf-8"))
        self.assertIn("synthetic", data["fixture"]["label"].lower())
        self.assertTrue({"buy", "sell", "fair", "empty", "missing", "unavailable"} <= set(data["cases"]))


if __name__ == "__main__":
    unittest.main()
