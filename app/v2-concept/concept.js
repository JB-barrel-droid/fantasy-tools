/* Clickable design preview. Reads window.CONCEPT_SAMPLE.
   DDF Charted Value uses each player's chart average.
   DDF Projected Value uses the projection series on the value scale.
   The Market is that chart average from the other side.
   No publisher names on the surface. No live value math. */
(function () {
  "use strict";

  const data = window.CONCEPT_SAMPLE;
  if (!data) return;

  const byId = new Map(data.players.map(player => [player.id, player]));
  const params = new URLSearchParams(location.search);
  const shot = params.get("shot") === "1";
  const CLOSE = 2;
  const SEND = 5;
  const LIST = 2.5;
  const TEAM_KEY = "ddf-concept-team";

  /* Sample league names for the picker. The match line does not parse a paste. */
  const TEAMS = [
    "The Sharp Friends",
    "Sunday Scaries",
    "Gridiron and Chill",
    "Waiver Heroes",
    "First Down",
    "Red Zone",
    "Bye Week Club",
    "Two Point Try",
    "Empty the Tank",
    "Fourth and Long",
    "Primetime",
    "The Group Chat"
  ];

  const TIPS = {
    sleeper: "One team per page. Paste a team, then the next. The count keeps track.",
    espn: "Open League, then Rosters. Select all, and copy.",
    yahoo: "Open the rosters page. Select all, and copy.",
    other: "Paste any player list, or type the names."
  };

  const VIEWS = ["home", "paste", "targets", "compare", "settings"];

  const state = {
    view: "home",
    side: "buy",
    openId: null,
    giveId: data.featured.give,
    getId: data.featured.get,
    why: params.get("why") === "1",
    share: params.get("share") === "1",
    picking: null,
    booted: false,
    from: null,
    pasteText: "",
    pasteCount: 0,
    pasteStep: "edit",
    team: null,
    toast: false,
    confettiKey: null
  };

  const $ = (sel, root) => (root || document).querySelector(sel);
  const live = $("#live");

  function esc(value) {
    return String(value).replace(/[&<>"']/g, ch => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[ch]));
  }

  function num(value) {
    return Math.abs(Number(value)).toFixed(1);
  }

  function signed(value) {
    const n = Number(value);
    const body = Math.abs(n).toFixed(1);
    if (n > 0.05) return "+" + body;
    if (n < -0.05) return "\u2212" + body;
    return "0.0";
  }

  function round1(value) {
    return Math.round(value * 10) / 10;
  }

  function motionOff() {
    return shot || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function readTeam() {
    try { return localStorage.getItem(TEAM_KEY); } catch (e) { return null; }
  }

  function writeTeam(name) {
    try { localStorage.setItem(TEAM_KEY, name); } catch (e) { /* private mode */ }
  }

  const INFO = {
    charted: "Our value for this player, starting from the trade charts and adjusted for position weight and your league's rosters.",
    projected: "Our value for this player, starting from rest-of-season projections and adjusted for position weight and your league's rosters.",
    market: "What the trade charts say before our adjustments \u2014 roughly how the other manager will see it."
  };
  let tipSeq = 0;

  function footnote() {
    return "Preview from " + data.asOf + ", full PPR, 12 teams. DDF Charted Value and DDF Projected Value are one read. The Market is the other team's read. A one-for-one swap stands in for a lineup check. This page is not the live site.";
  }

  function infoBtn(kind, align) {
    tipSeq += 1;
    const id = "tip-" + kind + "-" + tipSeq;
    const name = kind === "charted" ? "DDF Charted Value" : kind === "projected" ? "DDF Projected Value" : "The Market";
    return (
      '<span class="tip">' +
        '<button type="button" class="tip-btn" aria-expanded="false" aria-controls="' + id + '">' +
          '<span aria-hidden="true">i</span>' +
          '<span class="sr">About ' + name + "</span>" +
        "</button>" +
        '<span class="tip-pop" id="' + id + '" role="note" tabindex="-1" hidden' +
          (align === "end" ? ' data-align="end"' : "") + ">" + esc(INFO[kind]) + "</span>" +
      "</span>"
    );
  }

  function closeTips() {
    document.querySelectorAll(".tip-btn[aria-expanded='true']").forEach(btn => {
      btn.setAttribute("aria-expanded", "false");
      const pop = document.getElementById(btn.getAttribute("aria-controls"));
      if (!pop) return;
      pop.hidden = true;
      if (btn.isConnected && btn.parentElement) btn.parentElement.appendChild(pop);
    });
    document.querySelectorAll("body > .tip-pop").forEach(pop => pop.remove());
  }

  function openTip(btn) {
    const pop = document.getElementById(btn.getAttribute("aria-controls"));
    if (!pop) return;
    closeTips();
    btn.setAttribute("aria-expanded", "true");
    pop.hidden = false;
    document.body.appendChild(pop);
    const rect = btn.getBoundingClientRect();
    const width = Math.min(240, window.innerWidth - 32);
    let left = rect.left;
    if (pop.dataset.align === "end" || left + width > window.innerWidth - 16) {
      left = Math.max(16, rect.right - width);
    }
    pop.style.position = "fixed";
    pop.style.left = left + "px";
    pop.style.top = (rect.bottom + 8) + "px";
    pop.style.width = width + "px";
    pop.style.right = "auto";
    pop.focus();
  }

  function shortName(name) {
    return String(name).split(" ")[0];
  }

  function posChip(pos) {
    return '<span class="chip" data-pos="' + esc(pos) + '">' + esc(pos) + "</span>";
  }

  function numbersChip(value) {
    return (
      '<div class="chip-stat"><b data-count="' + value + '">' + signed(value) + "</b>" +
        '<span class="chip-terms"><span>DDF Projected Value</span>' + infoBtn("projected", "end") +
        "<span>vs the Market</span>" + infoBtn("market", "end") + "</span></div>"
    );
  }

  function listFor(side) {
    const featured = side === "buy" ? data.featured.buy : data.featured.sell;
    return data.players
      .filter(player => Math.abs(player.gap) >= LIST && (side === "buy" ? player.gap > 0 : player.gap < 0))
      .sort((a, b) => {
        if (a.id === featured) return -1;
        if (b.id === featured) return 1;
        return side === "buy" ? b.gap - a.gap : a.gap - b.gap;
      });
  }

  function buyCopy(player) {
    const buy = player.gap > 0;
    return {
      emoji: buy ? "\u2705" : "\uD83D\uDCB8",
      title: (buy ? "Buy " : "Sell ") + player.name,
      why: buy ? "DDF Projected Value is ahead of the Market." : "The Market is ahead of DDF Projected Value.",
      tone: buy ? "good" : "bad"
    };
  }

  function meters(player) {
    const rows = [
      {name: "DDF Projected Value", value: player.ddf, read: true, kind: "projected"},
      {name: "The Market", value: player.market, read: false, kind: "market"}
    ];
    return rows.map(row => {
      const width = Math.max(2, Math.min(100, (row.value / data.scaleMax) * 100));
      return (
        '<div class="meter-row">' +
          '<span class="meter-name"><span>' + row.name + "</span>" + infoBtn(row.kind, "end") + "</span>" +
          '<span class="meter-val">' + num(row.value) + "</span>" +
          '<span class="meter' + (row.read ? " is-read" : "") + '" aria-hidden="true"><span style="width:' + width.toFixed(1) + '%"></span></span>' +
        "</div>"
      );
    }).join("");
  }

  function detail(player) {
    const copy = buyCopy(player);
    const cap = player.capped
      ? '<p class="cap-note">This preview\'s projection figure stops at 70, so the lead is a floor.</p>'
      : "";
    return (
      '<div class="player-detail">' +
        '<p class="detail-blurb">' + esc(copy.why) + "</p>" +
        meters(player) +
        cap +
      "</div>"
    );
  }

  function countNodes(root) {
    (root || document).querySelectorAll("[data-count]").forEach(el => {
      const target = Number(el.dataset.count);
      const done = () => { el.textContent = signed(target); };
      if (motionOff()) { done(); return; }
      const t0 = performance.now();
      const step = now => {
        const p = Math.min(1, (now - t0) / 400);
        const eased = 1 - Math.pow(1 - p, 3);
        el.textContent = signed(target * eased);
        if (p < 1) requestAnimationFrame(step);
        else done();
      };
      requestAnimationFrame(step);
    });
  }

  function paintPeek() {
    const player = byId.get(data.featured.buy);
    const copy = buyCopy(player);
    $("#peekEmoji").textContent = copy.emoji;
    $("#peekName").textContent = copy.title;
    $("#peekBlurb").textContent = copy.why;
    $("#peekNums").innerHTML = numbersChip(player.gap);
    countNodes($("#peekNums"));
  }

  function headlinePlayer() {
    const list = listFor(state.side);
    if (state.openId != null) {
      const open = list.find(player => player.id === state.openId);
      if (open) return open;
    }
    const id = state.side === "buy" ? data.featured.buy : data.featured.sell;
    return byId.get(id) || list[0];
  }

  function paintTargets(tick) {
    const player = headlinePlayer();
    const copy = buyCopy(player);
    const titleEl = $("#targetsTitle");
    const changed = state.booted && tick && titleEl.textContent !== copy.title;
    $("#targetsEmoji").textContent = copy.emoji;
    titleEl.textContent = copy.title;
    $("#targetsSub").textContent = copy.why;
    $("#targetsChips").innerHTML = numbersChip(player.gap);
    countNodes($("#targetsChips"));
    if (changed) {
      titleEl.classList.remove("tick");
      void titleEl.offsetWidth;
      titleEl.classList.add("tick");
      if (state.view === "targets") live.textContent = copy.title;
    }
  }

  function renderList() {
    const list = listFor(state.side);
    $("#sideSeg").dataset.on = state.side;
    $("#sideBuy").setAttribute("aria-selected", state.side === "buy" ? "true" : "false");
    $("#sideSell").setAttribute("aria-selected", state.side === "sell" ? "true" : "false");
    $("#targetList").innerHTML = list.map(player => {
      const open = player.id === state.openId;
      const copy = buyCopy(player);
      return (
        '<article class="player' + (open ? " is-open" : "") + '" data-id="' + player.id + '">' +
          '<button type="button" class="player-sum" aria-expanded="' + (open ? "true" : "false") + '" aria-controls="detail-' + player.id + '">' +
            '<span class="who">' +
              '<span class="player-id"><span class="player-name">' + esc(player.name) + "</span></span>" +
              '<span class="player-meta">' + posChip(player.pos) + "<span>" + esc(player.team) + "</span></span>" +
              '<span class="player-short">' + esc(copy.why) + "</span>" +
              '<span class="player-figs"><span><b>' + num(player.ddf) + "</b> DDF Projected Value</span><span><b>" + num(player.market) + "</b> the Market</span></span>" +
            "</span>" +
            '<svg class="chev" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 8l5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
          "</button>" +
          '<div class="player-more"' + (open ? "" : " inert") + ' id="detail-' + player.id + '"><div class="player-more-inner">' +
            detail(player) +
          "</div></div>" +
        "</article>"
      );
    }).join("");
  }

  function verdict() {
    const give = state.giveId == null ? null : byId.get(state.giveId);
    const get = state.getId == null ? null : byId.get(state.getId);
    if (!give && !get) {
      return {title: "Add a player to each side.", why: "You get one sentence. The math opens under it.", gain: null};
    }
    if (!give) return {title: "Who are you giving up?", why: "Add that player and the answer sits up here.", gain: null};
    if (!get) return {title: "Who are you getting?", why: "Add that player and the answer sits up here.", gain: null};
    if (give.id === get.id) {
      return {title: "Pick two different players.", why: "A trade needs a player on each side.", gain: null};
    }
    const mine = round1(get.market - give.market);
    const proj = round1(get.ddf - give.ddf);
    const theirs = round1(give.market - get.market);
    const mineSmall = Math.abs(mine) < CLOSE;
    const theirsSmall = Math.abs(theirs) < CLOSE;
    let title;
    let emoji;
    let tone;
    let why;
    if (mineSmall && theirsSmall) {
      title = "Fair swap";
      emoji = "\uD83E\uDD1D";
      tone = "neutral";
      why = "You are about even on DDF Charted Value, and their lineup barely moves on the Market.";
    } else if (mine >= SEND && theirs > 0.05) {
      title = "Send it";
      emoji = "\uD83D\uDD25";
      tone = "good";
      why = "You gain " + num(mine) + " DDF Charted Value; their lineup improves on the Market, so they'll likely accept.";
    } else if (mine >= CLOSE && theirs > 0.05) {
      title = "Worth a shot";
      emoji = "\uD83D\uDC40";
      tone = "good";
      why = "You gain " + num(mine) + " DDF Charted Value; their lineup improves on the Market, so they'll likely accept.";
    } else if (mine > 0.05 && theirs <= 0.05) {
      title = "They'll pass";
      emoji = "\uD83D\uDE2C";
      tone = "warn";
      why = "You gain " + num(mine) + " DDF Charted Value, but their lineup does not improve on the Market, so they'll likely pass.";
    } else if (mine <= -CLOSE) {
      title = "Don't do it";
      emoji = "\uD83D\uDED1";
      tone = "bad";
      if (theirs > 0.05) {
        why = "You give up " + num(Math.abs(mine)) + " DDF Charted Value. Their lineup improves on the Market, so they'll likely accept.";
      } else if (theirs < -0.05) {
        why = "You give up " + num(Math.abs(mine)) + " DDF Charted Value, and their lineup does not improve on the Market.";
      } else {
        why = "You give up " + num(Math.abs(mine)) + " DDF Charted Value. Their lineup barely moves on the Market.";
      }
    } else {
      title = "Fair swap";
      emoji = "\uD83E\uDD1D";
      tone = "neutral";
      why = "You are about even on DDF Charted Value, and their lineup barely moves on the Market.";
    }
    const points = pointsRead(give, get, mine);
    return {
      title: title,
      emoji: emoji,
      tone: tone,
      why: why,
      gain: mine,
      charts: mine,
      proj: proj,
      theirs: theirs,
      points: points,
      give: give,
      get: get,
      confetti: title === "Send it" && mine >= 8
    };
  }

  function pointsRead(give, get, charts) {
    const ppg = round1(get.points.ppg - give.points.ppg);
    const ros = round1(get.points.ros - give.points.ros);
    const opposite = (charts > 0.05 && ppg < -0.05) || (charts < -0.05 && ppg > 0.05);
    let lean;
    if (opposite && Math.abs(ppg) < 1) {
      lean = "The points lean the other way from DDF Charted Value. The gap is small.";
    } else if (opposite) {
      lean = "The points lean the other way from DDF Charted Value.";
    } else if (Math.abs(ppg) < 1) {
      lean = "The points say the same thing as DDF Charted Value. The gap is small.";
    } else {
      lean = "The points say the same thing as DDF Charted Value.";
    }
    return {ppg: ppg, ros: ros, lean: lean};
  }

  function chartLine(charts) {
    if (charts < -0.05) return "What you give up.";
    if (charts > 0.05) return "What you gain.";
    return "About even for you.";
  }

  function projLean(charts, proj) {
    const opposite = (charts > 0.05 && proj < -0.05) || (charts < -0.05 && proj > 0.05);
    if (opposite) return "Leans the other way.";
    if (proj < -0.05) return "What you give up.";
    if (proj > 0.05) return "What you gain.";
    return "About even.";
  }

  function marketLine(theirs) {
    if (theirs > 0.05) return "Whether they'll accept. Their lineup improves, so they'll likely accept.";
    if (theirs < -0.05) return "Whether they'll accept. Their lineup does not improve.";
    return "Whether they'll accept. Their lineup barely moves.";
  }

  function pairSide(kind, value, line) {
    const label = kind === "charted" ? "DDF Charted Value" : "DDF Projected Value";
    return (
      '<article class="reading">' +
        '<p class="reading-label"><span>' + label + "</span>" + infoBtn(kind, kind === "projected" ? "end" : "") + "</p>" +
        '<p class="reading-num"><b data-count="' + value + '">' + signed(value) + "</b></p>" +
        '<p class="reading-why">' + esc(line) + "</p>" +
      "</article>"
    );
  }

  function readingsHtml(result) {
    const sizes = signed(result.points.ppg) + " a week, " + signed(result.points.ros) + " the rest of the season. " + result.points.lean;
    return (
      '<section class="read-group read-ddf">' +
        '<p class="read-kicker">The DDF read</p>' +
        '<p class="read-method">Same method, two inputs</p>' +
        '<div class="read-pair">' +
          pairSide("charted", result.charts, chartLine(result.charts)) +
          pairSide("projected", result.proj, projLean(result.charts, result.proj)) +
        "</div>" +
        '<p class="read-sizes">' + esc(sizes) + "</p>" +
      "</section>" +
      '<section class="read-group read-market">' +
        '<p class="read-kicker"><span>The Market</span>' + infoBtn("market", "end") + "</p>" +
        '<p class="read-method">The other team\'s read.</p>' +
        '<p class="reading-num"><b data-count="' + result.theirs + '">' + signed(result.theirs) + "</b></p>" +
        '<p class="reading-why">' + esc(marketLine(result.theirs)) + "</p>" +
      "</section>"
    );
  }

  function readBlock(name, giveRead, getRead, give, get) {
    const ppg = round1(getRead.ppg - giveRead.ppg);
    const ros = round1(getRead.ros - giveRead.ros);
    const week = ppg < -0.05
      ? "You give up " + num(Math.abs(ppg)) + " a week."
      : ppg > 0.05
        ? "You gain " + num(ppg) + " a week."
        : "Per week you are about even.";
    const season = ros < -0.05
      ? " You give up " + num(Math.abs(ros)) + " the rest of the season."
      : ros > 0.05
        ? " You gain " + num(ros) + " the rest of the season."
        : " The rest of the season is about even.";
    const them = ppg < -0.05 ? " They pick up the same." : ppg > 0.05 ? " They give up the same." : "";
    return (
      '<article class="read">' +
        '<h3>' + esc(name) + "</h3>" +
        "<p>" + esc(shortName(give.name)) + " " + num(giveRead.ppg) + " a week, " + num(giveRead.ros) + " the rest of the season.</p>" +
        "<p>" + esc(shortName(get.name)) + " " + num(getRead.ppg) + " a week, " + num(getRead.ros) + " the rest of the season.</p>" +
        "<p>" + week + season + them + "</p>" +
      "</article>"
    );
  }

  function slot(side, player) {
    const label = side === "give" ? "You give" : "You get";
    if (!player) {
      return (
        '<button type="button" class="slot is-empty" data-pick="' + side + '">' +
          '<span class="slot-kicker">' + label + "</span>" +
          '<span class="slot-name">Add a player</span>' +
          '<span class="slot-change">Choose</span>' +
        "</button>"
      );
    }
    return (
      '<button type="button" class="slot" data-pick="' + side + '">' +
        '<span class="slot-kicker">' + label + "</span>" +
        '<span class="slot-name">' + esc(player.name) + "</span>" +
        '<span class="slot-meta">' + posChip(player.pos) + "<span>" + esc(player.team) + "</span></span>" +
        '<span class="slot-nums">' +
          "<span><b>" + num(player.market) + "</b> DDF Charted Value</span>" +
          "<span><b>" + num(player.ddf) + "</b> DDF Projected Value</span>" +
        "</span>" +
        '<span class="slot-change">Change</span>' +
      "</button>"
    );
  }

  function whyCard(player, kicker) {
    return (
      '<article class="why-card">' +
        '<p class="kicker">' + kicker + "</p>" +
        '<p class="why-name">' + esc(player.name) + "</p>" +
        meters(player) +
      "</article>"
    );
  }

  function burst() {
    const box = $("#confetti");
    box.hidden = false;
    box.replaceChildren();
    const colors = ["var(--action)", "var(--warn-ink)", "var(--info-ink)", "var(--good-ink)"];
    for (let i = 0; i < 18; i++) {
      const bit = document.createElement("i");
      bit.style.left = (4 + Math.random() * 92) + "%";
      bit.style.background = colors[i % colors.length];
      bit.style.animationDelay = (Math.random() * 120) + "ms";
      bit.style.transform = "rotate(" + (Math.random() * 80) + "deg)";
      box.appendChild(bit);
    }
    window.setTimeout(() => {
      box.hidden = true;
      box.replaceChildren();
    }, 1100);
  }

  function maybeConfetti(result) {
    if (!result.confetti || motionOff() || state.view !== "compare") return;
    const key = state.giveId + ">" + state.getId;
    if (state.confettiKey === key) return;
    state.confettiKey = key;
    burst();
  }

  function renderCompare(tick) {
    const result = verdict();
    const titleEl = $("#compareTitle");
    const changed = state.booted && tick && titleEl.textContent && titleEl.textContent !== result.title;
    $("#compareEmoji").textContent = result.emoji || "";
    titleEl.textContent = result.title;
    $("#compareSub").textContent = result.why;
    const sample = state.giveId === data.featured.give && state.getId === data.featured.get;
    $("#compareEyebrow").innerHTML = sample
      ? 'Check a trade <span class="chip">Sample</span>'
      : "Check a trade";
    const stamp = $("#compareStamp");
    if (result.gain == null) {
      stamp.hidden = true;
      $("#readings").innerHTML = "";
    } else {
      stamp.hidden = false;
      stamp.textContent = result.title;
      stamp.dataset.tone = result.tone;
      stamp.classList.remove("is-live");
      if (!motionOff()) {
        void stamp.offsetWidth;
        stamp.classList.add("is-live");
      }
      $("#readings").innerHTML = readingsHtml(result);
      countNodes($("#readings"));
    }
    const give = result.give || (state.giveId == null ? null : byId.get(state.giveId));
    const get = result.get || (state.getId == null ? null : byId.get(state.getId));
    const ready = result.gain != null;
    $("#deal").innerHTML =
      slot("give", ready ? give : (state.giveId == null ? null : byId.get(state.giveId))) +
      '<div class="deal-for" aria-hidden="true">' +
        '<svg class="for-down" viewBox="0 0 24 24"><path d="M12 5v14M6 13l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
        '<svg class="for-right" viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
      "</div>" +
      slot("get", ready ? get : (state.getId == null ? null : byId.get(state.getId)));
    $("#compareActions").innerHTML =
      '<button type="button" class="texty" id="clearTrade">Clear</button>' +
      (sample ? "" : '<button type="button" class="texty" id="useSample">Use the sample</button>') +
      (ready ? '<button type="button" class="texty" id="shareBtn">' + (state.share ? "Hide the card" : "Share this trade") + "</button>" : "");
    const whyBtn = $("#whyBtn");
    whyBtn.hidden = !ready;
    $("#why").classList.toggle("is-open", state.why && ready);
    whyBtn.setAttribute("aria-expanded", state.why && ready ? "true" : "false");
    whyBtn.textContent = state.why ? "Hide the math" : "Show the math";
    if (ready) {
      const reads = give.points.reads.map((read, i) => readBlock(read.name, read, get.points.reads[i], give, get)).join("");
      $("#whyInner").innerHTML =
        '<p class="math">DDF Charted Value: ' + num(get.market) + " received \u2212 " + num(give.market) + " given = " + signed(result.charts) + ". On this preview that figure is the trade-chart average, before the position-weight adjustment is wired.</p>" +
        '<p class="math">DDF Projected Value: ' + num(get.ddf) + " received \u2212 " + num(give.ddf) + " given = " + signed(result.proj) + ". Same method, starting from projections. This preview uses one projection source on the value scale, not the three-source average.</p>" +
        '<p class="math">The Market, for them: ' + num(give.market) + " received \u2212 " + num(get.market) + " given = " + signed(result.theirs) + ". The other team\'s read. On this preview that is the same chart average, from their side.</p>" +
        '<p class="math">Points per week and for the rest of the season, full PPR. Each line is one read, then the three together.</p>' +
        '<div class="reads">' + reads +
          readBlock("The three together", {ppg: give.points.ppg, ros: give.points.ros}, {ppg: get.points.ppg, ros: get.points.ros}, give, get) +
        "</div>" +
        '<p class="math">A one-for-one swap stands in for their lineup. A full roster check comes with the live page.</p>';
    } else {
      $("#whyInner").innerHTML = "";
    }
    const card = $("#shareCard");
    if (ready && state.share) {
      card.hidden = false;
      card.innerHTML =
        '<p class="kicker">Data Driven Football</p>' +
        '<p class="verdict-emoji" aria-hidden="true">' + (result.emoji || "") + "</p>" +
        '<p class="share-title">' + esc(result.title) + "</p>" +
        '<p class="share-players">' + esc(give.name) + " \u2192 " + esc(get.name) + "</p>" +
        '<p class="share-why">' + esc(result.why) + "</p>" +
        '<p class="share-why">DDF Charted Value ' + signed(result.charts) + ". DDF Projected Value " + signed(result.proj) + ". " + signed(result.points.ppg) + " a week, " + signed(result.points.ros) + " the rest of the season.</p>" +
        '<button type="button" class="quiet" id="copyCard">Copy card</button>';
    } else {
      card.hidden = true;
      card.innerHTML = "";
    }
    if (changed && state.view === "compare") {
      titleEl.classList.remove("tick");
      void titleEl.offsetWidth;
      titleEl.classList.add("tick");
      live.textContent = result.title + ". " + result.why;
    }
    maybeConfetti(result);
  }

  function shareText() {
    const result = verdict();
    if (result.gain == null) return "";
    return result.title + "\n" + result.give.name + " for " + result.get.name + "\n" + result.why + "\nDDF Charted Value " + signed(result.charts) + ". DDF Projected Value " + signed(result.proj) + ". " + signed(result.points.ppg) + " a week.\nData Driven Football";
  }

  function exportData() {
    const team = state.team || "(none yet)";
    const text = "Saved on this device.\nTeam: " + team + "\n" + data.leagueTeams + " teams, " + data.leaguePlayers + " players\n";
    const blob = new Blob([text], {type: "text/plain"});
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "ddf-on-this-device.txt";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    live.textContent = "Export started";
  }

  function copyText(text, ok) {
    const done = () => { live.textContent = ok; };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
    } else {
      fallbackCopy(text, done);
    }
  }

  function fallbackCopy(text, done) {
    const input = document.createElement("textarea");
    input.value = text;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.left = "-999px";
    document.body.appendChild(input);
    input.select();
    try { document.execCommand("copy"); } catch (e) { /* still announce */ }
    input.remove();
    done();
  }

  function copyLink() {
    copyText(location.origin + location.pathname, "Link copied");
  }

  function showToast() {
    state.toast = true;
    $("#toast").hidden = false;
    live.textContent = $("#toastText").textContent;
    if (state.toastTimer) window.clearTimeout(state.toastTimer);
    if (!shot) {
      state.toastTimer = window.setTimeout(() => {
        state.toast = false;
        $("#toast").hidden = true;
      }, 8000);
    }
  }

  function hideToast() {
    state.toast = false;
    $("#toast").hidden = true;
  }

  function paintLeague() {
    $("#leagueBtn").textContent = state.team || "Paste a league";
  }

  function paintTeamNote() {
    $("#teamNote").textContent = state.team
      ? "Your team on this device: " + state.team + "."
      : "No team picked yet. Paste a league, then pick yours.";
  }

  function renderPaste() {
    const edit = $("#pasteEdit");
    const match = $("#pasteMatch");
    const onMatch = state.pasteStep === "match";
    edit.hidden = onMatch;
    match.hidden = !onMatch;
    document.querySelectorAll("[data-from]").forEach(btn => {
      btn.setAttribute("aria-checked", btn.dataset.from === state.from ? "true" : "false");
    });
    $("#pasteTip").textContent = state.from
      ? TIPS[state.from]
      : "Pick where you copy it from. The box stays the same.";
    const box = $("#pasteBox");
    if (box.value !== state.pasteText) box.value = state.pasteText;
    const count = $("#pasteCount");
    if (state.from === "sleeper") {
      count.hidden = false;
      const n = state.pasteCount;
      count.textContent = n === 1 ? "1 team pasted" : n + " teams pasted";
    } else {
      count.hidden = true;
    }
    const actions = $("#pasteActions");
    if (state.from === "sleeper") {
      actions.innerHTML =
        '<button type="button" class="btn" id="addTeam">Add this team</button>' +
        '<button type="button" class="texty" id="thatsAll">That\'s everyone</button>';
    } else if (state.from) {
      actions.innerHTML = '<button type="button" class="btn" id="checkPaste">Check the paste</button>';
    } else {
      actions.innerHTML = "";
    }
    if (onMatch) {
      $("#teamList").innerHTML = TEAMS.map(name => (
        '<button type="button" class="team' + (name === state.team ? " is-on" : "") + '" data-team="' + esc(name) + '">' +
          esc(name) +
        "</button>"
      )).join("");
    }
  }

  const TITLES = {
    home: "Data Driven Football — preview",
    paste: "Paste your league — DDF preview",
    targets: "Buy & sell — DDF preview",
    compare: "Check a trade — DDF preview",
    settings: "Settings — DDF preview"
  };

  let returnFocus = null;

  function show(view, opts) {
    opts = opts || {};
    if (!VIEWS.includes(view)) view = "home";
    state.view = view;
    document.querySelectorAll(".view").forEach(section => {
      const on = section.id === view;
      section.classList.toggle("is-on", on);
      section.toggleAttribute("inert", !on);
      section.setAttribute("aria-hidden", on ? "false" : "true");
    });
    document.querySelectorAll("[data-go]").forEach(btn => {
      if (btn.dataset.go === view) btn.setAttribute("aria-current", "page");
      else btn.removeAttribute("aria-current");
    });
    document.title = TITLES[view];
    if (opts.history !== false) {
      const next = "#" + view;
      if (location.hash !== next) history.pushState({view: view}, "", next);
    }
    window.scrollTo(0, 0);
    if (view === "compare") maybeConfetti(verdict());
    if (opts.focus && state.booted) {
      const target = document.getElementById(
        view === "paste" && state.pasteStep === "match" ? "matchTitle" : view + "Title"
      );
      if (target) target.focus();
    }
  }

  function openDialog(dialog) {
    if (typeof dialog.showModal === "function" && !dialog.open) dialog.showModal();
  }

  function closeDialog(dialog) {
    if (dialog.open) dialog.close();
  }

  function filteredPlayers(query) {
    const q = query.trim().toLowerCase();
    return data.players
      .filter(player => !q || player.name.toLowerCase().includes(q) || player.team.toLowerCase().includes(q) || player.pos.toLowerCase() === q)
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  function renderPicker() {
    const players = filteredPlayers($("#pickerSearch").value);
    if (!players.length) {
      $("#pickerList").innerHTML = '<p class="menu-note">No player in this sample matches.</p>';
      return;
    }
    $("#pickerList").innerHTML = players.map(player => {
      const fair = Math.abs(player.gap) < LIST
        ? '<span class="chip">Fair price</span>'
        : "";
      return (
        '<button type="button" class="pick" role="option" data-id="' + player.id + '">' +
          posChip(player.pos) +
          '<span class="pick-name">' + esc(player.name) + fair + "</span>" +
          '<span class="pick-team">' + esc(player.team) + "</span>" +
          '<span class="pick-num">' + num(player.ddf) + "</span>" +
        "</button>"
      );
    }).join("");
  }

  function openPicker(side, trigger) {
    state.picking = side;
    returnFocus = trigger || null;
    $("#pickerTitle").textContent = side === "give" ? "Who are you giving?" : "Who are you getting?";
    $("#pickerSearch").value = "";
    renderPicker();
    openDialog($("#picker"));
    $("#pickerSearch").focus();
  }

  function choose(id) {
    const side = state.picking;
    if (side === "give") state.giveId = id;
    if (side === "get") state.getId = id;
    state.confettiKey = null;
    renderCompare(true);
    returnFocus = document.querySelector('[data-pick="' + side + '"]');
    closeDialog($("#picker"));
  }

  function setSide(side) {
    if (state.side === side) return;
    state.side = side;
    state.openId = null;
    renderList();
    paintTargets(true);
  }

  function pickTeam(name) {
    state.team = name;
    writeTeam(name);
    paintLeague();
    paintTeamNote();
    renderPaste();
    showToast();
  }

  function goMatch() {
    state.pasteStep = "match";
    renderPaste();
    const title = $("#matchTitle");
    if (title) title.focus();
  }

  document.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    const open = document.querySelector(".tip-btn[aria-expanded='true']");
    if (!open) return;
    event.preventDefault();
    closeTips();
    open.focus();
  });

  document.addEventListener("click", event => {
    const tipBtn = event.target.closest(".tip-btn");
    if (tipBtn) {
      event.preventDefault();
      event.stopPropagation();
      const willOpen = tipBtn.getAttribute("aria-expanded") !== "true";
      if (willOpen) openTip(tipBtn);
      else closeTips();
      return;
    }
    if (!event.target.closest(".tip") && !event.target.closest(".tip-pop")) closeTips();
    const go = event.target.closest("[data-go]");
    if (go) {
      event.preventDefault();
      show(go.dataset.go, {focus: true});
      return;
    }
    const from = event.target.closest("[data-from]");
    if (from) {
      state.from = from.dataset.from;
      renderPaste();
      return;
    }
    if (event.target.closest("#addTeam")) {
      if (!state.pasteText.trim()) {
        live.textContent = "Paste a team first.";
        $("#pasteBox").focus();
        return;
      }
      state.pasteCount += 1;
      state.pasteText = "";
      renderPaste();
      live.textContent = state.pasteCount + " teams pasted";
      return;
    }
    if (event.target.closest("#thatsAll")) {
      if (state.pasteCount < 1) {
        live.textContent = "Paste at least one team.";
        return;
      }
      goMatch();
      return;
    }
    if (event.target.closest("#checkPaste")) {
      if (!state.pasteText.trim()) {
        live.textContent = "Paste a list first.";
        $("#pasteBox").focus();
        return;
      }
      goMatch();
      return;
    }
    if (event.target.closest("#pasteBack")) {
      state.pasteStep = "edit";
      renderPaste();
      return;
    }
    const teamBtn = event.target.closest("[data-team]");
    if (teamBtn) {
      pickTeam(teamBtn.dataset.team);
      return;
    }
    const sum = event.target.closest(".player-sum");
    if (sum) {
      const card = sum.closest(".player");
      const id = Number(card.dataset.id);
      state.openId = state.openId === id ? null : id;
      document.querySelectorAll("#targetList .player").forEach(node => {
        const on = Number(node.dataset.id) === state.openId;
        node.classList.toggle("is-open", on);
        node.querySelector(".player-sum").setAttribute("aria-expanded", on ? "true" : "false");
        const more = node.querySelector(".player-more");
        if (more) {
          if (on) more.removeAttribute("inert");
          else more.setAttribute("inert", "");
        }
      });
      paintTargets(true);
      return;
    }
    const pick = event.target.closest("[data-pick]");
    if (pick) {
      openPicker(pick.dataset.pick, pick);
      return;
    }
    const option = event.target.closest(".pick");
    if (option) {
      choose(Number(option.dataset.id));
      return;
    }
    if (event.target.closest("#clearTrade")) {
      state.giveId = null;
      state.getId = null;
      state.why = false;
      state.share = false;
      state.confettiKey = null;
      renderCompare(true);
      return;
    }
    if (event.target.closest("#useSample")) {
      state.giveId = data.featured.give;
      state.getId = data.featured.get;
      state.confettiKey = null;
      renderCompare(true);
      return;
    }
    if (event.target.closest("#whyBtn")) {
      state.why = !state.why;
      renderCompare(false);
      return;
    }
    if (event.target.closest("#shareBtn")) {
      state.share = !state.share;
      renderCompare(false);
      return;
    }
    if (event.target.closest("#copyCard")) {
      copyText(shareText(), "Card copied");
      return;
    }
    if (event.target.closest("#exportBtn") || event.target.closest("#toastExport")) {
      exportData();
      return;
    }
    if (event.target.closest("#copyLinkBtn") || event.target.closest("#toastCopy")) {
      copyLink();
      return;
    }
    if (event.target.closest("#importBtn")) {
      $("#importFile").click();
      return;
    }
    if (event.target.closest("#toastDismiss")) hideToast();
  });

  $("#pasteBox").addEventListener("input", () => {
    state.pasteText = $("#pasteBox").value;
  });

  $("#leagueBtn").addEventListener("click", () => {
    show(state.team ? "settings" : "paste", {focus: true});
  });

  $("#sideBuy").addEventListener("click", () => setSide("buy"));
  $("#sideSell").addEventListener("click", () => setSide("sell"));
  $("#sideSeg").addEventListener("keydown", event => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    setSide(state.side === "buy" ? "sell" : "buy");
    (state.side === "buy" ? $("#sideBuy") : $("#sideSell")).focus();
  });

  $("#pickerSearch").addEventListener("input", renderPicker);
  $("#pickerClose").addEventListener("click", () => closeDialog($("#picker")));
  $("#picker").addEventListener("close", () => {
    if (returnFocus) returnFocus.focus();
  });

  $("#importFile").addEventListener("change", () => {
    const file = $("#importFile").files && $("#importFile").files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      const line = text.split(/\r?\n/).find(row => row.indexOf("Team:") === 0);
      const name = line ? line.replace(/^Team:\s*/, "").trim() : "";
      if (name && name !== "(none yet)") {
        state.team = name;
        writeTeam(name);
        paintLeague();
        paintTeamNote();
        live.textContent = "Imported on this device.";
      } else {
        live.textContent = "That file has no team.";
      }
    };
    reader.readAsText(file);
    $("#importFile").value = "";
  });

  $("#themeBtn").addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    $("#themeBtn").setAttribute("aria-label", next === "dark" ? "Switch to light mode" : "Switch to dark mode");
    try { localStorage.setItem("ddf-concept-theme", next); } catch (e) { /* private mode */ }
  });

  window.addEventListener("hashchange", () => {
    const name = location.hash.replace("#", "");
    if (VIEWS.includes(name)) show(name, {history: false, focus: false});
  });

  document.querySelectorAll(".footnote").forEach(node => { node.textContent = footnote(); });

  state.team = readTeam();
  const from = params.get("from");
  if (TIPS[from]) state.from = from;
  const count = Number(params.get("count"));
  if (Number.isFinite(count) && count > 0) state.pasteCount = count;
  if (params.get("matched") === "1") state.pasteStep = "match";

  paintLeague();
  paintTeamNote();
  paintPeek();
  renderPaste();

  const openId = Number(params.get("open"));
  if (openId && byId.has(openId)) {
    const player = byId.get(openId);
    if (Math.abs(player.gap) >= LIST && player.gap !== 0) {
      state.side = player.gap < 0 ? "sell" : "buy";
      state.openId = openId;
    }
  }
  if (params.get("side") === "sell") {
    state.side = "sell";
    if (!params.get("open")) state.openId = null;
  }

  renderList();
  paintTargets(false);
  renderCompare(false);

  const themeNow = document.documentElement.getAttribute("data-theme");
  $("#themeBtn").setAttribute("aria-label", themeNow === "dark" ? "Switch to light mode" : "Switch to dark mode");

  let view = params.get("view") || location.hash.replace("#", "") || "home";
  if (!VIEWS.includes(view)) view = "home";
  show(view, {history: false, focus: false});
  state.booted = true;
  if (view === "compare") maybeConfetti(verdict());

  document.documentElement.dataset.ready = "1";
})();
