"""Offline policy and audit views over the same authoritative task records."""
from fastapi import HTTPException
from .. import db
from ..managed import records as managed
from ..bootstrap.scene import digest
from . import projection as a

FLAGS={'history_only':True,'historical':True,'live':False}


def history(value):
    if isinstance(value,list):return [history(v) for v in value]
    if not isinstance(value,dict):return value
    result={k:history(v) for k,v in value.items()}
    for key in ('active','effective','live','live_verified'):
        if key in result:result[key]=False
    if 'loaded' in result or 'current_loading' in result:
        result.update(evidence_kind='stored_loading_receipt',live_verified=False,active=False)
    return result


def state(con,task_id):
    row=con.execute('SELECT state_json FROM managed_tasks WHERE task_id=?',(task_id,)).fetchone()
    return {'phase':'not_recorded','version':0,**a.decode(row[0] if row else None)}


def refs(con,task_id,stage):
    result=[]
    if stage=='startup':
        for row in con.execute("SELECT * FROM history_jobs WHERE kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=?",(task_id,)):
            result.append({'id':'startup_job:'+row['id'],'source':'history_jobs','key':row['id'],'kind':'job','time':row['created_at']})
        for row in con.execute('SELECT * FROM bootstrap_proposals WHERE task_id=?',(task_id,)):
            result.append({'id':'startup:'+row['id'],'source':'bootstrap_proposals','key':row['id'],'kind':'candidate','time':row['created_at']})
            draft=a.decode(row['proposal_json']).get('draft',{})
            for field,label in (('atoms','atom'),('guidance','guide')):
                for i,_ in enumerate(draft.get(field,[])):
                    result.append({'id':f"startup:{row['id']}:{label}:{i}",'source':'bootstrap_proposals','key':row['id'],'kind':'statement','time':row['created_at']})
        for row in con.execute('SELECT * FROM policy_versions WHERE task_id=? AND NOT EXISTS (SELECT 1 FROM bootstrap_versions b WHERE b.policy_version_id=policy_versions.id)',(task_id,)):
            result.append({'id':'version:'+row['id'],'source':'policy_versions','key':row['id'],'kind':'version','time':row['created_at']})
    else:
        for row in con.execute('SELECT * FROM managed_jobs WHERE task_id=?',(task_id,)):
            result.append({'id':'runtime:'+row['id'],'source':'managed_jobs','key':row['id'],'kind':'job','time':row['created_at']})
            count=len(a.decode(row['proposal_json']).get('identified_statements',[]))
            if row['proposal_json'] and not count:
                try:
                    generated=managed.runtime_statement_records(con,a.require_task(con,task_id),{'phase':'not_recorded','version':0},row,True,False)
                    count=len([r for r in generated if ':statement:' in r['id']])
                except (ValueError,KeyError,TypeError):pass
            for i in range(count):
                result.append({'id':f"runtime:{row['id']}:statement:{i}",'source':'managed_jobs','key':row['id'],'kind':'statement','time':row['created_at']})
    return sorted(result,key=lambda x:(x['time'],x['id']),reverse=True)


def reviews(con,task_id,job_id=None,proposal=None):
    result=[]
    for row in con.execute("SELECT * FROM managed_events WHERE task_id=? AND kind IN ('review_pending','change_review','candidate_invalidated','change_apply_failed','request_resolved','startup_review_required','startup_confirmed','startup_rejected') ORDER BY id",(task_id,)):
        p=a.decode(row['payload_json'])
        matched=(job_id is not None and (p.get('job_id')==job_id or (row['kind']=='request_resolved' and row['event_key']==job_id)))
        if proposal is not None:
            matched=matched or row['event_key']==proposal['id']
        if matched:result.append({'id':row['id'],'kind':row['kind'],'time':row['occurred_at'],**a.managed_detail(dict(row))})
    return result


def review_status(items):
    for item in reversed(items):
        if item['kind'] in ('change_review','startup_confirmed','startup_rejected'):
            return {'approve':'approved','reject':'rejected','clarify':'clarify'}.get(item.get('decision'),'approved' if item['kind']=='startup_confirmed' else 'rejected')
        if item['kind'] in ('review_pending','startup_review_required'):return 'pending'
    return 'not_recorded'


