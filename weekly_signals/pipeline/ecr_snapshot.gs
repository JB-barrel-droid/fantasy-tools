/**
 * FantasyPros ECR + Projections Snapshotter (v2: position-aware)
 * -------------------------------------------------------------
 * ECR cheatsheets expose full embedded ecrData JSON per position.
 * Projections pages are HTML tables and -- without a FantasyPros login --
 * only expose the TOP 10 per position. The snapshotter captures what is
 * available and labels it honestly; do not treat proj tabs as full coverage.
 *
 * Menu "ECR": Snapshot ECR now (overall), Snapshot position ECR, Snapshot
 * projections. Time-driven triggers 1-2x/week. Each position page is ONE
 * request; a full position-ECR run = 4 requests, projections = 4 requests.
 */

// Which ECR board to snapshot. Options: 'ppr', 'half-ppr', 'non-ppr'
const ECR_SCORING = 'ppr';

const ECR_URLS = {
  'ppr': 'https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php',
  'half-ppr': 'https://www.fantasypros.com/nfl/rankings/half-ppr-cheatsheets.php',
  'non-ppr': 'https://www.fantasypros.com/nfl/rankings/non-ppr-cheatsheets.php',
};

// Position ECR boards. These are STD-scoring season ("Draft" type) boards;
// in-season, weekly boards live at /nfl/rankings/<pos>.php?week=N.
const POSITIONS = ['qb', 'rb', 'wr', 'te'];
const ECR_POS_URLS = {
  'qb': 'https://www.fantasypros.com/nfl/rankings/qb-cheatsheets.php',
  'rb': 'https://www.fantasypros.com/nfl/rankings/rb-cheatsheets.php',
  'wr': 'https://www.fantasypros.com/nfl/rankings/wr-cheatsheets.php',
  'te': 'https://www.fantasypros.com/nfl/rankings/te-cheatsheets.php',
};

// Projections pages. ?week=draft = season projections; in-season use ?week=N.
// NOTE: without login these pages render only the top 10 per position.
const PROJ_WEEK = 'draft'; // or e.g. '2' in-season
const PROJ_URLS = {
  'qb': 'https://www.fantasypros.com/nfl/projections/qb.php?week=' + PROJ_WEEK,
  'rb': 'https://www.fantasypros.com/nfl/projections/rb.php?week=' + PROJ_WEEK,
  'wr': 'https://www.fantasypros.com/nfl/projections/wr.php?week=' + PROJ_WEEK,
  'te': 'https://www.fantasypros.com/nfl/projections/te.php?week=' + PROJ_WEEK,
};

const SHEET_NAME = 'ecr_snapshots';

const HEADERS = [
  'snapshot_at', 'year', 'week', 'scoring', 'total_experts',
  'player_id', 'player_name', 'team', 'pos', 'pos_rank',
  'rank_ecr', 'rank_ave', 'rank_min', 'rank_max', 'rank_std',
  'tier', 'bye_week', 'fp_url',
];

// Per-position projection stat columns (as rendered on the page), then FPTS.
const PROJ_STAT_COLS = {
  'qb': ['pass_att', 'pass_cmp', 'pass_yds', 'pass_tds', 'pass_int',
         'rush_att', 'rush_yds', 'rush_tds', 'fum_lost'],
  'rb': ['rush_att', 'rush_yds', 'rush_tds',
         'rec', 'rec_yds', 'rec_tds', 'fum_lost'],
  'wr': ['rec', 'rec_yds', 'rec_tds',
         'rush_att', 'rush_yds', 'rush_tds', 'fum_lost'],
  'te': ['rec', 'rec_yds', 'rec_tds',
         'rush_att', 'rush_yds', 'rush_tds', 'fum_lost'],
};

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('ECR')
    .addItem('Snapshot ECR now', 'snapshotEcr')
    .addItem('Snapshot position ECR (QB/RB/WR/TE)', 'snapshotPositionEcr')
    .addItem('Snapshot projections (top-10 only)', 'snapshotProjections')
    .addToUi();
}

function fetchPage(url) {
  const resp = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: { 'User-Agent': UA },
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error('Fetch failed, HTTP ' + resp.getResponseCode() + ' for ' + url);
  }
  return resp.getContentText();
}

