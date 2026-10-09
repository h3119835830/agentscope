"""Evidence-bound startup recovery. Reading never probes or authorizes execution."""
import json
import time
import uuid

from .. import db
from ..bootstrap.scene import context, digest
from ..managed import controller as c
from ..policy_ir import PATTERN_MAX_UTF8_BYTES
from ..scope.manager import lock

SCHEMA = """
CREATE TABLE IF NOT EXISTS startup_recoveries(
 origin_task_id TEXT PRIMARY KEY REFERENCES tasks(id),
 origin_context_hash TEXT NOT NULL, manifest_hash TEXT NOT NULL,
 requirements_hash TEXT NOT NULL, action TEXT NOT NULL,
 request_id TEXT NOT NULL, target_task_id TEXT REFERENCES tasks(id),
 status TEXT NOT NULL, error_code TEXT, updated_at TEXT NOT NULL,
 claimed_at REAL NOT NULL);
"""

CONSTRAINT_FIELDS = ('declared_constraints', 'accepted_task_constraints',
                     'platform_constraints', 'execution_constraints', 'base_settings',
                     'startup_clarifications')


def identity(con, task_id):
    task = con.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not task:
        raise ValueError('任务不存在')
    task = dict(task)
    ctx = context(task_id, con)
    source = con.execute('SELECT * FROM workspace_task_sources WHERE task_id=?', (task_id,)).fetchone()
    frozen = ctx.get('workspace_source', {})
    if (not source or frozen.get('id') != source['workspace_id']
            or frozen.get('manifest_hash') != source['manifest_hash']
            or ctx.get('raw_prompt_hash') != digest(task['prompt'])):
        raise ValueError('缺少可核验的固定来源或原始目标，不能自动恢复')
    manifest = json.loads(source['manifest_json'])
    if digest(manifest.get('files')) != source['manifest_hash']:
        raise ValueError('来源清单校验失败')
    requirements = {'prompt_hash': ctx['raw_prompt_hash'],
                    **{key: ctx.get(key, [] if key.endswith('constraints') or key == 'startup_clarifications' else None)
                       for key in CONSTRAINT_FIELDS}}
    normalized = []
    for item in ctx.get('declared_constraints', []):
        if not isinstance(item, dict):
            raise ValueError('固定约束格式无法安全重建')
        normalized.append({**item, 'targets': [target_key(ctx, target) for target in item.get('targets', [])]})
    requirements['declared_constraints'] = normalized
    requirements['startup_clarifications'] = [
        {key: item.get(key) for key in ('text', 'request_key', 'authority')}
        for item in ctx.get('startup_clarifications', [])]
    return task, ctx, dict(source), digest(requirements)



def target_key(ctx, target):
    """Canonical exact object identity, independent of a snapshot's task ID."""
    for asset in ctx.get('assets', []):
        if target == asset['mapped_path']:
            return 'asset:' + asset.get('source_relative_path', asset['relative_path'])
    if target in (ctx['workspace'], ctx['workspace'] + '/**'):
        return 'workspace:' + target[len(ctx['workspace']):]
    raise ValueError('固定约束含无法精确重绑的目标，请重新读取场景')


def rebind_constraints(old, new):
    reverse = {'asset:' + a.get('source_relative_path', a['relative_path']): a['mapped_path']
               for a in new['assets']}
    reverse.update({'workspace:': new['workspace'], 'workspace:/**': new['workspace'] + '/**'})
    result = []
    for item in old.get('declared_constraints', []):
        targets = []
        for target in item.get('targets', []):
            key = target_key(old, target)
            if key not in reverse:
                raise ValueError('固定约束目标不属于新快照，请重新读取场景')
            targets.append(reverse[key])
        result.append({**item, 'targets': targets})
    return result


def same_instance(left, right):
    a, b = left.get('workspace_source', {}).get('instance', {}), right.get('workspace_source', {}).get('instance', {})
    return all(a.get(key) == b.get(key) for key in ('instance_id', 'generation', 'native_workspace_id'))