def loading(con,task_id,job_id=None,proposal=None,version=None):
    versions=[];resolutions=[]
    if job_id:
        for row in con.execute("SELECT * FROM managed_events WHERE task_id=? AND kind='request_resolved' AND event_key=?",(task_id,job_id)):
            p=a.decode(row['payload_json']);resolutions.append({'id':row['id'],'time':row['occurred_at'],**a.pick(p,'version','decision','confirmation','evidence_ids')})
            if p.get('decision') in ('restrict','expand') and isinstance(p.get('version'),int):versions.append(p['version'])
    if proposal:
        versions.extend(r[0] for r in con.execute('SELECT v.version FROM bootstrap_versions b JOIN policy_versions v ON v.id=b.policy_version_id AND v.task_id=? WHERE b.proposal_id=?',(task_id,proposal['id'])))
    if version is not None:versions.append(version)
    receipts=[]
    for row in con.execute("SELECT * FROM managed_events WHERE task_id=? AND kind='policy_active' ORDER BY id",(task_id,)):
        p=a.decode(row['payload_json'])
        if p.get('version') not in versions:continue
        receipts.append({'id':row['id'],'time':row['occurred_at'],**a.pick(p,'version','session_id','policy_hash','baseline_hash'),'binding':a.pick(p.get('binding',{}),'domain_id','runner_pid','watch_pid','session_id','executor'),'verification':a.pick(p.get('verification',{}),'passed')})
    # A resolution is a real load receipt even if an older installation lacks a
    # separately recorded policy_active event; it cannot supply a PID or domain.
    loaded=bool(receipts or any(r.get('decision') in ('restrict','expand') for r in resolutions))
    first=receipts[0] if receipts else resolutions[0] if loaded else {}
    return {'loaded':loaded,'version':first.get('version'),'session_id':first.get('session_id'),'binding':first.get('binding'),'receipts':receipts,'resolutions':resolutions,'status':'recorded' if loaded else 'not_recorded','evidence_kind':'stored_loading_receipt','live_verified':False,'active':False}


def statement_loading(record,ledger):
    if record.get('policy_type')=='semantic_only' or record.get('effect') in ('guidance','guidance_only'):
        return {'loaded':False,'version':ledger.get('version'),'status':'not_applicable','evidence_kind':'semantic_guidance','live_verified':False,'active':False,'bundle_receipt':ledger}
    compilation=record.get('compilation',{})
    if not compilation.get('dsl') and compilation.get('origin')!='permission_update':
        return {'loaded':False,'version':ledger.get('version'),'status':'mapping_not_recorded','evidence_kind':'stored_loading_receipt','live_verified':False,'active':False,'bundle_receipt':ledger}
    return ledger


def base_record(ident,kind,stage,job_id,when,status):
    return {'id':ident,'record_kind':kind,'stage':stage,'job_id':job_id,'created_at':when,'time':when,'status':status,'generation_status':status,'candidate_status':None,'review_status':'not_recorded','decision':None,'version':None,'statement':'启动策略生成' if stage=='startup' else '运行时策略评估','operations':[],'targets':[],'detail_available':True,**FLAGS}


def scoped_compilation(compiler,targets,names=None):
    """Compiler target-clause association, not model-level operation attribution."""
    rules=[r for r in compiler.get('rules',[]) if r.get('target_pattern') in targets and r.get('clause_text') and (names is None or r.get('name') in names)]
    scoped={**compiler,'rules':rules}
    result=managed.statement_compilation(scoped,targets,'per_event','restrict')
    result.update(scope='statement',mapping_scope='target',mapping_status='recorded' if result.get('dsl') else 'not_recorded',message='按已登记目标关联编译子句；不宣称模型逐操作精确归因。' if result.get('dsl') else '未登记该语句与编译子句的可靠关联。')
    result['has_new_os_rule']=False
    return result,rules


def previous_compiler(con,task,ctx):
    binding=ctx.get('current_binding',{});version=binding.get('version');expected=ctx.get('policy_hash')
    if type(version) is not int or not isinstance(expected,str):return None
    rows=con.execute('SELECT * FROM policy_versions WHERE task_id=? AND version IN (?,?)',(task['id'],version,10000+version)).fetchall()
    for row in rows:
        compiler=a.decode(row['compile_json'])
        if row['compile_state']=='compiled' and compiler.get('ok') is True and digest(row['policy_yaml'])==expected:
            return compiler
    return None


