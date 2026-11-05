/* JEG-1348: display-only measured context and fixed historical cohorts.
   Integration is held separately while another lane owns v2.js. */
(function (root) {
  "use strict";
  const POSITIONS = ["QB", "RB", "WR", "TE"];
  function measuredText(readout) {
    if (!readout || readout.error || !Number.isInteger(readout.weeksLeft)
        || readout.weeksLeft < 0) return "Measured: weeks left and byes left unavailable";
    const weeks = readout.weeksLeft;
    const window = readout.window;
    const horizon = weeks && Array.isArray(window)
      ? (window[0] === window[1] ? ` (week ${window[0]})` : ` (weeks ${window[0]}–${window[1]})`) : "";
    const byes = Number.isInteger(readout.byesLeft) && readout.byesLeft >= 0
      && Number.isInteger(readout.byeTeams) && readout.byeTeams > 0
      && readout.byesLeft <= readout.byeTeams
      ? `${readout.byesLeft} of ${readout.byeTeams} teams have a bye in this window` : "byes left unavailable";
    return `Measured: ${weeks} ${weeks === 1 ? "week" : "weeks"} left${horizon} · ${byes}`;
  }
  function evidenceRows(evidence) {
    if (!evidence || evidence.schema !== "bench-breakout-evidence/1"
        || evidence.evidence !== "historical" || evidence.measureWeek !== 9
        || evidence.teams !== 12 || evidence.seasons !== "2015–2025"
        || typeof evidence.basis !== "string" || !evidence.basis.trim()
        || !Array.isArray(evidence.rows)
        || !evidence.rows.every(row => row && typeof row === "object" && !Array.isArray(row))) return null;
    const rows = [];
    for (const pos of POSITIONS) {
      const cells = [];
      for (const depth of [1, 2, 3]) {
        const found = evidence.rows.filter(row => row.position === pos && row.depth === depth);
        if (found.length !== 1) return null;
        const row = found[0];
        if (row.id !== `O3.${pos}.d${depth}`
            || !Number.isFinite(row.rate) || row.rate < 0 || row.rate > 1
            || !Number.isInteger(row.n) || row.n <= 0 || !Number.isInteger(row.breakouts)
            || row.breakouts < 0 || row.breakouts > row.n
            || Math.abs(row.rate - row.breakouts / row.n) > 0.000051) return null;
        cells.push(`${(row.rate * 100).toFixed(1)}% (${row.breakouts}/${row.n})`);
      }
      rows.push({position: pos, cells});
    }
    return rows;
  }
  function mount(container, evidence) {
    const doc = container.ownerDocument;
    const line = doc.createElement("p");
    line.className = "v2-meta";
    line.dataset.benchContext = "";
    const details = doc.createElement("details");
    details.className = "v2-meta v2-padv";
    details.dataset.benchHistorical = "";
    const summary = doc.createElement("summary");
    summary.textContent = "Historical breakout odds · week-9 backups";
    details.appendChild(summary);
    const rows = evidenceRows(evidence);
    if (rows) {
      const table = doc.createElement("table");
      const caption = doc.createElement("caption");
      caption.textContent = `${evidence.seasons} · ${evidence.teams}-team cohorts · breakouts / sample count`;
      table.appendChild(caption);
      const thead = doc.createElement("thead"), header = doc.createElement("tr");
      for (const label of ["Position", "Backup #1", "Backup #2", "Backup #3"]) {
        const th = doc.createElement("th"); th.scope = "col"; th.textContent = label; header.appendChild(th);
      }
      thead.appendChild(header); table.appendChild(thead);
      const tbody = doc.createElement("tbody");
      for (const row of rows) {
        const tr = doc.createElement("tr"), th = doc.createElement("th");
        th.scope = "row"; th.textContent = row.position; tr.appendChild(th);
        for (const cell of row.cells) { const td = doc.createElement("td"); td.textContent = cell; tr.appendChild(td); }
        tbody.appendChild(tr);
      }
      table.appendChild(tbody); details.appendChild(table);
      const note = doc.createElement("p"); note.textContent = evidence.basis; details.appendChild(note);
    } else {
      const note = doc.createElement("p"); note.textContent = "Historical breakout odds unavailable"; details.appendChild(note);
    }
    container.append(line, details);
    return readout => { line.textContent = measuredText(readout); };
  }
  root.TradeValueBenchContext = Object.freeze({measuredText, evidenceRows, mount});
})(typeof window !== "undefined" ? window : globalThis);