def linked_target(con, row, source, requirements):
    target_id = row['target_task_id']
    task, ctx, own_source, own_requirements = identity(con, target_id)
    old_ctx = context(row['origin_task_id'], con)
    if (own_source['workspace_id'] != source['workspace_id'] or own_source['manifest_hash'] != source['manifest_hash']
            or own_requirements != requirements or not same_instance(old_ctx, ctx)):
        raise ValueError('恢复任务来源或约束已变化')
    state = c.load(con, target_id)
    if not unbound(con, task, state):
        raise ValueError('恢复任务已进入授权或执行阶段')
    if state['phase'] == 'policy_review':
        return candidate(con, target_id, source, requirements), 'awaiting_review'
    if state['phase'] not in ('prepared', 'generating', 'failed'):
        raise ValueError('恢复任务状态已变化')
    return {'task_id': target_id, 'context_hash': ctx['context_hash'],
            'context_revision': state.get('revision', 0), 'phase': state['phase'],
            'gate': state['gate'], 'status': state['phase'], 'job_id': state.get('startup_job')}, state['phase']


def unbound(con, task, state):
    return (state.get('version') == 0 and not state.get('session_id')
            and not state.get('binding') and not state.get('startup_confirmation')
            and not task.get('active_version') and not task.get('active_domain_id')
            and not task.get('active_pid') and not task.get('watch_pid') and not task.get('ended_at')
            and not con.execute('SELECT 1 FROM policy_versions WHERE task_id=?', (task['id'],)).fetchone()
            and not con.execute('SELECT 1 FROM task_credentials WHERE task_id=? AND revoked_at IS NULL', (task['id'],)).fetchone())


def origin(con, task_id, expected_context=None, expected_manifest=None):
    task, ctx, source, requirements = identity(con, task_id)
    state = c.load(con, task_id)
    if state.get('phase') != 'failed' or not unbound(con, task, state):
        raise ValueError('仅尚未授权、未加载且未绑定 DSH 的启动失败任务可恢复')
    job = con.execute("SELECT * FROM history_jobs WHERE id=? AND kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=?",
                      (state.get('startup_job'), task_id)).fetchone()
    if con.execute("SELECT 1 FROM history_jobs WHERE kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=? AND status IN ('queued','running')", (task_id,)).fetchone():
        raise ValueError('原任务仍有启动生成作业，请等待终止')
    terminal_failure = job and job['status'] in ('failed', 'interrupted', 'cancelled')
    if job and job['status'] == 'completed':
        # A real server-submitted unresolved proposal is a completed Pi job,
        # while admission has failed closed. Preserve it as failure evidence.
        row = con.execute("SELECT * FROM bootstrap_proposals WHERE task_id=? AND job_id=? AND context_hash=? AND state='needs_clarification' ORDER BY created_at DESC LIMIT 1",
                          (task_id, job['id'], ctx['context_hash'])).fetchone()
        if row:
            proposal, validation = json.loads(row['proposal_json']), json.loads(row['validation_json'])
            terminal_failure = (digest(proposal) == row['content_hash']
                and proposal.get('context_hash') == ctx['context_hash']
                and bool(proposal.get('draft', {}).get('unresolved'))
                and validation.get('valid') is False
                and validation.get('state') == 'needs_clarification'
                and validation.get('compile_state') == 'compiled'
                and validation.get('proposal_hash') == row['content_hash']
                and ('proposal' not in validation or digest(validation['proposal']) == row['content_hash']))
    if not terminal_failure:
        raise ValueError('缺少已终止的启动失败作业证据')
    if expected_context is not None and ctx['context_hash'] != expected_context:
        raise ValueError('固定上下文已变化，请刷新恢复信息')
    if expected_manifest is not None and source['manifest_hash'] != expected_manifest:
        raise ValueError('来源清单已变化，请重新读取场景')
    return task, ctx, source, requirements, state, dict(job)


