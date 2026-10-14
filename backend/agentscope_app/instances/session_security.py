"""Session-centred projection of existing authority; no independent permission store."""
from copy import deepcopy
import json
from .. import db
from . import dsl_policy as dsl, system_policy as system
from .policy import digest, records as typed_records

ACTION_NAMES = {'read': '文件读取', 'write': '文件写入与删除', 'tool': '工具使用',
                'network': '网络连接', 'behavior': '行为指导'}
METHODS = {'read': '隔离挂载与 ActPlane', 'write': '隔离挂载与 ActPlane',
           'tool': '原生工具准入', 'network': 'cgroup 网络过滤', 'behavior': '行为指导 · 非强制'}
LOCAL_REASON = '当前原生会话共用 Agent 执行器，暂不支持仅此会话的配置、应用或停用。'


def init(con):
    con.execute('''CREATE TABLE IF NOT EXISTS session_security_requests(
        instance_id TEXT NOT NULL,request_key TEXT NOT NULL,session_id TEXT NOT NULL,
        request_hash TEXT NOT NULL,approval_id TEXT NOT NULL,result_json TEXT NOT NULL,
        created_at TEXT NOT NULL,PRIMARY KEY(instance_id,request_key))''')


def pending_changes(ident, sid):
    from .approval_views import detail
    from fastapi import HTTPException
    with db.connect() as con:
        rows = con.execute('SELECT approval_id FROM session_security_requests WHERE instance_id=? AND session_id=? ORDER BY created_at DESC LIMIT 30', (ident, sid)).fetchall()
    result = []
    for saved in rows:
        try:
            row = detail(saved['approval_id'])
        except HTTPException as error:
            if error.status_code != 404:
                raise
            continue
        if row['status'] not in ('applied', 'rejected', 'withdrawn', 'superseded'):
            result.append({k: row.get(k) for k in ('id', 'name', 'scope_type', 'status', 'reason')})
    return result


