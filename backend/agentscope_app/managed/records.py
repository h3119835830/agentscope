"""Admin-only structured views over persisted policy sources and receipts.

These views never authorize a candidate and never read a native private stream.
"""
import hashlib,json,re
from . import controller as c
from .. import db

HOOKS={
 'startup':{'name':'DSH 启动前','events':['任务描述与已登记项目材料'],'sequence':['读取必读来源','Pi 识别策略','校验与编译','Broker 加载并核验','放行 DSH']},
 'runtime':{'name':'DSH 运行时','events':['真实用户消息','system/developer 提示词','工具 schema 与有效上下文','compaction 记忆','ActPlane 内核拒绝','已验证的误拦截'],'sequence':['Native hook 接收变化','冻结上下文并暂停新工具','Pi 评估增量','收紧自动加载 / 扩权待确认','核验后继续执行']}}

def digest(text):return hashlib.sha256(text.encode()).hexdigest()
def decode(row,key):return json.loads(row[key]) if row and row[key] else {}
def clean_dsl(compiler,names=None):
    rules={}
    for rule in compiler.get('rules',[]):
        if names is not None and rule.get('name') not in names:continue
        text=rule.get('source_text','')
        if text:rules[(rule.get('source_start_line',0),rule.get('name',''))]=text
    return '\n\n'.join(rules[k].rstrip() for k in sorted(rules))
def compilation(compiler,dsl,origin):
    return {'status':'compiled' if compiler.get('ok') is True else 'not_verified','dsl':dsl,'dsl_hash':digest(dsl) if dsl else None,'origin':origin,'rule_count':compiler.get('rule_count'),'warnings':compiler.get('warnings',[])}
def evidence(row):
    return {'id':row['id'],'role':row.get('role','project'),'path':row.get('path'),'content_hash':row.get('content_hash',row.get('hash')),'read_verified':row.get('read_verified',False)}

def binding(task_id='',workspace='',session_id=''):
    if workspace:workspace=workspace.rstrip('/')
    with db.connect() as con:
        rows=[]
        for row in con.execute('SELECT m.task_id,m.state_json,t.name,t.workspace FROM managed_tasks m JOIN tasks t ON t.id=m.task_id ORDER BY m.updated_at DESC'):
            s=decode(row,'state_json')
            if task_id and row['task_id']!=task_id:continue
            if workspace and row['workspace']!=workspace:continue
            if session_id and s.get('session_id')!=session_id:continue
            if not (task_id or workspace or session_id) and s.get('phase') not in ('running','recovering','generating','prepared'):continue
            rows.append({'task_id':row['task_id'],'name':row['name'],'workspace':row['workspace'],'session_id':s.get('session_id'),'phase':s['phase'],'binding_declared':bool(s.get('binding'))})
    selected=rows[0] if len(rows)==1 else None
    if selected and selected['binding_declared']:
        live=workbench(selected['task_id']);selected['process_verified']=live['execution'].get('domain_verified') is True
        selected['effective']=live['effective']
    return {'status':'matched' if selected else 'ambiguous' if rows else 'unmatched','binding':selected,'candidates':rows,'authority':'registered_workspace_and_session_binding; no_browser_guess'}

def workbench(task_id):
    with db.connect() as con:state=c.load(con,task_id)
    try:execution=c.broker({'action':'status','task_id':task_id})
    except Exception:execution={'status':'unavailable'}
    effective=state['phase']=='running' and state['gate']=='open' and execution.get('status')=='running' and execution.get('domain_id')==state.get('binding',{}).get('domain_id')
    keys=('phase','gate','version','session_id','web_url','error','startup_proposal','pending_expansion','execution_role_version')
    return {'state':{k:state[k] for k in keys if k in state},'execution':{k:execution[k] for k in ('status','domain_id','domain_verified') if k in execution},'effective':effective}