def clause_summary(rule):
    text=rule.get('clause_text','')
    return {'name':rule.get('name'),'operation':rule.get('clause_op'),'target':rule.get('target_pattern'),'clause_hash':rule.get('clause_hash') or digest(text),'dsl':'rule '+rule.get('name','not_recorded')+':\n'+text}


def output_permission(task,ctx,p,statement):
    before=ctx.get('base_snapshot',{}).get('payload',{}).get('allow_output');after=p.get('allow_output')
    if type(before) is not bool or type(after) is not bool or before==after:return None
    ids={str(v) for v in statement.get('evidence_ids',[])};text=statement.get('statement','')
    from pathlib import Path
    basename=Path(task['output_dir']).name
    import re
    pattern=r'(?<![A-Za-z0-9_./-])(?:'+re.escape(task['output_dir'])+'|'+re.escape(basename)+r')(?:/[A-Za-z0-9_.*/-]+)?(?![A-Za-z0-9_./-])'
    if not re.search(pattern,text):return None
    actual=[]
    for source in ctx.get('sources',[]):
        content=source.get('content',{})
        if str(source.get('evidence_id')) in ids and content.get('actor') in ('native_user','user','administrator') and isinstance(content.get('text'),str) and text in content['text']:
            actual.append(str(source['evidence_id']))
    if not actual:return None
    capability=next((c for c in ctx.get('capabilities',{}).get('execution_targets',[]) if c.get('kind')=='task_output' and c.get('path')==task['output_dir'] and c.get('authority')=='controller_verified_loaded_snapshot' and c.get('granted') is before and c.get('policy_version')==ctx.get('current_binding',{}).get('version') and c.get('policy_hash')==ctx.get('policy_hash')),None)
    if not capability:return None
    return {'allow_output_before':before,'allow_output_after':after,'target':task['output_dir']+'/**','source_evidence_ids':actual,'authority':capability['authority']}


def statement_projection(con,task,record,compiler,bundle,ctx=None,p=None,statement=None,names=None):
    ctx=ctx or {};p=p or {};statement=statement or {}
    record['bundle_compilation']={**bundle,'scope':'candidate_bundle'}
    record['parent_id']='runtime:'+record['job_id'] if record['stage']=='runtime' else 'startup:'+record['id'].split(':')[1]
    record['statement_effect']='not_recorded';record['change_status']='not_recorded'
    diff={'status':'not_recorded','before':'','after':'','removed_clauses':[],'added_clauses':[],'mapping_scope':'target','origin':'recorded_policy_versions_to_candidate_compile','message':'未记录可信的前态编译材料，不推断已移除或新增子句。'}
    if record.get('policy_type') in ('semantic_only','content') or record.get('effect')=='guidance':
        record.update(statement_effect='guidance',change_status='guidance',effect='guidance',operations=[],targets=[],delta=None)
        record['compilation']={'scope':'statement','status':'not_applicable','dsl':'','origin':'semantic_guidance','mapping_status':'not_applicable','has_new_os_rule':False,'message':'该语句属于内容或语义指导，不生成 OS DSL。'}
        diff.update(status='not_applicable',message='内容或语义指导没有 OS DSL 差异。')
    else:
        permission=output_permission(task,ctx,p,statement) if record['stage']=='runtime' else None
        if permission:
            record['permission_delta']=permission
            record['targets']=[permission['target']]
            record['delta']={'output_before':permission['allow_output_before'],'output_after':permission['allow_output_after']}
        targets=record.get('targets',[])
        comp,after_rules=scoped_compilation(compiler,targets,names)
        delta=record.get('delta') or {}
        if record['stage']=='startup':
            effect='restrict' if comp.get('dsl') else 'unmapped'
            change='added' if comp.get('dsl') else 'unmapped'
        elif permission:
            effect='expand' if permission['allow_output_after'] else 'restrict';change='permission_changed'
        elif delta.get('removed_protection'):
            effect='expand';change='removed'
        elif delta.get('added_protection'):
            effect='restrict';change='added'
        elif p.get('decision') in ('no_change','guidance_only') or comp.get('dsl'):
            effect='retained' if comp.get('dsl') else 'unmapped';change=effect
        else:effect='unmapped';change='unmapped'
        record.update(statement_effect=effect,change_status=change,effect=effect)
        comp['has_new_os_rule']=effect=='restrict' and change=='added' and bool(comp.get('dsl'))
        comp['reused']=effect=='retained' and bool(comp.get('dsl'))
        if effect=='expand':
            # Existing deny clauses in a rebuilt package are never new rules
            # generated by a removal/permission statement.
            comp.update(dsl='',status='not_applicable',origin='permission_update',has_new_os_rule=False,mapping_status='recorded_delta')
            comp.pop('fragments',None);comp.pop('clause_refs',None)
        record['compilation']=comp
        before=previous_compiler(con,task,ctx) if record['stage']=='runtime' else None
        if before is not None:
            old,before_rules=scoped_compilation(before,targets)
            key=lambda r:(r.get('target_pattern'),r.get('clause_op'),r.get('clause_hash') or digest(r.get('clause_text','')))
            oldkeys={key(r) for r in before_rules};newkeys={key(r) for r in after_rules}
            removed=[clause_summary(r) for r in before_rules if key(r) not in newkeys]
            added=[clause_summary(r) for r in after_rules if key(r) not in oldkeys]
            diff.update(status='recorded',before=old.get('dsl',''),after=managed.statement_compilation({**compiler,'rules':after_rules},targets,'per_event','restrict').get('dsl',''),removed_clauses=removed,added_clauses=added,message='同任务、同前态版本且包哈希核验一致的目标子句差异。')
        if p.get('decision') in ('no_change','guidance_only'):
            comp['has_new_os_rule']=False
        if effect=='unmapped':comp.update(status='not_recorded',dsl='',has_new_os_rule=False)
    record['dsl_diff']=diff
    record['loading']=statement_loading(record,record['loading'].get('bundle_receipt',record['loading']))
    return record


