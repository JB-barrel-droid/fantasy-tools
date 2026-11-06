"""Append-only native-content observations. SQLite schema is created locally only.

Collectors supply parsed native rows, never rescaled/baked values. Snapshots are
retained in each observation; failures cannot replace the last accepted payload.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from functools import wraps
from pathlib import Path
import sqlite3

try:
    from .timestamps import parse_iso_timestamp
except ImportError:  # standalone pullers import from pipelines/lib
    from timestamps import parse_iso_timestamp

VERSION = 'native-v3-cbs-scoring'
DEFAULT_PATH = Path(__file__).resolve().parents[2] / 'data/content-observations.sqlite3'
SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
 id INTEGER PRIMARY KEY, scope TEXT NOT NULL, attempted_at TEXT NOT NULL,
 result TEXT NOT NULL, observation_kind TEXT NOT NULL, successful_fetch_at TEXT, normalized_content_hash TEXT,
 normalizer_version TEXT NOT NULL, previous_hash TEXT, last_observed_change_at TEXT,
 source_updated_at TEXT, timestamp_reliability TEXT NOT NULL,
 coverage TEXT NOT NULL, raw_snapshot_reference TEXT, snapshot TEXT,
 consumers TEXT NOT NULL, ingested_hash TEXT, served_hash TEXT
);
CREATE INDEX IF NOT EXISTS observations_scope ON observations(scope, id);
CREATE TRIGGER IF NOT EXISTS observations_no_update BEFORE UPDATE ON observations
 BEGIN SELECT RAISE(ABORT, 'observations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS observations_no_delete BEFORE DELETE ON observations
 BEGIN SELECT RAISE(ABORT, 'observations are append-only'); END;
"""


def stamp(value):
    dt = parse_iso_timestamp(value)
    if dt.tzinfo is None or 'T' not in value:
        raise ValueError('exact timezone-aware timestamp required')
    return dt.astimezone(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True)
class Scope:
    source: str
    dataset: str
    season: int
    week_slate: str
    scoring: str
    variant: str

    def key(self):
        if any(v is None or v == '' for v in asdict(self).values()):
            raise ValueError('all scope dimensions required (use explicit all/ros/native)')
        return json.dumps(asdict(self), sort_keys=True)


def number(value):
    """Lossless decimal encoding at source precision; null is never zero."""
    if value is None or value == '':
        return None
    try:
        n = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('invalid numeric content') from exc
    if not n.is_finite():
        raise ValueError('non-finite numeric content')
    return '0' if n == 0 else format(n.normalize(), 'f')


# Explicit native columns. Retrieval/page stamps and derived trade values excluded.
CBS_FIELDS = ('gp pass_att pass_cmp pass_yds pass_yds_g pass_td int rate '
              'rush_att rush_yds rush_avg rush_td fl tgt rec rec_yds rec_yds_g '
              'rec_avg rec_td cbs_fpts cbs_fppg').split()
RAZZ_FIELDS = ('rz_std_ppg rz_half_ppr_ppg rz_ppr_ppg games_reported '
               'pass_att pass_cmp pass_yds pass_td int rush_att rush_yds rush_td '
               'tgt rec rec_yds rec_td fl pg_snaps pg_cmp pg_att pg_pass_yds pg_pass_td '
               'pg_int pg_sacks pg_rush_att pg_rush_yds pg_rush_td pg_fum pg_tgt '
               'pg_rec pg_rec_yds pg_rec_td share_rush share_tgt').split()


def normalize(source, rows):
    """Parsed row contracts: ESPN canon/pos/weeks (or stats); FC player/value;
    Razzball position-table native ppg columns; CBS parsed ROS stat columns.
    ESPN skill, kicker, defense must be submitted as separate dataset scopes.
    """
    out = []
    for row in rows:
        player = row.get('player') if isinstance(row.get('player'), dict) else {}
        identity = next((v for v in (row.get('player_key'), row.get('player_id'), row.get('fantasycalc_id'),
                        player.get('id'), row.get('canon'), row.get('player_name'),
                        row.get('name'), row.get('player')) if v is not None), None)
        if identity is None or isinstance(identity, dict):
            raise ValueError('missing stable source/player identity')
        pos = str(row.get('pos') or player.get('position') or '').strip().upper()
        base = {'id': str(identity).strip(), 'pos': pos,
                'team': str(row.get('team') or player.get('team') or '').strip()}
        if source == 'espn':
            stats = row.get('weeks', row.get('stats'))
            if not isinstance(stats, dict) or not stats:
                raise ValueError('ESPN requires native weeks/stats')
            def numeric_tree(obj):
                return {str(k): numeric_tree(v) for k, v in obj.items()} if isinstance(obj, dict) else number(obj)
            base['stats'] = numeric_tree(stats)
        elif source == 'fantasycalc':
            if 'value' not in row:
                raise ValueError('FantasyCalc native value missing')
            base['value'] = number(row['value'])
        elif source in ('razzball', 'cbsros'):
            fields = RAZZ_FIELDS if source == 'razzball' else CBS_FIELDS
            required = RAZZ_FIELDS[:3] if source == 'razzball' else ('gp',)
            if any(k not in row for k in required):
                raise ValueError('missing native columns')
            stats = dict(row.get('raw_stats') or {})
            stats.update({k: row[k] for k in fields if k in row})
            base['stats'] = {k: number(stats.get(k)) for k in fields}
        else:
            raise ValueError('unsupported source adapter: ' + source)
        out.append(base)
    if not out:
        raise ValueError('empty payload')
    keys = [(r['id'], r['pos']) for r in out]
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate identities')
    return sorted(out, key=lambda r: (r['id'], r['pos']))


