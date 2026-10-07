"""Disagreement detection: Vegas-implied vs position-specific ECR.

v2 methodology (per user feedback):
- Comparisons are cut by position (QB/RB/WR/TE). Overall ECR ranks mix
  positions with wildly different scoring baselines, so the rank delta is
  computed within each position group.
- ECR publishes ranks, not points, so both sides are reduced to an ordering
  *within the position* over the same player universe (players having both
  props and an ECR entry):
      delta = ecr_pos_rank - vegas_pos_rank
  Positive delta => the market is higher on the player than the experts.
- Where expert projected points exist they ride along for display
  (expert_ppg). FantasyPros only exposes top-10-per-position draft
  projections without auth, so this is elite-only until the weekly
  projections feed is wired.
"""

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from engine.fds_fallback import is_fds_prov  # noqa: E402

NEW_THRESHOLD = 8       # |delta| spots: movement-classification band for classify_event


def _ct_stamp(iso_or_ts) -> str | None:
    """Compact as-of stamp for the thread hook: 'Fri 2:46p CT'.

    Accepts an ISO-8601 string (assumed UTC if naive) or a POSIX timestamp.
    """
    try:
        if isinstance(iso_or_ts, (int, float)):
            dt = datetime.fromtimestamp(iso_or_ts, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(iso_or_ts))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        ct = dt.astimezone(ZoneInfo("America/Chicago"))
        h = ct.hour % 12 or 12
        ap = "a" if ct.hour < 12 else "p"
        return f"{ct:%a} {h}:{ct:%M}{ap} CT"
    except Exception:
        return None
WIDEN_BY = 5            # delta growth to flag a widening signal
CLOSE_BELOW = 4         # |delta| decay below this => signal closed

# --- injury sub-lines for thread tweets ----------------------------------
# Notable injury info = Questionable/Doubtful status in the injuries table
# (the pipeline sets sig["injury_flag"], e.g. "Questionable (ankle)"),
# and/or a short practice/news snippet in sig["injury_note"]
# (e.g. "limited in practice"). Healthy players with no news carry neither
# field and get no sub-line — never add noise.

# nflverse practice-participation statuses -> short thread note.
# (The injuries table carries one row per source; a player can have both a
# Sleeper game-status row and an nflverse practice row.)
_PRACTICE_NOTES = {
    "Limited Participation in Practice": "limited in practice",
    "Did Not Participate In Practice": "did not practice",
}

# Headlines that clear a player (not concern) — never notable.
_NEWS_CLEARANCE = ("off injury report", "sheds injury tag", "expected to play",
                   "cleared", "full participation", "practicing fully",
                   "practiced fully", "full practice", "practiced", "will play")
# Body-part vocabulary for "{part} injury" snippet extraction. "back" is
# deliberately excluded — too often a verb ("came back").
_BODY_PARTS = ("ankle", "calf", "knee", "hamstring", "shoulder", "groin",
               "hip", "neck", "elbow", "wrist", "hand", "finger",
               "toe", "foot", "leg", "arm", "chest", "rib", "quad", "acl",
               "mcl", "concussion", "illness", "oblique", "achilles")
# Capitalized words that may sit between a name and its injury clause
# without meaning another person is involved.
_NEWS_SPAN_OK = {"week", "fantasy", "football", "injury", "report", "update",
                 "news", "practice", "limited", "full", "questionable",
                 "doubtful", "ir", "vs"}


def practice_note(statuses: list) -> str | None:
    """Short note from a player's injury-table statuses, or None.

    Only practice-participation rows qualify (a 'Full Participation' row is
    not notable). Callers decide whether the player is notable enough to
    carry a sub-line; this just translates the status.
    """
    for st in statuses or []:
        if st in _PRACTICE_NOTES:
            return _PRACTICE_NOTES[st]
    return None