def candidate_detail(con,task,s,row):
    p=a.decode(row['proposal_json']);v=a.decode(row['validation_json'])
    # Reuse clause/source interpretation with loading disabled. Current state
    # binding/session must never be lent to this candidate's historical record.
    historical_state={**s,'startup_proposal':row['id'],'version':0,'binding':{},'session_id':None,'active_normalization':{}}
    verified=digest(p)==row['content_hash']
    try:children=managed.startup_records(con,task,historical_state,persist_links=False) if verified else []
    except (KeyError,TypeError,ValueError):children=[]
    ledger=loading(con,task['id'],proposal=row)
    items=reviews(con,task['id'],row['job_id'],row)
    out=base_record('startup:'+row['id'],'candidate','startup',row['job_id'],row['created_at'],row['state'])
    job=con.execute("SELECT status FROM history_jobs WHERE id=? AND kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=?",(row['job_id'],task['id'])).fetchone()
    out.update(generation_status=job[0] if job else 'not_recorded',candidate_status=row['state'],proposal_id=row['id'],candidate_hash=row['content_hash'],context_hash=row['context_hash'],statement=p.get('draft',{}).get('summary','启动策略候选'),decision='startup',review_status=review_status(items),reviews=items,loading=ledger,version=ledger['version'],proposal=a.proposal_projection(p))
    dsl=p.get('actplane_dsl',p.get('draft',{}).get('dsl_text','')) if verified else ''
    if not verified:
        out['material_status']='integrity_failed';out['proposal']={}
    out['compilation']={**managed.compilation(v.get('compiler',{}),dsl,'candidate_bundle'),'historical':True}
    if not verified:out['compilation']['status']='integrity_failed'
    for child in children:
        child.update(record_kind='statement',job_id=row['job_id'],generation_status=out['generation_status'],candidate_status=row['state'],review_status=out['review_status'],reviews=items,loading=statement_loading(child,ledger),status='guidance' if child.get('policy_type')=='semantic_only' else 'loaded_receipt' if ledger['loaded'] else row['state'],version=ledger['version'],decision='startup',time=child['created_at'],detail_available=True,**FLAGS)
        names=set()
        if ':atom:' in child['id']:
            number=int(child['id'].rsplit(':',1)[1])+1;names={'bootstrap-'+str(number)}
            report=v.get('normalization') or {}
            if report:
                names={name for e in report.get('clauses',[]) if e.get('name') in names for name in e.get('compiled_names',[])}
        statement_projection(con,task,child,v.get('compiler',{}),out['compilation'],names=names)
    out['bundle_compilation']={**out['compilation'],'scope':'candidate_bundle'}
    out['compilation']['scope']='candidate_bundle'
    out['statements']=children
    out['operations']=sorted({op for child in children for op in child.get('operations',[])})
    out['targets']=sorted({path for child in children for path in child.get('targets',[])})
    return out