def candidate(con, task_id, source, requirements, origin_ctx=None):
    task, ctx, own_source, own_requirements = identity(con, task_id)
    state = c.load(con, task_id)
    if (own_source['workspace_id'] != source['workspace_id'] or own_source['manifest_hash'] != source['manifest_hash']
            or own_requirements != requirements or (origin_ctx is not None and not same_instance(origin_ctx, ctx)) or not unbound(con, task, state)
            or state.get('phase') != 'policy_review' or state.get('gate') != 'waiting_confirmation'
            or not state.get('startup_review_required')):
        raise ValueError('恢复候选来源、目标、约束或待确认状态已变化')
    row = con.execute("SELECT p.* FROM bootstrap_proposals p JOIN history_jobs j ON j.id=p.job_id "
                      "WHERE p.id=? AND p.task_id=? AND p.job_id=? AND p.state='validated' "
                      "AND j.kind='task_bootstrap' AND j.status='completed' "
                      "AND json_extract(j.input_json,'$.task_id')=?",
                      (state.get('startup_proposal'), task_id, state.get('startup_job'), task_id)).fetchone()
    if not row:
        raise ValueError('恢复候选缺少已完成的服务端校验')
    proposal, validation = json.loads(row['proposal_json']), json.loads(row['validation_json'])
    if (row['context_hash'] != ctx['context_hash'] or proposal.get('context_hash') != ctx['context_hash']
            or digest(proposal) != row['content_hash'] or validation.get('valid') is not True
            or validation.get('state') != 'validated'
            or validation.get('compile_state') != 'compiled'
            or validation.get('proposal_hash') != row['content_hash']
            # submit_task_policy_proposal stores the proposal separately from
            # its validation summary. Authenticate that canonical body above;
            # legacy summaries containing a duplicate must also agree.
            or ('proposal' in validation and digest(validation['proposal']) != row['content_hash'])):
        raise ValueError('恢复候选校验材料不一致')
    return {'task_id': task_id, 'job_id': row['job_id'], 'proposal_id': row['id'],
            'proposal_hash': row['content_hash'], 'context_hash': ctx['context_hash'],
            'context_revision': state.get('revision', 0), 'phase': state['phase'],
            'gate': state['gate'], 'status': 'awaiting_review'}


def failure(con, job, ctx):
    # Never relay provider errors, private reasoning or arbitrary diagnostic text.
    code = 'startup_submission_missing'
    diagnostics = []
    rows = con.execute("SELECT input_json,output_json FROM bootstrap_tool_events WHERE job_id=? AND tool='validate_policy_draft' ORDER BY occurred_at DESC,rowid DESC", (job['id'],)).fetchall()
    registered = {a['mapped_path'] for a in ctx.get('assets', [])}
    for row in rows:
        output = json.loads(row['output_json'])
        if output.get('valid') is not False:
            continue
        details = output.get('diagnostic_details', {})
        legacy_errors = {'IR pattern 超过 ' + str(limit) + ' UTF-8 bytes 或包含控制字符' for limit in (64, PATTERN_MAX_UTF8_BYTES)}
        draft = json.loads(row['input_json']).get('draft', {})
        paths = [p for atom in draft.get('atoms', []) if isinstance(atom, dict)
                 for p in atom.get('paths', []) if isinstance(p, str)]
        overlong = [p for p in paths if p in registered and len(p.encode('utf-8')) > PATTERN_MAX_UTF8_BYTES]
        if ((isinstance(details, dict) and details.get('code') == 'engine_pattern_limit_exceeded')
                or (output.get('diagnostic') in legacy_errors and overlong)):
            code = 'engine_pattern_limit_exceeded'
            diagnostics = [{'code': code, 'max_utf8_bytes': PATTERN_MAX_UTF8_BYTES,
                            'target_utf8_bytes': sorted({len(p.encode('utf-8')) for p in overlong})}]
            break
    summary = ('文件路径超过执行引擎的 ' + str(PATTERN_MAX_UTF8_BYTES) + ' UTF-8 字节限制。请重建同源快照后重新生成策略。'
               if code == 'engine_pattern_limit_exceeded'
               else '启动策略未获得服务端有效提交。旧任务保留失败证据，可查看同源恢复候选或重新生成。')
    return {'code': code, 'summary': summary, 'diagnostics': diagnostics}


