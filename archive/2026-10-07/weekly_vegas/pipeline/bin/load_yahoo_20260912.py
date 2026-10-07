#!/usr/bin/env python3
"""Load the 2026-09-12 live Yahoo pull into uso-yahoo and refresh the
football project's rostered snapshot. Data copied verbatim from the
browser task's read-only roster-page pull (pulled ~2026-09-12T12:55Z)."""
import json, re, subprocess, sys

SUPA = ["python3", "/tmp/supa.py"]
YAHOO = "wbxyjzfbnmyiuisgksor"
FB = "iskiybsimubiujwuchsl"
SNAP = "2026-09-12"
PULLED_AT = "2026-09-12T12:55:00Z"
LEAGUE_ID = "848938"

TEAMS = {
"Noted Hana Guys": [("Drake Maye","QB","NE"),("Travis Etienne Jr.","RB","NO"),("Blake Corum","RB","LAR"),("Rashee Rice","WR","KC"),("Nico Collins","WR","HOU"),("Jayden Reed","WR","GB"),("Brock Bowers","TE","LV"),("Kenneth Walker","RB","KC"),("RJ Harvey","RB","DEN"),("Chris Rodriguez Jr.","RB","JAX"),("Jakobi Meyers","WR","JAX"),("Tank Bigsby","RB","PHI"),("Brenton Strange","TE","JAX"),("Brandon Aubrey","K","DAL"),("Chargers","DEF","LAC")],
"Tiny Hands": [("Josh Allen","QB","BUF"),("Bijan Robinson","RB","ATL"),("Aaron Jones Sr.","RB","MIN"),("Jaxon Smith-Njigba","WR","SEA"),("Tetairoa McMillan","WR","CAR"),("Rome Odunze","WR","CHI"),("Dallas Goedert","TE","PHI"),("Rachaad White","RB","WAS"),("Deebo Samuel Sr.","WR","SF"),("Tyjae Spears","RB","TEN"),("Trevor Lawrence","QB","JAX"),("Dontayvion Wicks","WR","PHI"),("Keenan Allen","WR","IND"),("Harrison Mevis","K","LAR"),("Vikings","DEF","MIN")],
"McCaffrican Pickens": [("Caleb Williams","QB","CHI"),("Christian McCaffrey","RB","SF"),("David Montgomery","RB","HOU"),("George Pickens","WR","DAL"),("Ladd McConkey","WR","LAC"),("Garrett Wilson","WR","NYJ"),("Dalton Kincaid","TE","BUF"),("Rico Dowdle","RB","PIT"),("Terry McLaurin","WR","WAS"),("Marvin Harrison Jr.","WR","ARI"),("Jacory Croskey-Merritt","RB","WAS"),("Matthew Golden","WR","GB"),("Denzel Boston","WR","CLE"),("Tyler Bass","K","BUF"),("Patriots","DEF","NE")],
"Good Morning My Nabers": [("Jalen Hurts","QB","PHI"),("Breece Hall","RB","NYJ"),("Javonte Williams","RB","DAL"),("Jaylen Waddle","WR","DEN"),("DK Metcalf","WR","PIT"),("Josh Downs","WR","IND"),("Isaiah Likely","TE","NYG"),("MarShawn Lloyd","RB","GB"),("Michael Pittman Jr.","WR","PIT"),("Travis Kelce","TE","KC"),("Stefon Diggs","WR","WAS"),("Josh Jacobs","RB","GB"),("Jonathon Brooks","RB","CAR"),("Jake Bates","K","DET"),("Lions","DEF","DET")],
"The Achilles Heals": [("Joe Burrow","QB","CIN"),("Ashton Jeanty","RB","LV"),("Cam Skattebo","RB","NYG"),("Emeka Egbuka","WR","TB"),("Christian Watson","WR","GB"),("Parker Washington","WR","JAX"),("Colston Loveland","TE","CHI"),("Jeremiyah Love","RB","ARI"),("Mike Evans","WR","SF"),("TreVeyon Henderson","RB","NE"),("Quentin Johnston","WR","LAC"),("Jonah Coleman","RB","DEN"),("Pat Bryant","WR","DEN"),("Cameron Dicker","K","LAC"),("Jaguars","DEF","JAX")],
"Jackson Goff": [("Lamar Jackson","QB","BAL"),("Quinshon Judkins","RB","CLE"),("Jadarian Price","RB","SEA"),("Puka Nacua","WR","LAR"),("Tee Higgins","WR","CIN"),("Courtland Sutton","WR","DEN"),("Mark Andrews","TE","BAL"),("Omarion Hampton","RB","LAC"),("Tony Pollard","RB","TEN"),("Carnell Tate","WR","TEN"),("Jared Goff","QB","DET"),("Xavier Worthy","WR","KC"),("Makai Lemon","WR","PHI"),("Ka'imi Fairbairn","K","HOU"),("Seahawks","DEF","SEA")],
"Imitative deception": [("Kyler Murray","QB","MIN"),("Jonathan Taylor","RB","IND"),("Saquon Barkley","RB","PHI"),("CeeDee Lamb","WR","DAL"),("Michael Wilson","WR","ARI"),("Romeo Doubs","WR","NE"),("Harold Fannin Jr.","TE","CLE"),("J.K. Dobbins","RB","DEN"),("Jerry Jeudy","WR","CLE"),("Terrance Ferguson","TE","LAR"),("Tutu Atwell","WR","LAR"),("Kaelon Black","RB","SF"),("Emmett Johnson","RB","KC"),("Daniel Carlson","K","NO"),("Raiders","DEF","LV")],
"Hurts Donut": [("Dak Prescott","QB","DAL"),("De'Von Achane","RB","MIA"),("Kyren Williams","RB","LAR"),("DeVonta Smith","WR","PHI"),("DJ Moore","WR","BUF"),("Jameson Williams","WR","DET"),("Tucker Kraft","TE","GB"),("D'Andre Swift","RB","CHI"),("Baker Mayfield","QB","TB"),("Jaylen Warren","RB","PIT"),("Chris Godwin Jr.","WR","TB"),("Alec Pierce","WR","IND"),("Tyler Loop","K","BAL"),("Titans","DEF","TEN"),("Broncos","DEF","DEN")],
"Amon-Ra Martyr Brown": [("Jaxson Dart","QB","NYG"),("Derrick Henry","RB","BAL"),("James Cook III","RB","BUF"),("Amon-Ra St. Brown","WR","DET"),("Jordan Addison","WR","MIN"),("Tre Tucker","WR","LV"),("Juwan Johnson","TE","NO"),("Jordan Mason","RB","MIN"),("Rashid Shaheed","WR","SEA"),("Zach Charbonnet","RB","SEA"),("Ray Davis","RB","BUF"),("Greg Dulcich","TE","MIA"),("Ja'Kobi Lane","WR","BAL"),("Cairo Santos","K","CHI"),("Eagles","DEF","PHI")],
"Fear Boners": [("Jayden Daniels","QB","WAS"),("Jahmyr Gibbs","RB","DET"),("Bhayshul Tuten","RB","JAX"),("A.J. Brown","WR","NE"),("Davante Adams","WR","LAR"),("Luther Burden III","WR","CHI"),("Tyler Warren","TE","IND"),("Jalen Coker","WR","CAR"),("George Kittle","TE","SF"),("De'Zhaun Stribling","WR","SF"),("KC Concepcion","WR","CLE"),("Tyler Allgeier","RB","ARI"),("Cam Little","K","JAX"),("Steelers","DEF","PIT"),("Packers","DEF","GB")],
"OnlyLinks": [("Matthew Stafford","QB","LAR"),("Chase Brown","RB","CIN"),("Bucky Irving","RB","TB"),("Drake London","WR","ATL"),("Chris Olave","WR","NO"),("Malik Nabers","WR","NYG"),("Sam LaPorta","TE","DET"),("Rhamondre Stevenson","RB","NE"),("Brian Thomas Jr.","WR","JAX"),("Jordan Love","QB","GB"),("Wan'Dale Robinson","WR","TEN"),("Woody Marks","RB","HOU"),("Jake Ferguson","TE","DAL"),("Will Reichard","K","MIN"),("Rams","DEF","LAR")],
"Benny and the Jets": [("Justin Herbert","QB","LAC"),("Chuba Hubbard","RB","CAR"),("Kenny Gainwell","RB","TB"),("Ja'Marr Chase","WR","CIN"),("Justin Jefferson","WR","MIN"),("Zay Flowers","WR","BAL"),("Trey McBride","TE","ARI"),("Adonai Mitchell","WR","NYJ"),("Kyle Monangai","RB","CHI"),("Kyle Pitts Sr.","TE","ATL"),("Mike Washington Jr.","RB","LV"),("Bo Nix","QB","DEN"),("Khalil Shakir","WR","BUF"),("Jason Myers","K","SEA"),("Texans","DEF","HOU")],
}

