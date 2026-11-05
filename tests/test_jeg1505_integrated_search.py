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
import ast
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import urljoin

from pipelines.build_jeg1505_search_identities import build, write_snapshot
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
  searchIdentityRevision:0,position:input.position||'ALL',scoring:'ppr',teams:12,viewMode:'indexed',
  VIEW_MODE_DEFS:{},lockOrder:null,benchShare:0.15,activeSourceKeys:()=>[],
  POSITION_ORDER:['QB','RB','WR','TE'],visibleSourceKeys:()=>['espn','fantasycalc'],
  COMPOSITE_VERSION_KEYS:['ddf_value','ddf_value_charts','ddf_value_projections'],
  buildRow:()=>{throw new Error('legacy materializer must not be called by additional identity tests');}};
vm.createContext(context);
vm.runInContext(section('  const rowCopy = row =>','  // One player\'s row from the pipeline:'),context);
vm.runInContext(section('  let pipelinePlayersCache = null;','  // A source\'s natives this week'),context);
vm.runInContext(section('  // JEG-1505 search-only boundary.','  function rebuildDomain()'),context);
// Copy real public accessor expressions instead of imitating their behavior.
const names=['getAllRows','getPlayer','searchPlayers','resolveSearchIdentity','prepareSearchSelection','getSearchIdentityRevision','isReady','getState'];
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
else if(input.action==='prepareBatch') result=input.cases.map(options=>context.controls.prepareSearchSelection(options));
else if(input.action==='prepareSparse') result=context.controls.prepareSearchSelection({...input.options,
  ownership:{...input.options.ownership,mine:Array(1)}});
