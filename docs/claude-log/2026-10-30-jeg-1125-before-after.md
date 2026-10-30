# JEG-1125 option A: before and after

Option A makes one "even" band for every trade call: a net counts as even when it is under max(1 point, 3% of the average side). Compare's verdict, Compare's Deal read and Find a trade all use it. Before, the Deal read used this band but the verdict and Find a trade called anything that showed as 0.1 or more a win or a loss. The 5% thin margin rule is separate and unchanged.

Branch `fe/jeg-1125-even-threshold`, draft PR #1033. Nothing is merged or deployed.

## Data used

- Values: published sources, week 8 of the 2026 season, Half PPR, 12 teams, your USO lineup. They were computed with the edge function's own pipeline on the repo's main build (76c12c2). The live endpoint couldn't be reached from here.
- Rosters: your USO league, read today. Kickers and defenses were skipped. Kenny Gainwell (Benny and the Jets) has no price, so he isn't in any trade.
- League page fit and bench share are modeled the same way the connector models them.
- Only Half PPR was measured. The band doesn't depend on scoring, so Standard and PPR move the same way, but the counts there weren't run.

## Your league: Tiny Hands against the other 11 teams

| | Before | After A |
|---|---|---|
| League page trades listed | 1,208 | 1,294 |
| Natural fit | 32 | 35 |
| Market fit | 770 | 764 |
| Force fit | 406 | 495 |
| Find a trade, raw count (up to 2 for 2) | 1,643 | 1,721 |

884 trades are on both lists, and none of their Compare answers change.

### 324 trades leave the list

Your DDF Value edge on these was only 0.05 to 2.82 points, which is inside the band, so A calls them even. One of them has an edge of exactly 1.00. A trade has to clear the band, so 1.00 on a small trade counts as even.

What Compare showed for these before A:

- Verdict: win.
- Deal read: already even on value (281 "even, market says lose", 41 "even, market even", 2 "even, market says win").
- "Should you propose?": already Unclear (Low).

After A, only the verdict changes, from win to even, and it now agrees with the Deal read.

By fit: 221 market, 97 force, 6 natural.

Example: you give Deebo Samuel Sr. + T.J. Hockenson to Jackson My Purdy Brock and get Tre Tucker + Tyler Higbee. Your edge is +0.99. Before, the verdict said win and the Deal read said even. Now both say even.

### 410 trades join the list

On these, 1 to 3 trade charts had you up by 0.06 to 2.46 points. A counts those charts as even, so the other team breaks even there and the trade qualifies. 328 trades have one such chart, 75 have two, and 7 have three.

How Compare's answers change on these trades:

- "Will they accept?":
  - Toss-up (Low) to Likely (High): 305
  - Unlikely (High) to Likely (High): 49
  - Toss-up (Low) to Likely (Low): 47
  - Unlikely (Low) to Likely (Low): 9
- Deal read title:
  - "Value win, but the trade charts split" to "Value win at a fair market price": 223
  - "Value win, but the trade charts split" to "DDF Value likes it. The market doesn't.": 111
  - "Win, but a hard sell" to "Value win, but the trade charts split": 30
- "Should you propose?":
  - Yes (Medium) to Yes (Low): 238
  - Yes (High) to Yes (Low): 31

The propose answer drops a level because a chart that leaned slightly your way now counts as even, not as agreeing.

By fit: 215 market, 186 force, 9 natural.

Example: you give Deebo Samuel Sr. + Keenan Allen to Good Morning My Nabers and get Braelon Allen + Josh Downs. Your edge is +4.93, and FantasyCalc had you up 0.50. Before, the Deal read said the charts split and "Will they accept?" said Toss-up (Low). Now FantasyCalc counts as even, the read is "Value win at a fair market price" and accept is Likely (High), with 3 of 4 charts.

### Top 10 by edge

The first five don't change. These four are new:

- Good Morning My Nabers: Deebo Samuel Sr. + Keenan Allen for Braelon Allen + Josh Downs (+4.93)
- Fear Boners: T.J. Hockenson + Treylon Burks for Kaelon Black + Seth McGowan (+4.76)
- Amon-Ra Martyr Brown: Deebo Samuel Sr. + Keenan Allen for Zach Charbonnet + Devaughn Vele (+4.54)
- Good Morning My Nabers: Deebo Samuel Sr. for Braelon Allen (+4.12)

### Trades per opponent, before and after

| Team | Before | After |
|---|---|---|
| Amon-Ra Martyr Brown | 139 | 149 |
| Benny and the Jets | 49 | 40 |
| Fear Boners | 80 | 99 |
| Good Morning My Nabers | 93 | 103 |
| Hurts Donut | 115 | 115 |
| Imitative deception | 170 | 163 |
| Jackson My Purdy Brock | 159 | 194 |
| Lisan Al-Caleb | 92 | 121 |
| Noted Hana Guys | 118 | 130 |
| OnlyLinks | 93 | 92 |
| The Achilles Heals | 100 | 88 |

### The trade from JEG-886: Hall + Higgins for Nacua

Before, the charts split and "Will they accept?" said Unlikely, with 1 of 3 charts. After A, the read is "value win, market even", not a split, and accept is Likely, with 2 of 3 charts.

## League-wide check: the 20-team test league

This is the repo's 20-team fixture, with team 0 against the other 19, up to 2 for 2.

| | Before | After A | Rival side only (the earlier estimate) |
|---|---|---|---|
| Find a trade count | 7,241 | 7,208 | 8,502 |
| Natural fit | 200 | 176 | 227 |
| Market fit | 4,312 | 4,006 | 4,725 |
| Force fit | 1,181 | 1,467 | 1,736 |
| Fit total | 5,693 | 5,649 | 6,688 |

The earlier estimate of about 8,500 applied the band only to the other team's side. A also applies it to your DDF edge, so Find a trade never lists a trade that Compare would call "Even on value". That takes trades off the list as well as adding them, so the total barely moves.

## Not changed

- The 5% thin margin rule.
- How a fit label is judged for any one trade. A changes which trades are on the list, not the fit of a trade that stays on it.
- The VORP rows in Compare use the same band now. They read the same win, even and lose rule as everything else.
