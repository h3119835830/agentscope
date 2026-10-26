"""Durable approval receipts over existing authoritative proposal/load contracts.

Approval never calls a loader. Only apply consumes an exact receipt, under the
same lifecycle lock used by the existing controllers. Legacy confirm is an
explicit approve-and-apply adapter, not a new source of execution authority.
"""
import json
import sqlite3
import uuid
from .. import db
from .policy import digest
from .system_policy import lifecycle
from .configuration_approvals import read_snapshot

SCHEMA = '''
CREATE TABLE IF NOT EXISTS policy_approval_decisions(
 id TEXT PRIMARY KEY, approval_id TEXT NOT NULL, request_key TEXT NOT NULL,
 request_hash TEXT NOT NULL, approval_hash TEXT NOT NULL, basis_json TEXT NOT NULL,
 owner_key TEXT NOT NULL, state TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(approval_id,request_key));
CREATE UNIQUE INDEX IF NOT EXISTS policy_one_approved_version
 ON policy_approval_decisions(owner_key) WHERE state IN ('approved','applying');
CREATE TABLE IF NOT EXISTS policy_application_requests(
 approval_id TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL,
 state TEXT NOT NULL, result_json TEXT, created_at TEXT NOT NULL,
 PRIMARY KEY(approval_id,request_key));
'''


def init(con):
    con.executescript(SCHEMA)
    if 'evidence_json' not in [r[1] for r in con.execute('PRAGMA table_info(policy_approval_decisions)')]:
        con.execute("ALTER TABLE policy_approval_decisions ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '{}'")


def basis(row):
    return {k: row.get(k) for k in ('id', 'kind', 'scope_id', 'target', 'candidate_hash', 'baseline')}


def receipts():
    with db.connect() as con:
        rows = con.execute('SELECT * FROM policy_approval_decisions ORDER BY rowid').fetchall()
    return {r['approval_id']: dict(r) for r in rows}


def project(row, saved=None):
    row = dict(row)
    receipt = (receipts() if saved is None else saved).get(row['id'])
    executable = bool(row.get('can_apply'))
    row.update(can_approve=bool(executable and row['status'] in ('pending', 'failed')),
               can_apply=False, approval_status='unrecorded', application_status=row['status'])
    if row['status'] == 'applied':
        row['approval_status'] = 'approved' if receipt else 'legacy_unrecorded'
        row['application_status'] = 'applied'
    elif receipt:
        row['approval_status'] = receipt['state']
        row['approval_hash'] = receipt['approval_hash']
        row['approved_at'] = receipt['created_at']
        valid = executable and json.loads(receipt['basis_json']) == basis(row)
        if receipt['state'] == 'approved' and valid:
            row.update(status='approved', can_approve=False, can_apply=True,
                       application_status='waiting', can_reject=True)
        elif receipt['state'] == 'approved':
            row.update(status='stale', can_approve=False,
                       reason=row.get('reason') or '批准后的候选或基线已变化，请重新校验。')
        elif receipt['state'] == 'applying':
            row.update(status='applying', can_approve=False, can_reject=False)
        elif receipt['state'] in ('failed','pause_unverified'):
            row.update(status='failed', can_approve=False,
                       reason='应用未完成；请重新校验并提交新的变更，执行保持暂停。' if receipt['state']=='failed' else '应用未完成，尚未核验执行暂停；请恢复可信控制连接。')
    application = row.get('application') or {}
    row['execution_results'] = application.get('targets', [])
    if 'documents' in row:
        evidence=json.loads(receipt.get('evidence_json','{}')) if receipt else {}
        if 'previous_documents' in evidence:
            row['previous_documents']=evidence['previous_documents']
        with db.connect() as con:
            version=con.execute('SELECT input_json,revision,draft_id FROM policy_draft_versions WHERE approval_id=? ORDER BY rowid DESC LIMIT 1',(row['id'],)).fetchone()
        if version:
            inputs=json.loads(version['input_json'])
            row['reference_materials']=inputs.get('materials',[])
            row['draft_version']=version['revision']
            row['requirement']=inputs.get('text')
    from .product_status import configuration
    row['configuration_status'] = configuration(row)
    return row


def project_many(rows):
    saved = receipts()
    return [project(r, saved) for r in rows]


def result(receipt, idempotent=False):
    return {'id': receipt['approval_id'], 'state': receipt['state'],
            'approval_hash': receipt['approval_hash'], 'approved_at': receipt['created_at'],
            'idempotent': idempotent}


