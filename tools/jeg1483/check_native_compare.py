"""Read-only native Compare probe against an existing coherent static build.

Usage: python tools/jeg1483/check_native_compare.py --site-root /path/to/bundle
The bundle must contain full/index.html and genuine engine inputs. No writes,
external requests, UI baseline modifications or new values are made.
"""
import argparse,functools,http.server,json,threading
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser();parser.add_argument('--site-root',type=Path,required=True);parser.add_argument('--width',type=int,default=390);args=parser.parse_args();site=args.site_root
assert (site/'full/index.html').is_file(),'Expected full/index.html in supplied native bundle'
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(site)));threading.Thread(target=server.serve_forever,daemon=True).start()
with sync_playwright() as pw:
 b=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);p=b.new_page(viewport={'width':args.width,'height':844});errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
 p.add_init_script("{const D=Date,t=D.parse('2026-10-31T12:00:00Z');globalThis.Date=class extends D{constructor(...x){super(...(x.length?x:[t]))}static now(){return t}}}")
 p.route('**/full-runtime.js',lambda r:r.fulfill(body='',content_type='text/javascript'))
 for f in ['trade-context.js','v2.js','league.js','finder.js','opportunities.js','trade-readout.js']:
  p.route('**/v2/'+f+'*',lambda r,request,f=f:r.fulfill(body=(root/'app/v2'/f).read_text(),content_type='text/javascript'))
 p.route(lambda u:not u.startswith('http://127.0.0.1'),lambda r:r.abort())
 p.goto(f'http://127.0.0.1:{server.server_address[1]}/full/index.html#compare-trade');p.wait_for_function('window.TradeValueV2?.compare()',timeout=30000)
 fx=json.loads((root/'tests/fixtures/league_levels/charlotte.json').read_text())
 out=p.evaluate('''doc=>{const C=TradeValueCurveControls,TC=TradeValueTradeContext,W=TradeValueWorkspace;
 C.setScoring('half_ppr',false);C.setTeams(12,false);for(const[k,v]of Object.entries({QB:1,RB:2,WR:2,TE:1,FLEX:1,SUPERFLEX:0,BENCH:6}))C.setRosterSpot(k,v,false);
 let ws=W.newWorkspace({id:'native-full-test'});const now=Date.now();for(const t of doc.league.teams)ws=W.ops.addTeam(ws,t.id,{id:t.id,entries:t.players.filter(p=>p.key),provenance:{unresolved:0,observedAt:now,editedAt:now,coverage:'whole_roster'},mine:t.id===doc.mine});W.store.replace(ws,'replace');
 const my=ws.teams.find(t=>t.id===doc.mine),their=ws.teams.find(t=>t.id!==doc.mine),deal={give:[my.entries.find(e=>e.pos==='RB').key],get:[their.entries.find(e=>e.pos==='WR').key]};
 const q=TradeValueV2.leagueQuery(),pr=TC.comparePricing(C,{workspace:ws,keys:TC.pricingKeys({mine:my.entries,theirs:their.entries,deal})});
 const common=TC.commonFromPage({leagueQuery:q,valueContext:{...DDFOverrides.snapshotContext(),basis:C.getBasis()},sources:TC.sourcesFromEngine(C.getSourceInfo())});
 const ctx=TC.createContext({route:'league',workspaceId:ws.id,common,pricing:pr.pricing,mine:TC.savedTeam(ws,my.id),opponents:[TC.savedTeam(ws,their.id)],deal});
 const hash='#compare-trade?'+q+'&give='+deal.give.join(',')+'&get='+deal.get.join(',')+'&tc='+TC.encodeTransfer(TC.toTransfer(ctx));location.hash=hash;
 window.testExpected={rows:Object.fromEntries(pr.rows.map(r=>[r.player_key,r.values])),pricing:pr.pricing,ws:JSON.stringify(ws),deal};return {mode:pr.pricing.mode,rows:pr.rows.length,hashLength:hash.length,source:C.getSourceInfo().filter(s=>s.available).map(s=>s.key)};}''',fx)
 p.wait_for_timeout(400)
 state=p.evaluate('''()=>{const v=TradeValueV2.compare(),e=testExpected;return {held:v.held,mode:v.pricing?.mode,ready:v.ready,sameRows:v.giveRows.concat(v.receiveRows).every(r=>JSON.stringify(r.values)===JSON.stringify(e.rows[r.player_key])),samePricing:JSON.stringify(v.pricing)===JSON.stringify(e.pricing),totals:v.totals,allRows:v.rowsByKey.size,workspaceUnchanged:JSON.stringify(TradeValueWorkspace.store.get())===e.ws,bench:document.querySelector('#v2CConstruction').dataset.benchLevel};}''')
 print(json.dumps({'setup':out,'state':state,'errors':errors}),flush=True)
 assert state['ready'] and not state['held'] and state['mode']=='league' and state['sameRows'] and state['samePricing'] and state['workspaceUnchanged'],state
 p.reload();p.wait_for_function('window.TradeValueV2?.compare()?.ready',timeout=30000)
 reloaded=p.evaluate('''()=>({held:TradeValueV2.compare().held,mode:TradeValueV2.compare().pricing?.mode,ready:TradeValueV2.compare().ready})''');assert reloaded['mode']=='league' and not reloaded['held'];print(json.dumps({'reload':reloaded,'errors':errors}),flush=True)
 # Compare's Swap, sample rotation and edited shared link all keep league pricing.
 p.evaluate("document.getElementById('v2CSwap').click()")
 assert p.evaluate("TradeValueV2.compare().pricing.mode==='league' && TradeValueV2.compare().ready")
 p.evaluate("document.getElementById('v2CTryExample').click()")
 first=p.evaluate("({deal:JSON.stringify(TradeValueV2.tradeState.give),mode:TradeValueV2.compare().pricing.mode,example:TradeValueV2.compare().example,rows:TradeValueV2.compare().giveRows.concat(TradeValueV2.compare().receiveRows).map(r=>[String(r.player_key),r.values]),hash:location.hash})")
 assert first['example'] and first['mode']=='league'
 p.evaluate("document.getElementById('v2CNextExample').click()")
 second=p.evaluate("({deal:JSON.stringify(TradeValueV2.tradeState.give),mode:TradeValueV2.compare().pricing.mode,example:TradeValueV2.compare().example})")
 assert second['example'] and second['mode']=='league' and first['deal']!=second['deal']
 # Reopen an edited sample, including off-roster rows in its refreshed level identity.
 p.goto(p.url.split('#')[0]+first['hash']);p.wait_for_function('window.TradeValueV2?.compare()?.ready',timeout=30000)
 assert p.evaluate("TradeValueV2.compare().pricing.mode==='league' && !TradeValueV2.compare().held")
 p.evaluate("location.hash='#values'");p.wait_for_timeout(150);p.go_back();p.wait_for_function('window.TradeValueV2?.compare()?.ready',timeout=30000)
 assert p.evaluate("TradeValueV2.compare().pricing.mode==='league' && !TradeValueV2.compare().held")
 # A missing requested level is a hold, with no totals; restoring it clears the hold.
 p.evaluate("window.savedLevel=TradeValueCurveControls.getLeagueLevel;TradeValueCurveControls.getLeagueLevel=()=>null;document.getElementById('v2CSwap').click()")
 assert p.evaluate("!!TradeValueV2.compare().held && !TradeValueV2.compare().ready && TradeValueV2.compare().totals===null")
 p.evaluate("TradeValueCurveControls.getLeagueLevel=window.savedLevel;document.getElementById('v2CSwap').click()")
 assert p.evaluate("TradeValueV2.compare().ready && !TradeValueV2.compare().held")
 # Test the manual league mode and its explicit opt-out without a carried transfer.
 p.evaluate("location.hash='#compare-trade?give=547&get=1381'");p.wait_for_timeout(250)
 assert p.evaluate("TradeValueV2.compare().pricing.mode==='league' && location.hash.includes('tc=')")
 p.evaluate("TradeValueWorkspace.store.update(ws=>({...ws,ui:{...ws.ui,leagueRosters:false}}),'ui:leagueRosters');location.hash='#compare-trade?give=547&get=1381'");p.wait_for_timeout(250)
 assert p.evaluate("TradeValueV2.compare().pricing.mode==='modeled' && !TradeValueV2.compare().held")
 assert not errors,errors
 print(json.dumps({'passed':True,'width':args.width,'journeys':['league carry','same values/identity','reload','swap','sample rotation','edited link','Back','missing-level hold/recovery','manual league','explicit modeled opt-out'],'errors':errors}),flush=True)
 b.close()
server.shutdown()