def startup_records(con,task,s):
    rows=con.execute('SELECT * FROM bootstrap_proposals WHERE task_id=? ORDER BY created_at DESC',(task['id'],)).fetchall()
    if not rows:return []
    row=next((r for r in rows if r['id']==s.get('startup_proposal')),rows[0]);p=decode(row,'proposal_json');v=decode(row,'validation_json');draft=p.get('draft',{})
    sources={r['id']:dict(r) for r in con.execute('SELECT * FROM bootstrap_sources WHERE task_id=?',(task['id'],))}
    reads={decode(r,'input_json').get('source_id'):decode(r,'output_json').get('content_hash') for r in con.execute("SELECT input_json,output_json FROM bootstrap_tool_events WHERE job_id=? AND tool='read_policy_source'",(row['job_id'],))}
    loaded=s.get('startup_proposal')==row['id'] and s.get('version',0)>0
    status='revoked' if loaded and s['phase']=='ended' else 'active' if loaded and s['phase']=='running' else 'paused' if loaded else row['state']
    records=[]
    for i,atom in enumerate(draft.get('atoms',[])):
        ev=[evidence({**sources[sid],'read_verified':reads.get(sid)==sources[sid]['content_hash']}) for sid in atom['evidence_ids'] if sid in sources]
        dsl=clean_dsl(v.get('compiler',{}),{'bootstrap-'+str(i+1)})
        required=any(e['role'] in ('asset','environment') for e in ev)
        records.append({'id':f"startup:{row['id']}:atom:{i}",'stage':'startup','statement':atom['statement'],'policy_type':'per_event','effect':'block','operations':atom['operations'],'targets':atom['paths'],'context_required':required,'context_scope':'project' if required else 'task','context_reason':'绑定当前工作区中的实际对象及来源哈希' if required else '由任务与平台条款直接确定','classification_origin':'validated_atom_and_evidence_roles','origin':atom['decision'],'status':status,'created_at':row['created_at'],'trigger':{'name':HOOKS['startup']['name'],'job_id':row['job_id'],'events':HOOKS['startup']['events']},'evidence':ev,'explanation':atom['reason'],'compilation':compilation(v.get('compiler',{}),dsl,'compiler_rule_source'),'loading':{'loaded':loaded,'version':1 if loaded else None,'baseline_retained':loaded,'session_id':s.get('session_id'),'binding':s.get('binding') if loaded else None}})
    for i,text in enumerate(draft.get('guidance',[])):
        records.append({'id':f"startup:{row['id']}:guide:{i}",'stage':'startup','statement':text,'policy_type':'semantic_only','effect':'guidance','operations':[],'targets':[],'context_required':True,'context_scope':'task','context_reason':'需结合原始任务和平台语义要求理解','classification_origin':'validated_guidance','origin':'guidance','status':'guidance','created_at':row['created_at'],'trigger':{'name':HOOKS['startup']['name'],'job_id':row['job_id']},'evidence':[],'explanation':'任务指导不生成 OS 执行规则','compilation':{'status':'not_applicable','dsl':'','origin':'semantic_guidance'},'loading':{'loaded':False}})
    return records

