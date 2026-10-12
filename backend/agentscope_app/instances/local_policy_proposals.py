"""Frozen local candidates in the shared approval center; no native local loader.

Submitting/rejecting only writes proposal metadata. A native local approval can
never call the instance-wide loader, even when called directly by an admin.
"""
import json
import uuid
from fastapi import HTTPException
from .. import db
from . import policy_targets
from .policy import digest
from .system_policy import lifecycle

SCHEMA = '''CREATE TABLE IF NOT EXISTS local_policy_proposals(
 id TEXT PRIMARY KEY, instance_id TEXT NOT NULL, request_key TEXT NOT NULL,
 request_hash TEXT NOT NULL, artifact_id TEXT NOT NULL, candidate_json TEXT NOT NULL,
 baseline_json TEXT NOT NULL, proposal_hash TEXT NOT NULL, state TEXT NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(instance_id,request_key));'''


def init(con):
    con.executescript(SCHEMA)


def load(key):
    with db.connect() as con:
        row = con.execute('SELECT * FROM local_policy_proposals WHERE id=?', (key,)).fetchone()
    if not row: raise HTTPException(404, '审批记录不存在')
    return dict(row)


@lifecycle
def submit(ident, artifact_id, body):
    from ..history.agent_context import selected_candidate
    from . import dsl_policy, system_policy
    request_hash = digest({'artifact_id': artifact_id, 'candidate_hash': body['candidate_hash']})
    with db.connect() as con:
        old = con.execute('SELECT * FROM local_policy_proposals WHERE instance_id=? AND request_key=?',
                          (ident, body['request_key'])).fetchone()
    if old:
        if old['request_hash'] != request_hash: raise ValueError('幂等键已用于其他目标或候选')
        return {'id': 'local:' + old['id'], 'proposal_hash': old['proposal_hash'], 'state': old['state']}
    candidate = selected_candidate(ident, artifact_id)
    if candidate['scopeType'] not in ('workspace', 'session') or candidate['candidate_hash'] != body['candidate_hash']:
        raise ValueError('候选或目标已变化，请重新查看后提交')
    baseline = {'dsl': {s: {k: dsl_policy.current(s)[k] for k in ('revision', 'document_hash')}
                        for s in ('system', ident)}, 'system_revision': system_policy.current()['revision']}
    proposal_hash = digest({'candidate': candidate, 'baseline': baseline})
    key = uuid.uuid4().hex
    with db.connect() as con:
        con.execute('INSERT INTO local_policy_proposals VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (key, ident, body['request_key'], request_hash, artifact_id, json.dumps(candidate),
                     json.dumps(baseline), proposal_hash, 'blocked', db.now()))
        db.audit(con, None, 'local_policy_submitted', 'authenticated_operator',
                 {'approval_id': 'local:' + key, 'target': candidate['target'], 'candidate_hash': proposal_hash})
    return {'id': 'local:' + key, 'proposal_hash': proposal_hash, 'state': 'blocked'}


def project(p, names, full=False, locations=None):
    candidate = json.loads(p['candidate_json'])
    target = candidate['target']
    capability = policy_targets.capability(target)  # Server capability, never a frozen/client claim.
    reason = capability['reason']
    status = p['state']
    # A blocked archive has no executable approval transition. Rendering it
    # must not re-run native session probes or repository scans per row.
    # submit() validates the full generation context; decide() independently
    # refuses application. Any future loader must add its own fresh checks.
    # Identity/provenance comes from the immutable stored statement, not the
    # currently selected UI session or the instance-wide PID.
    session = {'instance_id': p['instance_id'], 'session_id': candidate['sessionId'],
               'name': candidate['session_name'], 'available': False}
    row = {'schema': 'PolicyApproval/1', 'id': 'local:' + p['id'], 'kind': 'local_dsl',
           'origin': candidate['origin'], 'scope_id': p['instance_id'], 'scope_type': target['scope'],
           'target': target, 'target_name': names[p['instance_id']], 'scope_label': candidate['scope_label'],
           'name': candidate['document']['name'], 'status': status, 'reason': reason,
           'created_at': p['created_at'], 'can_apply': False, 'can_reject': p['state'] != 'rejected',
           'affected_count': 1, 'total_affected_count': 1, 'document_count': 1,
           'candidate_hash': p['proposal_hash'], 'proposal_hash': p['proposal_hash'],
           'baseline': json.loads(p['baseline_json']), 'application_capability': capability,
           'validation_label': '执行绑定尚不支持局部应用', 'origin_sessions': [session],
           'agents': [{'id': p['instance_id'], 'name': names[p['instance_id']], 'pid': None,
                       'process_state': 'unverified'}]}
    from .approval_locations import Locations
    location = (locations or Locations()).project(
        {'scope_id':p['instance_id'],'documents':[candidate['document']]}, [{'id':p['instance_id']}])
    row['agents'] = location['agents']
    if location['origin_sessions']: row['origin_sessions'] = location['origin_sessions']
    if full:
        statement = next(iter(candidate['document']['metadata'].values()), {}).get('statement') or candidate['document']['name']
        row.update(documents=[candidate['document']], records=[],
                   change_items=[{'label':'新增局部约束','before':'未添加此局部候选','after':statement}],
                   targets=[{'id': digest(target), 'name': names[p['instance_id']],
                             'scope_label': candidate['scope_label'], 'application_label': '未应用，权限保持不变'}],
                   explanation='本次仅保存局部候选；不修改已加载策略或执行权限。')
    return row


@lifecycle
def decide(key, decision, expected_hash):
    p = load(key)
    if p['proposal_hash'] != expected_hash: raise ValueError('候选确认内容不一致')
    if decision != 'reject':
        raise ValueError(policy_targets.capability(json.loads(p['candidate_json'])['target'])['reason'])
    with db.connect() as con:
        con.execute("UPDATE local_policy_proposals SET state='rejected' WHERE id=?", (key,))
    return {'id': 'local:' + key, 'state': 'rejected', 'idempotent': p['state'] == 'rejected'}
