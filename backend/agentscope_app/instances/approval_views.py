"""One approval object over authoritative DSL, typed-policy and runtime stores."""
import json
import threading
from concurrent.futures import Future
from fastapi import HTTPException
from .. import db
from . import dsl_policy as dsl, store
from .approval_locations import Locations, product
from .configuration_approvals import read_snapshot


def envelope(row,baseline):
    target = row['target']
    row['target'] = {'instance_id': row['scope_id'] if target['scope'] == 'agent' else None,
                     'workspace_id': None, 'session_id': None, **target}
    return {**row,'schema':'PolicyApproval/1','baseline':baseline}


def scopes():
    from ..console import hidden
    retained=hidden('agent')
    return {'system':'全部受控 Agent',**{r['id']:product(r) for r in store.rows() if r['mode']=='controlled' and r['id'] not in retained}}


def pending_count():
    # Keep the same freshness validation for eligible candidates, but do not
    # project every applied/failed historical approval just to count pending.
    return _read_directory(pending_only=True)['pending_count']


def project(p,names,full=False,locations=None):
    from ..console import hidden
    from .workspace_references import ReaderUnavailable
    base=dsl.current(p['scope_id'])
    status=p['state'];reason='';validation_stage=None;target_changes=[];validation_unavailable=False
    from .individual_approvals import completed as individual_completed
    if not individual_completed(p):
        status='blocked';reason='独立审批记录尚未准备完成，请稍后刷新。'
    elif status=='pending':
        try:
            validation_stage='recovery'
            from .approval_recovery import completed
            if not completed(p):raise ValueError('重新校验尚未完成，请重试原校验请求。')
            from .policy_library import verify_proposal
            validation_stage='library'
            verify_proposal(p['id'])
            from .template_configurations import verify_proposal as verify_template_proposal
            validation_stage='template'
            verify_template_proposal(p['id'],read_sources=False)
            validation_stage='baseline'
            if p['base_revision']!=base['revision'] or p['base_hash']!=base['document_hash']:
                raise ValueError('策略配置已经变化，请重新校验')
            validation_stage='target'
            actual_targets=dsl.target_snapshot(p['scope_id'],p['documents'])
            if actual_targets!=p['targets']:
                previous={target['id']:target for target in p['targets']}
                target_changes=[{'id':target['id'],'fields':sorted(key for key in set(target)|set(previous.get(target['id'],{})) if target.get(key)!=previous.get(target['id'],{}).get(key))} for target in actual_targets if target!=previous.get(target['id'])]
                raise ValueError('Agent 连接或运行环境已经变化，请重新校验')
            from ..history.agent_context import validate_documents
            validation_stage='documents'
            validate_documents(p['scope_id'],p['documents'],base['documents'])
        except ReaderUnavailable:
            status='blocked';reason='资料核验暂不可用，请稍后刷新。';validation_unavailable=True
        except (ValueError,RuntimeError,OSError) as error:
            status='stale';reason='场景依据已变化，请回到策略助手重新读取并生成候选。' if '场景' in str(error) or '项目文件' in str(error) else 'Agent 环境或策略配置已经变化，需要重新校验。'
            if str(error).startswith(('配置库版本已变化：','重新校验尚未完成')):reason=str(error)
    elif status=='invalid':reason='候选未通过运行环境校验，请调整配置后重新提交。'
    elif status=='failed':reason='上次应用未完成，请检查配置并重新校验。'
    visible_targets=[t for t in p['targets'] if p['scope_id']=='system' or t['id'] not in hidden('agent')]
    changes=p['result'].get('document_changes')
    change_name='；'.join(verb+' '+ '、'.join(changes[key]) for verb,key in (('新增','added'),('更新','updated'),('停用','removed')) if changes.get(key)) if changes else ''
    row={'id':p['id'],'scope_id':p['scope_id'],'scope_type':'system' if p['scope_id']=='system' else 'agent',
         'target_name':names[p['scope_id']],'name':change_name or '、'.join(d['name'] for d in p['documents']) or '移除本层策略',
         'status':status,'created_at':p['created_at'],'document_count':len(p['documents']),
         'can_apply':status=='pending','reason':reason,
         'affected_count':len(visible_targets),'total_affected_count':len(p['targets'])}
    row.update((locations or Locations()).project(p,visible_targets))
    if validation_unavailable:row['validation_unavailable']=True
    if status=='stale':row['validation_diagnostic']={'stage':validation_stage,'target_changes':target_changes}
    compilation=next((c for c in p['result'].get('compilations',[]) if c['instance_id'] in {t['id'] for t in visible_targets}),None)
    records=dsl.policy_records(compilation,p['scope_id']) if compilation else []
    row.update(records=records,document_changes=changes,documents=p['documents'],split_incomplete=not individual_completed(p))
    from .session_policy_records import action
    doc_ids={d['id'] for d in p['documents']}
    effects=[]
    for compilation in p['result'].get('compilations',[]):
        names={r['compiled_name'] for doc in compilation.get('documents',[]) if doc.get('id') in doc_ids and doc.get('scope_id')==p['scope_id'] for r in doc.get('rules',[])}
        effects.extend(r.get('effect') for r in compilation.get('compile',{}).get('rules',[]) if r.get('name') in names)
    row['default_action']=action(effects)
    if full:
        row.update(documents=p['documents'],records=records,targets=visible_targets,proposal_hash=p['proposal_hash'],application=p['result'].get('application'),document_changes=changes,
                   previous_documents=base['documents'] if p['base_hash']==base['document_hash'] else None)
    from .approval_configuration_records import records as configuration_records
    row['configuration_records'] = configuration_records(p)
    if row['configuration_records']:
        row['name'] = row['configuration_records'][0].get('name','配置记录暂不可用') if len(row['configuration_records'])==1 else '旧合并审批 · 待拆分'
    if len(row['configuration_records'])==1 and not row['configuration_records'][0].get('unavailable'):
        single=row['configuration_records'][0]
        row['approval_unit']={'configuration_id':single['id'],'revision':single['revision'],'operation':single['approval_operation']}
    if not row['configuration_records']:
        with db.connect() as con:
            legacy=con.execute('SELECT selections_json,removals_json FROM system_policy_library_proposals WHERE proposal_id=?',(p['id'],)).fetchone()
        choices=json.loads(legacy['selections_json']) if legacy else []
        if len(choices)==1:
            choice=choices[0];removals=json.loads(legacy['removals_json'])
            row['approval_unit']={'configuration_id':choice['id'],'revision':choice['revision'],'operation':'disable' if choice['id'] in removals else 'apply'}
    if len(row['configuration_records'])>1 and p['state'] in ('pending','splitting'):
        row.update(status='blocked',can_apply=False,reason='旧合并审批需要拆分为每项独立的记录。')
    row.update(kind='dsl',origin='manual',candidate_hash=p['proposal_hash'],
        target={'scope':row['scope_type'],'id':p['scope_id']},
        scope_label='全部受控 Agent' if p['scope_id']=='system' else '全部工作区与会话',
        can_reject=p['state'] in ('pending','invalid','failed') and len(row['configuration_records'])<=1,validation_label='环境与编译校验通过')
    return envelope(row,{'document_hash':p['base_hash'],'revision':p['base_revision']})