def news_injury_snippet(title: str, player_name: str,
                        body_part: str | None = None) -> str | None:
    """Conservative injury-note extraction from a news headline.

    `player_name` may be the full name or just the last name. Returns a
    short (<=60 char) snippet when the headline is genuinely about THIS
    player's injury concern, else None. Guards:
      - the player's last name must appear in the headline;
      - clearance headlines ("off injury report", "expected to play",
        "practicing fully", ...) are never notable;
      - the injury/concern clause must FOLLOW the player's name (the name is
        the subject of the clause), word-boundaried ("calf" must not match
        "Metcalf", "foot" must not match "football");
      - no other person-name may sit between the player's name and the
        clause ("Egbuka full, Jalen McMillan limited at practice" is about
        McMillan, not Egbuka);
      - body parts only count as "{part} injury" phrases ("came back" is a
        verb, not a back injury).
    A teammate's injury mentioned elsewhere in the same headline never
    attaches.
    """
    t = (title or "").lower()
    raw = title or ""
    parts = (player_name or "").split()
    ln = parts[-1].lower() if parts else ""
    own = {p.lower() for p in parts}
    if not ln or ln not in t:
        return None
    if any(c in t for c in _NEWS_CLEARANCE):
        return None
    name_hits = list(re.finditer(re.escape(ln), t))
    if not name_hits:
        return None

    def _clean_span(name_end: int, kw_start: int) -> bool:
        span = raw[name_end:kw_start]
        for w in re.findall(r"[A-Za-z]{3,}", span):
            if w.lower() in own or w.lower() in _NEWS_SPAN_OK:
                continue
            if w[0].isupper():
                return False
        return True

    def _after(phrase: str, window: int = 30) -> bool:
        pat = re.compile(r"\b" + re.escape(phrase) + r"\b")
        for nm in name_hits:
            for m in pat.finditer(t):
                if 0 <= m.start() - nm.end() <= window \
                        and _clean_span(nm.end(), m.start()):
                    return True
        return False

    if _after("did not participate") or _after("dnp"):
        return "did not practice"
    if _after("limited") and "practice" in t:
        return "limited in practice"
    if body_part:
        bp = body_part.lower()
        if _after(f"{bp} injury", 40) or _after(f"{bp} injured", 40):
            return f"{bp} injury"
    for bp in _BODY_PARTS:
        if _after(f"{bp} injury") or _after(f"{bp} injured"):
            return f"{bp} injury"
    if _after("unsure") or _after("50-50"):
        return "status unsure"
    if _after("game-time"):
        return "game-time decision"
    if _after("will miss"):
        return "will miss"
    if _after("sidelined"):
        return "sidelined"
    if _after("doubtful"):
        return "doubtful"
    if _after("questionable"):
        return "questionable"
    return None


def thread_injury_subline(sig: dict) -> str | None:
    """Optional injury sub-line for thread group tweets, or None.

    Format: `  ⚠️ {injury_flag} — {injury_note}`; whichever half exists is
    rendered alone (e.g. `  ⚠️ Questionable (ankle) — limited in practice`).
    Called at pack time so the sub-line stays beneath its player's line and
    counts toward the tweet's 280-char (_x_len) budget.
    """
    flag = (sig.get("injury_flag") or "").strip()
    note = (sig.get("injury_note") or "").strip()
    if not flag and not note:
        return None
    sub = "  \u26a0\ufe0f"
    if flag:
        sub += f" {flag}"
    if note:
        sub += f" \u2014 {note}"
    return sub

# --- v3: points-delta post-worthiness -------------------------------------
# A rank gap alone is noise (20 spots between two 3-pt players means
# nothing). A signal is post-worthy only if BOTH hold:
#   1. |pts_delta| >= PTS_DELTA_MIN (PPR) — the point disagreement is real.
#   2. max(vegas, expert) >= POS_FLOOR[pos] — at least one side prices the
#      player as a real contributor, not roster filler.
# Floors differ by position because scoring baselines do: a 7-pt TE week
# matters, a 7-pt QB week is a disaster.
PTS_DELTA_MIN = 2.0
POS_FLOOR = {'QB': 10.0, 'RB': 7.0, 'WR': 7.0, 'TE': 5.0}