def build(row, session, generation, active, policy_records, receipt):
    shared = system.current()
    owned = dsl.current(row['id'])
    common = dsl.current('system')
    controlled = row.get('mode') == 'controlled'
    current = generation == row.get('generation') and not session.get('historical')
    editable = controlled and current
    basis = {'instance_id': row['id'], 'session_id': session['id'], 'generation': generation,
             'resources': row.get('resources', []), 'policy_hash': row.get('policy_hash'),
             'local_policy': row.get('local_policy'), 'system_revision': shared['revision'],
             'system_hash': shared['policy_hash'], 'agent_dsl_hash': owned['document_hash'],
             'agent_dsl_revision': owned['revision'], 'system_dsl_hash': common['document_hash'],
             'system_dsl_revision': common['revision']}
    controls = []
    state = '绑定已核验' if active else '配置已记录 · 当前执行未核验'

    def add(kind, scope, key, title, target, method, **extra):
        controls.append({'id': digest([kind, scope, key]), 'kind': kind, 'scope': scope,
                         'title': title, 'target': target, 'method': method, 'status': state,
                         'can_configure': False, 'can_disable': False,
                         'reason': '由所属配置维护，不能在会话中移除继承约束。', **extra})

    if controlled:
        add('platform', 'platform', 'control', '保护控制目录与执行凭据', '控制平面和执行后代',
            '隔离挂载、非特权身份与 ActPlane', effect='deny',
            reason='平台底线不可在用户策略中停用。')
        add('baseline', 'agent', 'mounts', '登记资源默认只读，写入需显式授权',
            '；'.join(row.get('resources', [])), '隔离挂载与 ActPlane', effect='deny',
            reason='默认边界不可直接停用；可以通过所属 Agent 配置申请明确写入授权。')
        network = row['policy']['network']
        network_owner = 'system' if shared['policy']['network'] == 'disabled' else 'agent'
        add('network_mode', network_owner, 'network',
            '仅连接本机控制端、DNS 与模型地址' if network == 'model_only' else '保留本机控制端，禁止模型及外部连接',
            '实例网络范围', '实例 cgroup 网络过滤', effect='allow' if network == 'model_only' else 'deny',
            mode=network, can_configure=editable,
            reason='网络基础边界不能整体停用；修改会提交所属层的新候选。')
        for scope, rules in (('system', system.applicable(shared['policy']['rules'], row['resources'])),
                             ('agent', row['local_policy']['rules'])):
            for rule in rules:
                display = typed_records({'rules': [rule], 'network': network}, row['resources'], active)[-1]
                overridden = scope == 'agent' and rule.get('effect') == 'allow' and any(
                    r['effect'] == 'deny' and r['action'] == rule['action'] and
                    (r['target'] == rule['target'] or r['action'] in ('read', 'write') and
                     rule['target'].startswith(r['target'] + '/'))
                    for r in system.applicable(shared['policy']['rules'], row['resources']))
                add('typed', scope, rule, ACTION_NAMES[rule['action']], rule.get('target') or rule['text'],
                    METHODS[rule['action']], rule=rule, effect=rule['effect'], description=display['sentence'],
                    status='行为指导 · 不作强制执行声明' if rule['action'] == 'behavior' else
                           '受系统禁止约束' if overridden else
                           '工具准入检查已配置' if active and rule['action'] == 'tool' else state,
                    can_configure=editable, can_disable=editable, reason='')

    documents = {('system' if scope == 'system' else 'agent', doc['id']): doc
                 for scope, value in (('system', common), (row['id'], owned)) for doc in value['documents']}
    for record in policy_records:
        scope = record.get('scope_type', 'agent')
        scope = scope if scope in ('system', 'agent', 'workspace', 'session') else 'agent'
        doc_id = record.get('document_id')
        match = documents.get((scope, doc_id))
        refs = record.get('compiled_refs', [])
        legacy = record.get('source_kind') == 'legacy_generated'
        if legacy and refs and all(ref.get('immutable') for ref in refs):
            scope = 'platform'
        verbs = {'read': '读取', 'write': '写入', 'unlink': '删除', 'exec': '执行', 'connect': '网络连接'}
        operations = list(dict.fromkeys(verbs.get(ref.get('clause_op'), ref.get('clause_op', '操作')) for ref in refs))
        targets = list(dict.fromkeys((ref.get('target_pattern', '') + (' ' + ref['target_arg'] if ref.get('target_arg') else '')).strip() for ref in refs))
        matches_current = bool(match and match.get('original_dsl') == record.get('original_document'))
        mutable = bool(editable and matches_current and scope in ('system', 'agent'))
        add('dsl' if doc_id else 'execution_record', scope, record['id'],
            '启动执行约束 · ' + '、'.join(operations) if legacy else
            record.get('statement') or record.get('document_name') or record.get('rule_name') or '已记录约束',
            '；'.join(targets) or '见规则详情', 'ActPlane 内核规则' if refs else '受管任务记录',
            record_id=record['id'], document_id=doc_id, effects=record.get('effects', []),
            status='加载回执与当前绑定已核验' if active and record.get('loaded') else
                   '历史加载记录 · 当前未核验' if record.get('loaded') else '执行状态未核验',
            can_disable=mutable, can_configure=False,
            reason='复杂 DSL 需前往所属配置编辑；停用将移除整个文档。' if mutable else
                   '未取得可编辑的当前文档，或此记录属于受管任务；只读查看。')

    recorded_docs = {(r.get('scope_type'), r.get('document_id')) for r in policy_records
                     if r.get('document_id') and documents.get((r.get('scope_type'), r.get('document_id')), {}).get('original_dsl') == r.get('original_document')}
    missing = set(documents) - recorded_docs
    for (scope, doc_id) in sorted(missing):
        doc = documents[(scope, doc_id)]
        add('dsl_unverified', scope, doc_id, doc.get('name') or 'DSL 配置文档', '未取得规则映射',
            'ActPlane DSL', document_id=doc_id, status='配置存在 · 加载详情不完整',
            reason='缺少此文档的加载规则映射；前往所属配置核对后重新校验。')

    checks = [
        {'name': '运行绑定', 'ok': active, 'message': '当前 Agent 继承绑定已核验' if active else '当前执行保护未核验'},
        {'name': '结构化安全配置', 'ok': controlled, 'message': '已汇总平台、资源、网络、工具及行为约定' if controlled else '仅观测连接，未接管执行'},
        {'name': 'DSL 加载详情', 'ok': not missing, 'message': '已汇总当前可用规则映射' if not missing else '部分配置文档缺少加载映射，不能将其计为当前保护'},
        {'name': '会话独立应用', 'ok': False, 'message': LOCAL_REASON},
        {'name': '其他系统或业务约束', 'ok': False, 'message': '未接入的外部约束无法由本页面核验，不计入已保护范围。'}]
    return {'schema': 'SessionSecurity/1', 'instance_id': row['id'], 'session_id': session['id'],
            'generation': generation, 'basis_hash': digest(basis), 'checked_at': db.now(),
            'controls': controls, 'checks': checks, 'coverage_complete': controlled and not missing,
            'pending_changes': pending_changes(row['id'], session['id']),
            'can_propose': editable, 'session_local_supported': False, 'session_local_reason': LOCAL_REASON,
            'scope_labels': {'platform': '平台底线', 'system': '系统继承', 'agent': 'Agent 继承',
                             'workspace': '工作区继承', 'session': '本会话'},
            'network_modes': ['model_only', 'disabled']}


