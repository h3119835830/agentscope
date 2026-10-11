"""Evidence-bound recovery feedback; delivery is distinct from context admission."""
import hashlib
import json
from pathlib import Path
from .recovery import guidance_for, recovery_spec

PREFIX = '[ActPlane operation feedback] '


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def make_bundle(task, state, ctx, receipt, version, policy_hash):
    rules = []
    for scope, compiled in [('child', receipt.get('loaded_catalog') or receipt.get('compile', {})),
                            ('parent', (receipt.get('baseline_binding') or {}).get('compile', {}))]:
        for rule in compiled.get('rules', []):
            rules.append({'scope': scope, **{k: rule.get(k) for k in (
                'rule_id', 'name', 'reason', 'effect', 'clause_hash', 'source_hash',
                'clause_source_index', 'clause_op', 'target_kind', 'target_pattern')}})
    value = {'schema': 'AgentScopeRecoveryBundle/1', 'task_id': task['id'],
             'version': version, 'policy_hash': policy_hash, 'context_hash': ctx.get('context_hash'),
             'process_epoch': receipt.get('process_epoch') or digest([receipt.get('domain_id'), receipt.get('runner_pid'), version]),
             'engine': receipt.get('engine_identity', {}), 'process_domain_id': receipt.get('domain_id'),
             'recovery_spec': state.get('recovery_spec') or recovery_spec({}), 'rules': rules,
             'allowed_write_dirs': state['allowed_write_dirs'], 'allow_output': state['allow_output']}
    return {**value, 'hash': digest(value)}


def valid_bundle(bundle):
    return bool(bundle and bundle.get('hash') == digest({k: v for k, v in bundle.items() if k != 'hash'}))


def public_target(target, task):
    roots = [task['workspace'], task['output_dir'], str(Path(task['workspace']).parent / 'tmp')]
    return target if any(target == r or target.startswith(r + '/') for r in roots) and '/.actplane' not in target else '<任务可见范围之外>'


def operation_feedback(event_id, raw, task, *, bundle=None, payload=None):
    payload = payload or {}
    rule = raw.get('rule') or {}
    matches = []
    if valid_bundle(bundle) and raw.get('process_domain_id', raw.get('domain_id')) == bundle['process_domain_id']:
        matches = [r for r in bundle['rules'] if all(r.get(k) == rule.get(k) for k in
                   ('name', 'clause_hash', 'source_hash', 'clause_source_index', 'clause_op', 'effect'))
                   and r['rule_id'] == raw.get('rule_id')]
    known = len(matches) == 1
    compiled = matches[0] if known else {}
    result = 'blocked' if raw.get('blocked') else 'killed' if raw.get('killed') else 'notified' if raw.get('effect') == 'notify' else 'unverified'
    reason = compiled.get('reason') if known else '无法将事件唯一关联到已加载的规则版本；保持保护并等待控制面诊断。'
    guidance = guidance_for(compiled, bundle['recovery_spec'] if known else recovery_spec({}),
                            task['workspace'], bundle['allowed_write_dirs'] if known else [],
                            bundle['allow_output'] if known else False)
    facts = {'blocked': bool(raw.get('blocked')), 'killed': bool(raw.get('killed')),
             'effect': raw.get('effect'), 'operation': raw.get('op'),
             'target': public_target(str(raw.get('target', '')), task),
             'atomicity': '仅证明报告的操作；复合命令此前的其他副作用需要单独核对。'}
    identity = {'task_id': task.get('id'), 'session_id': payload.get('session_id'),
                'call_id': payload.get('tool_call_id'), 'version': payload.get('version'),
                'process_domain_id': raw.get('process_domain_id', raw.get('domain_id')),
                'process_epoch': bundle.get('process_epoch') if bundle else None,
                'engine': bundle.get('engine') if bundle else None,
                'pid': raw.get('pid'), 'kernel_call_tag': raw.get('tool_call_tag'),
                'timestamp_unix_ns': raw.get('timestamp_unix_ns')}
    return {'schema': 'AgentScopeFeedback/1', 'id': event_id,
            'feedback_id': digest([task.get('id'), event_id, identity['process_epoch']]),
            'identity': identity, 'operation': facts['operation'], 'target': facts['target'],
            'result': result, 'facts': facts, 'reason': reason, 'because': reason,
            'rule': {k: compiled.get(k) for k in ('name', 'rule_id', 'clause_hash', 'source_hash', 'clause_source_index')},
            'policy_hash': bundle.get('policy_hash') if bundle else None,
            'recovery_bundle_hash': bundle.get('hash') if bundle else None,
            'guidance': guidance, 'guidance_complete': known and result in ('blocked', 'killed', 'notified'),
            'authority': 'loaded_compiler_metadata_and_approved_recovery_spec' if known else 'kernel_fact_only; guidance_requires_review'}


def message(events):
    return PREFIX + json.dumps(events, ensure_ascii=False, separators=(',', ':')) + '\n请依据上述实际结果与 because 重新规划，执行允许的下一步；不要原样重试被拒绝的动作。'


def admitted_ids(con, task_id):
    return {ident for row in con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='feedback_context_admitted'", (task_id,))
            for ident in json.loads(row[0]).get('event_ids', [])}


def pending_events(con, task_id, state, *, call_id=None):
    admitted = admitted_ids(con, task_id)
    events = []
    for row in con.execute("SELECT id,payload_json FROM managed_events WHERE task_id=? AND kind='kernel' ORDER BY id", (task_id,)):
        p = json.loads(row['payload_json'])
        if row['id'] in admitted or p.get('verification_probe') or not p.get('tool_call_id'): continue
        f = p.get('feedback')
        if not f or f['identity']['session_id'] != state.get('session_id') or f['identity']['process_epoch'] != state.get('recovery_bundle', {}).get('process_epoch'): continue
        if call_id is not None and p['tool_call_id'] != call_id: continue
        events.append(f)
    return events


def offer(con, task_id, state, events, call_id=None, channel='immediate'):
    from .controller import event
    text = message(events)
    key = digest([state['session_id'], [e['feedback_id'] for e in events]])
    payload = {'session_id': state['session_id'], 'call_id': call_id,
               'event_ids': [e['id'] for e in events], 'feedback_ids': [e['feedback_id'] for e in events],
               'process_epoch': state['recovery_bundle']['process_epoch'], 'feedback': text,
               'channel': channel, 'authority': 'control_plane_offer; not_context_admission'}
    event(con, task_id, 'feedback_offer', key, payload)
    return {'events': events, 'message': text, 'offer_id': key}
