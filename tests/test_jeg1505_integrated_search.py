"""Pure local integration: actual widget functions, optional reader and engine.

The widget's search functions are evaluated verbatim without its DOM/init.
Numerical controls are computed by the existing ValueModel on its committed
worked example, not inferred from 875 universe flags or the reported 741 board.
No browser, server, network, runtime build or full-validation substitute.
"""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from pipelines.build_jeg1505_search_identities import build
from pipelines.lib.searchable_identity_eligibility import build_searchable_identities

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "app/trade-value-chart/assets/jeg1505-search-identities.json"
HARNESS = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const input = JSON.parse(fs.readFileSync(0, 'utf8')), root = process.argv[1];
const inputBefore=JSON.stringify(input);
const source = fs.readFileSync(path.join(root,'app/trade-value-chart/assets/curve-widget.js'),'utf8');
function section(start, end) {
  const a=source.indexOf(start), b=source.indexOf(end,a);
  if (a<0 || b<=a) throw new Error('widget boundary changed');
  return source.slice(a,b);
}
const fixed = JSON.parse(fs.readFileSync(path.join(root,'data/fixtures/current/players.json'))).players;
const doc = JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/value_pipeline_worked_example.json')));
const model = require(path.join(root,'app/trade-value-chart/assets/value-model.js'));
const basePlayers = input.mode === 'worked' ? doc.players : Object.fromEntries(fixed.map(p=>[p.player_key,p]));
const canonicalByKey = new Map(Object.entries(basePlayers).map(([k,p])=>[Number(k),
  {...p,player_key:Number(k),name:p.name,pos:p.pos}]));
const run = players => model.runValuePipeline({setting:doc.setting,players,sources:doc.inputs});
const beforeResult = input.mode === 'worked' ? run(doc.players) : null;
const universe = beforeResult ? Object.entries(beforeResult.rows).map(([k,r])=>({player_key:Number(k),
  name:doc.players[k].name,pos:doc.players[k].pos,values:{ddf_value:r.ddfByVersion.blended.value},
  ddfByVersion:r.ddfByVersion})) : [];
const beforeUniverse = JSON.stringify(universe), beforeCanonical = JSON.stringify([...canonicalByKey]);
const context={canonicalByKey,universe,searchIdentityByKey:new Map(),engineReady:input.ready!==false,
  POSITION_ORDER:['QB','RB','WR','TE'],visibleSourceKeys:()=>['espn','fantasycalc'],
  COMPOSITE_VERSION_KEYS:['ddf_value','ddf_value_charts','ddf_value_projections'],
  buildRow:()=>{throw new Error('legacy materializer must not be called by additional identity tests');}};