function snapshotEcr() {
  const url = ECR_URLS[ECR_SCORING];
  if (!url) throw new Error('Unknown ECR_SCORING: ' + ECR_SCORING);
  const html = fetchPage(url);
  const data = parseEcrData(html);
  writeRows(SHEET_NAME, HEADERS, ecrRows(data, ECR_SCORING));
  toast('ECR snapshot saved: ' + data.players.length + ' players, season ' +
    data.year + ' week ' + data.week + ' (' + ECR_SCORING + ', ' +
    data.total_experts + ' experts).');
}

function snapshotPositionEcr() {
  let total = 0;
  POSITIONS.forEach(function (pos) {
    const html = fetchPage(ECR_POS_URLS[pos]);
    const data = parseEcrData(html);
    const sheetName = pos + '_ecr';
    // Position boards are STD draft-type; record that in the scoring column.
    writeRows(sheetName, HEADERS, ecrRows(data, 'std-draft'));
    total += data.players.length;
  });
  toast('Position ECR saved: ' + total + ' players across QB/RB/WR/TE.');
}

function snapshotProjections() {
  let total = 0;
  POSITIONS.forEach(function (pos) {
    const html = fetchPage(PROJ_URLS[pos]);
    const rows = parseProjTable(html, pos);
    const headers = ['snapshot_at', 'proj_week', 'player_name', 'team', 'pos']
      .concat(PROJ_STAT_COLS[pos], ['fpts_std']);
    writeRows(pos + '_proj', headers, rows);
    total += rows.length;
  });
  toast('Projections saved: ' + total + ' players (page shows top-10 per position without login).');
}

function parseEcrData(html) {
  const m = html.match(/var ecrData = (\{[\s\S]*?\});/);
  if (!m) throw new Error('Could not find embedded ecrData JSON (layout may have changed).');
  const data = JSON.parse(m[1]);
  if (!data.players || !data.players.length) throw new Error('ecrData contained no players.');
  return data;
}

function ecrRows(data, scoring) {
  const now = new Date();
  return data.players.map(function (p) {
    return [
      now,
      num(data.year),
      num(data.week),
      scoring,
      num(data.total_experts),
      num(p.player_id),
      p.player_name || '',
      p.player_team_id || '',
      p.player_position_id || '',
      p.pos_rank || '',
      num(p.rank_ecr),
      num(p.rank_ave),
      num(p.rank_min),
      num(p.rank_max),
      num(p.rank_std),
      num(p.tier),
      num(p.player_bye_week),
      p.player_page_url || '',
    ];
  });
}

function parseProjTable(html, pos) {
  const now = new Date();
  const tbody = html.match(/<tbody[^>]*>([\s\S]*?)<\/tbody>/i);
  if (!tbody) throw new Error('No projections table body found for ' + pos + ' (layout may have changed).');
  const out = [];
  const trRe = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
  let tr;
  while ((tr = trRe.exec(tbody[1])) !== null) {
    const cells = [];
    const tdRe = /<td[^>]*>([\s\S]*?)<\/td>/gi;
    let td;
    while ((td = tdRe.exec(tr[1])) !== null) {
      cells.push(td[1].replace(/<[^>]+>/g, '').replace(/,/g, '').trim());
    }
    if (cells.length < 3) continue;
    // First cell is "Name TEAM"; last cell is FPTS.
    const nameTeam = cells[0].split(/\s+/);
    const team = nameTeam.pop();
    const name = nameTeam.join(' ');
    const stats = cells.slice(1, -1).map(num);
    const fpts = num(cells[cells.length - 1]);
    out.push([now, PROJ_WEEK, name, team, pos.toUpperCase()]
      .concat(stats, [fpts]));
  }
  if (!out.length) throw new Error('Projections table parsed to zero rows for ' + pos + '.');
  return out;
}

function writeRows(sheetName, headers, rows) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(1);
  }
  sheet
    .getRange(sheet.getLastRow() + 1, 1, rows.length, headers.length)
    .setValues(rows);
}

function toast(msg) {
  SpreadsheetApp.getActiveSpreadsheet().toast(msg, 'ECR Snapshot', 10);
  Logger.log(msg);
}

function num(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  return isNaN(n) ? '' : n;
}