def get(task_id):
    with db.connect() as con:
        con.execute('PRAGMA query_only=ON')
        try:
            task, ctx, source, requirements, state, job = origin(con, task_id)
        except ValueError as error:
            return {'eligible': False, 'blocked_reason': str(error), 'candidate': None,
                    'candidates': [], 'link': None}
        options = []
        for row in con.execute('SELECT task_id FROM workspace_task_sources WHERE workspace_id=? AND manifest_hash=? AND task_id<>? ORDER BY created_at DESC',
                               (source['workspace_id'], source['manifest_hash'], task_id)):
            try:
                options.append(candidate(con, row['task_id'], source, requirements, ctx))
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
        linkrow = con.execute('SELECT * FROM startup_recoveries WHERE origin_task_id=?', (task_id,)).fetchone()
        link, link_error, link_status = None, None, linkrow['status'] if linkrow else None
        if linkrow and linkrow['target_task_id']:
            try:
                link, link_status = linked_target(con, linkrow, source, requirements)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                link_error = '恢复任务尚未就绪或状态已变化'
        return {'eligible': True, 'blocked_reason': None, 'failure': failure(con, job, ctx),
                'origin': {'context_hash': ctx['context_hash'], 'manifest_hash': source['manifest_hash'],
                           'requirements_hash': requirements, 'failed_job_id': job['id'],
                           'context_revision': state.get('revision', 0)},
                'candidate': options[0] if len(options) == 1 else None, 'candidates': options,
                'link': link, 'link_status': link_status,
                'link_error': link_error}


def response(action, target, link):
    return {'action': action, 'target': target, 'link': dict(link)}