@system.lifecycle
def propose(ident, sid, body):
    """Revalidate the exact native target and change only the selected owner's config."""
    from . import sessions, controller as c
    request_hash = digest({'instance_id': ident, 'session_id': sid, 'body': body})
    with db.connect() as con:
        prior = con.execute('SELECT * FROM session_security_requests WHERE instance_id=? AND request_key=?', (ident, body['request_key'])).fetchone()
    if prior:
        if prior['request_hash'] != request_hash:
            raise ValueError('幂等键已用于其他会话或变更内容')
        return {**json.loads(prior['result_json']), 'idempotent': True}

    def record(value):
        with db.connect() as con:
            con.execute('INSERT INTO session_security_requests VALUES(?,?,?,?,?,?,?)',
                        (ident, body['request_key'], sid, request_hash, value['approval_id'], json.dumps(value), db.now()))
        return value
    data = sessions.policies(ident, sid)
    view = data['security']
    if body['scope'] in ('workspace', 'session'):
        raise ValueError(LOCAL_REASON)
    if not body['acknowledge_scope']:
        raise ValueError('请明确核对所属层及其全部影响范围')
    if not view['can_propose'] or body['basis_hash'] != view['basis_hash']:
        raise ValueError('会话、运行代次或策略配置已经变化，请刷新后重新配置')
    row = c.detail(ident)
    # A fresh context read may race with restart; never borrow another generation.
    if row.get('generation') != view['generation']:
        raise ValueError('运行代次已经变化，请刷新后重新配置')
    if build(row, data['session'], view['generation'], data['active'], data['records'], None)['basis_hash'] != view['basis_hash']:
        raise ValueError('配置已在读取期间变化，请刷新后重新配置')
    scope, operation = body['scope'], body['operation']
    if operation == 'add' and body.get('constraint_id'):
        raise ValueError('新增约束不能复用既有约束身份')
    selected = next((r for r in view['controls'] if r['id'] == body.get('constraint_id')), None)
    if operation != 'add' and (not selected or selected['scope'] != scope):
        raise ValueError('约束不属于本次会话视图或指定配置层')
    if operation == 'disable' and not selected['can_disable']:
        raise ValueError(selected['reason'])
    if operation == 'replace' and not selected['can_configure']:
        raise ValueError(selected['reason'])
    if selected and selected['kind'] == 'dsl':
        if operation != 'disable':
            raise ValueError('复杂 DSL 请在所属配置中编辑')
        owner = 'system' if scope == 'system' else ident
        base = dsl.current(owner)
        docs = [d for d in base['documents'] if d['id'] != selected['document_id']]
        if len(docs) == len(base['documents']):
            raise ValueError('DSL 文档已变化，请刷新后重试')
        p = dsl.propose(owner, {'documents': docs, 'base_hash': base['document_hash'],
                               'base_revision': base['revision'], 'request_key': body['request_key']})
        return record({'approval_id': p['id'], 'proposal': p, 'scope': scope})
    shared = system.current()
    policy = deepcopy(shared['policy'] if scope == 'system' else row['local_policy'])
    if selected and selected['kind'] == 'network_mode':
        if operation != 'replace' or body.get('network') not in ('model_only', 'disabled'):
            raise ValueError('请选择已支持的网络范围')
        policy['network'] = body['network']
    else:
        if selected:
            if selected['kind'] != 'typed' or selected['rule'] not in policy['rules']:
                raise ValueError('此约束不能通过结构化表单修改')
            policy['rules'].remove(selected['rule'])
        if operation in ('add', 'replace'):
            if not body.get('rule'):
                raise ValueError('请填写结构化安全约束')
            policy['rules'].append(body['rule'])
    try:
        if scope == 'system':
            p = system.propose({'policy': policy, 'base_hash': shared['policy_hash'],
                                'revision': shared['revision'], 'request_key': body['request_key']})
            approval_id = 'system:' + p['id']
        else:
            p = c.proposals(ident, {'policy': policy, 'base_hash': row['policy_hash'],
                                    'generation': row['generation'], 'request_key': body['request_key']}, 'user')
            approval_id = 'instance:' + p['id']
    except FileNotFoundError as error:
        raise ValueError('约束路径或运行资源不存在，请刷新并检查已登记资源中的实际路径') from error
    return record({'approval_id': approval_id, 'proposal': p, 'scope': scope})
