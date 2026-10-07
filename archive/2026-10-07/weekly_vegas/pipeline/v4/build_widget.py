#!/usr/bin/env python3
"""Build demo/widget.html (v4, TD-inclusive) from data/signals_v4.json."""
import json, html, os

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(BASE), "data")
sig = json.load(open(os.path.join(DATA, "signals_v4.json")))

def pts3(v_std, v_half, v_ppr):
    if v_ppr is None:
        return "—"
    return (f"{v_ppr:.1f}<div style='font-size:10px;color:var(--hatch-widget-muted);'>"
            f"{v_std:.1f} / {v_half:.1f} std/half</div>")

def row(s, dim=False):
    d = s.get("pts_delta_ppr")
    col = "var(--hatch-widget-accent)" if (d or 0) > 0 else "#c2410c"
    dcell = ('%+.1f' % d) if d is not None else "—"
    style = "opacity:.55;" if dim else ""
    td = ""
    if s.get("td_p_yes") is not None or s.get("expert_td_exp") is not None:
        v = f"{s['td_p_yes']:.2f}" if s.get("td_p_yes") is not None else "—"
        e = f"{s['expert_td_exp']:.2f}" if s.get("expert_td_exp") is not None else "—"
        td = f"<div style='font-size:10px;color:var(--hatch-widget-muted);'>TD: V {v} vs E {e}</div>"
    reason = (f"<div style='font-size:10px;color:var(--hatch-widget-muted);'>"
              f"{html.escape(s.get('worthy_reason',''))}</div>"
              if (dim and s.get("worthy_reason")) else "")
    return (f"<tr style='{style}'>"
            f"<td style='padding:7px 9px;font-weight:600;'>{html.escape(s['name'])} "
            f"<span style='color:var(--hatch-widget-muted);font-weight:400;'>"
            f"{html.escape(s['team'])} {s['pos']}</span>{reason}</td>"
            f"<td style='padding:7px 9px;'>{pts3(s['vegas_std'], s['vegas_half'], s['vegas_ppr'])}{td}</td>"
            f"<td style='padding:7px 9px;'>{pts3(s['expert_std'], s['expert_half'], s['expert_ppr'])}</td>"
            f"<td style='padding:7px 9px;font-weight:700;color:{col};'>{dcell}</td>"
            f"<td style='padding:7px 9px;'>#{s['vegas_pos_rank']}</td>"
            f"<td style='padding:7px 9px;'>{html.escape(s['ecr_official'])}</td>"
            f"<td style='padding:7px 9px;font-weight:700;'>{s['delta']:+d}</td></tr>")

worthy = sorted([s for s in sig if s["post_worthy"]],
                key=lambda s: -abs(s["pts_delta_ppr"]))
rest = [s for s in sig if not s["post_worthy"]]

top = worthy[0]
tweet = (f"MARKET vs EXPERTS\nVegas {top['vegas_ppr']:.1f} PPR pts vs experts "
         f"{top['expert_ppr']:.1f} ({top['pts_delta_ppr']:+.1f}) \u2014 {top['name']} "
         f"({top['team']} {top['pos']})\n"
         f"Vegas rank #{top['vegas_pos_rank']} {top['pos']} | ECR {top['ecr_official']} "
         f"(gap {top['delta']:+d})")

def card(title, body):
    return (f"<div style=\"background:var(--hatch-widget-surface);border:1px solid var(--hatch-widget-border);"
            f"border-radius:10px;padding:10px 12px;\"><div style=\"font-weight:700;font-size:13px;\">{title}</div>"
            f"<div style=\"color:var(--hatch-widget-muted);font-size:12px;\">{body}</div></div>")

arrow = ("<div style=\"text-align:center;color:var(--hatch-widget-accent);font-size:16px;"
         "line-height:1;margin:2px 0;\">&#8595;</div>")

fds = [("Ja'Marr Chase", 16.4, 16.7), ("Puka Nacua", 15.8, 16.1), ("Amon-Ra St. Brown", 14.8, 14.9),
       ("CeeDee Lamb", 13.9, 14.1), ("Chris Olave", 13.4, 13.8), ("Justin Jefferson", 12.9, 12.9),
       ("George Pickens", 12.2, 11.8), ("Nico Collins", 12.2, 12.0), ("De'Vonta Smith", 11.7, 11.8),
       ("Zay Flowers", 11.7, 11.3), ("Rashee Rice", 11.6, 11.7), ("Tee Higgins", 11.6, 12.1),
       ("Malik Nabers", 11.2, 11.2), ("Ladd McConkey", 11.0, 11.1), ("Drake London", 10.8, 10.8)]
