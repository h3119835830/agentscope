"""Durable public connection observations; never a source of live authority."""
import json
import sqlite3
from fastapi import HTTPException
from .. import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace_connection_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, instance_id TEXT NOT NULL,
 kind TEXT NOT NULL, name TEXT NOT NULL, event TEXT NOT NULL,
 status TEXT NOT NULL, previous_status TEXT, generation TEXT,
 occurred_at TEXT NOT NULL, snapshot_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workspace_connection_events_instance
 ON workspace_connection_events(instance_id,id DESC);
"""
STATES = {'connected','running_unattached','offline','unresponsive','unknown','stale','ended','removed'}


def snapshot(row):
    """Explicit metadata allowlist: no credentials, raw replies or file bytes."""
    result = {key: row.get(key) for key in
              ('pid','start_ticks','generation','check_sequence','observed_at','expires_at','session_id')}
    result.update(instance_id=row['id'], kind=row['kind'], name=str(row.get('name') or row['id'])[:120],
                  status=row.get('status') if row.get('status') in STATES else 'unknown',
                  connected=row.get('connected') is True, available=row.get('available') is True)
    result['workspaces'] = sorted([
        {'id': str(w['workspaceId']), 'name': str(w.get('title') or '')[:120],
         'session_ids': sorted(str(s) for s in w.get('sessionIds', []))}
        for w in row.get('workspaces', []) if w.get('workspaceId')
    ], key=lambda w: w['id'])
    return result


def stable(value):
    return {k: v for k, v in value.items()
            if k not in {'check_sequence','observed_at','expires_at'}}


def record(row, trigger='observation', manual=False):
    if row.get('kind') not in {'native','managed'}:
        return
    value = snapshot(row)
    with db.connect() as con:
        # Deduplication and append share the write lock, including API/worker races.
        con.execute('BEGIN IMMEDIATE')
        last = con.execute('SELECT * FROM workspace_connection_events WHERE instance_id=? ORDER BY id DESC LIMIT 1',
                           (value['instance_id'],)).fetchone()
        previous = json.loads(last['snapshot_json']) if last else None
        if not manual and previous and stable(previous) == stable(value):
            return
        last_generation = con.execute('''SELECT generation FROM workspace_connection_events
            WHERE instance_id=? AND generation IS NOT NULL ORDER BY id DESC LIMIT 1''',
                                      (value['instance_id'],)).fetchone()
        event = trigger
        if manual:
            event = 'manual_check'
        elif trigger == 'observation':
            event = ('first_observation' if not previous else
                     'generation_changed' if last_generation and value.get('generation')
                     and last_generation['generation'] != value['generation'] else
                     'status_changed' if previous['status'] != value['status'] else 'workspace_changed')
        con.execute('''INSERT INTO workspace_connection_events
            (instance_id,kind,name,event,status,previous_status,generation,occurred_at,snapshot_json)
            VALUES(?,?,?,?,?,?,?,?,?)''',
            (value['instance_id'], value['kind'], value['name'], event, value['status'],
             previous['status'] if previous else None, value['generation'], db.now(),
             json.dumps(value, ensure_ascii=False)))


def record_safely(row, trigger='observation', manual=False):
    try:
        record(row, trigger, manual)
        row.pop('history_error', None)
    except (sqlite3.Error, OSError):
        # An archive storage fault must not change independently observed liveness.
        row['history_error'] = '本次连接记录未能保存，后续检查将重试'
        import logging
        logging.getLogger(__name__).warning('Connection history storage unavailable')


def retire_missing(native_ids, managed_ids):
    """Close durable bindings after a successful inventory, also after API restart.

    This is a control-plane retirement, not a claim that a process was killed.
    GET snapshots can prune memory without losing this lifecycle receipt.
    """
    try:
        with db.connect() as con:
            rows = con.execute('''SELECT e.* FROM workspace_connection_events e JOIN
                (SELECT instance_id,MAX(id) AS latest FROM workspace_connection_events GROUP BY instance_id) s
                ON e.id=s.latest WHERE e.status NOT IN ('ended','removed')''').fetchall()
    except (sqlite3.Error, OSError):
        import logging
        logging.getLogger(__name__).warning('Connection retirement history storage unavailable')
        return
    for old in rows:
        kind = old['kind']
        if old['instance_id'] in (native_ids if kind=='native' else managed_ids):
            continue
        value = json.loads(old['snapshot_json'])
        value.update(id=old['instance_id'], connected=False, available=False,
                     status='removed' if kind=='native' else 'ended')
        value['workspaces'] = [{'workspaceId':w['id'],'title':w['name'],'sessionIds':w['session_ids']}
                               for w in value['workspaces']]
        record_safely(value, 'registration_removed' if kind=='native' else 'binding_ended')


def tasks_for(con, instance_id):
    # Association comes from the frozen task source, never a workspace's new generation.
    rows = con.execute('''SELECT t.id,t.name,t.status,t.ended_at,t.created_at,
        json_extract(b.context_json,'$.workspace_source.instance.generation') AS generation,
        'workspace_source' AS association_source
        FROM tasks t JOIN bootstrap_contexts b ON b.task_id=t.id
        WHERE json_extract(b.context_json,'$.workspace_source.agent_id')=?
        ORDER BY t.created_at DESC,t.id''', (instance_id,)).fetchall()
    result = [dict(r) for r in rows]
    if instance_id.startswith('managed:'):
        task = con.execute('SELECT id,name,status,ended_at,created_at FROM tasks WHERE id=?',
                           (instance_id.removeprefix('managed:'),)).fetchone()
        if task and task['id'] not in {t['id'] for t in result}:
            result.insert(0, {**dict(task), 'generation': None, 'association_source': 'managed_task_binding'})
    return result


def public_event(row):
    value = dict(row)
    value['observation'] = json.loads(value.pop('snapshot_json'))
    return {**value, 'history_only': True, 'live': False}


def history(page=0, limit=12):
    with db.connect() as con:
        total = con.execute('SELECT COUNT(DISTINCT instance_id) FROM workspace_connection_events').fetchone()[0]
        rows = con.execute('''SELECT e.*,s.first_recorded_at,s.event_count FROM workspace_connection_events e
            JOIN (SELECT instance_id,MAX(id) AS latest,MIN(occurred_at) AS first_recorded_at,
                         COUNT(*) AS event_count FROM workspace_connection_events GROUP BY instance_id) s
              ON e.id=s.latest ORDER BY e.id DESC LIMIT ? OFFSET ?''', (limit,page*limit)).fetchall()
        items = []
        for row in rows:
            item = public_event(row)
            item['task_count'] = len(tasks_for(con, row['instance_id']))
            items.append(item)
        started = con.execute('SELECT MIN(occurred_at) FROM workspace_connection_events').fetchone()[0]
    return {'records': items, 'total': total, 'page': page, 'limit': limit,
            'recording_started_at': started, 'history_only': True, 'live': False}


def detail(instance_id, before=None, limit=30):
    with db.connect() as con:
        total = con.execute('SELECT COUNT(*) FROM workspace_connection_events WHERE instance_id=?',
                            (instance_id,)).fetchone()[0]
        if not total:
            raise HTTPException(404, '此实例还没有连接历史')
        if before is not None and not con.execute('SELECT 1 FROM workspace_connection_events WHERE instance_id=? AND id=?',
                                                 (instance_id,before)).fetchone():
            raise HTTPException(422, '连接历史游标不属于此实例')
        rows = con.execute('''SELECT * FROM workspace_connection_events WHERE instance_id=?
            AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT ?''', (instance_id,before,before,limit+1)).fetchall()
        events = [public_event(row) for row in rows[:limit]]
        tasks = tasks_for(con, instance_id)
    return {'instance_id': instance_id, 'events': events, 'tasks': tasks, 'total': total,
            'next_before': events[-1]['id'] if len(rows)>limit else None, 'history_only': True, 'live': False}