def typed_changes(old,new):
    from .policy import records
    labels={'model_only':'仅模型与控制连接','disabled':'禁止模型和外部网络，保留控制连接'}
    changes=[]
    previous={v['source']:v for v in old.get('resource_views',{}).get('views',[])}
    for view in new.get('resource_views',{}).get('views',[]):
        if view != previous.get(view['source']):
            changes.append({'label':'新增精确资源映射（不自动授予写权限）','before':view['source'],'after':view['execution']})
    if old['network']!=new['network']:
        changes.append({'label':'网络访问','before':labels[old['network']],'after':labels[new['network']]})
    for verb,first,second in (('新增',new,old),('移除',old,new)):
        for rule in first['rules']:
            if rule not in second['rules']:
                sentence=records({'rules':[rule],'network':new['network']},[])[-1]['sentence']
                changes.append({'label':verb+'规则','before':'—' if verb=='新增' else sentence,'after':sentence if verb=='新增' else '—'})
    return changes


def typed_project(p,names,full=False,shared=False):
    from . import controller,system_policy
    from ..console import hidden
    scope='system' if shared else p['instance_id']
    state='stale' if p['state']=='superseded' else p['state'];reason=''
    if shared:
        candidate=json.loads(p['policy_json']);base=system_policy.current()['policy']
        targets=json.loads(p['targets_json'])
        if state=='pending' and (p['base_hash']!=system_policy.current()['policy_hash'] or p['revision']!=system_policy.current()['revision'] or system_policy.plan(candidate)!=targets):
            state='stale';reason='系统策略或影响范围已经变化，请重新提交。'
    else:
        agent=store.get(scope);base=agent['policy'];candidate=json.loads(p['policy_json'])
        targets=[{'id':scope,'name':names[scope],'agent_type':agent['agent_type'],'active':agent['gate'] in ('open','paused')}]
        if state=='pending':
            try:controller.validate_proposal(agent,p)
            except (ValueError,RuntimeError,OSError):state='stale';reason='Agent 环境或策略基线已经变化，请重新提交。'
    prefix='system' if shared else 'instance'
    runtime_origin=not shared and p['actor']=='agent'
    row={'id':prefix+':'+p['id'],'kind':prefix+'_policy','origin':'runtime' if runtime_origin else 'manual',
        'scope_id':scope,'scope_type':'system' if shared else 'agent','target':{'scope':'system' if shared else 'agent','id':scope},
        'target_name':names[scope],'name':'系统执行权限变更' if shared else 'Agent 运行时执行权限变更' if runtime_origin else 'Agent 执行权限变更',
        'status':state,'reason':reason,'created_at':p['created_at'],'can_apply':state=='pending','can_reject':p['state']=='pending',
        'document_count':0,'affected_count':sum(t['id'] not in hidden('agent') for t in targets),
        'total_affected_count':len(targets),'candidate_hash':p['proposal_hash'],'proposal_hash':p['proposal_hash'],
        'scope_label':'全部受控 Agent' if shared else '此 Agent 的共享执行域 · 全部工作区与会话','validation_label':'目标与权限基线已校验'}
    if full:
        with db.connect() as con:frozen=con.execute('SELECT policy_json FROM policy_approval_baselines WHERE approval_id=?',(row['id'],)).fetchone()
        if frozen:base=json.loads(frozen[0])
        elif p['base_hash']!=controller.digest(base):base=None
        visible=[{**t,'active':t.get('active',t.get('gate') in ('open','paused'))} for t in targets if t['id'] not in hidden('agent')]
        row.update(documents=[],records=[],targets=visible,change_items=typed_changes(base,candidate) if base else [],baseline_available=base is not None)
    return envelope(row,{'policy_hash':p['base_hash'],**({'revision':p['revision']} if shared else {'generation':p['generation']})})