vm.createContext(context);
vm.runInContext(section('  const rowCopy = row =>','  // One player\'s row from the pipeline:'),context);
vm.runInContext(section('  let pipelinePlayersCache = null;','  // A source\'s natives this week'),context);
vm.runInContext(section('  // JEG-1505 search-only boundary.','  function rebuildDomain()'),context);
// Copy real public accessor expressions instead of imitating their behavior.
const names=['getAllRows','getPlayer','searchPlayers','resolveSearchIdentity','prepareSearchSelection'];
const lines=names.map(name=>source.split('\n').find(line=>line.trim().startsWith(name+':')));
if(lines.some(line=>!line))throw new Error('missing actual public interface');
vm.runInContext('globalThis.controls={'+lines.join('\n')+'};',context);
const installed=context.installSearchIdentities(input.selection);
let result;
if(input.action==='invariance') {
  const afterPlayers=vm.runInContext('pipelinePlayers()',context);
  result={samePipeline:JSON.stringify(beforeResult)===JSON.stringify(run(afterPlayers)),
    computedKeys:context.controls.getAllRows().map(r=>r.player_key),
    getPlayerSame:universe.every(r=>JSON.stringify(context.controls.getPlayer(r.player_key))===JSON.stringify(vm.runInContext('rowCopy',context)(r)))};
} else if(input.action==='search') {
  result={hits:context.controls.searchPlayers(input.query,{limit:5000}),one:context.controls.getPlayer(input.key)};
} else if(input.action==='resolve') result=input.references.map(r=>context.controls.resolveSearchIdentity(r));
else if(input.action==='prepare') result=context.controls.prepareSearchSelection(input.options);
else if(input.action==='reject') result={accepted:context.installSearchIdentities(input.badSelection)};
else if(input.action==='override' || input.action==='overrideSearch') {
  const text=fs.readFileSync(path.join(root,'app/v2/overrides.js'),'utf8');
  const engine={...context.controls}; if(input.noGetPlayer)delete engine.getPlayer;
  const state={engine,names:{},values:{},selected:null,draft:null,query:input.query||''};
  let editorRow=null;
  const el=(tag,attrs,kids)=>({tag,attrs,children:kids||[],value:attrs?.value||'',
    replaceChildren(...nodes){this.children=nodes;},append(...nodes){this.children.push(...nodes);},addEventListener(){}});
  const editor={S:state,$:()=>null,el,fmt:v=>v===null?'—':String(v),render:()=>{editorRow=vm.runInContext('rowOf(S.selected)',editor);}};
  vm.createContext(editor);
  const a=text.indexOf('  const rows = () =>'),b=text.indexOf('  // The model\'s DDF Value',a);
  vm.runInContext(text.slice(a,b),editor);
  const c=text.indexOf(input.action==='overrideSearch'?'  function renderSearch(box)':'  function select(key, name)'),d=text.indexOf('  // ---------- editor:',c);
  vm.runInContext(text.slice(c,d),editor);
  const hit=context.controls.searchPlayers(input.query,{limit:8})[0];
  if(!hit)throw new Error('missing actual override search hit');
  if(input.action==='overrideSearch') {
    const box=el('section',{},[]); editor.renderSearch(box);
    const flatten=node=>[node,...(node.children||[]).flatMap(flatten)];
    const button=flatten(box).find(node=>node.attrs?.class==='v2-ov-hit');
    if(!button)throw new Error('actual renderSearch produced no hit');
    button.attrs.onclick();
    result={disabled:button.attrs.disabled===true,title:button.attrs.title,selected:state.selected,
      editorRow,metadata:button.children[1].attrs.text};
  } else {
    editor.select(hit.player_key,hit.name);
    result={hit,editorRow,selected:state.selected,selectedName:state.names[state.selected]||null};
  }
}
const afterUniverse=JSON.stringify(universe), afterCanonical=JSON.stringify([...canonicalByKey]);
console.log(JSON.stringify({installed,result,computedUnchanged:beforeUniverse===afterUniverse,
  canonicalUnchanged:beforeCanonical===afterCanonical,computedCount:universe.length,
  inputUnchanged:inputBefore===JSON.stringify(input)}));