TRANSACTIONS = [
("2026-09-11","Hurts Donut","add/drop","Titans",{"acquired_via":"Free Agent","dropped":"Keaton Mitchell (LAC - RB) to Waivers"}),
("2026-09-10","Amon-Ra Martyr Brown","add/drop","Ja'Kobi Lane",{"acquired_via":"Free Agent","dropped":"Malik Davis (Dal - RB, Out) to Waivers"}),
("2026-09-10","Fear Boners","add/drop","Packers",{"acquired_via":"Free Agent","dropped":"Malik Washington (Mia - WR) to Free Agent"}),
("2026-09-10","Fear Boners","add/drop","Malik Washington",{"acquired_via":"Free Agent","dropped":"Jalen McMillan (TB - WR, Doubtful) to Waivers"}),
("2026-09-09","Noted Hana Guys","add/drop","Brenton Strange",{"acquired_via":"Free Agent","dropped":"Kaleb Johnson (GB - RB) to Waivers"}),
("2026-09-08","Tiny Hands","waiver claim","Keenan Allen",{"cost":"$2","dropped":"Calvin Ridley (Ten - WR) to Waivers"}),
("2026-09-08","Tiny Hands","waiver claim","Rachaad White",{"cost":"$5","dropped":"George Holani (Sea - RB) to Waivers"}),
("2026-09-05","Imitative deception","add/drop","Raiders",{"acquired_via":"Free Agent","dropped":"Ravens (Bal - DEF) to Waivers"}),
("2026-09-05","Tiny Hands","add/drop","Calvin Ridley",{"acquired_via":"Free Agent","dropped":"Omar Cooper Jr. (NYJ - WR) to Waivers"}),
("2026-09-05","Good Morning My Nabers","add/drop","Lions",{"acquired_via":"Free Agent","dropped":"Tyreek Hill (Mia - WR, NA) to Waivers"}),
("2026-09-05","Good Morning My Nabers","waiver claim","Jake Bates",{"cost":"$0","dropped":"Rachaad White (Was - RB) to Waivers"}),
("2026-09-05","Tiny Hands","waiver claim","Deebo Samuel Sr.",{"cost":"$0","dropped":"Tre' Harris (LAC - WR) to Waivers"}),
("2026-09-05","Tiny Hands","waiver claim","George Holani",{"cost":"$0","dropped":"Ja'Kobi Lane (Bal - WR) to Waivers"}),
("2026-09-05","Noted Hana Guys","waiver claim","Kaleb Johnson",{"cost":"$0","dropped":"Patrick Mahomes (KC - QB) to Waivers"}),
("2026-09-05","The Achilles Heals","waiver claim","Pat Bryant",{"cost":"$0","dropped":"Brock Purdy (SF - QB) to Waivers"}),
("2026-09-05","Fear Boners","waiver claim","Jalen McMillan",{"cost":"$1","dropped":"Keenan Allen (Ind - WR) to Waivers"}),
("2026-09-05","Fear Boners","waiver claim","Steelers",{"cost":"$1","dropped":"Jordyn Tyson (NO - WR, IR-R) to Waivers"}),
("2026-09-05","Amon-Ra Martyr Brown","waiver claim","Greg Dulcich",{"cost":"$1","dropped":"Dalton Schultz (Hou - TE) to Waivers"}),
("2026-09-05","Amon-Ra Martyr Brown","waiver claim","Malik Davis",{"cost":"$2","dropped":"Malik Willis (Mia - QB) to Waivers"}),
("2026-09-03","Fear Boners","trading_list",None,{"note":"QB/WR/RB/TE/W-R-T wanted; A.J. Brown, Luther Burden III, Bhayshul Tuten, Tyler Warren, George Kittle listed available (no trade executed); outside 7-day window, kept for completeness"}),
]