@lifecycle
@read_snapshot
def approve(ident, expected_hash, request_key):
    from .approval_views import raw_detail
    request_hash = digest({'candidate_hash': expected_hash})
    with db.connect() as con:
        old = con.execute('SELECT * FROM policy_approval_decisions WHERE approval_id=? AND request_key=?',
                          (ident, request_key)).fetchone()
    if old:
        if old['request_hash'] != request_hash:
            raise ValueError('幂等键已用于另一候选')
        return result(dict(old), True)
    row = raw_detail(ident)
    if row['candidate_hash'] != expected_hash:
        raise ValueError('候选确认内容不一致')
    if not row.get('can_apply') or row['status'] not in ('pending', 'failed'):
        raise ValueError(row.get('reason') or '候选尚不可批准，请重新校验')
    snapshot = basis(row)
    approval_hash = digest(snapshot)
    existing = receipts().get(ident)
    if existing and existing['state'] == 'approved' and existing['approval_hash'] == approval_hash:
        return result(existing, True)
    unit=(row.get('approval_unit') or {}).get('configuration_id')
    scope_owner={'scope':row['scope_type'],'owner':row['scope_id']}
    whole_owner=digest(scope_owner)
    owner = digest({**scope_owner,**({'configuration_id':unit} if unit else {})})
    record = dict(id=uuid.uuid4().hex, approval_id=ident, request_key=request_key,
                  request_hash=request_hash, approval_hash=approval_hash,
                  basis_json=json.dumps(snapshot), owner_key=owner, state='approved',
                  actor='authenticated_operator', created_at=db.now(),
                  evidence_json=json.dumps({k:row[k] for k in ('previous_documents','change_items','targets') if k in row}))
    try:
        with db.connect() as con:
            # Stale approval slots may be released, but their immutable evidence remains.
            for old in con.execute("SELECT * FROM policy_approval_decisions WHERE state='approved'").fetchall():
                old_basis=json.loads(old['basis_json'])
                if old_basis.get('scope_id')!=row['scope_id'] or old_basis.get('target',{}).get('scope')!=row['target']['scope']:continue
                # A different configuration owns a different approval slot.
                # Only overlapping slots can prevent this decision; checking
                # unrelated sources here made N independent approvals O(N²).
                if unit and old['owner_key'] not in (owner,whole_owner):continue
                try:
                    previous = raw_detail(old['approval_id'])
                except Exception as error:
                    from fastapi import HTTPException
                    if not isinstance(error, HTTPException) or error.status_code != 404:
                        raise
                    previous = {}
                if not previous.get('can_apply') or basis(previous) != json.loads(old['basis_json']):
                    con.execute("UPDATE policy_approval_decisions SET state='stale' WHERE id=?", (old['id'],))
                else:
                    prior_unit=(previous.get('approval_unit') or {}).get('configuration_id')
                    if not unit or not prior_unit or unit==prior_unit:
                        raise ValueError('此策略或整个配置范围已有待应用变更，请先应用或撤回')
            con.execute('INSERT INTO policy_approval_decisions('+','.join(record)+') VALUES('+','.join('?' for _ in record)+')', tuple(record.values()))
            db.audit(con, None, 'policy_approved', record['actor'],
                     {'approval_id': ident, 'approval_hash': approval_hash, 'target': row['target']})
    except sqlite3.IntegrityError:
        raise ValueError('此配置范围已有待应用变更，请先应用或撤回') from None
    return result(record)