def post_worthy(sig: dict) -> tuple[bool, str]:
    """Decide whether a signal deserves a post. Returns (worthy, reason).

    The points gate runs on the LEVEL-ADJUSTED delta (pts_delta_adj):
    Vegas and ECR sit at systematically different levels (Vegas runs
    cool), so the 2.0 bar must measure genuine disagreement, not the
    house level gap. Falls back to the raw delta when no adjusted value
    was computed (legacy/backtest dicts).
    """
    pos = sig.get('pos', '')
    floor = POS_FLOOR.get(pos, 7.0)
    raw = sig.get('pts_delta_ppr')
    adj = sig.get('pts_delta_adj', raw)
    pd = abs(adj if adj is not None else 0.0)
    peak = max(sig.get('vegas_ppr') or 0.0, sig.get('expert_ppr') or 0.0)
    pos_label = pos or 'player'
    if pd < PTS_DELTA_MIN:
        return False, (
            f"gap {pd:.1f} pts is under our {PTS_DELTA_MIN:.1f}-pt bar "
            f"for a real disagreement")
    if peak < floor:
        return False, (
            f"roster-filler zone: best projection {peak:.1f} pts is under "
            f"the {pos_label} contributor line ({floor:.0f} pts)")
    # PMM-plain flag reason (2026-09-17): the gate scores the NET-OF-TILT
    # gap, but the raw Vegas/ECR numbers are what a reader can check, so
    # the reason shows both and explains the tilt in one clause. Never
    # restate the adjusted gap as if it were the raw visible gap.
    v = sig.get('vegas_ppr')
    e = sig.get('expert_ppr')
    v_s = f"{v:.1f}" if v is not None else "n/a"
    e_s = f"{e:.1f}" if e is not None else "n/a"
    gap = sig.get('pos_level_gap')
    if gap is None:
        tilt_clause = "a {pd:.1f}-pt real disagreement".format(pd=pd)
    else:
        tilt_word = 'below' if gap < 0 else 'above'
        tilt_clause = (
            f"Vegas usually prices {pos_label}s about {abs(gap):.1f} pts "
            f"{tilt_word} the experts; against that normal tilt, this is "
            f"a {pd:.1f}-pt real disagreement")
    hotter = "Vegas is hotter than the experts" if (
        adj if adj is not None else 0.0) >= 0 else \
        "The experts are hotter than Vegas"
    return True, (
        f"{hotter} (Vegas {v_s} vs experts {e_s} PPR). {tilt_clause} — "
        f"past our {PTS_DELTA_MIN:.1f}-pt bar.")


def rank_deltas(vegas_points: dict, ecr_ranks: dict) -> list[dict]:
    """Legacy overall-universe comparison (kept for backtests).
    vegas_points: {player_key: implied_pts}, ecr_ranks: {player_key: ecr_rank}.
    Returns list of dicts sorted by |delta| desc."""
    common = set(vegas_points) & set(ecr_ranks)
    ordered = sorted(common, key=lambda k: vegas_points[k], reverse=True)
    vegas_rank = {k: i + 1 for i, k in enumerate(ordered)}
    out = []
    for k in common:
        d = ecr_ranks[k] - vegas_rank[k]
        out.append({
            'player_key': k,
            'vegas_points': round(vegas_points[k], 2),
            'vegas_rank': vegas_rank[k],
            'ecr_rank': ecr_ranks[k],
            'delta': d,
            'abs_delta': abs(d),
            'direction': 'vegas_high' if d > 0 else 'experts_high' if d < 0 else 'agree',
        })
    return sorted(out, key=lambda r: r['abs_delta'], reverse=True)


def rank_deltas_by_position(vegas_by_pos: dict, ecr_by_pos: dict,
                            expert_ppg: dict | None = None,
                            expert_pts: dict | None = None,
                            official_pos_rank: dict | None = None,
                            meta: dict | None = None) -> list[dict]:
    """Position-aware disagreement (v3).

    vegas_by_pos: {pos: {player_key: {'std':x,'half':y,'ppr':z}}}
                  (a bare float is treated as PPR)
    ecr_by_pos:   {pos: {player_key: ecr_position_rank}} (numeric, e.g. 12 for QB12)
    expert_pts:   {player_key: {'std':x,'half':y,'ppr':z}} expert projected
                  pts/game (a bare float is treated as PPR)
    expert_ppg:   legacy alias for a single-number expert projection (PPR)
    official_pos_rank: {player_key: 'QB12'} display string (optional)
    meta: {player_key: {'name':..., 'team':...}} (optional)

    IMPORTANT: both sides must be on the same basis. Early Vegas snapshots
    had no TD markets, so the expert projections had to be stripped of TD
    points too for apples-to-apples. v4+ is TD-inclusive on both sides
    (the ECR feed's projections include TDs; Vegas adds Poisson E[TDs]
    from anytime-TD props).

    Within each position, ranks are computed over the intersection universe
    (players present on both sides) so the delta is apples-to-apples.
    Every signal gets pts_delta_ppr and a post-worthy verdict; the list is
    sorted by |pts_delta| desc (the points delta is the story, rank gap
    second).
    """