def prepare(task_id, body):
    with lock(task_id):
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            task, ctx, source, requirements, state, job = origin(
                con, task_id, body['expected_context_hash'], body['expected_manifest_hash'])
            existing = con.execute('SELECT * FROM startup_recoveries WHERE origin_task_id=?', (task_id,)).fetchone()
            if existing and (existing['origin_context_hash'] != ctx['context_hash'] or existing['requirements_hash'] != requirements):
                raise ValueError('恢复关联已过期，请重新读取场景')
            if body['action'] == 'reuse':
                target_id = body.get('expected_candidate_task_id')
                target_hash = body.get('expected_candidate_proposal_hash')
                if not target_id or not target_hash:
                    raise ValueError('请选择明确的恢复候选及校验哈希')
                if existing and existing['target_task_id'] != target_id:
                    raise ValueError('任务已有不同恢复关联，不能静默替换')
                target = candidate(con, target_id, source, requirements, ctx)
                if target['proposal_hash'] != target_hash:
                    raise ValueError('恢复候选已过期，请刷新')
                if not existing:
                    con.execute('INSERT INTO startup_recoveries VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                                (task_id, ctx['context_hash'], source['manifest_hash'], requirements,
                                 'reuse', uuid.uuid4().hex, target_id, 'awaiting_review', None, db.now(), time.time()))
                    db.audit(con, task_id, 'startup_recovery_linked', 'administrator',
                             {'target_task_id': target_id, 'context_hash': ctx['context_hash'],
                              'proposal_hash': target_hash, 'manifest_hash': source['manifest_hash']})
                link = con.execute('SELECT * FROM startup_recoveries WHERE origin_task_id=?', (task_id,)).fetchone()
                return response('reuse', target, link)
            if existing and existing['target_task_id']:
                target_id = existing['target_task_id']
                managed_row = con.execute('SELECT state_json FROM managed_tasks WHERE task_id=?', (target_id,)).fetchone()
                target_state = json.loads(managed_row[0]) if managed_row else {'phase': 'prepared'}
                if target_state['phase'] in ('generating', 'policy_review'):
                    # Revalidate the specific linked child; never substitute another.
                    target, status = linked_target(con, existing, source, requirements)
                    return response('rebuild', target, {**dict(existing), 'status': status})
                if existing['status'] not in ('failed', 'building') or target_state['phase'] != 'prepared':
                    raise ValueError('恢复任务已变化；请查看该任务自身的失败证据后恢复')
            if existing and existing['status'] == 'building' and time.time() - existing['claimed_at'] < 120:
                raise ValueError('恢复任务正在创建，请稍后刷新')
            request_id = uuid.uuid4().hex
            con.execute('INSERT INTO startup_recoveries VALUES(?,?,?,?,?,?,?,?,?,?,?) '
                        'ON CONFLICT(origin_task_id) DO UPDATE SET request_id=excluded.request_id,action=excluded.action,status=excluded.status,error_code=NULL,updated_at=excluded.updated_at,claimed_at=excluded.claimed_at',
                        (task_id, ctx['context_hash'], source['manifest_hash'], requirements, 'rebuild',
                         request_id, None, 'building', None, db.now(), time.time()))
            target_id = existing['target_task_id'] if existing else None
        try:
            from . import registry
            if not target_id:
                result = registry.create_task(source['workspace_id'], task['name'], task['prompt'], source['manifest_hash'],
                                              recovery_origin={'task_id': task_id, 'context_hash': ctx['context_hash'],
                                                               'request_id': request_id})
                target_id = result['id']
            else:
                # Resume only a committed child whose enqueue/initialization failed.
                with db.connect() as con:
                    child = dict(con.execute('SELECT * FROM tasks WHERE id=?', (target_id,)).fetchone())
                c.initialize({'id': target_id, 'workspace': child['workspace']}) if not c.exists(target_id) else None
                with db.connect() as con:
                    child_state = c.load(con, target_id)
                    child_state['startup_review_required'] = True
                    c.save(con, target_id, child_state)
            with db.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                origin(con, task_id, body['expected_context_hash'], body['expected_manifest_hash'])
                claim = con.execute('SELECT * FROM startup_recoveries WHERE origin_task_id=? AND request_id=? AND target_task_id=?',
                                    (task_id, request_id, target_id)).fetchone()
                if not claim:
                    raise ValueError('恢复请求已由另一请求接管')
                linked_target(con, claim, source, requirements)
            started = c.start(target_id)  # Generates a candidate; never confirms or loads it.
            with db.connect() as con:
                con.execute("UPDATE startup_recoveries SET status='generating',error_code=NULL,updated_at=? WHERE origin_task_id=? AND request_id=?",
                            (db.now(), task_id, request_id))
                target_state = c.load(con, target_id)
                link = con.execute('SELECT * FROM startup_recoveries WHERE origin_task_id=?', (task_id,)).fetchone()
                return response('rebuild', {'task_id': target_id, 'phase': target_state['phase'],
                                           'gate': target_state['gate'], 'status': started['status']}, link)
        except Exception:
            with db.connect() as con:
                con.execute("UPDATE startup_recoveries SET status='failed',error_code='recovery_generation_failed',updated_at=? WHERE origin_task_id=? AND request_id=?",
                            (db.now(), task_id, request_id))
                db.audit(con, task_id, 'startup_recovery_failed', 'administrator',
                         {'request_id': request_id, 'code': 'recovery_generation_failed'})
            raise ValueError('恢复候选创建失败；旧失败证据保持不变，可重试恢复')