def runtime_project(job,task,state,full=False):
    p=json.loads(job['proposal_json']);ctx=json.loads(job['context_json']);pending=state.get('pending_change') or state.get('pending_expansion')
    # Legacy archives can lack the frozen candidate/baseline contract. Keep
    # them inspectable without manufacturing authority or breaking the list.
    baseline=ctx.get('base_snapshot',{}).get('payload',{})
    if not p.get('hash') or not all(k in p and k in baseline for k in ('allowed_write_dirs','allow_output')):
        row={'id':'runtime:'+job['id'],'kind':'runtime','origin':'runtime','scope_id':job['task_id'],'scope_type':'session',
            'target':{'scope':'session','task_id':job['task_id'],'session_id':ctx.get('session_id')},
            'target_name':task['name'],'name':'运行时权限变更','status':'invalid',
            'reason':'旧记录缺少候选指纹或权限基线，请重新生成并校验。','created_at':job['created_at'],
            'can_apply':False,'can_reject':False,'document_count':0,'affected_count':1,'total_affected_count':1,
            'candidate_hash':p.get('hash'),'proposal_hash':p.get('hash'),'scope_label':'当前任务会话','validation_label':'需要重新校验'}
        if full:row.update(documents=[],records=[],change_items=[],targets=[])
        return envelope(row,{'policy_hash':job['policy_hash'],'revision':job['revision']})
    binding=ctx.get('current_binding',{})
    current=bool(pending and pending['job_id']==job['id'] and pending['hash']==p['hash'])
    with db.connect() as con:
        applied=con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='request_resolved' AND json_extract(payload_json,'$.confirmation')=? AND event_key=?",(job['task_id'],p['hash'],job['id'])).fetchone()
        failed=con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='change_apply_failed' AND json_extract(payload_json,'$.candidate_hash')=? AND json_extract(payload_json,'$.job_id')=?",(job['task_id'],p['hash'],job['id'])).fetchone()
    valid=(current and state['phase']=='running' and job['status']=='completed'
        and job['revision']==state['revision'] and job['policy_hash']==state['policy_hash']
        and pending.get('base_version',state['version'])==state['version']
        and all(binding.get(k)==state.get('binding',{}).get(k) for k in ('domain_id','runner_pid') if k in binding)
        and all(pending.get('binding',{}).get(k)==state.get('binding',{}).get(k) for k in ('domain_id','runner_pid','watch_pid','process_cgroup') if k in pending.get('binding',{}))
        and bool(ctx.get('session_id',binding.get('session_id')))
        and ctx.get('session_id',binding.get('session_id'))==state.get('session_id'))
    status=('applied' if applied else 'rejected' if job['status']=='rejected' else 'applying' if valid and state['gate']=='applying' else 'failed' if failed else 'stale' if not valid else 'pending')
    reason=''
    if status=='stale':reason='任务、会话或策略基线已经变化，此候选不可应用。'
    if status=='failed':reason='上次应用未完成；再次批准时会重新核对当前执行域。'
    row={'id':'runtime:'+job['id'],'kind':'runtime','origin':'runtime','scope_id':job['task_id'],'scope_type':'session',
        'target':{'scope':'session','task_id':job['task_id'],'session_id':ctx.get('session_id',binding.get('session_id'))},
        'target_name':task['name'],'name':'运行时'+('权限收紧' if p['decision']=='restrict' else '权限扩展'),
        'status':status,'reason':reason,'created_at':job['created_at'],'can_apply':bool(valid and status in ('pending','failed')),
        'can_reject':bool(valid and status in ('pending','failed')),'document_count':0,'affected_count':1,'total_affected_count':1,
        'candidate_hash':p['hash'],'proposal_hash':p['hash'],'scope_label':'当前任务会话','validation_label':'候选已校验，应用前复核执行域'}
    if full:
        old=ctx['base_snapshot']['payload']
        display=lambda values:'、'.join(values) or '无'
        changes=[{'label':'可写目录','before':display(old['allowed_write_dirs']),'after':display(p['allowed_write_dirs'])},
            {'label':'任务输出写入','before':'允许' if old['allow_output'] else '禁止','after':'允许' if p['allow_output'] else '禁止'},
            {'label':'运行时保护对象','before':display(old.get('protected_paths',[])),'after':display(p.get('protected_paths',[]))}]
        row.update(documents=[],records=[],change_items=[c for c in changes if c['before']!=c['after']],explanation=p.get('explanation',''),
            targets=[{'id':job['task_id'],'name':task['name'],'scope_label':'当前任务会话','application_label':'确认后重建当前任务执行域'}])
        if p.get('compiled_dsl'):row['documents']=[{'id':job['id'],'name':'当前任务候选 DSL','original_dsl':p['compiled_dsl']}]
    return envelope(row,{'policy_hash':job['policy_hash'],'revision':job['revision'],'version':binding.get('version')})