# --- injury sub-lines for thread tweets (approved 2026-09-11) ------------
# Notable injury info = Questionable/Doubtful status in the injuries table
# (the pipeline sets sig["injury_flag"], e.g. "Questionable (ankle)"),
# and/or a short practice/news snippet in sig["injury_note"]
# (e.g. "limited in practice"). Healthy players with no news carry neither
# field and get no sub-line — never add noise.
    expert_ppg = expert_ppg or {}
    expert_pts = dict(expert_pts or {})
    for k, v in expert_ppg.items():
        expert_pts.setdefault(k, v)
    official_pos_rank = official_pos_rank or {}
    meta = meta or {}

    def _tri(v):
        if isinstance(v, dict):
            return v
        return {'std': v, 'half': v, 'ppr': v}

    out = []
    for pos, vpts in vegas_by_pos.items():
        eranks = ecr_by_pos.get(pos, {})
        common = [k for k in vpts if k in eranks]
        if not common:
            continue
        vrank = {k: i + 1 for i, k in
                 enumerate(sorted(common, key=lambda k: _tri(vpts[k])['ppr'], reverse=True))}
        erank = {k: i + 1 for i, k in
                 enumerate(sorted(common, key=lambda k: eranks[k]))}
        for k in common:
            d = erank[k] - vrank[k]
            m = meta.get(k, {})
            vp = _tri(vpts[k])
            ep = _tri(expert_pts.get(k))
            pts_delta = None
            if ep.get('ppr') is not None:
                pts_delta = round(vp['ppr'] - ep['ppr'], 2)
            sig = {
                'player_key': k,
                'pos': pos,
                'name': m.get('name', k),
                'team': m.get('team', ''),
                'vegas_std': (round(vp['std'], 2)
                              if vp['std'] is not None else None),
                'vegas_half': (round(vp['half'], 2)
                               if vp['half'] is not None else None),
                'vegas_ppr': (round(vp['ppr'], 2)
                              if vp['ppr'] is not None else None),
                'expert_std': ep.get('std'),
                'expert_half': ep.get('half'),
                'expert_ppr': ep.get('ppr'),
                'pts_delta_ppr': pts_delta,
                'vegas_pos_rank': vrank[k],
                'ecr_pos_rank': erank[k],
                'ecr_official': official_pos_rank.get(k, ''),
                'n_pos': len(common),
                'delta': d,
                'abs_delta': abs(d),
                'direction': 'vegas_high' if d > 0 else 'experts_high' if d < 0 else 'agree',
            }
            sig = {
                'player_key': k,
                'pos': pos,
                'name': m.get('name', k),
                'team': m.get('team', ''),
                'vegas_std': (round(vp['std'], 2)
                              if vp['std'] is not None else None),
                'vegas_half': (round(vp['half'], 2)
                               if vp['half'] is not None else None),
                'vegas_ppr': (round(vp['ppr'], 2)
                              if vp['ppr'] is not None else None),
                'expert_std': ep.get('std'),
                'expert_half': ep.get('half'),
                'expert_ppr': ep.get('ppr'),
                'pts_delta_ppr': pts_delta,
                'vegas_pos_rank': vrank[k],
                'ecr_pos_rank': erank[k],
                'ecr_official': official_pos_rank.get(k, ''),
                'n_pos': len(common),
                'delta': d,
                'abs_delta': abs(d),
                'direction': 'vegas_high' if d > 0 else 'experts_high' if d < 0 else 'agree',
            }
            out.append(sig)
    # --- level adjustment (2026-09-13): Vegas and ECR sit at systematically
    # different levels (Vegas runs cool). The post-worthy gate must measure
    # genuine disagreement, not the house level gap, so every signal gets a
    # de-meaned delta: pts_delta_adj = raw_delta − position mean(raw_delta)
    # over the full intersection universe. Display copy (draft_post,
    # build_thread) keeps showing the RAW numbers — they are the verifiable
    # facts; only the gate uses the adjusted value.
    _level = {}
    for _pos in {s['pos'] for s in out}:
        _ds = [s['pts_delta_ppr'] for s in out
               if s['pos'] == _pos and s['pts_delta_ppr'] is not None]
        if _ds:
            _level[_pos] = sum(_ds) / len(_ds)
    for sig in out:
        _pd = sig['pts_delta_ppr']
        _gap = _level.get(sig['pos'], 0.0)
        sig['pos_level_gap'] = round(_gap, 2)
        sig['pts_delta_adj'] = round(_pd - _gap, 2) if _pd is not None else None
        worthy, reason = post_worthy(sig)
        sig['post_worthy'] = worthy
        sig['worthy_reason'] = reason
    return sorted(out, key=lambda r: (abs(r['pts_delta_adj']
                                         if r['pts_delta_adj'] is not None
                                         else (r['pts_delta_ppr'] or 0)),
                                         r['abs_delta']),
                  reverse=True)


