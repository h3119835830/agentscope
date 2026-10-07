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
            for i,_ in enumerate(a.decode(row['proposal_json']).get('identified_statements',[])):
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
            for key in ('compilation','loading','reviews','review_status','version','candidate_status','candidate_hash','proposal','operations','targets'):out[key]=candidates[0].get(key)
        return out
    if ref['source']=='policy_versions':
        row=con.execute('SELECT * FROM policy_versions WHERE id=? AND task_id=?',(ref['key'],tid)).fetchone()
        out=base_record(ident,'version','startup',None,row['created_at'],row['status'])
        out.update(version=row['version'],candidate_status=row['status'],statement='策略版本 '+str(row['version']),review_status='not_recorded',compilation={'status':row['compile_state'],'dsl':row['dsl_text'],'origin':'stored_policy_version'},loading=loading(con,tid,version=row['version']),statements=[])
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
    if ident==out['id']:return out
    child=next((x for x in out['statements'] if x['id']==ident),None)
    if child is None:raise HTTPException(404,'Historical statement material unavailable')
    return child


def policy_records(task_id,stage='startup',before=None,limit=50):
    if stage not in ('startup','runtime') or not 1<=limit<=200:raise HTTPException(422,'Invalid policy query')
    with db.connect() as con:
        con.execute('PRAGMA query_only=ON')
        task=a.require_task(con,task_id);s=state(con,task_id);all_refs=refs(con,task_id,stage)
        jobs={r['key'] for r in all_refs if r['source']=='history_jobs'}
        candidate_jobs={r['id']:r['job_id'] for r in con.execute('SELECT id,job_id FROM bootstrap_proposals WHERE task_id=?',(task_id,))}
        items=[r for r in all_refs if r['kind']!='statement' and not (r['source']=='bootstrap_proposals' and candidate_jobs.get(r['key']) in jobs)]
        total=len(items)
        if before:
            time,ident=a.cursor_decode(before,task_id,'policies:'+stage)
            items=[x for x in items if (x['time'],x['id'])<(time,ident)]
        selected=items[:limit];records=[]
        for ref in selected:
            full=detail_from_ref(con,task,s,ref)
            compact={k:v for k,v in full.items() if k not in ('statements','candidates','proposal','compilation','loading','reviews','evidence','explanation','delta','normalization')}
            compact.update(compile_status=full['compilation']['status'],loaded=full['loading'].get('loaded',False))
            records.append(compact)
        cursor=a.cursor_encode(task_id,'policies:'+stage,selected[-1]) if len(items)>limit else None
    return a.safe(history({'task_id':task_id,'stage':stage,'records':records,'total':total,'next_cursor':cursor,**FLAGS}))


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
