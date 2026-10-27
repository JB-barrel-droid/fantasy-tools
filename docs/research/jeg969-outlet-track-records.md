# JEG-969 Lane C: Outlet Track Records — Who Makes Each Source and How Accurate Are They?

Written 2026-10-23. All external figures are attributed to the publishing source
and year; "not found" means no published evidence was located. Internal backtest
data from lane B is cited where it intersects. Full citations in sources.md.

---

## 1. Projection Sources (used in DDF Value)

### ESPN Projections

| Field | Detail |
|-------|--------|
| **Who/what** | Mike Clay's hybrid model: expert analysis + IBM watsonx ML pipeline. Clay was inducted into the FSWA Hall of Fame in 2025. ESPN describes the system as a "hybrid" combining statistical models with expert overrides. |
| **Method** | Algorithmic base (deep neural nets, strength-of-schedule, regression) with manual expert adjustments. Week-ahead and rest-of-season projections published. Updated at least weekly. |
| **Independent accuracy** | FFA 11-season (2015-2025) QB MAE: 6.38 (middle of pack among 9 sources). RB MAE: 5.23 (#3 of 9). TE MAE: 3.85 (#1 of 9 over 7+ seasons). MASE 2012-2016: .647 (#8 of 12). |
| **Our data** | Lane B: ESPN week-ahead MAE 4.499 (2026 wk 1-6, 1,812 player-weeks). Indistinguishable from RotoWire (paired diff CI includes zero). |
| **Position notes** | Strong at TE, middling at QB. All sources over-project QBs. |

### CBS Rest-of-Season Projections

| Field | Detail |
|-------|--------|
| **Who/what** | Editorial team: Jamey Eisenberg (senior fantasy writer), Dave Richard (15+ year veteran, also authors the trade chart), Heath Cummings. Expert-driven, not a disclosed statistical model. |
| **Method** | Human expert projections updated weekly. ROS format. Also published through SportsLine with extended analysis. |
| **Independent accuracy** | FFA 11-season QB MAE: 6.23 (#3 of 9). Recent 3-season QB MAE: 6.13 (best). RB MAE: best of 9 over 12 seasons in the season-long study. MASE 2012-2016: .649 (#9 of 12, near ESPN). |
| **Our data** | Not yet testable head-to-head (no stored week-ahead captures; pending JEG-944). |
| **Position notes** | Historically strong at RB. Recent QB improvement (best over last 3 years per FFA). |

### Razzball Projections

| Field | Detail |
|-------|--------|
| **Who/what** | Rudy Gamble, Razzball co-founder. Sole author of football projections. Won FantasyPros "Best Bold Ranker" 2017-2019. Known for baseball (Steamer collaboration). |
| **Method** | Proprietary model by a single analyst. Preseason projections free; in-season weekly projections are subscription. |
| **Independent accuracy** | Not tracked as a named source in the FFA multi-year study or the FantasyPros projection comparisons. Gamble appears as an individual ranker on FantasyPros (ranked 9th-most accurate in one week of 2022; not a consistent top-10 finisher in full-season results). No multi-season accuracy study found. |
| **Our data** | Not yet testable (no stored week-ahead captures). |
| **Position notes** | Insufficient external evidence to assess position-level strengths. |

### RotoWire / Sleeper (fourth source, pending #850)

| Field | Detail |
|-------|--------|
| **Who/what** | RotoWire editorial staff; Paul Mammino leads the ranking process. Statistical projections combined with expert adjustments. Sleeper uses RotoWire projections as its default. |
| **Method** | Statistical base (historical performance, usage trends, efficiency, SOS, regression indicators, injury probability) with expert overlay. Published week-ahead and ROS. |
| **Independent accuracy** | FFA does not break out RotoWire as a named source in recent studies. Not found in FantasyPros projection-source accuracy rankings. |
| **Our data** | Lane B: RotoWire week-ahead MAE 4.495 (2026 wk 1-6). Indistinguishable from ESPN. 8-season stability: CV of per-season MAE = 0.09. QB positive bias +3.4 ppg. |
| **Position notes** | Stable multi-year track record from our own data. QB overshoot consistent with industry-wide pattern. |

---

## 2. Trade Chart Sources (shown alongside DDF Value)

### FantasyPros Trade Value Chart

| Field | Detail |
|-------|--------|
| **Who/what** | Derived from Expert Consensus Rankings (ECR): aggregation of 150+ individual rankers weighted by accuracy. Not a single author. |
| **Method** | ECR rankings converted to trade values via auction-price framework. Updated weekly. Effectively a crowd aggregate of expert opinion. |
| **Accuracy evidence** | FantasyPros ECR-based projections are the most accurate single "source" in FFA's 12-season study: QB MAE 6.20 (#1), 28 of 44 top-three finishes across positions. This is the wisdom-of-crowds effect. |

### CBS Sports Trade Value Chart

| Field | Detail |
|-------|--------|
| **Who/what** | Dave Richard, sole author for 15+ years. |
| **Method** | Expert-driven: expected future performance, schedule, and public sentiment. Not model-derived. Weekly updates. |
| **Accuracy evidence** | No published accuracy study of trade chart values vs realized outcomes found. |

### USA Today Trade Value Chart

| Field | Detail |
|-------|--------|
| **Who/what** | Not found. No USA Today-authored fantasy football trade value chart located in web search. USA Today's fantasy content appears to syndicate CBS Sports/SportsLine material under the USA Today SMG umbrella. |
| **Method** | Not found. |
| **Accuracy evidence** | Not found. |

### FantasyCalc

| Field | Detail |
|-------|--------|
| **Who/what** | Anonymous creator. Algorithmic, not expert-driven. |
| **Method** | Revealed-preference model: values derived from 1.2M+ actual completed trades across real leagues (MFL, Sleeper). Updated continuously. |
| **Accuracy evidence** | No published accuracy study found. Methodology is theoretically aligned with "trades others will accept" framing (revealed vs stated preference). |

---

## 3. What the Accuracy Evidence Shows

### The aggregation premium is real and consistent

Every multi-year study reaches the same conclusion:

- FFA (12 seasons): aggregate projections beat every single source every year.
  Simple average MASE .569 vs best individual source .587 (Yahoo).
- FantasyPros ECR is the most accurate "source" precisely because it IS an aggregate.
- R-bloggers (2012-2016): combined projections more accurate than all single
  sources every year.
- Academic literature (PMC 2025): collective predictions outperform individuals.
- Jayanti/Wharton (2026): industry hybrid models maintain superior MAE over pure ML.

### Individual sources cluster tightly

| Source | MASE (2012-2016) | QB MAE (11-season) | RB MAE (11-season) |
|--------|-------------------|--------------------|--------------------|
| FantasyPros (aggregate) | .573 | 6.20 (#1) | 5.22 (#2) |
| ESPN | .647 | 6.38 (#6) | 5.23 (#3) |
| CBS | .649 | 6.23 (#3) | best (season-long) |

ESPN and CBS are close to each other and both midpack among single sources.
RotoWire is not separately tracked but our lane B data shows it ties ESPN.

### Razzball is the least-evidenced source

No multi-year accuracy study includes Razzball as a named projection source.
The "Best Bold Ranker" awards measure contrarian accuracy, not overall accuracy.

### Trade charts have no published accuracy validation

No study was found comparing trade chart values to realized outcomes. FantasyCalc's
revealed-preference approach is most directly aligned with "trades others will accept."

---

## 4. Implications for DDF Value Weighting

### Cross-check with lane B

Lane B tested 6 aggregators and found no alternative beats equal weights. The
external evidence is consistent: sources cluster tightly, no runaway winner to
upweight, simple average matches or beats weighted average.

### What the evidence could justify

1. Adding sources helps more than re-weighting existing ones.
2. Razzball is the weakest link by evidence (not by demonstrated poor performance).
3. Position-specific adjustments are premature.
4. QB bias correction is strong signal but lane B showed it makes things worse
   because expected-starts already handles the same effect.

### Confidence levels

- **High confidence** that equal weights are not leaving significant accuracy on
  the table right now.
- **Medium confidence** that adding RotoWire as fourth source will help.
- **Low confidence** on any specific source deserving more or less credit.

---

## 5. Options for Jeremy

### Option A: Keep equal weights, add RotoWire as fourth equal source (RECOMMENDED)

Equal weight across all sources, expanding from 3 to 4 when #850 merges.

For: consistent with all external evidence and our own backtest. Adding a source
is the highest-expected-value change. No risk of overfitting.

Against: if Razzball is genuinely noisier, equal weight dilutes slightly.

### Option B: Keep equal weights among existing three, wait on RotoWire

Do nothing until more week-ahead captures accumulate (estimated December 2026).

For: maximum caution. Against: aggregation premium from fourth source likely positive.

### Option C: Downweight Razzball (e.g., 30/30/30/10 or 33/33/33/0)

Reduce Razzball's influence due to least external accuracy evidence.

For: epistemically honest. Against: absence of evidence is not evidence of absence.
Lane B found no weighting scheme beats equal weights. Removing a source reduces
aggregation premium.

### Option D: Weight by inverse historical MAE once data is available

Commit to accuracy-based weighting when JEG-944 delivers enough data.

For: principled and data-driven. Against: lane B early results show inverse-error
weighting produces negligible improvement (MAE diff +0.001, CI spans zero).

---

*No code changes proposed. This is a research-only deliverable.*
