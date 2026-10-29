"""JEG-1213: bounded league sharing keeps settings and Yahoo navigation stays out of rosters.

The shareHash tests fail on the pre-fix build (there is no settings-bearing league hash).
The Yahoo guard fails when its navigation exclusion is removed.
"""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LeagueImport(unittest.TestCase):
    def node(self, body):
        result = subprocess.run(
            ["node", "-e", "const assert=require('assert'); const W=require('./app/v2/workspace.js');\n" + body],
            cwd=ROOT, text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_share_hash_keeps_settings_and_marked_team(self):
        self.node("""
          let ws=W.newWorkspace();
          ['First', 'Second', 'Third'].forEach((name, i)=>{ws=W.ops.addTeam(ws,name,{entries:[{key:String(i+1),name:'Player '+i,pos:'RB'}]});});
          ws=W.ops.setMyTeam(ws,ws.teams[2].id);
          const settings='scoring=half_ppr&teams=10&roster=QB1.RB2.WR3.TE1.FLEX2.SF0.BN5&regend=13&playoffs=14-16&optimize=playoffs&bench=0.200&bso=1&shares=QB0.100_RB0.350_WR0.400_TE0.150';
          const encoded=W.shareHash(ws,settings);
          const params=new URLSearchParams(encoded.hash.split('?')[1]);
          for (const [key,value] of new URLSearchParams(settings)) assert.strictEqual(params.get(key),value,key);
          assert.strictEqual(params.get('wm'),'0');
          const text=encoded.hash.split('workspace=')[1].split('&')[0];
          assert.deepStrictEqual(W.decodeShare(text).map(t=>t.name),['Third','First','Second']);
          assert.strictEqual(encoded.full,true);
          assert.strictEqual(new URLSearchParams(W.shareHash(W.ops.setMyTeam(ws,null),settings).hash.split('?')[1]).get('wm'),'none');
        """)

    def test_share_hash_preserves_codec_limit_and_fallback(self):
        self.node("""
          let ws=W.newWorkspace();
          for(let i=0;i<20;i++) ws=W.ops.addTeam(ws,'Team '+i+' '+('x'.repeat(32)),{entries:Array.from({length:25},(_,j)=>({key:'key-'+i+'-'+j,name:'P '+j,pos:'RB'}))});
          ws=W.ops.setMyTeam(ws,ws.teams[4].id);
          const link=W.shareHash(ws,'scoring=ppr&teams=12');
          assert.strictEqual(link.full,false);
          assert.ok(link.text.length<=W.SHARE_LIMIT);
          assert.deepStrictEqual(W.decodeShare(link.text).map(t=>t.name),[ws.teams[4].name]);
          assert.ok(link.hash.endsWith('&scoring=ppr&teams=12'));
        """)

    def test_kicker_and_defense_identity_roundtrip_and_legacy_links(self):
        self.node("""
          const entries=[
            {key:'x:DEF:SF',name:'49ers D/ST',pos:'DEF',team:'SF'},
            {key:'x:K:KC',name:'Harrison Butker',pos:'K',team:'KC'},
            {key:'x:K:a:b!%c',name:'A. B: Kicker!',pos:'K'},
          ];
          const ws=W.ops.addTeam(W.newWorkspace(),'Team!',{entries});
          const roundtrip=W.decodeShare(W.encodeShare(ws).text);
          assert.deepStrictEqual(roundtrip[0].entries,entries);
          assert.deepStrictEqual(W.decodeShare('Old:!49ers%20D%2FST.DEF,!Harrison%20Butker.K')[0].entries,[
            {key:'x:DEF:49ers d st',name:'49ers D/ST',pos:'DEF'},
            {key:'x:K:harrison butker',name:'Harrison Butker',pos:'K'},
          ]);
        """)

    def test_malformed_link_is_rejected_without_partial_league(self):
        self.node("""
          for(const broken of ['Bad%:1','A:!Bad%.DEF','A:~bad%','Good:1|Bad%:2','A:!Name.DEF:x%3ADEF%3ASF:Bad%']) {
            assert.deepStrictEqual(W.decodeShare(broken),[],broken);
          }
        """)

    def test_yahoo_search_header_is_neither_team_nor_ignored_player(self):
        self.node("""
          const P=require('./app/v2/roster-paste.js'), fs=require('fs');
          const teams=JSON.parse(fs.readFileSync('tests/fixtures/league_paste/teams.json','utf8'));
          const rows=Object.values(teams).flat().filter(p=>!['K','D/ST'].includes(p[2])).map((p,i)=>({player_key:String(i+1),name:p[0],team:p[1],pos:p[2]}));
          const junk='Yahoo Sports Yahoo Sports Search query S';
          const text=fs.readFileSync('tests/fixtures/league_paste/yahoo-league-rosters.txt','utf8');
          const clean=P.parseLeague(text,rows);
          const pasted=P.parseLeague(text.replace('Team Alpha\\nPos','Team Alpha\\n'+junk+'\\nPos'),rows);
          assert.deepStrictEqual(pasted.teams.map(t=>[t.teamName,t.players.length]),clean.teams.map(t=>[t.teamName,t.players.length]));
          const extracted=P.extractPlayers(junk+'\\n'+rows[0].name,rows);
          assert.ok(!extracted.ignoredLines.includes(junk));
          assert.ok(!extracted.unmatched.some(u=>u.line===junk));
        """)


if __name__ == "__main__":
    unittest.main()