def detail_from_ref(con,task,s,ref):
    tid=task['id'];ident=ref['id']
    if ref['source']=='bootstrap_proposals':
        row=con.execute('SELECT * FROM bootstrap_proposals WHERE id=? AND task_id=?',(ref['key'],tid)).fetchone()
        parent=candidate_detail(con,task,s,row)
        if ident==parent['id']:return parent
        child=next((x for x in parent['statements'] if x['id']==ident),None)
        if child is None:raise HTTPException(404,'Historical statement material unavailable')
        return child
    if ref['source']=='history_jobs':
        row=con.execute("SELECT * FROM history_jobs WHERE id=? AND kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=?",(ref['key'],tid)).fetchone()
        out=base_record(ident,'job','startup',row['id'],row['created_at'],row['status'])
        candidates=[candidate_detail(con,task,s,p) for p in con.execute('SELECT * FROM bootstrap_proposals WHERE task_id=? AND job_id=? ORDER BY created_at,id',(tid,row['id']))]
        out.update(candidates=candidates,statements=[x for p in candidates for x in p['statements']],error='generation_failed' if row['status']=='failed' else None,started_at=row['started_at'],finished_at=row['finished_at'],loading={'loaded':False,'evidence_kind':'stored_loading_receipt','active':False,'live_verified':False},compilation={'status':'not_recorded','dsl':'','origin':'no_candidate'})
        if len(candidates)==1:
            for key in ('compilation','loading','reviews','review_status','version','candidate_status','candidate_hash','proposal','operations','targets','bundle_compilation'):out[key]=candidates[0].get(key)
        out['compilation']['scope']='candidate_bundle'
        out.setdefault('bundle_compilation',dict(out['compilation']))
        return out
    if ref['source']=='policy_versions':
        row=con.execute('SELECT * FROM policy_versions WHERE id=? AND task_id=?',(ref['key'],tid)).fetchone()
        out=base_record(ident,'version','startup',None,row['created_at'],row['status'])
        out.update(version=row['version'],candidate_status=row['status'],statement='策略版本 '+str(row['version']),review_status='not_recorded',compilation={'status':row['compile_state'],'dsl':row['dsl_text'],'origin':'stored_policy_version'},loading=loading(con,tid,version=row['version']),statements=[])
        out['compilation']['scope']='candidate_bundle';out['bundle_compilation']=dict(out['compilation'])
        return out
    row=con.execute('SELECT * FROM managed_jobs WHERE id=? AND task_id=?',(ref['key'],tid)).fetchone();p=a.decode(row['proposal_json'])
    out=base_record('runtime:'+row['id'],'job','runtime',row['id'],row['created_at'],row['status'])
    items=reviews(con,tid,row['id']);ledger=loading(con,tid,job_id=row['id'])
    lifecycle=next((r for r in reversed(items) if r['kind'] in ('candidate_invalidated','change_apply_failed','change_review','review_pending','request_resolved')),None)
    candidate_status=('invalidated' if lifecycle['kind']=='candidate_invalidated' else 'apply_failed' if lifecycle['kind']=='change_apply_failed' else lifecycle.get('decision','recorded') if lifecycle['kind']=='change_review' else 'pending' if lifecycle['kind']=='review_pending' else 'applied' if lifecycle.get('decision') in ('restrict','expand') else 'assessed') if lifecycle else 'recorded' if p else 'not_recorded'
    out.update(decision=p.get('decision'),candidate_hash=p.get('hash'),candidate_status=candidate_status,review_status=review_status(items),reviews=items,loading=ledger,version=ledger['version'],error='generation_failed' if row['status']=='failed' else None,proposal=a.proposal_projection(p),statements=[])
    if p:
        parent={}
        try:
            historical_state={**s,'active_normalization':{}}
            parent=managed.runtime_record(con,task,historical_state,row)
            children=managed.runtime_statement_records(con,task,historical_state,row,include_assessments=True,persist_links=False)
        except (ValueError,KeyError,TypeError):
            # An integrity failure is visible and never exports its DSL.
            children=[];out['material_status']='integrity_failed'
        for child in children:
            child.update(record_kind='statement' if ':statement:' in child['id'] else 'job',job_id=row['id'],generation_status=row['status'],candidate_status=candidate_status,review_status=out['review_status'],reviews=items,loading=statement_loading(child,ledger),status=row['status'],version=ledger['version'],decision=p.get('decision'),time=child['created_at'],detail_available=True,**FLAGS)
        out['statements']=[x for x in children if x['id']!=out['id']]
        if parent:
            for key in ('statement','policy_type','effect','context_required','context_scope','context_reason','classification_origin','trigger','evidence','explanation','delta','targets','operations','process_generation','base_version','base_policy_hash'):out[key]=parent.get(key)
        full=p.get('compiled_dsl','');verified=not full or p.get('compiled_dsl_hash')==managed.digest(full)
        out['compilation']={**managed.compilation(p.get('compile',{}),full if verified else '','candidate_bundle'),'status':'integrity_failed' if not verified else 'compiled' if p.get('compile',{}).get('ok') is True else 'not_recorded'}
        if not verified:
            out['proposal'].pop('compiled_dsl',None);out['proposal'].pop('compile',None)
    else:out['compilation']={'status':'not_recorded','dsl':'','origin':'no_candidate'}
    out['compilation']['scope']='candidate_bundle';out['bundle_compilation']=dict(out['compilation'])
    for index,child in enumerate(out['statements']):
        raw_statement=p.get('identified_statements',[])
        raw_statement=raw_statement[index] if index<len(raw_statement) else {'statement':child.get('statement',''),'evidence_ids':[e['id'] for e in child.get('evidence',[])]}
        statement_projection(con,task,child,p.get('compile',{}),out['compilation'],a.decode(row['context_json']),p,raw_statement)
    if ident==out['id']:return out
    child=next((x for x in out['statements'] if x['id']==ident),None)
    if child is None:raise HTTPException(404,'Historical statement material unavailable')
    return child