def classify_event(prev_delta: int | None, curr_delta: int,
                   prev_abs: int | None = None) -> str | None:
    """Given a player's previous and current delta, decide what happened."""
    curr_abs = abs(curr_delta)
    if prev_delta is None:
        return 'new' if curr_abs >= NEW_THRESHOLD else None
    prev_abs = abs(prev_delta) if prev_abs is None else prev_abs
    if prev_abs < NEW_THRESHOLD and curr_abs >= NEW_THRESHOLD:
        return 'new'
    if curr_abs < CLOSE_BELOW <= prev_abs:
        return 'closing'
    if curr_abs >= prev_abs + WIDEN_BY:
        return 'widening'
    if prev_abs >= curr_abs + WIDEN_BY:
        return 'narrowing'
    return None


def _fmt_pts(x) -> str:
    return f"{x:.1f}" if x is not None else "n/a"


# --- X character counting -------------------------------------------------
# X counts some symbols as 2 characters (verified 2026-09-11: each ▼/▲
# counts 2 — a 6-line group tweet measured 2 over the 280 limit while
# len() said it fit). Pack thread tweets with _x_len(), not len().
_X_DOUBLE = set("\u25bc\u25b2\u26a0\ufe0f\U0001f9f5")


def _x_len(s: str) -> int:
    """Approximate X's character count: astral-plane chars and known
    double-width symbols (▼ ▲ ⚠ 🧵) count 2, everything else counts 1."""
    return sum(2 if (ord(ch) > 0xFFFF or ch in _X_DOUBLE) else 1 for ch in s)


def draft_post(sig: dict, event: str, meta: dict | None = None,
               week: int | None = None) -> str:
    """Single post text (<=280 X-counted chars). Points only — no ranks.

    Approved 2026-09-11 format (as posted for Week 1), repointed 2026-09-12
    per the ECR-supplies-both framework (the expert points number is the
    ECR feed's expert projection):
        MARKET vs EXPERTS — Wk 1
        ▼ J. Love, RB, ARI
        vegas implied fantasy points 9.9 vs ECR 14.7 (Δ -4.8)
        ⚠️ Questionable (ankle)
    The injury line appears only when the signal carries an injury_flag.
    ECR supplies position ranks (informational since the 2026-09-11 rank-gate
    elimination) AND the expert point projections. Ranks never appear in
    the post.
    """
    meta = meta or {}
    name = _short_name(meta.get('name', sig.get('name', '')))
    team = meta.get('team', sig.get('team', ''))
    pos = meta.get('pos', sig.get('pos', ''))
    if event == 'new':
        head = "MARKET vs EXPERTS"
    elif event == 'widening':
        head = "GAP WIDENING"
    elif event == 'closing':
        head = "EDGE GONE"
    elif event == 'narrowing':
        head = "GAP NARROWING"
    elif event == 'final_call':
        head = "FINAL CALL"
    elif event == 'scorecard':
        head = "SCORECARD"
    else:
        head = "SIGNAL"
    if week is not None:
        head = f"{head} \u2014 Wk {week}"
    pd = sig.get('pts_delta_ppr')
    # PMM 2026-09-13: the post-worthy gate runs on the level-adjusted delta,
    # so every Δ shows both — the raw gap (verifiable against the printed
    # legs) and the net gap (what actually cleared the bar). Never show a
    # net number alone: readers can subtract the legs and must see the raw
    # figure match.
    pa = sig.get('pts_delta_adj', pd)
    arrow = "\u25b2" if (pd or 0) > 0 else "\u25bc" if (pd or 0) < 0 else ""
    vppr = _fmt_pts(sig.get('vegas_ppr'))
    eppr = _fmt_pts(sig.get('expert_ppr'))
    lines = [head, f"{arrow} {name}, {pos}, {team}".strip()]
    if pd is not None:
        sign = "+" if pd > 0 else ""
        pa_txt = ""
        if pa is not None:
            signa = "+" if pa > 0 else ""
            pa_txt = f", {signa}{pa:.1f} net of house level"
        lines.append(
            f"vegas implied fantasy points {vppr} vs ECR {eppr} "
            f"(\u0394 {sign}{pd:.1f}{pa_txt})"
        )
    else:
        lines.append(f"vegas implied fantasy points {vppr}")
    if is_fds_prov(sig.get("vegas_provenance")):
        # Labeled fallback (2026-09-17): this number is NOT locally
        # calculated from raw sportsbook odds. It is our scoring math
        # applied to First Down Studio's vegas-attributed translated stats
        # (their projection-attributed stats never feed it). It must never
        # be presented as our own raw-odds Vegas math.
        lines.append("Vegas leg: First Down Studio estimates")
    if sig.get('injury_flag'):
        lines.append(f"\u26a0\ufe0f {sig['injury_flag']}")
    text = "\n".join(lines)
    assert _x_len(text) <= 280, f"draft too long ({_x_len(text)}): {text}"
    return text