def runtime_record(con,task,s,row):
    p=decode(row,'proposal_json');ctx=decode(row,'context_json');decision=p.get('decision')
    resolved=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='request_resolved' AND event_key=?",(task['id'],row['id'])).fetchone();receipt=decode(resolved,'payload_json')
    applied=decision in ('restrict','expand') and bool(receipt)
    before=ctx.get('base_snapshot',{}).get('payload',{})
    retained=[]
    added=set(p.get('protected_paths',[]))-set(before.get('protected_paths',[]))
    removed=set(before.get('protected_paths',[]))-set(p.get('protected_paths',[]))
    if added:retained.append(added<=set(s.get('runtime_protected',[])))
    if removed:retained.append(not removed&set(s.get('runtime_protected',[])))
    if p.get('allowed_write_dirs')!=before.get('allowed_write_dirs'):retained.append(p.get('allowed_write_dirs')==s.get('allowed_write_dirs'))
    if p.get('allow_output')!=before.get('allow_output'):retained.append(p.get('allow_output')==s.get('allow_output'))
    same=bool(retained) and all(retained)
    status='revoked' if applied and s['phase']=='ended' else 'active' if applied and same and s['phase']=='running' else 'paused' if applied and same else 'partially_active' if applied and any(retained) and s['phase']=='running' else 'superseded' if applied else 'pending_confirmation' if (s.get('pending_expansion') or {}).get('job_id')==row['id'] else 'needs_clarification' if p.get('unresolved_requests') else 'assessed' if decision in ('no_change','guidance_only') else 'expired'
    source=next((x.get('content',{}) for x in ctx.get('sources',[]) if x['evidence_id']==ctx.get('request_evidence_id')),{});actor=source.get('actor','native_user')
    native=ctx.get('native_execution_context',{})
    dispatched=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='request' AND id=?",(task['id'],ctx.get('request_evidence_id'))).fetchone()
    dispatch=decode(dispatched,'payload_json')
    trigger={'name':{'native_context':'原生上下文变化','kernel':'ActPlane 拒绝反馈','verified_feedback':'误拦截复核','recovery':'原生会话恢复','control_review':'控制面复核','native_user':'真实用户消息','user':'管理员约束','DSH':'执行能力申请'}.get(actor,actor),'actor':actor,'request_id':ctx.get('request_evidence_id'),'job_id':row['id'],'revision':row['revision'],'turn':dispatch.get('dispatched_turn',source.get('turn')),'accepted_turn':source.get('turn'),'observations':[{'category':v['category'],'type':v['type'],'seq':v['seq'],'content_hash':v['content_hash']} for v in native.values()]}
    before=ctx.get('base_snapshot',{}).get('payload',{});delta={'added_protection':sorted(set(p.get('protected_paths',[]))-set(before.get('protected_paths',[]))),'removed_protection':sorted(set(before.get('protected_paths',[]))-set(p.get('protected_paths',[]))),'write_scope_before':before.get('allowed_write_dirs'),'write_scope_after':p.get('allowed_write_dirs'),'output_before':before.get('allow_output'),'output_after':p.get('allow_output')}
    ev=[]
    for sid in p.get('evidence_ids',[]):
        if sid.startswith('project:'):
            project=next((x for x in ctx.get('project_sources',[]) if x['id']==sid[8:]),None)
            if project:
                read=con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='pi_source' AND event_key=?",(task['id'],row['id']+':'+project['id'])).fetchone();ev.append(evidence({**project,'id':sid,'role':'project','read_verified':bool(read)}))
        else:ev.append({'id':sid,'role':'event','read_verified':bool(con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='pi_read' AND event_key=?",(task['id'],row['id'])).fetchone())})
    statements=p.get('identified_statements',[])
    if not statements:
        # Historical records lack a model statement field. Preserve exact source
        # clauses for changed targets and explicitly label the provenance.
        quotes=[b['quote'] for target in delta['added_protection'] for b in ctx.get('capabilities',{}).get('authorized_protection_targets',{}).get(target,[]) if b['request_id'] in p.get('evidence_ids',[])]
        statements=[{'statement':q,'context_required':True,'context_reason':'已读取项目来源确定实际保护对象','policy_type':'per_event','evidence_ids':p.get('evidence_ids',[]),'origin':'authenticated_target_clause'} for q in dict.fromkeys(quotes)]
    text=statements[0]['statement'] if statements else source.get('text') if actor in ('native_user','user','administrator') else None
    if not text:text={'no_change':'本轮上下文无需调整 OS 策略','guidance_only':'本轮更新任务指导，保持 OS 策略','expand':'任务执行权限扩展候选','restrict':'任务执行权限收紧候选'}.get(decision,'Pi 正在评估')
    comp=p.get('compile',{});full=p.get('compiled_dsl')
    if full and p.get('compiled_dsl_hash')!=digest(full):raise ValueError('Persisted compiled DSL hash mismatch')
    # Keep full-bundle integrity verification internal. A record never exports it.
    scoped=compilation({},'', 'assessment_no_rule')
    scoped.update(status='not_applicable',message='这是评估记录，没有逐句登记的 OS 规则。',has_new_os_rule=False)
    return {'id':'runtime:'+row['id'],'stage':'runtime','statement':text,'identified_statements':statements,'policy_type':'per_event' if decision in ('restrict','expand') else 'semantic_only' if decision=='guidance_only' else 'assessment','effect':decision,'context_required':True,'context_scope':'task','context_reason':'评估冻结任务、现行策略、运行上下文与已读取项目证据','classification_origin':'validated_snapshot_delta; historical_source_clause_when_available','status':status,'created_at':row['created_at'],'trigger':trigger,'evidence':ev,'explanation':p.get('explanation'),'delta':delta,'targets':delta['added_protection']+delta['removed_protection'],'operations':['write','unlink'] if decision in ('restrict','expand') else [],'compilation':scoped,'loading':{'loaded':applied,'version':receipt.get('version'),'confirmation':receipt.get('confirmation'),'session_id':s.get('session_id'),'candidate_hash':p.get('hash'),'baseline_hash':ctx.get('baseline',{}).get('hash')}}

def mentions(text,path):
    # Match an actual registered path token, not a filename suffix or another file.
    return bool(re.search(r'(?<![A-Za-z0-9_./-])'+re.escape(path)+r'(?![A-Za-z0-9_./-])',text))


def statement_targets(statement,parent,ctx,task):
    if statement.get('policy_type')=='semantic_only':return []
    text=statement['statement'];ids=set(statement.get('evidence_ids',[]));targets=set()
    for source in ctx.get('project_sources',[]):
        if 'project:'+source['id'] in ids and mentions(text,source['id']):targets.add(source['path'])
    for path,receipts in ctx.get('capabilities',{}).get('authorized_protection_targets',{}).items():
        if any(r['request_id'] in ids and (r['quote']==text or mentions(text,path)) for r in receipts):targets.add(task['workspace']+'/'+path)
    for path in parent['delta']['added_protection']+parent['delta']['removed_protection']:
        if mentions(text,path):targets.add(task['workspace']+'/'+path)
    if statement.get('origin')=='authenticated_delta_request':
        if parent['delta']['output_before']!=parent['delta']['output_after']:targets.add(task['output_dir']+'/**')
        if parent['delta']['write_scope_before']!=parent['delta']['write_scope_after']:targets.add(task['workspace']+'/**')
    return sorted(targets)


def statement_compilation(compiler,targets,policy_type,decision):
    if policy_type=='semantic_only':return {'status':'not_applicable','dsl':'','origin':'semantic_guidance','message':'该语句属于语义指导，不生成 OS DSL。','has_new_os_rule':False}
    matched=[r for r in compiler.get('rules',[]) if r.get('target_pattern') in targets and r.get('clause_text')]
    groups={}
    for rule in matched:
        key=(rule.get('source_start_line',0),rule['name']);group=groups.setdefault(key,{'clauses':{},'reason':rule.get('reason')})
        group['clauses'][rule.get('clause_start_line',0)]=rule['clause_text']
    fragments=[]
    for key in sorted(groups):
        group=groups[key];lines=['rule '+key[1]+':']+[group['clauses'][line] for line in sorted(group['clauses'])]
        if group['reason']:lines.append('  because '+c.quote_dsl(group['reason']))
        fragments.append('\n'.join(lines))
    dsl='\n\n'.join(fragments)
    if dsl:
        return {'status':'compiled' if compiler.get('ok') is True else 'not_verified','dsl':dsl,'dsl_hash':digest(dsl),'origin':'statement_compiler_clauses','rule_count':len(matched),'reused':decision in ('no_change','guidance_only'),'has_new_os_rule':decision in ('restrict','expand'),'clause_refs':[{'name':r['name'],'target':r['target_pattern'],'clause_start_line':r.get('clause_start_line'),'clause_hash':r.get('clause_hash')} for r in matched]}
    permission=decision=='expand' and bool(targets)
    return {'status':'not_applicable' if permission else 'not_recorded','dsl':'','origin':'permission_update' if permission else 'unmapped_statement','has_new_os_rule':False,'message':'该语句对应权限授予或解除限制，没有新增拒绝 DSL。' if permission else '未登记该语句与编译子句的可靠关联，不展示其他策略。'}


def runtime_statement_records(con,task,state,row,include_assessments=False):
    parent=runtime_record(con,task,state,row);ctx=decode(row,'context_json');proposal=decode(row,'proposal_json')
    statements=parent['identified_statements']
    if not statements and parent['effect'] in ('restrict','expand'):
        source=next((x.get('content',{}) for x in ctx.get('sources',[]) if x['evidence_id']==ctx.get('request_evidence_id')),{})
        if source.get('actor') in ('native_user','user','administrator') and source.get('text'):
            statements=[{'statement':source['text'],'policy_type':'per_event','context_required':True,'context_reason':'历史认证请求与实际权限增量关联，未追补 Pi 逐句识别。','evidence_ids':proposal.get('evidence_ids',[]),'origin':'authenticated_delta_request'}]
    if not statements:return [parent] if include_assessments else []
    result=[]
    for i,statement in enumerate(statements):
        targets=statement_targets(statement,parent,ctx,task)
        compiled=statement_compilation(proposal.get('compile',{}),targets,statement['policy_type'],parent['effect'])
        evidence_ids=set(statement.get('evidence_ids',[]))
        semantic=statement['policy_type']=='semantic_only'
        delta={}
        if not semantic:
            for field in ('added_protection','removed_protection'):
                relevant=[path for path in parent['delta'][field] if task['workspace']+'/'+path in targets]
                if relevant:delta[field]=relevant
            if task['output_dir']+'/**' in targets and parent['delta']['output_before']!=parent['delta']['output_after']:
                delta.update(output_before=parent['delta']['output_before'],output_after=parent['delta']['output_after'])
            if task['workspace']+'/**' in targets and parent['delta']['write_scope_before']!=parent['delta']['write_scope_after']:
                delta.update(write_scope_before=parent['delta']['write_scope_before'],write_scope_after=parent['delta']['write_scope_after'])
        loading={**parent['loading'],'loaded':parent['loading']['loaded'] and (bool(compiled['dsl']) or compiled['origin']=='permission_update')}
        status='guidance' if semantic else 'unmapped' if compiled['status']=='not_recorded' and parent['status'] in ('active','partially_active') else parent['status']
        result.append({**parent,'effect':'guidance' if semantic else parent['effect'],'status':status,'loading':loading,'delta':delta or None,'id':parent['id']+':statement:'+str(i),'statement':statement['statement'],'policy_type':statement['policy_type'],'context_required':statement['context_required'],'context_reason':statement['context_reason'],'classification_origin':statement.get('origin','pi_statement'),'targets':targets,'operations':sorted({r.get('clause_op') for r in proposal.get('compile',{}).get('rules',[]) if r.get('target_pattern') in targets and r.get('clause_op')}) if compiled['dsl'] else [],'identified_statements':[],'evidence':[e for e in parent['evidence'] if e['id'] in evidence_ids],'compilation':compiled})
    return result


def records(task_id,stage='startup',before=None,include_assessments=False):
    with db.connect() as con:
        state=c.load(con,task_id);task=c.task_row(con,task_id)
        if stage=='startup':items=startup_records(con,task,state);cursor=None
        else:
            boundary=None;offset=-1
            if before is not None:
                parts=str(before).split(':')
                if not all(p.isdigit() for p in parts) or len(parts)>2:raise ValueError('Invalid record cursor')
                boundary=int(parts[0]);offset=int(parts[1]) if len(parts)>1 else 10**6
            items=[];cursors=[];first=True
            while len(items)<13:
                predicate="task_id=? AND proposal_json IS NOT NULL AND status='completed'";args=[task_id]
                if boundary is not None:predicate+=' AND rowid<=?';args.append(boundary)
                rows=con.execute('SELECT rowid AS cursor,* FROM managed_jobs WHERE '+predicate+' ORDER BY rowid DESC LIMIT 32',args).fetchall()
                if not rows:break
                for row in rows:
                    children=runtime_statement_records(con,task,state,row,include_assessments)
                    for index,item in enumerate(children):
                        if first and row['cursor']==boundary and index<=offset:continue
                        items.append(item);cursors.append(str(row['cursor'])+':'+str(index))
                        if len(items)==13:break
                    if len(items)==13:break
                if len(items)==13:break
                boundary=rows[-1]['cursor']-1;first=False
            cursor=cursors[11] if len(items)>12 else None;items=items[:12]
        compact=[{k:v for k,v in record.items() if k not in ('evidence','explanation','compilation','loading','delta','identified_statements')}|{'compile_status':record['compilation']['status'],'loaded':record['loading'].get('loaded',False),'version':record['loading'].get('version')} for record in items]
        counts={r[0]:r[1] for r in con.execute("SELECT json_extract(proposal_json,'$.decision'),count(*) FROM managed_jobs WHERE task_id=? AND status='completed' AND proposal_json IS NOT NULL GROUP BY json_extract(proposal_json,'$.decision')",(task_id,))}
    return {'stage':stage,'records':compact,'next_cursor':cursor,'counts':counts,'hook':HOOKS[stage]}


def detail(task_id,record_id):
    with db.connect() as con:
        state=c.load(con,task_id);task=c.task_row(con,task_id)
        if record_id.startswith('startup:'):
            record=next((r for r in startup_records(con,task,state) if r['id']==record_id),None)
        elif record_id.startswith('runtime:'):
            job_id=record_id[8:].split(':statement:')[0]
            row=con.execute('SELECT * FROM managed_jobs WHERE task_id=? AND id=? AND proposal_json IS NOT NULL',(task_id,job_id)).fetchone()
            children=runtime_statement_records(con,task,state,row,True) if row else []
            record=next((r for r in children if r['id']==record_id),None)
            if row and record_id=='runtime:'+job_id:record=children[0] if len(children)==1 else runtime_record(con,task,state,row)
        else:record=None
    if not record:raise ValueError('策略记录不属于当前任务')
    return record


def execution_audit(task_id,category='os',before=None):
    kinds={'os':('kernel','operation_verified'),'tools':('tool_start','tool_result'),'control':('control_pause','failure','feedback_delivery','policy_active','closed')}
    with db.connect() as con:
        state=c.load(con,task_id);task=c.task_row(con,task_id);ks=kinds[category]
        domain_versions={b['domain_id']:b['version'] for b in state.get('binding_history',[])}
        predicate='task_id=? AND kind IN ('+','.join('?' for _ in ks)+')';args=[task_id,*ks]
        if before:predicate+=' AND id<?';args.append(before)
        rows=con.execute('SELECT * FROM managed_events WHERE '+predicate+' ORDER BY id DESC LIMIT 51',args).fetchall()
        result=[]
        for row in rows[:50]:
            p=decode(row,'payload_json');kind=row['kind'];raw=p.get('event',{}) if kind=='kernel' else p.get('probe',{}) if kind=='operation_verified' else p
            start={}
            if category=='tools' and p.get('call_id'):
                start_row=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='tool_start' AND event_key=?",(task_id,p['call_id'])).fetchone();start=decode(start_row,'payload_json')
            result.append({'id':row['id'],'category':category,'kind':kind,'time':row['occurred_at'],'operation':raw.get('op',raw.get('operation',raw.get('name',kind))),'target':raw.get('target',p.get('target',start.get('target'))),'result':'denied' if kind=='kernel' else p.get('classification') if kind=='operation_verified' else 'success' if p.get('succeeded') is True else 'failure' if p.get('succeeded') is False else 'started' if kind=='tool_start' else kind,'source':'independent_probe' if p.get('verification_probe') or p.get('native_sdk_verification') or start.get('verification_probe') or start.get('native_sdk_verification') or kind=='operation_verified' else 'native_tool' if category=='tools' else 'kernel' if kind=='kernel' else 'controller','call_id':p.get('tool_call_id',p.get('call_id')),'pid':raw.get('pid',p.get('pid')),'domain_id':raw.get('process_domain_id',p.get('domain_id',start.get('domain_id'))),'version':p.get('version',start.get('started',{}).get('version',domain_versions.get(p.get('domain_id')))),'reason':p.get('reason',p.get('error')) or raw.get('rule',{}).get('reason') if isinstance(raw.get('rule',{}),dict) else p.get('reason'),'rule':raw.get('rule') if kind=='kernel' else None,'feedback_event_ids':p.get('event_ids',[])})
    return {'records':result,'category':category,'next_cursor':rows[49]['id'] if len(rows)>50 else None,'coverage':'kernel denials and independently verified effects; successful tools are not proof of OS allow'}