_directory_lock = threading.Lock()
_directory_inflight = None


def directory():
    """Coalesce concurrent reads only; sequential reads always get fresh state."""
    global _directory_inflight
    with _directory_lock:
        leader = _directory_inflight is None
        if leader: _directory_inflight = Future()
        pending = _directory_inflight
    if not leader: return pending.result()
    try:
        value = _read_directory()
        pending.set_result(value)
        return value
    except BaseException as error:
        pending.set_exception(error)
        raise
    finally:
        with _directory_lock:
            if _directory_inflight is pending: _directory_inflight = None


@read_snapshot
def _read_directory(pending_only=False):
    names=scopes()
    with db.connect() as con:
        rows=[dsl.unpack(p) for p in con.execute("SELECT * FROM instance_dsl_proposals "+("WHERE state='pending' " if pending_only else '')+"ORDER BY created_at DESC,id DESC") if p['scope_id'] in names]
    locations=Locations()
    from .individual_approvals import replacements
    records=[project(p,names,locations=locations) for p in rows if not replacements(p['id'])]
    from . import local_policy_proposals as local
    with db.connect() as con:
        records.extend(local.project(dict(p), names, full=True,locations=locations) for p in con.execute('SELECT * FROM local_policy_proposals'+(" WHERE state='pending'" if pending_only else '')) if p['instance_id'] in names)
    with db.connect() as con:
        native=[dict(r) for r in con.execute('SELECT * FROM instance_proposals'+(" WHERE state='pending'" if pending_only else '')) if r['instance_id'] in names]
        shared=[dict(r) for r in con.execute('SELECT * FROM system_security_proposals'+(" WHERE state='pending'" if pending_only else ''))]
        # Filter retained/removed tasks before projecting history. Otherwise
        # every overview poll opens several connections per hidden job, even
        # though none can appear in the customer approval directory.
        jobs=[dict(r) for r in con.execute("""SELECT j.* FROM managed_jobs j
            JOIN tasks t ON t.id=j.task_id JOIN managed_tasks m ON m.task_id=j.task_id
            WHERE j.proposal_json IS NOT NULL
            AND json_extract(j.proposal_json,'$.decision') IN ('restrict','expand')
            AND j.task_id NOT IN (SELECT record_id FROM console_retained_records WHERE kind='task')"""+(" AND j.status='completed' AND json_extract(m.state_json,'$.phase')='running'" if pending_only else ''))]
    records.extend(typed_project(p,names,full=True) for p in native)
    records.extend(typed_project(p,names,full=True,shared=True) for p in shared)
    for job in jobs:
        row=runtime_detail(job['id'],full=True)
        if row:records.append(row)
    records.sort(key=lambda r:(r['created_at'],r['id']),reverse=True)
    from .approval_decisions import project_many
    records=project_many(records)
    from .approval_recovery import hint
    records=[{**row,'revalidation':hint(row)} for row in records]
    return {'records':records,'pending_count':sum(r['status']=='pending' for r in records)}