def policy_records(task_id,stage='startup',before=None,limit=50,view='jobs'):
    if stage not in ('startup','runtime') or view not in ('jobs','statements') or not 1<=limit<=200:raise HTTPException(422,'Invalid policy query')
    with db.connect() as con:
        con.execute('PRAGMA query_only=ON')
        task=a.require_task(con,task_id);s=state(con,task_id);all_refs=refs(con,task_id,stage)
        jobs={r['key'] for r in all_refs if r['source']=='history_jobs'}
        candidate_jobs={r['id']:r['job_id'] for r in con.execute('SELECT id,job_id FROM bootstrap_proposals WHERE task_id=?',(task_id,))}
        items=[r for r in all_refs if r['kind']!='statement' and not (r['source']=='bootstrap_proposals' and candidate_jobs.get(r['key']) in jobs)]
        if view=='statements':
            children=[r for r in all_refs if r['kind']=='statement']
            child_owners={r['key'] for r in children}
            candidate_owners={candidate_jobs.get(r['key']) for r in children if r['source']=='bootstrap_proposals'}
            placeholders=[]
            for r in items:
                owner_has_children=r['key'] in child_owners or (r['source']=='history_jobs' and r['key'] in candidate_owners)
                failed=False
                if r['kind']=='job':
                    table='history_jobs' if r['source']=='history_jobs' else 'managed_jobs'
                    row=con.execute('SELECT status FROM '+table+' WHERE id=?',(r['key'],)).fetchone()
                    failed=row and row[0] in ('failed','cancelled','interrupted','rejected','stale')
                if not owner_has_children or failed:placeholders.append(r)
            items=sorted(children+placeholders,key=lambda r:(r['time'],r['id']),reverse=True)
        total=len(items)
        if before:
            time,ident=a.cursor_decode(before,task_id,'policies:'+stage+(':'+view if view!='jobs' else ''))
            items=[x for x in items if (x['time'],x['id'])<(time,ident)]
        selected=items[:limit];records=[]
        for ref in selected:
            try:full=detail_from_ref(con,task,s,ref)
            except HTTPException as error:
                if error.status_code!=404 or ref['kind']!='statement':raise
                row=con.execute('SELECT job_id FROM bootstrap_proposals WHERE id=? AND task_id=?',(ref['key'],task_id)).fetchone() if stage=='startup' else None
                job_id=row['job_id'] if row else ref['key']
                full=base_record(ref['id'],'statement',stage,job_id,ref['time'],'not_recorded')
                full.update(statement='策略语句材料不可用',parent_id=('startup_job:' if stage=='startup' else 'runtime:')+job_id,material_status='unavailable',detail_available=False,statement_effect='not_recorded',change_status='not_recorded',compilation={'scope':'statement','status':'not_recorded','dsl':'','origin':'material_unavailable'},loading={'loaded':False})
            compact={k:v for k,v in full.items() if k not in ('statements','candidates','proposal','compilation','loading','reviews','evidence','explanation','delta','normalization','bundle_compilation','dsl_diff')}
            compact.update(compile_status=full['compilation']['status'],compilation_scope=full['compilation'].get('scope'),compilation={k:v for k,v in full['compilation'].items() if k in ('scope','status','origin','mapping_scope','mapping_status','reused','has_new_os_rule')},loaded=full['loading'].get('loaded',False))
            records.append(compact)
        cursor=a.cursor_encode(task_id,'policies:'+stage+(':'+view if view!='jobs' else ''),selected[-1]) if len(items)>limit else None
    return a.safe(history({'task_id':task_id,'stage':stage,'view':view,'records':records,'total':total,'next_cursor':cursor,**FLAGS}))


