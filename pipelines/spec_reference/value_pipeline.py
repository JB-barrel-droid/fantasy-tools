"""Source-neutral value pipeline, clean-room (JEG-508).

Written only from docs/methodology.md "Value Pipeline (source-neutral,
2026-10-09)", steps VP-0..VP-12 and the decided OC table, plus the data
formats of the inputs. It shares no code with, and was written without
reading, the engine (curve-widget.js, value-model.js) or the Python reference
(pipelines/value_reference.py). Where the text leaves a detail open the most
literal reading is taken and recorded in SPEC_AMBIGUITIES.md (ids SA-n are
cited inline).

Entry points:
- run_week(...)      one week at one league setting (VP-2 .. VP-7).
- run(...)           both weeks plus the change (VP-8).
- included_set(...)  VP-1.

The result of run_week is shaped like `expected` in
tests/fixtures/value_pipeline_worked_example.json (schema /2), so the fixture
test can walk every pinned leaf. Player keys are ints throughout; the caller
converts at the edges.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

POSITIONS = ("QB", "RB", "WR", "TE")
POS_ORDER = {p: i for i, p in enumerate(POSITIONS)}
GROUP_KEYS = tuple(f"{p}|{r}" for p in POSITIONS for r in ("starter", "bench"))

BENCH_MIX_12 = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}
IMPUTE_MIN_FIT = 3
ESTIMATE_FIT_N = 10
DEFAULT_BENCH_SHARE = 0.15
PIE_PER_STARTING_SLOT = 28.0

PROJECTION = "projection"
CHART = "chart"


@dataclass
class Setting:
    """League setting L (VP-0)."""
    teams: int
    slots: dict                       # dedicated slots per team, {pos: D_p}
    flex: int = 1                     # F
    superflex: int = 0                # SF
    bench_per_team: float = 6         # B
    bench_share: float = DEFAULT_BENCH_SHARE
    flex_eligible: tuple = ("RB", "WR", "TE")
    position_shares: dict | None = None   # reader position shares (VP-4.4)

    @classmethod
    def from_fixture(cls, s: dict) -> "Setting":
        return cls(teams=int(s["teams"]), slots=dict(s["slots"]), flex=int(s.get("flex", 0)),
                   superflex=int(s.get("superflex", 0)),
                   bench_per_team=s.get("bench_per_team", 6),
                   bench_share=float(s.get("bench_share", DEFAULT_BENCH_SHARE)),
                   flex_eligible=tuple(s.get("flex_eligible") or ("RB", "WR", "TE")),
                   position_shares=s.get("position_shares"))

    def starting_slots_per_team(self) -> int:
        return sum(int(self.slots.get(p, 0)) for p in POSITIONS) + self.flex + self.superflex

    def pie(self) -> float:
        """VP-5.1 (OC-1): 28 per starting slot."""
        return PIE_PER_STARTING_SLOT * self.teams * self.starting_slots_per_team()


# ---------------------------------------------------------------- helpers

def round_half_up(x) -> int:
    f = Fraction(x)
    return int((f + Fraction(1, 2)) // 1)


def median(values: list) -> float:
    v = sorted(values)
    n = len(v)
    if n % 2:
        return v[n // 2]
    return (v[n // 2 - 1] + v[n // 2]) / 2.0


def fsum_in_order(values) -> float:
    """Plain left-to-right double sum (VP-0: sums run in sort order)."""
    total = 0.0
    for x in values:
        total += x
    return total


def included_set(eligible: list, has_prior: dict) -> tuple[list, bool]:
    """VP-1.2. Returns (I, has_prior_week)."""
    with_prior = [s for s in eligible if has_prior.get(s)]
    if with_prior:
        return with_prior, True
    return list(eligible), False


# ---------------------------------------------------------------- VP-0 m

def mean_ppg(sources: dict, included: list, pos_of: dict) -> dict:
    """m_i: mean of the natives of the projections in I that list i."""
    acc: dict = {}
    for s in included:
        src = sources.get(s)
        if not src or src["family"] != PROJECTION:
            continue
        for k, x in src["values"].items():
            if pos_of.get(k) in POS_ORDER and x is not None:
                acc.setdefault(k, []).append(float(x))
    return {k: fsum_in_order(v) / len(v) for k, v in acc.items()}


def score_order(scores: dict, pos_of: dict) -> dict:
    """{pos: [keys]} by score descending, then player_key ascending."""
    out = {p: [] for p in POSITIONS}
    for k in scores:
        p = pos_of.get(k)
        if p in out:
            out[p].append(k)
    for p in out:
        out[p].sort(key=lambda k: (-scores[k], k))
    return out


# ---------------------------------------------------------------- VP-2.2 allocation

def dhondt_bench(teams: int, bench_per_team) -> dict:
    seats = round_half_up(Fraction(teams) * Fraction(str(bench_per_team)))
    got = {p: 0 for p in POSITIONS}
    for _ in range(seats):
        best = None
        for p in POSITIONS:   # position order breaks ties (strict > keeps the first)
            q = Fraction(BENCH_MIX_12[p], got[p] + 1)
            if best is None or q > best[0]:
                best = (q, p)
        got[best[1]] += 1
    return got


def allocate(setting: Setting, order: dict, scores: dict) -> dict:
    """League allocation (VP-2.2 a-e) on a per-position order with scores."""
    T = setting.teams
    ded = {p: T * int(setting.slots.get(p, 0)) for p in POSITIONS}

    def take(cands: list, n: int) -> dict:
        cands.sort(key=lambda kp: (-scores[kp[0]], POS_ORDER[kp[1]], kp[0]))
        got = {p: 0 for p in POSITIONS}
        for _, p in cands[:max(0, n)]:
            got[p] += 1
        return got

    sf_cands = [(k, p) for p in POSITIONS for k in order[p][ded[p]:]]
    sf = take(sf_cands, T * setting.superflex)
    fx_cands = [(k, p) for p in POSITIONS if p in setting.flex_eligible
                for k in order[p][ded[p] + sf[p]:]]
    fx = take(fx_cands, T * setting.flex)
    bench = dhondt_bench(T, setting.bench_per_team)
    out = {}
    for p in POSITIONS:
        starters = ded[p] + sf[p] + fx[p]
        out[p] = {"dedicated": ded[p], "superflex": sf[p], "flex": fx[p], "bench": bench[p],
                  "starters": starters, "rostered": starters + bench[p]}
    return out


# ---------------------------------------------------------------- VP-2.4 fill-in

def _sorted_listed(values: dict, keys) -> list:
    return sorted(keys, key=lambda k: (-values[k], k))


def estimate_player(c: str, i: int, p: str, listed_c: list, natives: dict, peers: list,
                    peer_listed: dict, m: dict) -> dict:
    """One estimate for chart c, player i at position p (VP-2.4 d-f).

    listed_c: c's listed players at p in c's sort order.
    natives:  {source: {key: native}} listed natives only (overlay applied).
    peer_listed: {peer: set of keys the peer lists at p}.
    """
    nat_c = natives[c]
    rec: dict = {"peers": {}, "cap": nat_c[listed_c[-1]]}
    ests = []
    for k in peers:
        nat_k = natives[k]
        if i not in nat_k:
            continue
        shared = [j for j in listed_c if j in peer_listed[k]]
        fit = shared[-min(ESTIMATE_FIT_N, len(shared)):] if shared else []
        num = fsum_in_order(nat_c[j] for j in fit)
        den = fsum_in_order(nat_k[j] for j in fit)
        entry = {"fit_players": list(fit), "num": num, "den": den, "peer_native": nat_k[i]}
        if len(fit) < IMPUTE_MIN_FIT or den <= 0:
            entry.update(usable=False, ratio=None, estimate=None,
                         reason="fit set under 3" if len(fit) < IMPUTE_MIN_FIT else "peer sum <= 0")
        else:
            ratio = num / den
            est = ratio * nat_k[i]
            entry.update(usable=True, ratio=ratio, estimate=est)
            ests.append(est)
        rec["peers"][k] = entry
    if ests:
        rec["path"] = "peers"
        raw = median(ests)
    else:
        rec["path"] = "curve"
        pts = [j for j in listed_c if j in m]
        pts = pts[-min(ESTIMATE_FIT_N, len(pts)):] if pts else []
        mi = m[i]
        if len(pts) >= IMPUTE_MIN_FIT and len({m[j] for j in pts}) > 1:
            mx = fsum_in_order(m[j] for j in pts) / len(pts)
            xx = fsum_in_order(nat_c[j] for j in pts) / len(pts)
            sxy = fsum_in_order((m[j] - mx) * (nat_c[j] - xx) for j in pts)
            sxx = fsum_in_order((m[j] - mx) ** 2 for j in pts)
            b = sxy / sxx
            a = xx - b * mx
            raw = a + b * mi
            rec["curve"] = {"kind": "ols", "points": pts, "slope": b, "intercept": a, "mean_ppg": mi}
        else:
            pos_m = [j for j in listed_c if j in m and m[j] > 0]
            if pos_m:
                low = pos_m[-1]
                raw = nat_c[low] * mi / m[low]
                rec["curve"] = {"kind": "proportional", "points": pts, "low": low, "mean_ppg": mi}
            else:
                raw = 0.0
                rec["curve"] = {"kind": "zero", "points": pts, "mean_ppg": mi}
    cap = rec["cap"]
    rec["raw"] = raw
    rec["value"] = min(max(raw, 0.0), cap)
    rec["capped"] = raw > cap
    return rec


# ---------------------------------------------------------------- one source, VP-2/3

def price_source(s: str, family: str, natives: dict, pos_of: dict, alloc: dict,
                 fill_sets: dict | None, peers: list, m: dict, bs: float) -> dict:
    """VP-2 (work lists, waiver/starter lines, slices) and VP-3 for one source."""
    nat = natives[s]
    listed_by_pos = {p: [] for p in POSITIONS}
    for k in nat:
        p = pos_of.get(k)
        if p in listed_by_pos:
            listed_by_pos[p].append(k)
    positions, players = {}, {}
    groups = {g: 0.0 for g in GROUP_KEYS}
    for p in POSITIONS:
        a = alloc[p]
        listed = _sorted_listed(nat, listed_by_pos[p])
        estimates = {}
        if family == CHART and fill_sets is not None and listed:
            listed_set = set(listed)
            peer_listed = {k: {j for j in natives[k] if pos_of.get(j) == p} for k in peers}
            for i in fill_sets[p]:
                if i not in listed_set:
                    estimates[i] = estimate_player(s, i, p, listed, natives, peers, peer_listed, m)
        work_val = {k: nat[k] for k in listed}
        work_val.update({i: e["value"] for i, e in estimates.items()})
        work = sorted(work_val, key=lambda k: (-work_val[k], k in estimates, k))
        N, S = a["rostered"], a["starters"]
        info = dict(a)
        info.update(listed=len(listed), extended=bool(estimates),
                    imputation_ratios=estimates or None)
        if len(work) > N:
            w = work_val[work[N]]
            method = "estimated" if work[N] in estimates else "roster_determined"
        elif work:
            w = work_val[work[-1]]
            method = "insufficient_coverage"
        else:
            info.update(waiver_value=None, starter_line=None, method="no_players")
            positions[p] = info
            continue
        line = work_val[work[S]] if len(work) > S else w
        line = max(line, w)
        info.update(waiver_value=w, starter_line=line, method=method)
        positions[p] = info
        g_s, g_b = [], []
        for rank, k in enumerate(work, start=1):
            x = work_val[k]
            v = max(0.0, x - w)
            bsl = max(0.0, min(x, line) - w)
            ssl = max(0.0, x - line)
            role = "starter" if rank <= S else ("bench" if rank <= N else "waiver")
            players[k] = {"pos": p, "native": x, "imputed": k in estimates, "rank": rank,
                          "role": role, "vorp": v, "bench_slice": bsl, "starter_slice": ssl}
            g_s.append(ssl)
            g_b.append(bsl)
        groups[f"{p}|starter"] = fsum_in_order(g_s)
        groups[f"{p}|bench"] = fsum_in_order(g_b)
    total = fsum_in_order(groups[g] for g in GROUP_KEYS)
    st_tot = fsum_in_order(groups[f"{p}|starter"] for p in POSITIONS)
    be_tot = fsum_in_order(groups[f"{p}|bench"] for p in POSITIONS)
    has_weights = total != 0
    sig = {p: groups[f"{p}|starter"] / st_tot for p in POSITIONS} if has_weights and st_tot > 0 else None
    beta = {p: groups[f"{p}|bench"] / be_tot for p in POSITIONS} if has_weights and be_tot > 0 else None
    weights = None
    if has_weights:
        weights = {}
        for p in POSITIONS:
            if sig is not None and beta is not None:
                weights[f"{p}|starter"] = (1 - bs) * sig[p]
                weights[f"{p}|bench"] = bs * beta[p]
            elif sig is not None:          # bench mix undefined
                weights[f"{p}|starter"] = sig[p]
                weights[f"{p}|bench"] = 0.0
            else:                          # starter mix undefined
                weights[f"{p}|starter"] = 0.0
                weights[f"{p}|bench"] = beta[p]
    return {"family": family, "positions": positions, "groups": groups, "total_vorp": total,
            "players": players, "weights": weights, "starter_mix": sig, "bench_mix": beta,
            "has_weights": has_weights}


# ---------------------------------------------------------------- VP-4

def ddf_weights(priced: dict, included: list, bs: float, position_shares: dict | None) -> tuple:
    S_raw, B_raw = {}, {}
    for p in POSITIONS:
        s_vals, b_vals = [], []
        for s in included:
            r = priced.get(s)
            if not r or not r["has_weights"] or r["positions"][p]["method"] == "no_players":
                continue
            if r["starter_mix"] is not None:
                s_vals.append(r["starter_mix"][p])
            if r["bench_mix"] is not None:
                b_vals.append(r["bench_mix"][p])
        S_raw[p] = fsum_in_order(s_vals) / len(s_vals) if s_vals else 0.0
        B_raw[p] = fsum_in_order(b_vals) / len(b_vals) if b_vals else 0.0
    s_sum = fsum_in_order(S_raw[p] for p in POSITIONS)
    b_sum = fsum_in_order(B_raw[p] for p in POSITIONS)
    if b_sum == 0:
        bs_star = 0.0
    elif s_sum == 0:
        bs_star = 1.0
    else:
        bs_star = bs
    W = {}
    for p in POSITIONS:
        W[f"{p}|starter"] = (1 - bs_star) * S_raw[p] / s_sum if s_sum else 0.0
        W[f"{p}|bench"] = bs_star * B_raw[p] / b_sum if b_sum else 0.0
    if position_shares:
        for p in POSITIONS:
            tot = W[f"{p}|starter"] + W[f"{p}|bench"]
            if tot == 0 or p not in position_shares:
                continue
            share = float(position_shares[p])
            for r in ("starter", "bench"):
                W[f"{p}|{r}"] = W[f"{p}|{r}"] * share / tot
    return S_raw, B_raw, bs_star, W


# ---------------------------------------------------------------- VP-5

def adjust_source(r: dict, pie: float, W: dict) -> None:
    budgets = {g: pie * W[g] for g in GROUP_KEYS}
    G = r["groups"]
    moved, unpaid = [], []
    bprime = dict(budgets)
    for p in POSITIONS:
        for a_role, b_role in (("starter", "bench"), ("bench", "starter")):
            g, other = f"{p}|{a_role}", f"{p}|{b_role}"
            if G[g] == 0 and budgets[g] > 0:
                if G[other] > 0:
                    bprime[other] += budgets[g]
                    bprime[g] = 0.0
                    moved.append({"from": g, "to": other, "budget": budgets[g]})
                else:
                    unpaid.append({"group": g, "budget": budgets[g]})
    if not r["has_weights"]:
        rates = {g: 0.0 for g in GROUP_KEYS}
    else:
        rates = {g: (bprime[g] / G[g] if G[g] != 0 else 0.0) for g in GROUP_KEYS}
    factor = pie / r["total_vorp"] if r["has_weights"] else 0.0
    for k, pl in r["players"].items():
        p = pl["pos"]
        pl["adjusted"] = rates[f"{p}|bench"] * pl["bench_slice"] + rates[f"{p}|starter"] * pl["starter_slice"]
        pl["vorp_display"] = pl["vorp"] * factor
    r["rates"] = rates
    r["unfunded_moved"] = moved
    r["unfunded_groups"] = unpaid
    r["vorp_display_factor"] = factor
    r["budgets_paid"] = bprime


# ---------------------------------------------------------------- VP-6 rows

def row_value(r: dict, family: str, k: int, p: str, view: str):
    """VP-6.2: (value, estimated_path_or_None)."""
    if r["positions"][p]["method"] == "no_players":
        return None, None
    pl = r["players"].get(k)
    if pl is not None:
        return pl[view], (r["positions"][p]["imputation_ratios"] or {}).get(k, {}).get("path") if pl["imputed"] else None
    if family == CHART:
        return 0.0, None          # below rosterable depth
    return None, None             # projection that does not list him


def ddf_version(values: dict, members: list) -> dict:
    used = [(s, values[s]) for s in members if values.get(s) is not None]
    if not used:
        return {"value": None, "count": 0, "low_confidence": False, "sources": [],
                "reason": "No source prices this player"}
    val = fsum_in_order(v for _, v in used) / len(used)
    out = {"value": val, "count": len(used), "low_confidence": len(used) == 1,
           "sources": [s for s, _ in used]}
    if len(used) == 1:
        out["reason"] = "Only one source prices this player"
    return out


# ---------------------------------------------------------------- one week

def run_week(setting: Setting, pos_of: dict, sources: dict, included: list,
             selection: list | None = None, names: dict | None = None) -> dict:
    """VP-2 .. VP-7 for one week.

    sources: {key: {"family": "projection"|"chart", "values": {player_key: native}}}
             in source-key display order; natives already carry the superflex
             overlay. Every source here is shown (VP-1.4); only `included`
             counts.
    selection: the reader's input selection (VP-1.5); filters DDF averaging only.
    """
    bs = setting.bench_share
    natives = {s: {int(k): float(v) for k, v in src["values"].items()
                   if v is not None and pos_of.get(int(k)) in POS_ORDER}
               for s, src in sources.items()}
    family = {s: src["family"] for s, src in sources.items()}
    inc = [s for s in included if s in sources]
    proj_in = [s for s in inc if family[s] == PROJECTION]
    m = mean_ppg({s: {"family": family[s], "values": natives[s]} for s in sources}, inc, pos_of)
    pie = setting.pie()
    degenerate = not proj_in
    if not degenerate:
        p_order = score_order(m, pos_of)
        alloc = allocate(setting, p_order, m)
        fill_sets = {p: p_order[p][:alloc[p]["rostered"] + 1] for p in POSITIONS}
    else:   # VP-2.2 f (SA-3)
        alloc, fill_sets, p_order = None, None, None
    peers_all = sorted(s for s in inc if family[s] == CHART)
    priced = {}
    for s in sources:
        if degenerate:
            own = score_order(natives[s], pos_of)
            a = allocate(setting, own, natives[s])
        else:
            a = alloc
        peers = [k for k in peers_all if k != s]
        priced[s] = price_source(s, family[s], natives, pos_of, a, fill_sets, peers, m, bs)
        priced[s]["status"] = "included" if s in inc else sources[s].get("status", "excluded")
        priced[s]["allocation"] = a
    S_raw, B_raw, bs_star, W = ddf_weights(priced, inc, bs, setting.position_shares)
    for s in sources:
        adjust_source(priced[s], pie, W)

    # rows: every player any source lists (VP-6.1)
    row_keys = sorted({k for s in sources for k in natives[s]})
    sel = set(selection) if selection is not None else None
    members = {
        "blended": [s for s in inc if sel is None or s in sel],
        "charts": [s for s in inc if family[s] == CHART and (sel is None or s in sel)],
        "projections": [s for s in inc if family[s] == PROJECTION and (sel is None or s in sel)],
    }
    rows = {}
    for k in row_keys:
        p = pos_of[k]
        adj, vorp, est = {}, {}, {}
        for s in sources:
            a_v, path = row_value(priced[s], family[s], k, p, "adjusted")
            v_v, _ = row_value(priced[s], family[s], k, p, "vorp_display")
            adj[s], vorp[s] = a_v, v_v
            if path:
                est[s] = path
        rows[k] = {"name": (names or {}).get(k), "pos": p, "adjusted": adj, "vorp_vs_waivers": vorp,
                   "estimated": est,
                   "ddf_blended": ddf_version(adj, members["blended"]),
                   "ddf_charts": ddf_version(adj, members["charts"]),
                   "ddf_projections": ddf_version(adj, members["projections"]),
                   "mean_ppg": m.get(k)}

    # VP-6.4 Indexed, every chart (held ones too)
    indexed = {}
    for s in sources:
        if family[s] != CHART:
            continue
        r = priced[s]
        shared = [k for k in sorted(natives[s], key=lambda k: (POS_ORDER[pos_of[k]], -natives[s][k], k))
                  if rows[k]["ddf_blended"]["value"] is not None]
        ddf_tot = fsum_in_order(rows[k]["ddf_blended"]["value"] for k in shared)
        nat_tot = fsum_in_order(natives[s][k] for k in shared)
        f = ddf_tot / nat_tot if shared and nat_tot > 0 else None
        vals = {}
        for k in row_keys:
            p = pos_of[k]
            if r["positions"][p]["method"] == "no_players":
                vals[k] = None
            elif k in r["players"]:
                vals[k] = r["players"][k]["native"] * f if f is not None else None
            else:
                vals[k] = 0.0     # below rosterable depth (VP-6.2), even with no factor (SA-9)
        indexed[s] = {"factor": f, "shared_players": len(shared), "ddf_total": ddf_tot,
                      "native_total": nat_tot, "values": vals}
        r["indexed_factor"] = f
        for k in row_keys:
            rows[k].setdefault("indexed", {})[s] = vals[k]

    # VP-7 slot fill and tiers
    if degenerate:
        ddf_scores = {k: rows[k]["ddf_blended"]["value"] for k in row_keys
                      if rows[k]["ddf_blended"]["value"] is not None}
        slot_fill = allocate(setting, score_order(ddf_scores, pos_of), ddf_scores)
    else:
        slot_fill = alloc
    for p in POSITIONS:
        ranked = [k for k in row_keys if pos_of[k] == p and rows[k]["ddf_blended"]["value"] is not None]
        ranked.sort(key=lambda k: (-rows[k]["ddf_blended"]["value"],
                                   0 if k in m else 1, -m.get(k, 0.0), k))
        for rank, k in enumerate(ranked, start=1):
            v = rows[k]["ddf_blended"]["value"]
            if v == 0:
                t = "waiver"
            elif rank <= slot_fill[p]["starters"]:
                t = "starter"
            elif rank <= slot_fill[p]["rostered"]:
                t = "bench"
            else:
                t = "waiver"
            rows[k]["ddf_tier"] = t
    for k in row_keys:
        rows[k].setdefault("ddf_tier", None)
        rows[k].setdefault("indexed", {})
    ranking = sorted(row_keys, key=lambda k: (rows[k]["ddf_blended"]["value"] is None,
                                              -(rows[k]["ddf_blended"]["value"] or 0.0), k))
    budgets = {g: pie * W[g] for g in GROUP_KEYS}
    src_out = {}
    for s in sources:
        r = priced[s]
        src_out[s] = {k: r[k] for k in ("family", "status", "positions", "groups", "total_vorp",
                                        "players", "weights", "starter_mix", "bench_mix", "rates",
                                        "unfunded_moved", "unfunded_groups", "vorp_display_factor",
                                        "indexed_factor") if k in r}
        if degenerate:
            src_out[s]["allocation"] = r["allocation"]
    return {
        "included": inc,
        "pie": pie,
        "starting_slots_per_team": setting.starting_slots_per_team(),
        "bench_share_applied": bs_star,
        "mean_ppg": m,
        "allocation": alloc,
        "fill_sets": fill_sets,
        "sources": src_out,
        "starter_mix_mean": S_raw,
        "bench_mix_mean": B_raw,
        "ddf_weights": W,
        "group_budgets": budgets,
        "indexed": indexed,
        "slot_fill_mean_ppg": slot_fill,
        "default_ranking": ranking,
        "rows": rows,
    }


# ---------------------------------------------------------------- VP-8

VERSIONS = (("blended", "ddf_blended"), ("charts", "ddf_charts"), ("projections", "ddf_projections"))


def run(setting: Setting, pos_of: dict, current: dict, prior: dict | None, included: list,
        selection: list | None = None, names: dict | None = None,
        prior_pos_of: dict | None = None) -> dict:
    """Both weeks and the change. `prior` holds only sources with a prior
    snapshot; the prior week uses the same I and setting (VP-8.1)."""
    cur = run_week(setting, pos_of, current, included, selection, names)
    out = {"current": cur, "prior": None}
    if prior:
        prior_src = {s: prior[s] for s in included if s in prior}
        pw = run_week(setting, prior_pos_of or pos_of, prior_src, included, selection, names)
        out["prior"] = pw
        for k, row in cur["rows"].items():
            prow = pw["rows"].get(k)
            for _, field_ in VERSIONS:
                c = row[field_]
                pv = prow[field_] if prow else None
                c["prior"] = pv["value"] if pv else None
                c["prior_count"] = pv["count"] if pv else 0
                c["prior_low_confidence"] = pv["low_confidence"] if pv else False
                c["change"] = (c["value"] - c["prior"]) if (c["value"] is not None and c["prior"] is not None) else None
    return out