@lifecycle
def apply(ident, expected_hash, approval_hash, request_key):
    from .approval_views import raw_detail, execute_decision
    request_hash = digest({'candidate_hash': expected_hash, 'approval_hash': approval_hash})
    with db.connect() as con:
        old = con.execute('SELECT * FROM policy_application_requests WHERE approval_id=? AND request_key=?',
                          (ident, request_key)).fetchone()
    if old:
        if old['request_hash'] != request_hash:
            raise ValueError('幂等键已用于另一应用请求')
        if old['state'] == 'applied':
            return {**json.loads(old['result_json']), 'idempotent': True}
        raise ValueError('此应用请求尚未完成或曾失败，请查看回执并重新校验')
    row = raw_detail(ident)
    receipt = receipts().get(ident)
    if not receipt or receipt['approval_hash'] != approval_hash or row['candidate_hash'] != expected_hash:
        raise ValueError('必须先批准当前候选，应用需匹配批准回执')
    if receipt['state'] == 'applied' and row['status'] == 'applied':
        return {'id': ident, 'state': 'applied', 'idempotent': True}
    if receipt['state'] != 'approved' or not row.get('can_apply') or basis(row) != json.loads(receipt['basis_json']):
        raise ValueError('候选、目标或继承基线已变化，请重新校验后审批')
    with db.connect() as con:
        changed = con.execute("UPDATE policy_approval_decisions SET state='applying' WHERE id=? AND state='approved'", (receipt['id'],)).rowcount
        if changed != 1:
            raise ValueError('审批已被其他操作处理')
        con.execute('INSERT INTO policy_application_requests VALUES(?,?,?,?,?,?)',
                    (ident, request_key, request_hash, 'applying', None, db.now()))
    try:
        applied = execute_decision(ident, 'confirm', expected_hash)
    except Exception:
        pause_state='failed'
        try:
            fail_closed(row)
        except Exception:
            pause_state='pause_unverified'
        with db.connect() as con:
            con.execute('UPDATE policy_approval_decisions SET state=? WHERE id=?', (pause_state,receipt['id']))
            con.execute("UPDATE policy_application_requests SET state='failed' WHERE approval_id=? AND request_key=?", (ident, request_key))
        if pause_state=='pause_unverified':
            raise RuntimeError('应用失败且执行暂停尚未核验，请恢复可信控制连接') from None
        raise
    with db.connect() as con:
        con.execute("UPDATE policy_approval_decisions SET state='applied' WHERE id=?", (receipt['id'],))
        con.execute("UPDATE policy_application_requests SET state='applied',result_json=? WHERE approval_id=? AND request_key=?", (json.dumps(applied), ident, request_key))
    return applied


@lifecycle
def reject(ident, expected_hash):
    from .approval_views import execute_decision
    receipt = receipts().get(ident)
    if receipt and receipt['state'] in ('applying', 'applied'):
        raise ValueError('正在应用或已应用的变更不能撤回，请起草新的变更')
    value = execute_decision(ident, 'reject', expected_hash)
    if receipt:
        with db.connect() as con:
            con.execute("UPDATE policy_approval_decisions SET state='withdrawn' WHERE id=?", (receipt['id'],))
    return value


def confirm(ident, expected_hash):
    from .approval_views import raw_detail
    row=raw_detail(ident)
    if row['candidate_hash']!=expected_hash:
        raise ValueError('候选确认内容不一致')
    if row['status'] == 'applied':
        return {'id': ident, 'state': 'applied', 'idempotent': True}
    receipt = approve(ident, expected_hash, 'legacy-confirm-' + digest({'id': ident, 'hash': expected_hash}))
    # Compatibility confirmation records consent only. Loading always requires
    # the separate application endpoint with this exact approval receipt.
    return {**receipt, 'application_required': True}


def confirm_scoped(scope,ident,expected_hash):
    from .approval_views import raw_detail
    if raw_detail(ident)['scope_id']!=scope:
        raise ValueError('候选范围不一致')
    return confirm(ident,expected_hash)


def reject_scoped(scope,ident,expected_hash):
    from .approval_views import raw_detail
    if raw_detail(ident)['scope_id']!=scope:
        raise ValueError('候选范围不一致')
    return reject(ident,expected_hash)


def fail_closed(row):
    """Reuse the existing controllers to pause/stop; never reload old authority."""
    if row['kind']=='runtime':
        from ..managed.worker import worker
        worker.fail(row['scope_id'],'Policy application interrupted; explicit recovery required')
        return
    from . import controller,store
    errors=[]
    for target in row.get('targets',[]):
        current=store.get(target['id'])
        if current['gate']=='closed':continue
        store.update(current['id'],gate='paused')
        try:controller.close_runtime_gates([current])
        except Exception:pass # The authoritative stop below also closes the execution domain.
        try:controller.adapter(current).stop(current)
        except Exception as error:errors.append(error)
    if errors:raise RuntimeError('Execution pause not verified') from errors[0]


@lifecycle
def reconcile_interrupted():
    """Startup repairs only the pause, never retries an application."""
    from .approval_views import raw_detail
    values=[r for r in receipts().values() if r['state'] in ('applying','pause_unverified')]
    for receipt in values:
        row=raw_detail(receipt['approval_id'])
        frozen=json.loads(receipt.get('evidence_json','{}'))
        if 'targets' in frozen:row['targets']=frozen['targets']
        fail_closed(row)
        with db.connect() as con:
            con.execute("UPDATE policy_approval_decisions SET state='failed' WHERE id=?",(receipt['id'],))
            con.execute("UPDATE policy_application_requests SET state='failed' WHERE approval_id=? AND state='applying'",(receipt['approval_id'],))
    return len(values)