"""


def widget(action, **data):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    supplied = {"selection": json.loads(ASSET.read_text()), "action": action, **data}
    proc = subprocess.run(["node", "-e", HARNESS, str(ROOT)], input=json.dumps(supplied),
                          capture_output=True, text=True, check=True, timeout=45)
    return json.loads(proc.stdout)


class IntegratedSearchTest(unittest.TestCase):
    def test_build_is_reproducible_unknown_and_does_not_mutate_source_inputs(self):
        files = [ROOT / p for p in ("data/inputs/players_identity_snapshot.json",
                 "data/inputs/player_platform_spellings.json", "data/fixtures/current/players.json")]
        before = {p: p.read_bytes() for p in files}
        payload = build()
        self.assertEqual(payload, json.loads(ASSET.read_text()))
        self.assertEqual(len(payload["identities"]), 1517)
        self.assertTrue(all(p["eligibility_status"] == "unknown" and p["pricing_status"] == "unknown"
                            for p in payload["identities"]))
        self.assertEqual({p: p.read_bytes() for p in files}, before)
        self.assertEqual({p["from_player_key"] for p in payload["redirect_claims"]}, {4653, 4655, 4660})

    def test_actual_engine_and_computed_rows_are_identical_after_identity_additions(self):
        out = widget("invariance", mode="worked")
        self.assertTrue(out["installed"])
        self.assertGreater(out["computedCount"], 0)
        self.assertTrue(out["result"]["samePipeline"])
        self.assertTrue(out["result"]["getPlayerSame"])
        self.assertTrue(out["computedUnchanged"])
        self.assertTrue(out["canonicalUnchanged"])
        self.assertTrue(out["inputUnchanged"])

    def test_retained_fa_search_and_get_player_use_unknown_values_without_pricing(self):
        out = widget("search", query="Eric Tomlinson", key=33)
        self.assertEqual(len(out["result"]["hits"]), 1)
        row = out["result"]["one"]
        self.assertEqual(row, out["result"]["hits"][0])
        self.assertEqual(row["player_key"], 33)
        self.assertEqual(row["eligibility_status"], "unknown")
        self.assertTrue(row["search_identity_only"])
        self.assertFalse(row["universe_only"])
        self.assertTrue(all(v is None for v in row["values"].values()))
        self.assertTrue(out["computedUnchanged"] and out["canonicalUnchanged"])

    def test_namespace_collision_aiyuk_and_invalid_ids(self):
        references = [{"namespace": "sleeper", "id": "4046"}, {"namespace": "canonical", "id": 4046},
                      {"namespace": "sleeper", "id": "6803"}, {"id": "6803"},
                      {"namespace": "canonical", "id": [568]}]
        out = widget("resolve", references=references)["result"]
        self.assertEqual([r.get("player_key") for r in out[:3]], [3594, 4046, 568])
        self.assertTrue(all(r["status"] == "resolved" for r in out[:3]))
        self.assertTrue(all(r["status"] == "pending" for r in out[3:]))

    def test_resolve_dedupe_and_all_ownership_apply_to_override_additions(self):
        canonical = {"namespace": "canonical", "id": 568}
        provider = {"namespace": "sleeper", "id": "6803"}
        for owner in ("mine", "others"):
            options = {"inputs": [canonical], "overrideAdds": [provider],
                       "ownership": {"complete": True, owner: [provider]}}
            result = widget("prepare", options=options)["result"]
            self.assertEqual(result["resolvedKeys"], [568])
            self.assertEqual(result["duplicates"], 1)
            self.assertEqual(result["excludedOwnership"], [568])
            self.assertEqual(result["wireKeys"], [])
            self.assertFalse(result["readyForPricing"])

    def test_unpriced_unknown_and_incomplete_ownership_stay_pending(self):
        options = {"inputs": [{"namespace": "sleeper", "id": "6803"}],
                   "overrideAdds": [{"namespace": "sleeper", "id": "unknown"}],
                   "ownership": {"complete": True}}
        result = widget("prepare", options=options)["result"]
        self.assertEqual(result["unresolvedKeys"], [568])
        self.assertEqual(result["wireKeys"], [])
        self.assertFalse(result["readyForPricing"])
        self.assertEqual(len(result["pending"]), 1)
        options["ownership"] = {"complete": True, "others": [{"namespace": "sleeper", "id": "unknown"}]}
        self.assertFalse(widget("prepare", options=options)["result"]["ownershipReady"])

    def test_namespace_collision_does_not_filter_a_different_person(self):
        options = {"inputs": [{"namespace": "canonical", "id": 4046}],
                   "overrideAdds": [{"namespace": "sleeper", "id": "4046"}],
                   "ownership": {"complete": True, "others": [{"namespace": "sleeper", "id": "4046"}]}}
        out = widget("prepare", options=options)
        self.assertEqual(out["result"]["resolvedKeys"], [4046, 3594])
        self.assertEqual(out["result"]["excludedOwnership"], [3594])
        self.assertEqual(out["result"]["requestedKeys"], [4046])
        self.assertTrue(out["inputUnchanged"])

    def test_malformed_optional_selection_is_rejected_atomically(self):
        payload = json.loads(ASSET.read_text())
        bad = deepcopy(payload)
        bad["identities"].append(deepcopy(bad["identities"][0]))
        out = widget("reject", badSelection=bad)
        self.assertFalse(out["result"]["accepted"])
        self.assertTrue(out["canonicalUnchanged"] and out["computedUnchanged"] and out["inputUnchanged"])

    def test_wire_keys_come_from_actual_engine_result_only(self):
        options = {"inputs": [{"namespace": "canonical", "id": 101}], "ownership": {"complete": True}}
        out = widget("prepare", mode="worked", options=options)
        self.assertTrue(out["result"]["readyForPricing"])
        self.assertEqual(out["result"]["wireKeys"], [101])
        self.assertTrue(out["canonicalUnchanged"] and out["computedUnchanged"])
        self.assertFalse(widget("prepare", mode="worked", ready=False, options=options)["result"]["readyForPricing"])

    def test_own_roster_unpriced_identity_blocks_priced_candidate(self):
        for reference in ({"namespace": "canonical", "id": 568}, {"namespace": "sleeper", "id": "6803"}):
            with self.subTest(reference=reference):
                options = {"inputs": [{"namespace": "canonical", "id": 101}],
                           "ownership": {"complete": True, "mine": [reference]}}
                result = widget("prepare", mode="worked", options=options)["result"]
                self.assertFalse(result["readyForPricing"])
                self.assertEqual(result["wireKeys"], [])
                self.assertEqual(result["unresolvedOwnKeys"], [568])
                self.assertEqual(result["pricedKeys"], [101])
                self.assertTrue(result["ownershipReady"])
                self.assertEqual(result["pending"], [{"status": "pending", "player_key": 568,
                    "reason": "Own-roster identity has no computed pricing", "boundary": "own_roster_pricing"}])

    def test_other_team_unpriced_identity_is_filtered_without_blocking_priced_candidate(self):
        options = {"inputs": [{"namespace": "canonical", "id": 101}],
                   "overrideAdds": [{"namespace": "sleeper", "id": "6803"}],
                   "ownership": {"complete": True, "others": [{"namespace": "canonical", "id": 568}]}}
        result = widget("prepare", mode="worked", options=options)["result"]
        self.assertTrue(result["readyForPricing"])
        self.assertEqual(result["wireKeys"], [101])
        self.assertEqual(result["excludedOwnership"], [568])
        self.assertEqual(result["unresolvedOwnKeys"], [])
        self.assertEqual(result["pending"], [])

    def test_priced_own_roster_control_does_not_block_priced_candidate(self):
        options = {"inputs": [{"namespace": "canonical", "id": 101}],
                   "ownership": {"complete": True, "mine": [{"namespace": "canonical", "id": 102}]}}
        result = widget("prepare", mode="worked", options=options)["result"]
        self.assertTrue(result["readyForPricing"])
        self.assertEqual(result["wireKeys"], [101])
        self.assertEqual(result["unresolvedOwnKeys"], [])

    def test_override_select_opens_retained_identity_by_canonical_key(self):
        out = widget("override", query="Eric Tomlinson")
        self.assertEqual(out["result"]["selected"], "33")
        self.assertIsNotNone(out["result"]["editorRow"])
        self.assertEqual(out["result"]["editorRow"]["player_key"], 33)
        self.assertEqual(out["result"]["selectedName"], "Eric Tomlinson")
        self.assertTrue(out["computedUnchanged"] and out["canonicalUnchanged"])

    def test_override_lookup_preserves_computed_row_and_name_fallback(self):
        computed = widget("override", mode="worked", query="QB Alpha")
        self.assertEqual(computed["result"]["editorRow"], computed["result"]["hit"])
        self.assertTrue(computed["computedUnchanged"])
        retained = widget("override", query="Eric Tomlinson", noGetPlayer=True)
        self.assertEqual(retained["result"]["editorRow"]["player_key"], 33)

    def test_override_unknown_hit_is_explicitly_pending_and_cannot_trigger_editing(self):
        pending = widget("overrideSearch", query="Eric Tomlinson")["result"]
        self.assertTrue(pending["disabled"])
        self.assertIn("Pending", pending["title"])
        self.assertIn("Pending pricing", pending["metadata"])
        self.assertIsNone(pending["selected"])
        priced = widget("overrideSearch", mode="worked", query="QB Alpha")["result"]
        self.assertFalse(priced["disabled"])
        self.assertEqual(priced["selected"], "101")
        self.assertEqual(priced["editorRow"]["player_key"], 101)

    def test_retirement_and_return_preserve_lookup_key_and_history(self):
        canonical = [{"player_key": 900001, "full_name": "Synthetic Returning Identity", "position": "WR"}]
        retired = {"player_key": 900001, "kind": "retired", "date": "2024-01-01", "source": "https://example.invalid/retired"}
        returned = {"player_key": 900001, "kind": "returned", "date": "2026-01-01", "source": "https://example.invalid/returned"}
        for events, expected in (([], 1), ([retired], 0), ([retired, returned], 1)):
            selection = build_searchable_identities(canonical, {}, events, as_of=date(2026, 11, 4))
            selection["schema"] = "jeg1505-search-identities/1"
            out = widget("search", selection=selection, query="Synthetic Returning Identity", key=900001)
            self.assertEqual(len(out["result"]["hits"]), expected)
            self.assertEqual(out["result"]["one"]["player_key"], 900001)
            self.assertEqual(out["result"]["one"]["lifecycle_history"], events)

    def test_optional_provider_conflict_does_not_hide_a_known_canonical_identity(self):
        identity = {"player_key": 101, "name": "QB Alpha", "pos": "QB", "sleeper_id": None,
                    "eligibility_status": "unknown", "selectable": False,
                    "selection_reason": "Conflicting provider identity", "lifecycle_history": []}
        selection = {"schema": "jeg1505-search-identities/1", "identities": [identity]}
        out = widget("search", mode="worked", selection=selection, query="QB Alpha", key=101)
        self.assertEqual(len(out["result"]["hits"]), 1)
        self.assertTrue(out["computedUnchanged"] and out["canonicalUnchanged"])
        pending = widget("resolve", mode="worked", selection=selection,
                         references=[{"namespace": "canonical", "id": 101}])["result"]
        self.assertEqual(pending[0]["status"], "pending")

    def test_optional_product_reader_is_separate_and_fetch_failure_is_nonfatal(self):
        script = """
const payload=JSON.parse(require('fs').readFileSync(0,'utf8'));
let calls=[];global.fetch=async url=>{calls.push(url);if(payload.fail)throw Error('offline');return {ok:true,json:async()=>payload.selection};};
const P=require(process.argv[1]);
Promise.all([P.getSearchIdentitySelection(),P.getSearchIdentitySelection()]).then(results=>console.log(JSON.stringify({calls,results})));
"""
        for fail in (False, True):
            payload = {"selection": {"schema": "jeg1505-search-identities/1", "identities": []}, "fail": fail}
            out = subprocess.run([shutil.which("node"), "-e", script, str(ROOT / "app/trade-value-chart/assets/product-data.js")],
                                 input=json.dumps(payload), text=True, capture_output=True, check=True, timeout=10)
            data = json.loads(out.stdout)
            self.assertEqual(data["calls"], ["assets/jeg1505-search-identities.json"])
            self.assertEqual(data["results"], [None, None] if fail else [payload["selection"]] * 2)


if __name__ == "__main__":
    unittest.main()
