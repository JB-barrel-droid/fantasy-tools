/* Clickable design preview. Reads window.CONCEPT_SAMPLE. Does no value math. */
(function () {
  "use strict";

  const data = window.CONCEPT_SAMPLE;
  if (!data) return;

  const byId = new Map(data.players.map(player => [player.id, player]));
  const params = new URLSearchParams(location.search);
  const shot = params.get("shot") === "1";
  const CLOSE = 2;

  const state = {
    view: "home",
    side: "buy",
    openId: null,
    giveId: data.featured.give,
    getId: data.featured.get,
    why: params.get("why") === "1",
    picking: null,
    booted: false
  };

  const $ = (sel, root) => (root || document).querySelector(sel);
  const live = $("#live");

  function esc(value) {
    return String(value).replace(/[&<>"']/g, ch => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[ch]));
  }

  function num(value) {
    return Number(value).toFixed(1);
  }

  function signed(value) {
    const n = Number(value);
    const body = Math.abs(n).toFixed(1);
    if (n > 0.05) return "+" + body;
    if (n < -0.05) return "\u2212" + body;
    return "0.0";
  }

  function titleFor(player) {
    if (player.camps) return "The charts are split on " + player.name + ".";
    if (player.gap >= 2.5) return "The charts are light on " + player.name + ".";
    if (player.gap <= -2.5) return "The charts pay up for " + player.name + ".";
    return player.name + " is close.";
  }

  function listFor(side) {
    const featured = side === "buy" ? data.featured.buy : data.featured.sell;
    return data.players
      .filter(player => (player.camps || Math.abs(player.gap) >= 2.5) && (side === "buy" ? player.gap > 0 : player.gap < 0))
      .sort((a, b) => {
        if (a.id === featured) return -1;
        if (b.id === featured) return 1;
        return side === "buy" ? b.gap - a.gap : a.gap - b.gap;
      });
  }

  function footnote() {
    return "Sample numbers from " + data.asOf + ", full PPR, 12 teams. The charts are rescaled onto one scale. The projection read is ESPN on that same scale. This is not live DDF Value, and this preview does not change the site.";
  }

  function posChip(pos) {
    return '<span class="chip" data-pos="' + esc(pos) + '">' + esc(pos) + "</span>";
  }

  function meters(player) {
    const charts = data.publishers
      .map(pub => ({name: pub.name, value: player.charts[pub.id]}))
      .sort((a, b) => b.value - a.value);
    const rows = [{name: "Projection read", value: player.espn, read: true}].concat(charts);
    return rows.map(row => {
      const width = Math.max(2, Math.min(100, (row.value / data.scaleMax) * 100));
      return (
        '<div class="meter-row">' +
          '<span class="meter-name">' + esc(row.name) + "</span>" +
          '<span class="meter-val">' + num(row.value) + "</span>" +
          '<span class="meter' + (row.read ? " is-read" : "") + '" aria-hidden="true"><span style="width:' + width.toFixed(1) + '%"></span></span>' +
        "</div>"
      );
    }).join("");
  }

  function detail(player) {
    const cap = player.capped
      ? '<p class="cap-note">In this sample the projection read stops at 70, so the lead is a floor.</p>'
      : "";
    return (
      '<div class="player-detail">' +
        meters(player) +
        '<p class="detail-blurb">' + esc(player.blurb) + "</p>" +
        cap +
      "</div>"
    );
  }

  function paintPeek() {
    const player = byId.get(data.featured.buy);
    $("#peekName").textContent = titleFor(player);
    $("#peekBlurb").textContent = player.blurb;
    $("#peekNums").innerHTML =
      '<span><b>' + num(player.espn) + "</b> projection</span>" +
      '<span><b>' + num(player.mid) + "</b> charts' middle</span>";
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
    const title = titleFor(player);
    const titleEl = $("#targetsTitle");
    const changed = state.booted && tick && titleEl.textContent !== title;
    titleEl.textContent = title;
    $("#targetsSub").textContent = player.blurb;
    $("#targetsChips").innerHTML =
      '<div class="chip-stat"><b>' + num(player.espn) + "</b><span>projection</span></div>" +
      '<div class="chip-stat"><b>' + num(player.mid) + "</b><span>charts' middle</span></div>";
    if (changed) {
      titleEl.classList.remove("tick");
      void titleEl.offsetWidth;
      titleEl.classList.add("tick");
      if (state.view === "targets") live.textContent = title;
    }
  }

  function renderList() {
    const list = listFor(state.side);
    $("#sideSeg").dataset.on = state.side;
    $("#sideBuy").setAttribute("aria-selected", state.side === "buy" ? "true" : "false");
    $("#sideSell").setAttribute("aria-selected", state.side === "sell" ? "true" : "false");
    $("#targetList").innerHTML = list.map(player => {
      const open = player.id === state.openId;
      return (
        '<article class="player' + (open ? " is-open" : "") + '" data-id="' + player.id + '">' +
          '<button type="button" class="player-sum" aria-expanded="' + (open ? "true" : "false") + '" aria-controls="detail-' + player.id + '">' +
            '<span class="who">' +
              '<span class="player-id"><span class="player-name">' + esc(player.name) + "</span></span>" +
              '<span class="player-meta">' + posChip(player.pos) + "<span>" + esc(player.team) + "</span></span>" +
              '<span class="player-short">' + esc(player.short) + "</span>" +
              '<span class="player-figs"><span><b>' + num(player.espn) + "</b> projection</span><span><b>" + num(player.mid) + "</b> charts</span></span>" +
            "</span>" +
            '<svg class="chev" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 8l5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
          "</button>" +
          '<div class="player-more" id="detail-' + player.id + '"><div class="player-more-inner">' +
            detail(player) +
          "</div></div>" +
        "</article>"
      );
    }).join("");
  }

  function round1(value) {
    return Math.round(value * 10) / 10;
  }

  function verdict() {
    const give = state.giveId == null ? null : byId.get(state.giveId);
    const get = state.getId == null ? null : byId.get(state.getId);
    if (!give && !get) {
      return {title: "Add a player to each side.", sub: "You get one sentence. The charts open under it.", proj: null, mid: null};
    }
    if (!give) return {title: "Who are you giving up?", sub: "Add that player and the answer sits up here.", proj: null, mid: null};
    if (!get) return {title: "Who are you getting?", sub: "Add that player and the answer sits up here.", proj: null, mid: null};
    if (give.id === get.id) {
      return {title: "Pick two different players.", sub: "A trade needs a player on each side.", proj: null, mid: null};
    }
    const proj = round1(get.espn - give.espn);
    const mid = round1(get.mid - give.mid);
    const close = n => Math.abs(n) < CLOSE;
    const sign = n => (n > 0.05 ? 1 : n < -0.05 ? -1 : 0);
    let title;
    if (close(proj) && close(mid)) title = "This is close on both reads.";
    else if (!close(proj) && !close(mid) && sign(proj) !== sign(mid)) title = "The two reads disagree.";
    else if (close(mid) && !close(proj)) title = "Close for the charts. Not for the projection read.";
    else if (close(proj) && !close(mid)) title = "Close on the projection read. Not for the charts.";
    else if (sign(proj) > 0 || (close(proj) && sign(mid) > 0)) title = "You come out ahead.";
    else title = "You come out behind.";

    function clause(label, n) {
      if (Math.abs(n) < CLOSE) return "On the " + label + ", you are about even (" + signed(n) + ").";
      if (n > 0) return "On the " + label + ", you gain " + num(n) + ".";
      return "On the " + label + ", you give up " + num(Math.abs(n)) + ".";
    }
    return {
      title: title,
      sub: clause("projection read", proj) + " " + clause("charts' middle", mid),
      proj: proj,
      mid: mid
    };
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
          "<span><b>" + num(player.espn) + "</b> projection</span>" +
          "<span><b>" + num(player.mid) + "</b> charts</span>" +
        "</span>" +
        '<span class="slot-change">Change</span>' +
      "</button>"
    );
  }

  function renderCompare(tick) {
    const result = verdict();
    const titleEl = $("#compareTitle");
    const changed = state.booted && tick && titleEl.textContent && titleEl.textContent !== result.title;
    titleEl.textContent = result.title;
    $("#compareSub").textContent = result.sub;
    const sample = state.giveId === data.featured.give && state.getId === data.featured.get;
    $("#compareEyebrow").innerHTML = sample
      ? 'Compare a trade <span class="chip">Sample</span>'
      : "Compare a trade";
    $("#compareChips").innerHTML = result.proj == null ? "" : (
      '<div class="chip-stat"><b>' + signed(result.proj) + "</b><span>projection</span></div>" +
      '<div class="chip-stat"><b>' + signed(result.mid) + "</b><span>charts' middle</span></div>"
    );
    const give = state.giveId == null ? null : byId.get(state.giveId);
    const get = state.getId == null ? null : byId.get(state.getId);
    $("#deal").innerHTML =
      slot("give", give) +
      '<div class="deal-for" aria-hidden="true">' +
        '<svg class="for-down" viewBox="0 0 24 24"><path d="M12 5v14M6 13l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
        '<svg class="for-right" viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
      "</div>" +
      slot("get", get);
    const onSample = sample;
    $("#compareActions").innerHTML =
      '<button type="button" class="texty" id="clearTrade">Clear</button>' +
      (onSample ? "" : '<button type="button" class="texty" id="useSample">Use the sample</button>');
    const ready = give && get && give.id !== get.id;
    const whyBtn = $("#whyBtn");
    whyBtn.hidden = !ready;
    $("#why").classList.toggle("is-open", state.why && ready);
    whyBtn.setAttribute("aria-expanded", state.why && ready ? "true" : "false");
    whyBtn.textContent = state.why ? "Hide the charts" : "Show the charts";
    if (ready) {
      $("#whyInner").innerHTML =
        '<div class="why-grid">' +
          whyCard(give, "You give") +
          whyCard(get, "You get") +
        "</div>" +
        '<p class="math">Charts\' middle, ' + num(get.mid) + " received \u2212 " + num(give.mid) + " given = " + signed(result.mid) + ". Projection read, " + num(get.espn) + " \u2212 " + num(give.espn) + " = " + signed(result.proj) + ".</p>";
    } else {
      $("#whyInner").innerHTML = "";
    }
    if (changed && state.view === "compare") {
      titleEl.classList.remove("tick");
      void titleEl.offsetWidth;
      titleEl.classList.add("tick");
      live.textContent = result.title;
    }
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

  const TITLES = {
    home: "Data Driven Football — preview",
    targets: "Targets — DDF preview",
    compare: "Compare — DDF preview"
  };

  function show(view, opts) {
    opts = opts || {};
    if (view === "more") { openDialog($("#moreSheet")); return; }
    if (view === "league") { openDialog($("#leagueSheet")); return; }
    if (view !== "home" && view !== "targets" && view !== "compare") view = "home";
    state.view = view;
    document.querySelectorAll(".view").forEach(section => {
      const on = section.id === view;
      section.classList.toggle("is-on", on);
      section.toggleAttribute("inert", !on);
      section.setAttribute("aria-hidden", on ? "false" : "true");
    });
    document.querySelectorAll("[data-go]").forEach(btn => {
      if (btn.dataset.go === "more" || btn.dataset.go === "league") return;
      if (btn.dataset.go === view) btn.setAttribute("aria-current", "page");
      else btn.removeAttribute("aria-current");
    });
    document.title = TITLES[view];
    if (opts.history !== false) {
      const next = "#" + view;
      if (location.hash !== next) history.pushState({view: view}, "", next);
    }
    window.scrollTo(0, 0);
    if (opts.focus && state.booted) {
      const target = document.getElementById(view + "Title");
      if (target) target.focus();
    }
  }

  let returnFocus = null;

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
    $("#pickerList").innerHTML = players.map(player => (
      '<button type="button" class="pick" role="option" data-id="' + player.id + '">' +
        posChip(player.pos) +
        '<span class="pick-name">' + esc(player.name) + "</span>" +
        '<span class="pick-team">' + esc(player.team) + "</span>" +
        '<span class="pick-num">' + num(player.espn) + "</span>" +
      "</button>"
    )).join("");
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

  document.addEventListener("click", event => {
    const go = event.target.closest("[data-go]");
    if (go) {
      event.preventDefault();
      show(go.dataset.go, {focus: true});
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
      renderCompare(true);
      return;
    }
    if (event.target.closest("#useSample")) {
      state.giveId = data.featured.give;
      state.getId = data.featured.get;
      renderCompare(true);
      return;
    }
    if (event.target.closest("#whyBtn")) {
      state.why = !state.why;
      renderCompare(false);
    }
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
  document.querySelectorAll("[data-close]").forEach(btn => {
    btn.addEventListener("click", () => closeDialog(btn.closest("dialog")));
  });
  $("#picker").addEventListener("close", () => {
    if (returnFocus) returnFocus.focus();
  });

  $("#themeBtn").addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    $("#themeBtn").setAttribute("aria-label", next === "dark" ? "Switch to light mode" : "Switch to dark mode");
    try { localStorage.setItem("ddf-concept-theme", next); } catch (e) { /* private mode */ }
  });

  window.addEventListener("hashchange", () => {
    const name = location.hash.replace("#", "");
    if (name === "home" || name === "targets" || name === "compare") show(name, {history: false, focus: false});
  });

  document.querySelectorAll(".footnote").forEach(node => { node.textContent = footnote(); });
  paintPeek();

  const openId = Number(params.get("open"));
  if (openId && byId.has(openId)) {
    const player = byId.get(openId);
    if ((player.camps || Math.abs(player.gap) >= 2.5) && player.gap !== 0) {
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
  if (view === "more" || view === "league") view = "home";
  show(view, {history: false, focus: false});
  state.booted = true;

  if (params.get("sheet") === "more") openDialog($("#moreSheet"));
  if (params.get("sheet") === "league") openDialog($("#leagueSheet"));

  document.documentElement.dataset.ready = "1";
})();