else if(input.action==='reject') result={accepted:context.installSearchIdentities(input.badSelection)};
else if(input.action==='readout') {
  const text=fs.readFileSync(path.join(root,'app/v2/v2.js'),'utf8');
  const NS=require(path.join(root,'app/v2/namesearch.js'));
  const node=tag=>({tag,children:[],dataset:{},hidden:false,textContent:'',className:'',value:'',
    append(...v){this.children.push(...v);},appendChild(v){this.children.push(v);return v;},
    replaceChildren(...v){this.children=v;},setAttribute(k,v){this[k]=v;},addEventListener(){}});
  const boxes={};['v2Unpriced','v2TUnpriced','v2RUnpriced','giveInput','giveResults','receiveInput','receiveResults']
    .forEach(id=>boxes[id]=node('section'));
  boxes.giveInput.value=input.query;boxes.receiveInput.value=input.query;
  const listeners=new Map(),events=[];
  const bus={TradeValueNameSearch:NS,addEventListener:(type,fn)=>listeners.set(type,fn),
    dispatchEvent:event=>{events.push(event.type);listeners.get(event.type)?.(event);}};
  const ui={C:context.controls,window:bus,document:{createElement:node,createTextNode:value=>({...node('text'),textContent:value})},
    $:id=>boxes[id]||null,DDF_KEY:'ddf_value',state:{search:input.query},T:{search:input.query},R:{search:input.query},
    currentView:()=>input.compare?'compare':'values',SIDE_IDS:{give:{search:'giveInput',results:'giveResults'},receive:{search:'receiveInput',results:'receiveResults'}},
    compareView:{},TR:{give:[],receive:[]},compareRosterContext:()=>({ready:false}),searchMatches:()=>[]};
  vm.createContext(ui);
  const start=text.indexOf('  const UNPRICED_REASON ='),stop=text.indexOf('  // GAP-025:',start);
  vm.runInContext(text.slice(start,stop),ui);
  const a=text.indexOf('  function renderSearch(side)'),b=text.indexOf('  // "A, B and C"',a);
  vm.runInContext(text.slice(a,b),ui);
  const registration=text.split('\n').find(line=>line.includes('addEventListener("trade-value-search-identities-change"'));
  if(!registration)throw new Error('missing actual identity event registration');
  vm.runInContext(registration,ui);
  let before=[];
  if(input.lazy){
    context.searchIdentityByKey=new Map();
    before=JSON.parse(vm.runInContext('JSON.stringify(unpricedMatches(state.search))',ui));
  }
  context.window=bus;context.CustomEvent=class {constructor(type){this.type=type;}};
  context.installSearchIdentities(input.selection);
  const found=ui.renderUnpriced('v2Unpriced',input.query);
  const addable=input.compare?ui.renderSearch('give'):[];
  result={before,keys:found.map(r=>r.player_key),box:boxes.v2Unpriced,compare:boxes.giveResults,
    addable,events,legacyValue:vm.runInContext('unpricedValue({universe_only:true})',ui),
    legacyNameKey:vm.runInContext('window.TradeValueNameSearch.key(state.search)',ui)};
}
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
    def copy_inputs(self, destination):
        for name in ("players_identity_snapshot.json", "sleeper_identity_base.json", "player_platform_spellings.json", "player_aliases.json"):
            target = destination / "data/inputs" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "data/inputs" / name, target)
        target = destination / "data/fixtures/current/players.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "data/fixtures/current/players.json", target)
        # The checked-in owned artifact is cumulative refresh input, not a
        # disposable output. New catalogs must bootstrap explicitly.
        target = destination / "app/trade-value-chart/assets/jeg1505-search-identities.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ASSET, target)

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

    def test_reported_nine_malformed_lists_hold_instead_of_becoming_ready(self):
        candidate = {"namespace": "canonical", "id": 101}
        cases = []
        for field in ("mine", "others"):
            for value in (False, 0, "", None):
                ownership = {"complete": True, "mine": [], "others": [], field: value}
                cases.append({"inputs": [candidate], "ownership": ownership})
        cases.append({"inputs": [candidate], "overrideAdds": "",
                      "ownership": {"complete": True, "mine": [], "others": []}})
        out = widget("prepareBatch", mode="worked", cases=cases)
        for options, result in zip(cases, out["result"]):
            with self.subTest(options=options):
                self.assertFalse(result["readyForPricing"])
                self.assertEqual(result["wireKeys"], [])
                self.assertTrue(any(p.get("boundary") == "request_shape" for p in result["pending"]))
        self.assertTrue(out["inputUnchanged"] and out["canonicalUnchanged"] and out["computedUnchanged"])

    def test_present_non_array_candidates_overrides_and_ownership_hold(self):
        candidate = {"namespace": "canonical", "id": 101}
        cases = []
        for field in ("inputs", "overrideAdds", "ownership.mine", "ownership.others"):
            for value in (None, False, True, 0, "", "101", {}, {"0": candidate}):
                options = {"inputs": [candidate], "ownership": {"complete": True, "mine": [], "others": []}}
                if field.startswith("ownership."):
                    options["ownership"][field.split(".")[1]] = value
                else:
                    options[field] = value
                cases.append(options)
        for value in (None, False, True, 0, "", "ownership", [], [candidate]):
            cases.append({"inputs": [candidate], "ownership": value})
            cases.append(value)
        out = widget("prepareBatch", mode="worked", cases=cases)
        for options, result in zip(cases, out["result"]):
            with self.subTest(options=options):
                self.assertFalse(result["readyForPricing"])
                self.assertEqual(result["wireKeys"], [])
                self.assertTrue(any(p.get("boundary") == "request_shape" for p in result["pending"]))
        self.assertTrue(out["inputUnchanged"] and out["canonicalUnchanged"] and out["computedUnchanged"])

    def test_optional_omitted_lists_and_explicit_empty_arrays_remain_valid(self):
        candidate = {"namespace": "canonical", "id": 101}
        cases = [{"inputs": [candidate], "ownership": {"complete": True}},
                 {"overrideAdds": [candidate], "ownership": {"complete": True}},
                 {"inputs": [candidate], "overrideAdds": [], "ownership": {"complete": True, "mine": [], "others": []}}]
        out = widget("prepareBatch", mode="worked", cases=cases)
        for result in out["result"]:
            self.assertTrue(result["readyForPricing"])
            self.assertEqual(result["wireKeys"], [101])
            self.assertEqual(result["pending"], [])
        self.assertTrue(out["inputUnchanged"] and out["computedUnchanged"])

    def test_sparse_ownership_array_does_not_silently_skip_unknown_entry(self):
        options = {"inputs": [{"namespace": "canonical", "id": 101}],
                   "ownership": {"complete": True, "mine": [], "others": []}}
        out = widget("prepareSparse", mode="worked", options=options)
        self.assertFalse(out["result"]["readyForPricing"])
        self.assertEqual(out["result"]["wireKeys"], [])
        self.assertEqual(out["result"]["pending"][0]["boundary"], "ownership")
        self.assertTrue(out["inputUnchanged"] and out["canonicalUnchanged"] and out["computedUnchanged"])

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

    def test_conflicting_own_and_other_claims_are_detected_before_flattening(self):
        options = {"inputs": [{"namespace": "canonical", "id": 102}],
                   "ownership": {"complete": True, "mine": [{"namespace": "canonical", "id": 101}],
                                 "others": [{"namespace": "canonical", "id": "0101"}]}}
        result = widget("prepare", mode="worked", options=options)["result"]
        self.assertFalse(result["ownershipReady"])
        self.assertFalse(result["readyForPricing"])
        self.assertEqual(result["wireKeys"], [])
        self.assertEqual(result["ownershipConflictKeys"], [101])
        self.assertEqual(result["pending"], [{"status": "pending", "player_key": 101,
                    "reason": "Identity is claimed by own and other rosters", "boundary": "ownership_conflict"}])

    def test_repeated_other_claims_do_not_create_a_false_own_other_conflict(self):
        other = {"namespace": "canonical", "id": 101}
        options = {"inputs": [{"namespace": "canonical", "id": 102}],
                   "ownership": {"complete": True, "others": [other, other]}}
        result = widget("prepare", mode="worked", options=options)["result"]
        self.assertTrue(result["readyForPricing"])
        self.assertEqual(result["wireKeys"], [102])
        self.assertEqual(result["ownershipConflictKeys"], [])

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

    def test_main_readout_shows_retained_identity_as_unavailable_not_zero(self):
        out = widget("readout", mode="worked", query="Eric Tomlinson")
        self.assertEqual(out["result"]["keys"], [33])
        head, listing = out["result"]["box"]["children"]
        self.assertNotIn("worth 0.0", head["textContent"])
        values = [part["textContent"] for part in listing["children"][0]["children"]]
        self.assertIn("DDF Value unavailable (pending)", values)
        self.assertEqual(out["result"]["legacyValue"], "0.0")
        self.assertTrue(out["computedUnchanged"] and out["canonicalUnchanged"])

    def test_late_identity_load_invalidates_empty_query_cache_and_refreshes_sections(self):
        out = widget("readout", mode="worked", query="Eric Tomlinson", lazy=True)
        self.assertEqual(out["result"]["before"], [])
        self.assertEqual(out["result"]["keys"], [33])
        self.assertEqual(out["result"]["events"], ["trade-value-search-identities-change"])
        self.assertTrue(out["computedUnchanged"])

    def test_compare_retained_hit_stays_disabled_and_is_not_an_addable_trade(self):
        out = widget("readout", mode="worked", query="Eric Tomlinson", compare=True)
        self.assertEqual(out["result"]["addable"], [])
        button = out["result"]["compare"]["children"][0]["children"][0]
        self.assertTrue(button["disabled"])
        self.assertEqual(button["aria-disabled"], "true")
        self.assertIn("unavailable (pending)", button["children"][1]["textContent"])

    def test_unknown_readout_respects_position_filter(self):
        out = widget("readout", mode="worked", query="Eric Tomlinson", position="QB")
        self.assertEqual(out["result"]["keys"], [])
        self.assertTrue(out["result"]["box"]["hidden"])

    def test_snapshot_writer_is_deterministic_checkable_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_inputs(root)
            out = root / "assets/search.json"
            write_snapshot(root=root, out=out)
            initial = out.read_bytes()
            write_snapshot(root=root, out=out, check=True)
            write_snapshot(root=root, out=out)
            self.assertEqual(out.read_bytes(), initial)
            out.write_text("stale")
            with self.assertRaisesRegex(ValueError, "missing or stale"):
                write_snapshot(root=root, out=out, check=True)
            self.assertEqual(out.read_text(), "stale")
            snapshot = root / "data/inputs/players_identity_snapshot.json"
            rows = json.loads(snapshot.read_text())
            rows.append(deepcopy(rows[0]))
            snapshot.write_text(json.dumps(rows))
            with self.assertRaisesRegex(ValueError, "duplicate canonical"):
                write_snapshot(root=root, out=out)
            self.assertEqual(out.read_text(), "stale")

    def test_sync_path_generates_search_asset_before_copy_without_running_full_sync(self):
        with mock.patch.object(sys, "path", [str(ROOT / "pipelines"), *sys.path]):
            import sync_dashboard_artifacts as sync
        tree = ast.parse((ROOT / "pipelines/sync_dashboard_artifacts.py").read_text())
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        calls = [n for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        refresh_line = next(n.lineno for n in calls if n.func.id == "sync_search_identity_asset")
        copy_line = next(n.lineno for n in calls if n.func.id == "copy_tree")
        self.assertLess(refresh_line, copy_line)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_inputs(root)
            app = root / "app/trade-value-chart"
            with mock.patch.object(sync, "ROOT", root), mock.patch.object(sync, "APP", app), mock.patch.object(sys, "path", [str(ROOT / "pipelines"), *sys.path]):
                sync.sync_search_identity_asset()
            self.assertEqual(json.loads((app / "assets/jeg1505-search-identities.json").read_text()), build(root))


class CumulativeRetentionTest(unittest.TestCase):
    """Synthetic canonical refreshes, never an invented NFL lifecycle ledger."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / "app/trade-value-chart/assets/jeg1505-search-identities.json"
        self.canonical = [
            {"player_key": 900001, "full_name": "Synthetic Retained Player", "position": "WR", "gsis_id": "00-900001"},
            {"player_key": 900002, "full_name": "Synthetic Control", "position": "TE", "gsis_id": "00-900002"}]
        self.base = {"meta": {"pulled_at": "2026-11-03T00:00:00+00:00"}, "by_sleeper_id": {
            "900011": {"gsis_id": "00-900001", "pos": "WR", "team": "SF", "status": "Active"},
            "900012": {"gsis_id": "00-900002", "pos": "TE", "team": "SEA", "status": "Injured Reserve"}}}
        self.fixture = {"players": [{"player_key": row["player_key"], "name": row["full_name"],
            "pos": row["position"], "sleeper_id": str(900011 + index)} for index, row in enumerate(self.canonical)]}
        self.save_inputs()
        write_snapshot(root=self.root, prior_snapshot=None)

    def save(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, sort_keys=True) + "\n")

    def save_inputs(self):
        self.save("data/inputs/players_identity_snapshot.json", self.canonical)
        self.save("data/inputs/sleeper_identity_base.json", self.base)
        self.save("data/fixtures/current/players.json", self.fixture)
        self.save("data/inputs/player_platform_spellings.json", {"rows": []})
        self.save("data/inputs/player_aliases.json", {"aliases": []})

    def omit_player(self):
        self.canonical = [row for row in self.canonical if row["player_key"] != 900001]
        self.fixture["players"] = [row for row in self.fixture["players"] if row["player_key"] != 900001]
        self.base["by_sleeper_id"].pop("900011", None)
        self.save_inputs()

    def refresh(self, **kwargs):
        return write_snapshot(root=self.root, **kwargs)

    def player(self, payload, key=900001):
        return next(row for row in payload["identities"] if row["player_key"] == key)

    def test_disappearance_retains_identity_without_invented_current_status_or_zero_price(self):
        old = self.player(json.loads(self.out.read_text()))
        self.omit_player()
        payload = self.refresh()
        self.assertEqual([p["player_key"] for p in payload["identities"]], [900001, 900002])
        row = self.player(payload)
        self.assertTrue(row["selectable"])
        self.assertFalse(row["retention"]["present_in_canonical_export"])
        self.assertEqual(row["retention"]["canonical_observations"], old["retention"]["canonical_observations"])
        self.assertEqual(row["sleeper_id"], "900011")
        self.assertEqual(row["eligibility_status"], "unknown")
        self.assertEqual(row["pricing_status"], "unknown")
        for field in ("team", "roster_status", "injury_status"):
            self.assertIsNone(row[field])
        self.assertFalse({"value", "values", "espn_ros", "blend_ros"} & row.keys())
        out = widget("search", mode="worked", selection=payload, query=row["name"], key=900001)
        self.assertEqual(len(out["result"]["hits"]), 1)
        self.assertTrue(all(value is None for value in out["result"]["one"]["values"].values()))
        self.assertTrue(out["computedUnchanged"] and out["canonicalUnchanged"])

    def test_disappears_and_returns_to_same_key_once_with_evidence_intact(self):
        first = json.loads(self.out.read_text())
        original = deepcopy(self.canonical[0])
        self.omit_player()
        missing = self.refresh()
        self.canonical.append(original)
        self.base["meta"]["pulled_at"] = "2026-11-05T00:00:00+00:00"
        self.base["by_sleeper_id"]["900011"] = {"gsis_id": "00-900001", "pos": "WR", "team": "LAR", "status": "Practice Squad"}
        self.save_inputs()
        returned = self.refresh()
        row = self.player(returned)
        self.assertEqual(sum(p["player_key"] == 900001 for p in returned["identities"]), 1)
        self.assertTrue(row["retention"]["present_in_canonical_export"] and row["selectable"])
        self.assertEqual(row["eligibility_status"], "unknown") # A roster status is not a sourced return event.
        self.assertEqual(row["lifecycle_history"], [])
        old_evidence = self.player(first)["retention"]["canonical_observations"]
        self.assertTrue(all(e in row["retention"]["canonical_observations"] for e in old_evidence))
        self.assertEqual(self.player(missing)["player_key"], row["player_key"])
        self.assertEqual(row["team"], "LAR")

    def test_sourced_retirement_and_return_survive_export_and_event_feed_omission(self):
        retired = {"player_key": 900001, "kind": "retired", "date": "2026-11-03", "source": "https://example.invalid/synthetic-retirement"}
        returned = {"player_key": 900001, "kind": "returned", "date": "2026-11-04", "source": "https://example.invalid/synthetic-return"}
        before = self.refresh(lifecycle_events=[retired])
        self.assertFalse(self.player(before)["selectable"])
        self.omit_player()
        after = self.refresh()
        self.assertEqual(self.player(after)["eligibility_status"], "retired")
        self.assertEqual(self.player(after)["lifecycle_history"], [retired])
        self.assertEqual(widget("search", mode="worked", selection=after, query="Synthetic Retained Player", key=900001)["result"]["hits"], [])
        active = self.refresh(lifecycle_events=[returned], as_of=date(2026, 11, 4))
        self.assertTrue(self.player(active)["selectable"])
        self.assertEqual(self.player(active)["eligibility_status"], "returned")
        self.assertEqual(self.player(active)["lifecycle_history"], [retired, returned])
        repeated = self.refresh()
        self.assertEqual(self.player(repeated), self.player(active))
        self.assertEqual(repeated["meta"]["lifecycle_as_of"], "2026-11-04")

    def test_future_lifecycle_evidence_is_retained_and_replay_cannot_regress(self):
        event = {"player_key": 900001, "kind": "retired", "date": "2026-11-05", "source": "https://example.invalid/synthetic-future"}
        future = self.refresh(lifecycle_events=[event])
        self.assertEqual(self.player(future)["eligibility_status"], "unknown")
        self.assertEqual(self.player(future)["lifecycle_history"], [event])
        effective = self.refresh(as_of=date(2026, 11, 5))
        self.assertEqual(self.player(effective)["eligibility_status"], "retired")
        before = self.out.read_bytes()
        with self.assertRaisesRegex(ValueError, "cannot move backwards"):
            self.refresh(as_of=date(2026, 11, 4))
        self.assertEqual(self.out.read_bytes(), before)

    def test_equivalent_lifecycle_key_forms_deduplicate_before_first_write_and_check(self):
        original = {"player_key": 900001, "kind": "retired", "date": "2026-11-03", "source": "https://example.invalid/synthetic-mixed-key"}
        feed = [dict(original, player_key=key) for key in (900001, "900001", "0900001", "000900001")]
        saved_feed = deepcopy(feed)
        first = self.refresh(lifecycle_events=feed)
        self.assertEqual(self.player(first)["lifecycle_history"], [original])
        self.assertEqual(self.player(first)["eligibility_status"], "retired")
        first_bytes = self.out.read_bytes()
        self.refresh(check=True)
        self.refresh()
        self.assertEqual(self.out.read_bytes(), first_bytes)
        self.refresh(lifecycle_events=list(reversed(feed)))
        self.refresh(check=True, lifecycle_events=feed)
        self.assertEqual(self.out.read_bytes(), first_bytes)
        self.assertEqual(feed, saved_feed)

    def test_lifecycle_deduplication_keeps_distinct_sources_and_rejects_conflicting_kinds(self):
        event = {"player_key": 900001, "kind": "retired", "date": "2026-11-03", "source": "https://example.invalid/synthetic-source-one"}
        other_source = dict(event, player_key="0900001", source="https://example.invalid/synthetic-source-two")
        first = self.refresh(lifecycle_events=[event, other_source, dict(event, player_key="900001")])
        history = self.player(first)["lifecycle_history"]
        self.assertEqual(len(history), 2)
        self.assertEqual({row["player_key"] for row in history}, {900001})
        self.assertEqual({row["source"] for row in history}, {event["source"], other_source["source"]})
        saved = self.out.read_bytes()
        self.refresh(check=True)
        self.refresh()
        self.assertEqual(self.out.read_bytes(), saved)
        contradiction = [dict(other_source, kind="returned")]
        before = deepcopy(contradiction)
        with self.assertRaisesRegex(ValueError, "conflicting lifecycle evidence"):
            self.refresh(lifecycle_events=contradiction)
        self.assertEqual(contradiction, before)
        self.assertEqual(self.out.read_bytes(), saved) # Atomic refresh hold; no evidence chosen/dropped.

    def test_lifecycle_normalization_deduplicates_emitted_fields_and_prior_mixed_forms(self):
        event = {"player_key": 900001, "kind": "retired", "date": "2026-11-03", "source": "https://example.invalid/synthetic-normalized"}
        feed = [dict(event, caller_note="one"), dict(event, player_key="900001", caller_note="two")]
        first = self.refresh(lifecycle_events=feed)
        self.assertEqual(self.player(first)["lifecycle_history"], [event])
        self.refresh(check=True)
        # Existing malformed duplicate history is normalized once on refresh;
        # distinct recognized evidence remains intact in the preceding control.
        self.player(first)["lifecycle_history"].append(dict(event, player_key="0900001"))
        self.out.write_text(json.dumps(first))
        fixed = self.refresh()
        self.assertEqual(self.player(fixed)["lifecycle_history"], [event])
        saved = self.out.read_bytes()
        self.refresh(check=True)
        self.refresh()
        self.assertEqual(self.out.read_bytes(), saved)

    def test_empty_later_export_and_provider_feed_do_not_erase_known_identities(self):
        self.canonical = []
        self.fixture = {"players": []}
        self.base["by_sleeper_id"] = {}
        self.save_inputs()
        payload = self.refresh()
        self.assertEqual(payload["eligible_player_keys"], [900001, 900002])
        self.assertTrue(all(row["eligibility_status"] == "unknown" and row["team"] is None
                            and not row["retention"]["present_in_canonical_export"] for row in payload["identities"]))

    def test_sourced_return_does_not_clear_unresolved_identity_mapping(self):
        self.base["by_sleeper_id"]["900011"]["pos"] = "TE"
        self.save_inputs()
        self.refresh()
        events = [{"player_key": 900001, "kind": kind, "date": day,
                   "source": "https://example.invalid/synthetic-" + kind}
                  for kind, day in (("retired", "2026-11-03"), ("returned", "2026-11-04"))]
        row = self.player(self.refresh(lifecycle_events=events, as_of=date(2026, 11, 4)))
        self.assertEqual(row["eligibility_status"], "returned")
        self.assertEqual(row["lifecycle_history"], events)
        self.assertFalse(row["selectable"])
        self.assertIn("positions disagree", row["selection_reason"])

    def test_reused_id_collides_with_retained_absent_identity_and_holds_both(self):
        self.omit_player()
        self.canonical.append({"player_key": 900003, "full_name": "Synthetic ID Collision", "position": "WR", "gsis_id": "00-900001"})
        self.fixture["players"].append({"player_key": 900003, "sleeper_id": "900011"})
        self.save_inputs()
        payload = self.refresh()
        for key in (900001, 900003):
            row = self.player(payload, key)
            self.assertFalse(row["selectable"])
            self.assertIsNone(row["sleeper_id"])
            self.assertIn("historical", row["selection_reason"])
        self.assertTrue(self.player(payload, 900002)["selectable"])

    def test_suppressed_conflicting_ids_remain_in_future_ambiguity_detection(self):
        self.canonical[0]["gsis_id"] = "00-900099"
        self.fixture["players"][0]["sleeper_id"] = "900099"
        self.base["by_sleeper_id"]["900099"] = {"gsis_id": "00-900099", "pos": "WR"}
        self.save_inputs()
        held = self.refresh()
        self.assertFalse(self.player(held)["selectable"])
        self.assertIsNone(self.player(held)["sleeper_id"])
        self.omit_player()
        self.canonical.append({"player_key": 900003, "full_name": "Synthetic Reused Held ID", "position": "WR", "gsis_id": "00-900001"})
        self.fixture["players"].append({"player_key": 900003, "sleeper_id": "900011"})
        self.save_inputs()
        payload = self.refresh()
        self.assertFalse(self.player(payload)["selectable"])
        self.assertFalse(self.player(payload, 900003)["selectable"])
        # One ID can have several source observations; count distinct claims.
        self.assertEqual({c["id"] for c in self.player(payload)["retention"]["sleeper_claims"]}, {"900011", "900099"})

    def test_ambiguous_gsis_only_candidates_survive_later_provider_id_reuse(self):
        self.base["by_sleeper_id"]["900099"] = {"gsis_id": "00-900001", "pos": "WR"}
        self.save_inputs()
        first = self.refresh()
        self.assertFalse(self.player(first)["selectable"])
        self.assertIsNone(self.player(first)["sleeper_id"])
        self.omit_player()
        self.canonical.append({"player_key": 900003, "full_name": "Synthetic Reused Ambiguous ID", "position": "WR", "gsis_id": "00-900099"})
        self.fixture["players"].append({"player_key": 900003, "sleeper_id": "900099"})
        self.base["by_sleeper_id"]["900099"] = {"gsis_id": "00-900099", "pos": "WR"}
        self.save_inputs()
        after = self.refresh()
        self.assertFalse(self.player(after, 900003)["selectable"])
        self.assertIn("historical sleeper_id", self.player(after, 900003)["selection_reason"])

    def test_provider_only_gsis_ambiguity_survives_new_sleeper_id_after_omission(self):
        self.root = self.root / "provider-only"
        self.out = self.root / "app/trade-value-chart/assets/jeg1505-search-identities.json"
        self.canonical[0]["gsis_id"] = None
        self.base["by_sleeper_id"]["900099"] = {"gsis_id": "00-900001", "pos": "WR"}
        self.save_inputs()
        first = write_snapshot(root=self.root, prior_snapshot=None)
        self.assertFalse(self.player(first)["selectable"])
        self.omit_player()
        self.base["by_sleeper_id"].pop("900099")
        self.canonical.append({"player_key": 900003, "full_name": "Synthetic Historical GSIS Collision", "position": "WR", "gsis_id": "00-900001"})
        self.fixture["players"].append({"player_key": 900003, "sleeper_id": "900033"})
        self.base["by_sleeper_id"]["900033"] = {"gsis_id": "00-900001", "pos": "WR"}
        self.save_inputs()
        after = self.refresh()
        self.assertFalse(self.player(after, 900003)["selectable"])
        self.assertIn("historical gsis_id", self.player(after, 900003)["selection_reason"])

    def test_historical_hold_does_not_publish_one_candidate_current_status(self):
        self.fixture["players"][0]["sleeper_id"] = "900099"
        self.base["by_sleeper_id"]["900099"] = {"gsis_id": "00-900099", "pos": "WR", "team": "LAR", "status": "Active"}
        self.save_inputs()
        row = self.player(self.refresh())
        self.assertFalse(row["selectable"])
        for field in ("sleeper_id", "gsis_id", "team", "roster_status", "injury_status"):
            self.assertIsNone(row[field])

    def test_pending_redirect_hold_survives_alias_and_export_omission(self):
        self.save("data/inputs/player_aliases.json", {"aliases": [{"player_key": 900002, "verified": "Row 900001 is a duplicate; confirmation pending"}]})
        first = self.refresh()
        self.assertFalse(self.player(first)["selectable"])
        self.omit_player()
        payload = self.refresh()
        self.assertFalse(self.player(payload)["selectable"])
        self.assertEqual(payload["redirect_claims"], first["redirect_claims"])
        self.assertEqual(payload["redirect_claims"][0]["status"], "pending_current_registry_confirmation")

    def test_legacy_held_identity_without_reconstructable_claims_stays_held(self):
        legacy = json.loads(self.out.read_text())
        for row in legacy["identities"]:
            row.pop("retention")
        legacy["meta"].pop("retention_version")
        legacy["meta"].pop("retention_sources")
        row = self.player(legacy)
        row.update(selectable=False, sleeper_id=None, gsis_id=None, selection_reason="Synthetic unresolved prior mapping")
        self.out.write_text(json.dumps(legacy))
        self.omit_player()
        payload = self.refresh()
        self.assertFalse(self.player(payload)["selectable"])
        self.assertIn("unresolved prior mapping", self.player(payload)["selection_reason"])

    def test_version_one_retention_migrates_without_reset_when_export_omits_player(self):
        prior = json.loads(self.out.read_text())
        prior["meta"]["retention_version"] = 1
        for row in prior["identities"]:
            row["retention"].pop("gsis_claims")
        self.out.write_text(json.dumps(prior))
        self.omit_player()
        payload = self.refresh()
        self.assertEqual(payload["meta"]["retention_version"], 2)
        self.assertEqual(payload["eligible_player_keys"], [900001, 900002])
        self.assertEqual(self.player(payload)["sleeper_id"], "900011")
        self.assertEqual(self.player(payload)["eligibility_status"], "unknown")
        self.assertIsNone(self.player(payload)["team"])

    def test_position_reclassification_holds_identity_instead_of_deleting_it(self):
        self.canonical[0]["position"] = "CB"
        self.save_inputs()
        row = self.player(self.refresh())
        self.assertEqual(row["pos"], "WR")
        self.assertFalse(row["selectable"])
        self.assertEqual(row["eligibility_status"], "unknown")

    def test_provider_position_conflict_does_not_resolve_by_source_omission(self):
        self.base["by_sleeper_id"]["900011"]["pos"] = "TE"
        self.save_inputs()
        first = self.refresh()
        self.assertFalse(self.player(first)["selectable"])
        self.omit_player()
        after = self.refresh()
        self.assertFalse(self.player(after)["selectable"])
        self.assertIn("positions disagree", self.player(after)["selection_reason"])

    def test_gsis_resolved_provider_id_survives_later_provider_omission(self):
        new_root = self.root / "gsis-only"
        shutil.copytree(self.root / "data", new_root / "data")
        fixture = new_root / "data/fixtures/current/players.json"
        fixture.write_text(json.dumps({"players": []}))
        first = write_snapshot(root=new_root, prior_snapshot=None)
        self.assertEqual(self.player(first)["sleeper_id"], "900011")
        self.assertTrue(self.player(first)["retention"]["sleeper_claims"])
        (new_root / "data/inputs/players_identity_snapshot.json").write_text(json.dumps([self.canonical[1]]))
        base = deepcopy(self.base)
        base["by_sleeper_id"].pop("900011")
        (new_root / "data/inputs/sleeper_identity_base.json").write_text(json.dumps(base))
        after = write_snapshot(root=new_root)
        self.assertEqual(self.player(after)["sleeper_id"], "900011")
        self.assertIsNone(self.player(after)["team"])
        self.assertTrue(self.player(after)["selectable"])

    def test_refresh_and_check_are_fixed_points_and_preserve_source_inputs(self):
        self.omit_player()
        before = {p: p.read_bytes() for p in (self.root / "data").rglob("*.json")}
        self.refresh()
        first = self.out.read_bytes()
        self.refresh()
        self.refresh(check=True)
        self.assertEqual(self.out.read_bytes(), first)
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_identical_multi_refresh_sequences_produce_identical_artifacts(self):
        second = self.root / "replayed"
        shutil.copytree(self.root / "data", second / "data")
        write_snapshot(root=second, prior_snapshot=None)
        other = second / "app/trade-value-chart/assets/jeg1505-search-identities.json"
        self.assertEqual(self.out.read_bytes(), other.read_bytes())
        self.omit_player()
        shutil.copytree(self.root / "data", second / "data", dirs_exist_ok=True)
        self.refresh()
        write_snapshot(root=second)
        self.assertEqual(self.out.read_bytes(), other.read_bytes())
        event = {"player_key": 900001, "kind": "retired", "date": "2026-11-04", "source": "https://example.invalid/synthetic-replay"}
        self.refresh(lifecycle_events=[event], as_of=date(2026, 11, 4))
        write_snapshot(root=second, lifecycle_events=[event], as_of=date(2026, 11, 4))
        self.assertEqual(self.out.read_bytes(), other.read_bytes())

    def test_omitted_identity_readout_and_actual_root_v2_templates_share_asset_path(self):
        from pipelines.build_v2_page import build_v2_html
        self.omit_player()
        payload = self.refresh()
        out = widget("readout", mode="worked", selection=payload, query="Synthetic Retained Player", lazy=True, compare=True)
        self.assertEqual(out["result"]["keys"], [900001])
        self.assertEqual(out["result"]["addable"], [])
        self.assertTrue(out["result"]["compare"]["children"][0]["children"][0]["disabled"])
        displayed = json.dumps(out["result"]["box"])
        self.assertIn("DDF Value unavailable (pending)", displayed)
        self.assertTrue(out["computedUnchanged"] and out["canonicalUnchanged"])
        reader = (ROOT / "app/trade-value-chart/assets/product-data.js").read_text()
        asset = re.search(r'searchIdentities: "([^"]+)"', reader).group(1)
        # Execute the actual HTML builder without full sync, a browser, a bind,
        # generated-dist writes or a claim about live asset delivery.
        for at_root, page_url in ((True, "https://example.invalid/"), (False, "https://example.invalid/v2/")):
            page = build_v2_html((ROOT / "app/trade-value-chart/index.html").read_text(),
                                 (ROOT / "app/v2/shell.html").read_text(), at_root=at_root, posts=[])
            base = re.search(r'<base href="([^"]+)"', page)
            resolved = urljoin(urljoin(page_url, base.group(1)) if base else page_url, asset)
            self.assertEqual(resolved, "https://example.invalid/assets/jeg1505-search-identities.json")
            for script in ("assets/product-data.js", "assets/curve-widget.js", "v2/v2.js"):
                self.assertIn(script, page)
            self.assertIn('id="v2Unpriced"', page)

    def test_missing_prior_requires_explicit_bootstrap_and_existing_history_cannot_reset(self):
        before = self.out.read_bytes()
        with self.assertRaisesRegex(ValueError, "cannot be replaced"):
            self.refresh(prior_snapshot=None)
        other = self.root / "older.json"
        other.write_bytes(before)
        with self.assertRaisesRegex(ValueError, "cannot be replaced"):
            self.refresh(prior_snapshot=other)
        self.assertEqual(self.out.read_bytes(), before)
        # Simulate an absent catalog in a separate new destination; never remove
        # the existing artifact or an identity to exercise this guard.
        new_root = self.root / "new-catalog"
        shutil.copytree(self.root / "data", new_root / "data")
        with self.assertRaisesRegex(ValueError, "prior.*required"):
            write_snapshot(root=new_root)
        explicit = write_snapshot(root=new_root, prior_snapshot=None)
        self.assertEqual(len(explicit["identities"]), 2)

    def test_malformed_prior_and_unsourced_events_fail_before_replacing_history(self):
        initial = json.loads(self.out.read_text())
        for mutation in ("duplicate", "unknown_source", "price", "retention_price", "unsourced_retirement"):
            bad = deepcopy(initial)
            if mutation == "duplicate": bad["identities"].append(deepcopy(bad["identities"][0]))
            elif mutation == "unknown_source": bad["identities"][0]["retention"]["canonical_observations"][0]["source_sha256"] = "0" * 64
            elif mutation == "price": bad["identities"][0]["retention"]["sleeper_claims"][0]["value"] = 0
            elif mutation == "retention_price": bad["identities"][0]["retention"]["values"] = {"ddf_value": 0}
            else: bad["identities"][0]["eligibility_status"] = "retired"
            self.out.write_text(json.dumps(bad))
            before = self.out.read_bytes()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.refresh()
            self.assertEqual(self.out.read_bytes(), before)
        self.out.write_text(json.dumps(initial))
        before = self.out.read_bytes()
        with self.assertRaises(ValueError):
            self.refresh(lifecycle_events=[{"player_key": 900001, "kind": "retired", "date": "2026-11-03", "source": ""}])
        self.assertEqual(self.out.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