def q(v):
    if v is None: return "NULL"
    return "'" + str(v).replace("'", "''") + "'"

def run(ref, sql):
    p = subprocess.run(SUPA + [ref, sql], capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        print("SQL FAILED:", p.stderr[:400]); sys.exit(1)
    return p.stdout

import sys as _sys
_sys.path.insert(0, "/home/hatch/workspace/football-signal/engine")
import snapshot as _snap
_ALIASES = {"hollywood brown": "marquise brown", "kenny gainwell": "kenneth gainwell",
            "scotty miller": "scott miller"}

def norm(name):
    # must match engine.snapshot.norm_loose + fantasypros loader aliases,
    # otherwise is_rostered joins in the VORP views silently miss players
    # (e.g. Jaxon Smith-Njigba, Cam Skattebo).
    return _snap.norm_loose(_ALIASES.get(_snap.norm(name), name))

# --- uso-yahoo ---
run(YAHOO, f"""insert into yahoo_leagues (league_id, name, season, settings, extracted_at) values
({q(LEAGUE_ID)}, {q('USO Season XVIII')}, 2026,
 {q(json.dumps({'scoring':'half-PPR','teams':12,'starters':['QB','2 RB','3 WR','TE','W/R/T','K','DEF'],'bench':5,'trade_deadline':'2026-11-28','mahomes_status':'on waivers; dropped by Noted Hana Guys 2026-09-05'}) )},
 {q(PULLED_AT)})
on conflict (league_id) do update set name=excluded.name, season=excluded.season,
settings=excluded.settings, extracted_at=excluded.extracted_at;""")

trows = ",\n".join(f"({q(LEAGUE_ID)},{q(SNAP)},{q(t)},NULL,{str(t=='Tiny Hands').lower()})" for t in TEAMS)
run(YAHOO, f"insert into yahoo_teams (league_id,snapshot_date,team_name,manager,is_user) values {trows};")

rrows = []
for t, pls in TEAMS.items():
    for name, pos, nfl in pls:
        rrows.append(f"({q(LEAGUE_ID)},{q(SNAP)},{q(t)},{q(name)},{q(nfl)},{q(pos)},NULL,NULL)")
run(YAHOO, f"insert into yahoo_rosters (league_id,snapshot_date,team_name,player_name,nfl_team,position,slot,status) values " + ",\n".join(rrows) + ";")

t2 = []
for d, team, typ, pname, det in TRANSACTIONS:
    det2 = dict(det); det2["txn_date"] = d
    t2.append(f"({q(LEAGUE_ID)},{q(PULLED_AT)},{q(typ)},{q(team)},{q(pname)},{q(json.dumps(det2))})")
run(YAHOO, f"insert into yahoo_transactions (league_id,pulled_at,type,team_name,player_name,detail) values " + ",\n".join(t2) + ";")

# --- football project snapshot refresh ---
srows = []
for t, pls in TEAMS.items():
    for name, pos, nfl in pls:
        srows.append(f"({q(SNAP)},{q(t)},{q(name)},{q(norm(name))},{q(pos)},{q(nfl)})")
run(FB, "delete from yahoo_rostered_snapshot where snapshot_date=" + q(SNAP) + ";")
run(FB, "insert into yahoo_rostered_snapshot (snapshot_date,team_name,player_name,player_norm,pos,nfl_team) values " + ",\n".join(srows) + ";")
run(FB, "delete from yahoo_rosters where league_id=" + q(LEAGUE_ID) + " and snapshot_date=" + q(SNAP) + ";")
run(FB, "insert into yahoo_rosters (league_id,snapshot_date,team_name,player_name,nfl_team,position) values " + ",\n".join(
    f"({q(LEAGUE_ID)},{q(SNAP)},{q(t)},{q(n)},{q(nfl)},{q(p)})" for t, pls in TEAMS.items() for n, p, nfl in pls) + ";")
# fix known 2026-09-11 defect: Caleb Williams duplicated on OnlyLinks
run(FB, "delete from yahoo_rostered_snapshot where snapshot_date='2026-09-11' and team_name='OnlyLinks' and player_name='Caleb Williams';")
run(FB, "delete from yahoo_rosters where league_id=" + q(LEAGUE_ID) + " and snapshot_date='2026-09-11' and team_name='OnlyLinks' and player_name='Caleb Williams';")

print("counts:")
print(run(YAHOO, "select count(*) as rosters from yahoo_rosters where snapshot_date='2026-09-12';"))
print(run(YAHOO, "select count(*) as txns from yahoo_transactions;"))
print(run(FB, "select count(*) as snap from yahoo_rostered_snapshot where snapshot_date='2026-09-12';"))
print(run(FB, "select count(*) as onlylinks_caleb from yahoo_rostered_snapshot where snapshot_date='2026-09-11' and team_name='OnlyLinks' and player_name='Caleb Williams';"))
