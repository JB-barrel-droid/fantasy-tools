(function (root) {
  'use strict';
  const choices = {
    scoring: ['half_ppr', 'ppr', 'standard'],
    position: ['all', 'QB', 'RB', 'WR', 'TE', 'K', 'DST'],
    coverage: ['all', 'both', 'partial', 'missing', 'comparable'],
    sort: ['name', 'difference']
  };
  function filters(search) {
    const params = new URLSearchParams(search);
    return Object.fromEntries(Object.entries(choices).map(([key, values]) =>
      [key, values.includes(params.get(key)) ? params.get(key) : values[0]]));
  }
  function selectRows(view, state) {
    const rows = view.players.filter(row => {
      const cell = row.scoring[state.scoring];
      return (state.position === 'all' || row.position === state.position) &&
        (state.coverage === 'all' || (state.coverage === 'comparable' ?
          cell.difference !== null : cell.coverage === state.coverage));
    });
    return rows.sort((a, b) => {
      if (state.sort === 'difference') {
        const av = a.scoring[state.scoring].difference, bv = b.scoring[state.scoring].difference;
        if (av === null && bv !== null) return 1;
        if (bv === null && av !== null) return -1;
        if (av !== null && bv !== null && Math.abs(av) !== Math.abs(bv)) return Math.abs(bv) - Math.abs(av);
      }
      return a.name.localeCompare(b.name) || (a.player_key || 0) - (b.player_key || 0);
    });
  }
  function counts(rows, scoring) {
    const out = {total: rows.length, both: 0, partial: 0, missing: 0, comparable: 0};
    rows.forEach(row => {
      const cell = row.scoring[scoring];
      out[cell.coverage]++;
      if (cell.difference !== null) out.comparable++;
    });
    return out;
  }
  function cellText(cell) {
    if (cell.value === null) return '—';
    return cell.units === 'rank' ? '#' + cell.value : cell.value.toLocaleString('en-US', {maximumFractionDigits: 2}) + ' pts';
  }
  function mount(view, doc, win) {
    const byId = id => doc.getElementById(id);
    const node = (tag, text, cls) => {
      const el = doc.createElement(tag);
      el.textContent = text;
      if (cls) el.className = cls;
      return el;
    };
    byId('week').textContent = view.season + ' · Week ' + view.content_week + ' · Built ' + view.built_at;
    Object.entries(view.legs).forEach(([side, leg]) => {
      const card = node('article', '');
      card.append(node('h3', side === 'ecr' ? 'ECR · weekly' : 'Vegas · PropLine'));
      card.append(node('p', leg ? [leg.availability, leg.freshness || 'unavailable', leg.label].join(' · ') : 'Unavailable'));
      card.append(node('p', leg ? 'Content: ' + (leg.content_vintage || 'unknown') + ' · Week ' + (leg.content_week || 'unknown') : 'Weekly input not supplied', 'vintage'));
      if (leg && leg.missing_reason) card.append(node('p', leg.missing_reason, 'vintage'));
      byId('health').append(card);
    });
    byId('warnings').textContent = view.warnings.map(i => i.code + ': ' + i.message).join(' · ');
    byId('plays').textContent = view.plays_reason;
    byId('provenance').textContent = 'Producer: ' + view.producer + (view.input_sha256 ? ' · Input SHA-256: ' + view.input_sha256 : '');
    byId('metadata').textContent = JSON.stringify(view.legs, null, 2);
    function render() {
      const state = filters(win.location.search);
      Object.keys(choices).forEach(key => { byId(key).value = state[key]; });
      const rows = selectRows(view, state), count = counts(rows, state.scoring);
      byId('summary').textContent = count.total + ' players shown · ' + count.both + ' with both values · ' + count.partial + ' with one · ' + count.missing + ' with neither · ' + count.comparable + ' comparable';
      byId('players').replaceChildren();
      rows.forEach(row => {
        const cell = row.scoring[state.scoring], tr = node('tr', '');
        const name = node('td', '');
        name.append(node('span', row.name, 'player-name'), node('span', row.position + ' · ' + (row.team || 'Team unknown'), 'player-meta'));
        if (row.unresolved_reason) name.append(node('span', row.unresolved_reason, 'cell-reason'));
        const identity = node('details', '', 'identity ddf-fn-disclosure');
        identity.append(node('summary', 'Player identity'));
        identity.append(node('p', 'Player key: ' + (row.player_key === null ? 'Unresolved' : row.player_key)));
        identity.append(node('p', 'Resolved by: ' + (row.resolved_by || 'Not supplied')));
        identity.append(node('pre', 'Source IDs: ' + JSON.stringify(row.source_ids, null, 2)));
        name.append(identity);
        tr.append(name);
        ['ecr', 'vegas'].forEach(side => {
          const source = cell[side], td = node('td', cellText(source));
          td.dataset.label = side === 'ecr' ? 'ECR (weekly)' : 'Vegas (props-implied)';
          if (source.reason) td.append(node('span', source.reason, 'cell-reason'));
          tr.append(td);
        });
        // Keep the sign at display precision consistent with the direction.
        const difference = cell.difference;
        const text = difference === null ? '—' : difference === 0 ? '0.0 pts' :
          (difference > 0 ? '+' : '−') + (Math.abs(difference) < 0.05 ? '<0.1' : Math.abs(difference).toFixed(1)) + ' pts';
        const delta = node('td', text);
        delta.dataset.label = 'Difference';
        const read = node('td', cell.direction || cell.reason, cell.direction ? 'direction' : '');
        read.dataset.label = 'Read / coverage';
        tr.append(delta, read);
        byId('players').append(tr);
      });
      byId('empty').hidden = rows.length !== 0;
    }
    byId('filters').addEventListener('submit', event => event.preventDefault());
    byId('filters').addEventListener('change', () => {
      const url = new URL(win.location.href);
      Object.keys(choices).forEach(key => url.searchParams.set(key, byId(key).value));
      win.history.pushState(null, '', url);
      render();
    });
    win.addEventListener('popstate', render);
    render();
  }
  const api = {filters, selectRows, counts, cellText, mount};
  if (typeof module === 'object' && module.exports) module.exports = api;
  else {
    root.VersusVegas = api;
    mount(JSON.parse(document.getElementById('versus-data').textContent), document, root);
  }
})(typeof window === 'undefined' ? globalThis : window);