def policy_detail(task_id,record_id):
    with db.connect() as con:
        con.execute('PRAGMA query_only=ON')
        task=a.require_task(con,task_id);s=state(con,task_id)
        ref=next((x for stage in ('startup','runtime') for x in refs(con,task_id,stage) if x['id']==record_id),None)
        if not ref:raise HTTPException(404,'Policy record does not belong to this task')
        result=detail_from_ref(con,task,s,ref)
    return a.safe(history({**result,'task_id':task_id,**FLAGS}))


def execution_audit(task_id,category='os',before=None):
    if category not in ('os','tools','control'):raise HTTPException(422,'Invalid audit category')
    with db.connect() as con:
        a.require_task(con,task_id)
        has_state=con.execute('SELECT 1 FROM managed_tasks WHERE task_id=?',(task_id,)).fetchone()
    if not has_state:
        return {'task_id':task_id,'records':[],'category':category,'next_cursor':None,'status':'not_recorded','coverage':'kernel denials and independently verified effects; successful tools are not proof of OS allow',**FLAGS}
    result=managed.execution_audit(task_id,category,before)
    # Retain event identity and provenance; storage table is not the executor.
    with db.connect() as con:
        for row in result['records']:
            event=con.execute('SELECT payload_json FROM managed_events WHERE task_id=? AND id=?',(task_id,row['id'])).fetchone()
            payload=a.decode(event[0] if event else None);raw=payload.get('event',{}) if row['kind']=='kernel' else payload.get('probe',{}) if row['kind']=='operation_verified' else payload
            if category=='tools' and not row.get('target') and row.get('call_id'):
                start=con.execute("SELECT id,payload_json FROM managed_events WHERE task_id=? AND kind='tool_start' AND event_key=? ORDER BY id DESC LIMIT 1",(task_id,row['call_id'])).fetchone()
                target=a.decode(start['payload_json']).get('target') if start else None
                if target:
                    row.update(target=target,target_evidence_event_id=start['id'])
            row.update(task_id=task_id,event_id=row['id'],detail_id='managed_events:'+str(row['id'])+':record',detail_available=True,action_source=row['source'],process_domain_id=raw.get('process_domain_id',payload.get('domain_id')),rule_domain_id=raw.get('domain_id') if row['kind']=='kernel' else None,**FLAGS)
            if row['kind']=='kernel':
                row['domain_id']=row['process_domain_id']
                row['rule']=a.kernel_projection(raw).get('rule')
            for key in ('verification_probe','native_sdk_verification'):
                if isinstance(payload.get(key),bool):row[key]=payload[key]
    return a.safe(history({**result,'task_id':task_id,**FLAGS}))
