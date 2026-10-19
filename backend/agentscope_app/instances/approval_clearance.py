"""Reversible approval-list cleanup, independent of authorization and execution."""
import json
from .. import db
from .policy import digest
from .system_policy import lifecycle

CLEARABLE = frozenset(('applied', 'rejected', 'stale', 'invalid', 'failed', 'blocked'))


def marker(con, ident):
    saved = con.execute("SELECT reason,retained_at FROM console_retained_records WHERE kind='approval' AND record_id=?", (ident,)).fetchone()
    if not saved:
        return {'revision': 0, 'cleared': False}
    return {**json.loads(saved['reason']), 'updated_at': saved['retained_at']}


def content_hash(row):
    return digest({k: row.get(k) for k in ('id', 'kind', 'scope_id', 'scope_type', 'target',
                                         'candidate_hash', 'baseline', 'status', 'approval_hash')})


def project(row, saved=None):
    if saved is None:
        with db.connect() as con:
            saved = marker(con, row['id'])
    can_clear = row['status'] in CLEARABLE
    cleared = bool(can_clear and saved['cleared'] and saved.get('content_hash') == content_hash(row))
    return {**row, 'can_clear': can_clear, 'cleared': cleared, 'can_restore': cleared,
            'cleared_at': saved.get('updated_at') if cleared else None,
            'clearance_hash': digest({'content': content_hash(row), 'visibility_revision': saved['revision']})}


def directory(cleared=False):
    from .approval_views import directory as approvals
    data = approvals()
    with db.connect() as con:
        projected = [project(row, marker(con, row['id'])) for row in data['records']]
    records = [row for row in projected if row['cleared'] == cleared]
    return {**data, 'records': records, 'cleared_count': sum(row['cleared'] for row in projected),
            'pending_count': sum(row['status'] == 'pending' for row in records)}


def detail(ident):
    from .approval_views import detail as approval
    return project(approval(ident))


@lifecycle
def change(ident, action, expected_hash, request_key):
    from .approval_views import detail as approval
    if action not in ('clear', 'restore'):
        raise ValueError('未知清理操作')
    row = approval(ident)
    request_hash = digest({'action': action, 'expected_hash': expected_hash})
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        saved = marker(con, ident)
        if saved.get('request_key') == request_key:
            if saved['request_hash'] != request_hash:
                raise ValueError('幂等键已用于其他清理操作')
            return {**project(row, saved), 'idempotent': True}
        current = project(row, saved)
        if current['clearance_hash'] != expected_hash:
            raise ValueError('记录状态、范围或清理状态已变化，请重新读取预览')
        if action == 'clear' and (not current['can_clear'] or current['cleared']):
            raise ValueError('待审批或待应用记录请先拒绝或撤回；正在应用的记录不能清理')
        if action == 'restore' and not current['can_restore']:
            raise ValueError('此记录当前没有需要恢复的清理标记')
        value = {'revision': saved['revision'] + 1, 'cleared': action == 'clear',
                 'content_hash': content_hash(row), 'request_key': request_key, 'request_hash': request_hash}
        now = db.now()
        con.execute("INSERT INTO console_retained_records VALUES('approval',?,?,?) ON CONFLICT(kind,record_id) DO UPDATE SET reason=excluded.reason,retained_at=excluded.retained_at",
                    (ident, json.dumps(value), now))
        db.audit(con, None, 'approval_record_cleared' if action == 'clear' else 'approval_record_restored',
                 'authenticated_operator', {'approval_id': ident, 'scope_id': row['scope_id'],
                                            'status': row['status'], 'visibility_revision': value['revision']})
    # State drift can make a retained record actionable again. It stays visible;
    # a list-cleanup marker must never suppress an actionable approval.
    return {**detail(ident), 'idempotent': False}