def numeric_hash(normalized):
    # Keep descriptive fields in snapshots/coverage, but only identity and native
    # numbers can renew the numeric-change clock. Sort after removing metadata.
    numeric = [{k: v for k, v in row.items() if k not in ('team', 'pos')}
               for row in normalized]
    numeric.sort(key=lambda row: json.dumps(row, sort_keys=True))
    return hashlib.sha256(json.dumps(numeric, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def content_hash(source, rows):
    return numeric_hash(normalize(source, rows))


class Ledger:
    def __init__(self, path=None):
        configured = path or os.environ.get('CONTENT_OBSERVATION_LEDGER') or DEFAULT_PATH
        self.path = Path(configured).absolute()

    def latest(self, scope):
        if not self.path.exists():
            return None
        with sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM observations WHERE scope=? ORDER BY id DESC LIMIT 1',
                             (scope.key(),)).fetchone()
            return dict(row) if row else None

    def observe(self, scope, rows=None, *, attempted_at, expected, complete=True,
                result='success', source_updated_at=None, trusted_numeric_time=False,
                raw_snapshot_reference=None, consumers=(), normalizer_version=VERSION,
                ingested_hash=None, served_hash=None):
        now = stamp(attempted_at)
        scope.key()  # validate before any write
        normalized = normalize(scope.source, rows) if result == 'success' else None
        if normalized and scope.source == 'espn':
            allowed = {'skill': {'QB', 'RB', 'WR', 'TE'}, 'k': {'K'}, 'dst': {'DST', 'DEF', 'D/ST'}}
            if scope.dataset not in allowed or any(r['pos'] not in allowed[scope.dataset] for r in normalized):
                raise ValueError('ESPN requires independent skill/k/dst dataset scopes')
        count = len(normalized or [])
        if expected <= 0:
            raise ValueError('positive expected coverage required')
        if result == 'success' and (not complete or count != expected):
            result = 'incomplete_scope'
        if source_updated_at and trusted_numeric_time:
            stamp(source_updated_at)
        digest = numeric_hash(normalized) if normalized else None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript(SCHEMA)
            db.execute('BEGIN IMMEDIATE')
            db.row_factory = sqlite3.Row
            previous = db.execute('SELECT * FROM observations WHERE scope=? ORDER BY id DESC LIMIT 1',
                                  (scope.key(),)).fetchone()
            p = dict(previous) if previous else {}
            if p and now < stamp(p['attempted_at']):
                raise ValueError('observations must be chronological')
            accepted = result == 'success'
            same_version = p.get('normalizer_version') == normalizer_version
            change = p.get('last_observed_change_at') if same_version or not accepted else None
            old_hash = p.get('normalized_content_hash')
            if accepted and old_hash and same_version and digest != old_hash:
                change = iso(now)
            kind = ('not_accepted' if not accepted else 'initial_baseline' if not old_hash
                    else 'normalizer_baseline' if not same_version
                    else 'unchanged' if digest == old_hash else 'observed_change')
            values = dict(scope=scope.key(), attempted_at=iso(now), result=result,
                observation_kind=kind,
                successful_fetch_at=iso(now) if accepted else p.get('successful_fetch_at'),
                normalized_content_hash=digest if accepted else old_hash,
                normalizer_version=normalizer_version if accepted else p.get('normalizer_version', normalizer_version), previous_hash=old_hash,
                last_observed_change_at=change,
                source_updated_at=(p.get('source_updated_at') if digest == old_hash and same_version else source_updated_at) if accepted else p.get('source_updated_at'),
                timestamp_reliability=(p.get('timestamp_reliability', 'unverified') if not accepted or (digest == old_hash and same_version) else 'trusted_numeric' if trusted_numeric_time else 'unverified'),
                coverage=json.dumps({'complete': accepted, 'observed': count, 'expected': expected}),
                raw_snapshot_reference=raw_snapshot_reference,
                snapshot=json.dumps(normalized), consumers=json.dumps(list(consumers)),
                ingested_hash=ingested_hash, served_hash=served_hash)
            db.execute(f"INSERT INTO observations ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
        return self.latest(scope)


def verdict(observation, now=None):
    now = stamp(now) if now else datetime.now(timezone.utc)
    o = observation or {}
    reasons = []
    change = o.get('last_observed_change_at')
    vendor = o.get('source_updated_at') if o.get('timestamp_reliability') == 'trusted_numeric' else None
    times = [stamp(t) for t in (change, vendor) if t]
    age = max((now - t).total_seconds() for t in times) if times else None
    if not times:
        reasons.append('content_vintage_unknown')
    if any(t > now for t in times):
        reasons.append('future_timestamp')
    if len(times) == 2 and abs((times[0] - times[1]).total_seconds()) > 86400:
        reasons.append('timestamp_inconsistent')
    if age is not None and age > 86400:
        reasons.append('content_stale')
    for label in ('ingested_hash', 'served_hash'):
        if o.get(label) and o[label] != o.get('normalized_content_hash'):
            reasons.append(label + '_mismatch')
    fetch = o.get('successful_fetch_at')
    if fetch and stamp(fetch) > now:
        reasons.append('future_fetch_timestamp')
    if not fetch or (now - stamp(fetch)).total_seconds() > 86400:
        reasons.append('pull_overdue')
    coverage = json.loads(o['coverage']) if o.get('coverage') else {}
    if not coverage.get('complete') or not coverage.get('expected') or coverage.get('observed') != coverage.get('expected'):
        reasons.append('incomplete_coverage')
    if o.get('result') and o['result'] != 'success':
        reasons.append(o['result'])
    return dict(stale=bool(reasons), reason=reasons[0] if reasons else None,
                reasons=reasons, content_age_seconds=age,
                successful_fetch_at=fetch, last_observed_change_at=change,
                normalized_content_hash=o.get('normalized_content_hash'),
                coverage=json.loads(o['coverage']) if o.get('coverage') else None,
                evaluated_at=iso(now))


def acquisition_scope(source, scoring='native', variant='native'):
    # These acquisition entry points are explicitly 2026 ROS producers.
    return Scope(source, 'skill' if source == 'espn' else
                 'values' if source == 'fantasycalc' else 'ros',
                 2026, 'ros', scoring, variant)


class ObservationWriteError(OSError):
    pass


def espn_expectations():
    """Independent, operator-reviewed manifest: [{"id": canon, "pos": position}].

    Never bootstrap this expectation from the acquisition being checked.
    Missing configuration deliberately prevents complete coverage.
    """
    path = os.environ.get('CONTENT_OBSERVATION_ESPN_EXPECTATIONS')
    if not path:
        return set()
    rows = json.loads(Path(path).read_text())
    pairs = {(str(r['id']).strip(), str(r['pos']).upper()) for r in rows}
    if not pairs or len(pairs) != len(rows) or any(not i or p not in
            {'QB', 'RB', 'WR', 'TE'} for i, p in pairs):
        raise ValueError('invalid ESPN coverage manifest')
    return pairs


def acquired(source, rows, *, scoring='native', variant='native', complete=True):
    """Must succeed before promoting an acquisition, including unchanged pulls."""
    try:
        expected = max(1, len(rows))
        if source == 'espn':
            required = espn_expectations()
            received = {(r['id'], r['pos']) for r in normalize(source, rows)}
            complete = complete and bool(required) and received == required
            expected = max(1, len(required))
        return Ledger().observe(acquisition_scope(source, scoring, variant), rows,
            attempted_at=iso(datetime.now(timezone.utc)), expected=expected,
            complete=complete, consumers=('dataset_status',))
    except (OSError, sqlite3.Error) as exc:
        raise ObservationWriteError('content observation write failed; promotion stopped') from exc


def recorded_scopes(ledger=None):
    """Read acquisition scope keys; status validates required coverage separately."""
    ledger = ledger or Ledger()
    if not ledger.path.exists():
        return {}
    with sqlite3.connect(ledger.path.as_uri() + '?mode=ro', uri=True) as db:
        keys = [json.loads(r[0]) for r in db.execute('SELECT DISTINCT scope FROM observations')]
    out = {}
    for key in keys:
        if key['season'] == 2026 and key['week_slate'] == 'ros':
            out.setdefault(key['source'], []).append(key)
    return out


def acquisition_entry(source):
    """Record failed/partial runs without swallowing producer or ledger failures."""
    def decorate(fn):
        @wraps(fn)
        def run(*args, **kwargs):
            try:
                result = fn(*args, **kwargs)
            except SystemExit as exc:
                if exc.code:
                    record_failure(source)
                raise
            except ObservationWriteError:
                raise
            except Exception:
                record_failure(source)
                raise
            if result:
                record_failure(source)
            return result
        return run
    return decorate


def record_failure(source, scopes=None):
    ledger = Ledger()
    defaults = ([asdict(acquisition_scope(source, scoring, f'12_qb{qbs}'))
                 for qbs in (1, 2) for scoring in ('standard', 'half', 'full')]
                if source == 'fantasycalc' else [asdict(acquisition_scope(source))])
    keys = ([asdict(k) for k in scopes] if scopes is not None
            else recorded_scopes(ledger).get(source) or defaults)
    try:
        for key in keys:
            ledger.observe(Scope(**key), attempted_at=iso(datetime.now(timezone.utc)),
                           expected=1, result='failed', consumers=('dataset_status',))
    except (OSError, sqlite3.Error) as exc:
        raise ObservationWriteError('failure observation write failed') from exc
