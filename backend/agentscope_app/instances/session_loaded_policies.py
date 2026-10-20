"""Read-only projection of the current kernel load, never desired configuration.

The observer verifies process/cgroup/domain/protection identity and expires after
eight seconds. A historical loading receipt alone is not current-load evidence.
The legacy security proposal API remains separate from this product read model.
"""
from . import dsl_policy

SCOPES = {'system': '系统策略', 'agent': 'Agent 策略'}
NOTICE = '同一 Agent 进程内的工作区和会话共享这些策略；这里不代表会话独立隔离。'


def build(row, session, generation, receipt):
    result = {
        'schema': 'SessionLoadedPolicies/1', 'state': 'unverified',
        'records': [], 'coverage_complete': False, 'scope_labels': SCOPES,
        'notice': NOTICE, 'generation': generation,
        'checked_at': row.get('last_checked_at'), 'bundle_hash': None,
        'message': '当前加载证据尚未核验，请刷新后重试；历史回执不计为当前已加载策略。',
    }
    if row.get('mode') != 'controlled':
        return {**result, 'state': 'observed', 'message': '此连接仅用于观测，不能确认其已加载的 ActPlane 策略。'}
    if session.get('historical') or generation != row.get('generation'):
        return {**result, 'state': 'historical', 'message': '这是历史会话或运行代次，不展示历史策略为当前已加载策略。'}
    if not receipt:
        return {**result, 'message': '尚无可核验的内核加载快照；默认保护说明和已保存配置不计入此列表。'}
    artifact = receipt.get('artifact', {})
    binding = artifact.get('binding', {})
    runtime = row.get('runtime', {})
    loaded = runtime.get('policy_artifact', {})
    execution = row.get('execution_status', {})
    # Do not use controller.active: it also compares the latest desired DSL.
    # A newly saved configuration is not evidence that the old kernel load changed.
    verified = (
        row.get('connected') is True and row.get('verified') is True
        and row.get('gate') in ('open', 'paused')
        and receipt.get('instance_id') == row.get('id')
        and receipt.get('generation') == generation == runtime.get('generation')
        and binding.get('generation') == generation
        and bool(row.get('domain_id')) and binding.get('domain_id') == row['domain_id'] == runtime.get('domain_id')
        and bool(row.get('pid')) and binding.get('pid') == row['pid'] == runtime.get('pid')
        and artifact.get('loaded') is True and loaded.get('loaded') is True
        and bool(receipt.get('bundle_hash'))
        and receipt['bundle_hash'] == artifact.get('bundle_hash') == loaded.get('bundle_hash')
        and receipt.get('dsl_hash') == artifact.get('dsl_hash') == row.get('dsl_hash') == runtime.get('dsl_hash')
        and row.get('evidence_age_seconds', 0) < 8
        and (row.get('supervision') != 'broker-admission-v1' or execution.get('protection_fresh') is True)
    )
    for key in ('start_ticks', 'boot_id', 'host_id'):
        if runtime.get(key) is not None and row.get(key) != runtime[key]:
            verified = False
        if binding.get(key) is not None and binding[key] != row.get(key):
            verified = False
    if not verified:
        return result

    compiled = artifact.get('compile', {})
    refs = compiled.get('rules', [])
    if compiled.get('ok') is not True or not isinstance(refs, list):
        return {**result, 'state': 'incomplete', 'message': '已取得加载快照，但缺少完整的编译映射，暂不展示策略清单。'}
    groups = []
    claimed = set()
    complete = True
    evidence = {'generation': generation, 'domain_id': row['domain_id'], 'pid': row['pid'],
                'bundle_hash': receipt['bundle_hash'], 'loaded_at': receipt.get('created_at'),
                'checked_at': result['checked_at']}
    for doc in artifact.get('documents', []):
        if doc.get('scope_id') not in ('system', row['id']):
            complete = False
            continue
        rules = dsl_policy.policy_records({**artifact, 'documents': [doc]}, active=True)
        if not rules or any(not r.get('compiled_refs') or any(not ref.get('clause_hash') for ref in r['compiled_refs']) for r in rules):
            complete = False
            continue
        for rule in rules:
            claimed.add(rule['compiled_name'])
        groups.append(_group(
            doc['scope_id'] + ':' + doc['id'], doc['name'],
            'system' if doc['scope_id'] == 'system' else 'agent',
            rules, evidence, document_id=doc['id'], original_dsl=doc['original_dsl'],
            label_sources=doc.get('label_sources', []), source_kind='configuration',
        ))
    # Compiled startup rules are real kernel clauses; mount/network/tool
    # descriptions are not. Never infer a clause from current policy settings.
    document_names = {r['compiled_name'] for d in artifact.get('documents', []) for r in d.get('rules', [])}
    namespaces = [d['namespace'] + '-' for d in artifact.get('documents', []) if d.get('namespace')]
    startup = {}
    for ref in refs:
        if ref.get('name') in document_names or any(str(ref.get('name', '')).startswith(ns) for ns in namespaces):
            if ref['name'] not in claimed:
                complete = False
            continue
        if not ref.get('name') or not ref.get('clause_hash') or not ref.get('source_text'):
            complete = False
            continue
        if not (ref['name'] == 'immutable-no-publish' or ref['name'].startswith(('instance-readonly-', 'instance-read-deny-'))):
            complete = False
            continue
        startup.setdefault(ref['name'], []).append(ref)
    for name, rules in startup.items():
        fixed = all(r.get('immutable') for r in rules)
        title = ('发布边界（系统内置）' if name == 'immutable-no-publish' else
                 '资源写入保护（启动规则）' if name.startswith('instance-readonly-') else
                 '资源读取保护（启动规则）' if name.startswith('instance-read-deny-') else name)
        groups.append(_group(
            'startup:' + name, title, 'system' if fixed else 'agent',
            [{'rule_name': name, 'compiled_refs': rules, 'statement': rules[0].get('reason', '')}],
            evidence, source_kind='startup', original_dsl=rules[0]['source_text'],
            description='系统内置规则。' if fixed else 'Agent 启动时的合成规则；历史加载回执未细分原始配置归属。',
        ))
    return {**result, 'state': 'verified' if complete else 'incomplete',
            'records': groups, 'coverage_complete': complete, 'bundle_hash': receipt['bundle_hash'],
            'message': '' if complete else '部分加载映射缺失，仅展示已有完整映射的策略，数量不代表全部策略。'}