fds_rows = "".join(
    f"<tr><td style='padding:5px 8px;font-weight:600;'>{html.escape(n)}</td>"
    f"<td style='padding:5px 8px;'>{f:.1f}</td><td style='padding:5px 8px;'>{o:.1f}</td>"
    f"<td style='padding:5px 8px;font-weight:700;color:"
    f"{'#c2410c' if o - f < 0 else 'var(--hatch-widget-accent)'};'>{(o - f):+.1f}</td></tr>"
    for n, f, o in fds)

h = f"""<div style="box-sizing:border-box;max-width:100%;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:var(--hatch-widget-text);font-size:14px;line-height:1.45;padding:4px 2px;">

<div style="margin-bottom:12px;">
  <div style="font-size:17px;font-weight:700;">Football Signal &mdash; live demo <span style="font-size:12px;font-weight:400;color:var(--hatch-widget-muted);">v4 &middot; TD-inclusive, FDS-validated</span></div>
  <div style="color:var(--hatch-widget-muted);font-size:12px;">Week 1 slate &middot; run just now with real data &middot; 12 drafts in the queue, nothing posted &middot; Odds API quota: 269 remaining</div>
</div>

<div style="font-size:13px;font-weight:700;margin:10px 0 6px;">1 &middot; The pipeline, live</div>
<div style="display:flex;flex-direction:column;gap:0;">
  {card("Sources", "Odds API props: <b style='color:var(--hatch-widget-text);'>2,856</b> lines across <b style='color:var(--hatch-widget-text);'>6</b> markets (yardage, catches, anytime-TD, QB pass-TD; DraftKings + FanDuel) &middot; ECR: <b style='color:var(--hatch-widget-text);'>754</b> players, position-specific ranks + expert point projections")}
  {arrow}
  {card("Engine", "<b style='color:var(--hatch-widget-text);'>465</b> prop players &rarr; Vegas-implied points (std / half / PPR) incl. TD value &mdash; anytime-TD odds de-vigged and converted to expected TDs via Poisson &mdash; vs ECR projected points, same scoring, same TD treatment")}
  {arrow}
  {card("Disagreement detector <span style='font-weight:400;font-size:11px;color:var(--hatch-widget-muted);'>cut by position, points first</span>", "<b style='color:var(--hatch-widget-text);'>172</b> rank-gap signals &rarr; post-worthy only if <b style='color:var(--hatch-widget-text);'>|pts &Delta;| &ge; 2.0</b> <i>and</i> one side clears the position floor <i>and</i> the player has yardage props posted (no TD-only ghosts) &rarr; <b style='color:var(--hatch-widget-text);'>12</b> post-worthy")}
  {arrow}
  {card("Draft queue", "<b style='color:var(--hatch-widget-text);'>12</b> draft posts written to <span style='font-family:monospace;'>post_queue</span> (status <span style='font-family:monospace;'>draft</span>) &mdash; the older drafts were rejected as superseded")}
  {arrow}
  <div style="background:var(--hatch-widget-surface-muted);border:1px dashed var(--hatch-widget-border);border-radius:10px;padding:10px 12px;">
    <div style="font-weight:700;font-size:13px;">Scorecard <span style="font-weight:400;color:var(--hatch-widget-muted);font-size:11px;">(after kickoff)</span></div>
    <div style="color:var(--hatch-widget-muted);font-size:12px;">After the games, each signal is graded against actual fantasy points &mdash; hits and misses both published</div>
  </div>
</div>

<div style="font-size:13px;font-weight:700;margin:14px 0 6px;">2 &middot; Post-worthy signals: the points delta is the story</div>
<div style="overflow-x:auto;border:1px solid var(--hatch-widget-border);border-radius:10px;">
<table style="border-collapse:collapse;width:100%;font-size:12px;white-space:nowrap;">
  <thead><tr style="background:var(--hatch-widget-surface-muted);text-align:left;">
    <th style="padding:7px 9px;">Player</th><th style="padding:7px 9px;">Vegas PPR</th><th style="padding:7px 9px;">Expert PPR</th><th style="padding:7px 9px;">Pts &Delta;</th><th style="padding:7px 9px;">Vegas rank</th><th style="padding:7px 9px;">ECR</th><th style="padding:7px 9px;">Gap</th>
  </tr></thead>
  <tbody>{"".join(row(s) for s in worthy)}</tbody>
</table>
</div>

<details style="margin-top:8px;border:1px solid var(--hatch-widget-border);border-radius:10px;padding:8px 12px;">
<summary style="font-size:12px;font-weight:700;cursor:pointer;">{len(rest)} more signals didn&rsquo;t clear the bar &mdash; tap to see why</summary>
<div style="overflow-x:auto;margin-top:8px;">
<table style="border-collapse:collapse;width:100%;font-size:12px;white-space:nowrap;">
  <thead><tr style="background:var(--hatch-widget-surface-muted);text-align:left;">
    <th style="padding:7px 9px;">Player</th><th style="padding:7px 9px;">Vegas PPR</th><th style="padding:7px 9px;">Expert PPR</th><th style="padding:7px 9px;">Pts &Delta;</th><th style="padding:7px 9px;">Vegas rank</th><th style="padding:7px 9px;">ECR</th><th style="padding:7px 9px;">Gap</th>
  </tr></thead>
  <tbody>{"".join(row(s, dim=True) for s in rest)}</tbody>
</table>
</div>
<div style="font-size:11px;color:var(--hatch-widget-muted);margin-top:6px;">Example: Brian Thomas Jr. has a 21-spot rank gap but only a 1.7-pt delta &mdash; exactly the noise the points gate filters out. TD-only entries (e.g. Jonathon Brooks) are flagged and never posted.</div>
</details>

<div style="font-size:13px;font-weight:700;margin:14px 0 6px;">3 &middot; Sanity check: our WR numbers vs First Down Studio</div>
<div style="color:var(--hatch-widget-muted);font-size:12px;margin-bottom:6px;">Independent implementation, same raw inputs &mdash; 61 of their 69 WRs matched, <b style="color:var(--hatch-widget-text);">mean |diff| = 0.20</b> half-PPR points. The TD modeling lands.</div>
<div style="overflow-x:auto;border:1px solid var(--hatch-widget-border);border-radius:10px;">
<table style="border-collapse:collapse;width:100%;font-size:12px;white-space:nowrap;">
  <thead><tr style="background:var(--hatch-widget-surface-muted);text-align:left;">
    <th style="padding:5px 8px;">WR</th><th style="padding:5px 8px;">FDS</th><th style="padding:5px 8px;">Ours</th><th style="padding:5px 8px;">Diff</th>
  </tr></thead>
  <tbody>{fds_rows}</tbody>
</table>
</div>

<div style="font-size:13px;font-weight:700;margin:14px 0 6px;">4 &middot; What the post would look like</div>
<div style="background:var(--hatch-widget-surface);border:1px solid var(--hatch-widget-border);border-radius:12px;padding:12px 14px;box-shadow:var(--hatch-widget-shadow);">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
    <div style="width:34px;height:34px;border-radius:50%;background:var(--hatch-widget-accent);color:var(--hatch-widget-on-accent);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px;">FS</div>
    <div><div style="font-weight:700;font-size:13px;">Football Signal</div><div style="color:var(--hatch-widget-muted);font-size:11px;">@footballsignal &middot; draft preview</div></div>
  </div>
  <div style="font-size:14px;white-space:pre-line;">{html.escape(tweet)}</div>
  <div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--hatch-widget-border);color:var(--hatch-widget-muted);font-size:11px;">Status: <span style="font-family:monospace;">draft</span> &mdash; needs your approval before anything posts</div>
</div>

<div style="font-size:13px;font-weight:700;margin:14px 0 6px;">5 &middot; What&rsquo;s still open</div>
<div style="color:var(--hatch-widget-muted);font-size:12px;">
&bull; Weekly ECR (not the draft board) still needs the one-click Sheet install + your FantasyPros login &mdash; the numbers above use the position draft board as a stand-in.<br>
&bull; QB pass-TD props are now in; rush/receiving TDs ride on the anytime-TD market.<br>
&bull; Scorecards grade themselves after kickoff; the movement-alert and final-call crons get wired once the weekly ECR flow is stable.
</div>

</div>"""

out = os.path.join(os.path.dirname(BASE), "demo", "widget.html")
open(out, "w").write(h)
print("widget written:", out)