def raw_detail(ident):
    if ident.startswith('local:'):
        from . import local_policy_proposals as local
        p = local.load(ident.split(':', 1)[1]); names = scopes()
        if p['instance_id'] not in names: raise HTTPException(404, '审批记录不存在')
        return local.project(p, names, full=True)
    if ident.startswith(('instance:','system:')):
        kind,key=ident.split(':',1);names=scopes();table='instance_proposals' if kind=='instance' else 'system_security_proposals'
        with db.connect() as con:p=con.execute('SELECT * FROM '+table+' WHERE id=?',(key,)).fetchone()
        if not p or kind=='instance' and p['instance_id'] not in names:raise HTTPException(404,'审批记录不存在')
        return typed_project(dict(p),names,full=True,shared=kind=='system')
    if ident.startswith('runtime:'):
        row=runtime_detail(ident.split(':',1)[1],full=True)
        if not row:raise HTTPException(404,'审批记录不存在')
        return row
    names=scopes()
    with db.connect() as con:p=con.execute('SELECT * FROM instance_dsl_proposals WHERE id=?',(ident,)).fetchone()
    if not p or p['scope_id'] not in names:raise HTTPException(404,'审批记录不存在')
    return project(dsl.unpack(p),names,full=True)


def runtime_detail(key,full=False):
    from ..console import hidden
    from ..managed import controller
    with db.connect() as con:
        job=con.execute('SELECT * FROM managed_jobs WHERE id=?',(key,)).fetchone()
        if not job or job['task_id'] in hidden('task'):return None
        task=con.execute('SELECT id,name FROM tasks WHERE id=?',(job['task_id'],)).fetchone()
        managed=con.execute('SELECT 1 FROM managed_tasks WHERE task_id=?',(job['task_id'],)).fetchone()
        if not task or not managed or not job['proposal_json'] or json.loads(job['proposal_json']).get('decision') not in ('restrict','expand'):return None
        state=controller.load(con,job['task_id'])
    return runtime_project(dict(job),dict(task),state,full)


def execute_decision(ident,decision,expected_hash):
    """Administrator router only. Reuse authoritative loaders and their locks."""
    from . import controller,system_policy
    row=raw_detail(ident)
    if row['candidate_hash']!=expected_hash:raise ValueError('候选确认内容不一致')
    if decision=='confirm' and not row['can_apply'] and row['status']!='applied':raise ValueError('候选需要重新校验或已处理')
    if decision=='reject' and not row['can_reject'] and row['status']!='rejected':raise ValueError('候选已变化或已处理')
    if row['kind']=='local_dsl':
        from . import local_policy_proposals as local
        result=local.decide(ident.split(':',1)[1],decision,expected_hash)
    elif row['kind']=='dsl':result=(dsl.apply if decision=='confirm' else dsl.reject)(row['scope_id'],ident,expected_hash)
    elif row['kind']=='instance_policy':result=(controller.apply if decision=='confirm' else controller.reject)(row['scope_id'],ident.split(':',1)[1],expected_hash)
    elif row['kind']=='system_policy':result=(system_policy.apply if decision=='confirm' else system_policy.reject)(ident.split(':',1)[1],expected_hash)
    elif row['status'] in ('applied','rejected'):result={'id':ident,'state':row['status'],'idempotent':True}
    else:raise ValueError('运行时限制由控制面校验后自动追加，不存在人工审批动作')
    with db.connect() as con:
        db.audit(con,None,'policy_approval_decision','authenticated_operator',{'approval_id':ident,'candidate_hash':expected_hash,'scope_id':row['scope_id'],'kind':row['kind'],'decision':decision})
    return result


@read_snapshot
def detail(ident):
    from .approval_decisions import project
    from .approval_recovery import hint,lineage
    row=project(raw_detail(ident))
    from .individual_approvals import replacements
    return {**row,'revalidation':hint(row),**lineage(ident),'replacement_approvals':replacements(ident)}


def decide(ident,decision,expected_hash):
    from . import approval_decisions
    return (approval_decisions.confirm if decision=='confirm' else approval_decisions.reject)(ident,expected_hash)