THREAD_POS_ORDER = ("WR", "RB", "TE", "QB")


# Generational suffixes never count as the last name ("Harold Fannin Jr."
# shortens to "H. Fannin", not "H. Jr.").
_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _short_name(name: str) -> str:
    """First initial + last name: 'C. Tate'."""
    parts = name.split()
    if len(parts) >= 2:
        last = parts[-1]
        if last.rstrip(".").lower() in _NAME_SUFFIXES and len(parts) >= 3:
            last = parts[-2]
        return f"{parts[0][0]}. {last}"
    return name


def build_thread(worthy: list, week: int, sourcing: dict | None = None) -> list:
    """Weekly thread: one tweet per (position, direction) group, points only.

    Order: WR, RB, TE, QB; loves (Vegas high) before fades (Vegas low)
    within a position. Empty groups are skipped. Group tweets carry a
    "— Wk {week}" tag so standalone views stay dated. Players with notable
    injury info (injury_flag / injury_note) get an indented sub-line beneath
    their main line (thread_injury_subline); each player is one indivisible
    block so sub-lines never detach from their player when big groups
    re-split. Every tweet is packed and asserted with _x_len() (X's real
    counting, where ▼/▲ count double) — never len().

    sourcing (optional): {"books": [...], "vegas_at": iso/ts, "ecr_at": iso/ts}
    appends a source line to the hook tweet, e.g.
    "Vegas: DraftKings + FanDuel lines (Odds API) as of Fri 2:46p CT ·
     ECR projections as of Fri 12:11p CT".
    """
    n_up = sum(1 for s in worthy if (s.get("pts_delta_ppr") or 0) > 0)
    n_down = sum(1 for s in worthy if (s.get("pts_delta_ppr") or 0) < 0)
    total = len(worthy)
    if n_up == 0:
        hook = (f"Vegas is lower than the experts on all {total} names this week. "
                "A clean sweep of fades.")
    elif n_down == 0:
        hook = (f"Vegas is higher than the experts on all {total} names this week. "
                "A clean sweep of loves.")
    elif n_up == 1:
        hook = (f"Vegas is down on {n_down} of {total} names vs the experts "
                "this week\u2026 with one exception.")
    elif n_down == 1:
        hook = (f"Vegas is up on {n_up} of {total} names vs the experts "
                "this week\u2026 with one exception.")
    else:
        hook = (f"Vegas and the experts disagree on {total} names this week \u2014 "
                f"{n_up} the market loves, {n_down} it fades.")
    tweets = [
        f"MARKET vs EXPERTS \u2014 NFL Week {week} \U0001f9f5\n{hook} Full-PPR."
    ]
    if sourcing:
        bits = []
        books = sourcing.get("books") or []
        vegas_at = _ct_stamp(sourcing.get("vegas_at")) if sourcing.get("vegas_at") else None
        ecr_at = _ct_stamp(sourcing.get("ecr_at")) if sourcing.get("ecr_at") else None
        if books:
            bits.append(
                f"Vegas: {' + '.join(books)} lines (Odds API)"
                + (f" as of {vegas_at}" if vegas_at else "")
            )
        if ecr_at:
            bits.append(f"ECR projections as of {ecr_at}")
        n_fds = sourcing.get("fds_derived") or 0
        if n_fds:
            # Labeled fallback (2026-09-17): these players' Vegas numbers
            # are our math on First Down Studio's vegas-attributed stat
            # estimates — not our raw sportsbook math.
            # Kept short: the hook tweet is hard-capped at 280 chars and the
            # assert below fails the build loudly if it ever overflows again.
            bits.append(f"{n_fds} via First Down Studio")
        if bits:
            tweets[0] += "\n" + " \u00b7 ".join(bits)
    assert _x_len(tweets[0]) <= 280, f"hook too long: {tweets[0]}"
    # How-to-read card (PMM 2026-09-13): the level adjustment is disclosed
    # up front, in this week's actual number. Vegas usually prices below
    # ECR — that's the house level, not a take — so each Δ shows the raw
    # gap then the net gap, and only net gaps ≥2pts are posted. Stating it
    # here covers the group tweets; singles carry the "net of house level"
    # label on their own Δ line.
    _gaps = [s.get("pos_level_gap") for s in worthy
             if s.get("pos_level_gap") is not None]
    if _gaps:
        _m = sum(_gaps) / len(_gaps)
        _dir = "below" if _m <= 0 else "above"
        _howto = (
            f"How to read: Vegas is running {abs(_m):.1f}pts {_dir} ECR "
            f"this week \u2014 that's the house level, not a take. Each "
            f"\u0394 shows the raw gap, then net of that level; we only "
            f"post gaps that clear 2pts net."
        )
        assert _x_len(_howto) <= 280, f"how-to too long: {_howto}"
        tweets.append(_howto)
    for pos in THREAD_POS_ORDER:
        for direction in ("up", "down"):
            grp = [s for s in worthy
                   if s.get("pos") == pos
                   and ((s.get("pts_delta_ppr") or 0) > 0) == (direction == "up")]
            if not grp:
                continue
            verb = "loves" if direction == "up" else "is fading"
            arrow = "\u25b2" if direction == "up" else "\u25bc"
            blocks = []
            for s in sorted(grp, key=lambda x: abs(x.get("pts_delta_ppr") or 0),
                            reverse=True):
                pd = s.get("pts_delta_ppr") or 0.0
                pa = s.get("pts_delta_adj", pd) or 0.0
                sign = "+" if pd > 0 else ""
                signa = "+" if pa > 0 else ""
                main = (
                    f"{arrow} {_short_name(s.get('name', ''))} ({s.get('team', '')}): "
                    f"{_fmt_pts(s.get('vegas_ppr'))} vs {_fmt_pts(s.get('expert_ppr'))} "
                    f"(\u0394 {sign}{pd:.1f}, {signa}{pa:.1f} net)"
                )
                # A player is one indivisible block: main line plus, when
                # notable injury info exists, the indented sub-line beneath
                # it (approved 2026-09-11). Blocks never split across tweets.
                sub = thread_injury_subline(s)
                blocks.append([main] if sub is None else [main, sub])
            # Pack blocks into <=280-char (X-counted) tweets, splitting big
            # groups. Reserve room for the header including a "(n/n)" split
            # suffix, so no chunk can overflow once finalized.
            header_base = f"{pos}s Vegas {verb} vs the experts"
            week_tag = f" \u2014 Wk {week}"
            reserve = _x_len(header_base + week_tag) + _x_len(" (10/10):") + 1
            chunks: list = []
            cur: list = []
            cur_len = 0
            for blk in blocks:
                blk_len = sum(_x_len(ln) for ln in blk) + (len(blk) - 1)
                if cur and cur_len + 1 + blk_len + reserve > 280:
                    chunks.append(cur)
                    cur, cur_len = [], 0
                cur.append(blk)
                cur_len += blk_len + 1
            if cur:
                chunks.append(cur)
            for i, ch in enumerate(chunks):
                suffix = f" ({i + 1}/{len(chunks)})" if len(chunks) > 1 else ""
                header = f"{header_base}{suffix}{week_tag}:"
                tweet = header + "\n" + "\n".join(
                    ln for blk in ch for ln in blk)
                assert _x_len(tweet) <= 280, \
                    f"tweet too long ({_x_len(tweet)}): {tweet}"
                tweets.append(tweet)
    return tweets