def _group(ident, name, scope, rules, evidence, **extra):
    clauses = []
    for rule in rules:
        for ref in rule['compiled_refs']:
            clauses.append({
                'rule_name': rule['rule_name'], 'operation': ref.get('clause_op'),
                'target': ref.get('target_pattern'), 'argument': ref.get('target_arg'),
                'effect': ref.get('effect'), 'condition': ref.get('clause_text'),
                'reason': ref.get('reason'), 'source_ref': ref.get('source_ref'),
                'clause_hash': ref['clause_hash'], 'compiler_rule_id': ref.get('rule_id'),
            })
    return {'id': ident, 'name': name, 'scope': scope, 'status': 'loaded',
            'rule_count': len(rules), 'clauses': clauses, 'evidence': evidence, **extra}


def domains(view):
    complete = view['coverage_complete']
    return {
        'coverage_complete': complete, 'notice': NOTICE,
        'nodes': [{
            'id': scope, 'title': title,
            'count': sum(r['scope'] == scope for r in view['records']) if complete else None,
            'count_label': (str(sum(r['scope'] == scope for r in view['records'])) + ' 项已加载策略') if complete else '加载数量尚未完整核验',
            'status': '加载快照已核验' if complete else '当前加载证据不完整',
            'applies_to': '系统策略在此 Agent 中的实际加载结果' if scope == 'system' else '此 Agent 进程及其共享会话',
        } for scope, title in SCOPES.items()],
        # Both owners feed one execution domain, not an inheritance chain
        # through invented workspace/session policy domains.
        'edges': [],
    }
