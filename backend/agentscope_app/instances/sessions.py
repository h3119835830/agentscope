"""Native session directory and independently sourced kernel/tool projections."""
import json
import threading
from .. import db
from ..broker_client import call as broker
from . import store,dsl_policy
from .session_names import with_session_names

SCHEMA='''
CREATE TABLE IF NOT EXISTS instance_session_cache(instance_id TEXT NOT NULL,session_id TEXT NOT NULL,
 metadata_json TEXT NOT NULL,generation TEXT,observed_at TEXT NOT NULL,PRIMARY KEY(instance_id,session_id));
CREATE TABLE IF NOT EXISTS instance_kernel_cursors(instance_id TEXT NOT NULL,generation TEXT NOT NULL,
 cursor_json TEXT NOT NULL,PRIMARY KEY(instance_id,generation));
CREATE TABLE IF NOT EXISTS instance_kernel_events(id INTEGER PRIMARY KEY AUTOINCREMENT,instance_id TEXT NOT NULL,
 generation TEXT NOT NULL,source_key TEXT NOT NULL,bundle_hash TEXT,domain_id INTEGER,event_json TEXT NOT NULL,
 created_at TEXT NOT NULL,UNIQUE(instance_id,generation,source_key));
CREATE INDEX IF NOT EXISTS instance_kernel_by_generation ON instance_kernel_events(instance_id,generation,id);
CREATE TABLE IF NOT EXISTS instance_session_task_bindings(instance_id TEXT NOT NULL,generation TEXT NOT NULL,
 session_id TEXT NOT NULL,task_id TEXT NOT NULL,managed_session_id TEXT NOT NULL,
 PRIMARY KEY(instance_id,generation,session_id));
'''

def init(con):con.executescript(SCHEMA)

def native_sessions(row):
    if not row.get('connected'):
        with db.connect() as con:cached=con.execute('SELECT * FROM instance_session_cache WHERE instance_id=? ORDER BY observed_at DESC',(row['id'],)).fetchall()
        return {'sessions':[{**json.loads(r['metadata_json']),'process_ids':[],'status':'stored','historical':True,'last_observed_at':r['observed_at']} for r in cached],
            'mapping_available':False,'historical':bool(cached),'disconnected':True,'executor_shared':True}
    result=broker({'action':'agent-instance-sessions','instance_id':row['id']},timeout=5)
    result=with_session_names(row,result,lambda:broker({'action':'agent-instance-open','instance_id':row['id']}))
    rows=[]
    for raw in result.get('sessions',[]):
        if not isinstance(raw.get('id'),str):continue
        # Never turn a source alias or an arbitrary cwd into an asserted workspace.
        resource=raw.get('resource');known=raw.get('mapping') in ('native_registry','native_session_database','native_gateway')
        if not known or not isinstance(resource,str) or resource.startswith('/w/') or row.get('mode')=='controlled' and not any(resource==p or resource.startswith(p+'/') for p in row.get('resources',[])):
            resource=None
        item={k:raw[k] for k in ('id','name','status','running','parent_id','updated_at','mapping','runtime_session_id') if k in raw}
        item.update(resource=resource,process_ids=[p for p in raw.get('process_ids',[]) if isinstance(p,int) and p>0],historical=False)
        rows.append(item)
    if row.get('mode')=='controlled':
        with db.connect() as con:
            for item in rows:con.execute('INSERT OR REPLACE INTO instance_session_cache VALUES(?,?,?,?,?)',(row['id'],item['id'],json.dumps(item),row.get('generation'),db.now()))
    return {**result,'sessions':rows,'mapping_available':True}

def current_agent_pid(row):
    pid=row.get('pid')
    return pid if row.get('connected') and isinstance(pid,int) and not isinstance(pid,bool) and pid>0 else None


def directory(agent_type='',instance_id='',q='',cursor=0,limit=30,workspace=''):
    from . import controller as c
    products=[r for r in c.listing()['instances'] if (r['mode']=='controlled' or r.get('connected')) and (not agent_type or r['agent_type']==agent_type)]
    selected=[r for r in products if not instance_id or r['id']==instance_id]
    rows=[];errors=[];workspaces=set()
    connections=[{'id':r['id'],'name':r['name'],'agent_type':r['agent_type'],'connected':r.get('connected',False),
        'pid':current_agent_pid(r),'resources':r.get('resources',[])} for r in products]
    for row in selected:
        try:result=native_sessions(row)
        except (OSError,RuntimeError,ValueError,TimeoutError):
            errors.append({'instance_id':row['id'],'message':'原生会话映射读取失败'});continue
        if not result.get('mapping_available'):errors.append({'instance_id':row['id'],'message':'当前会话映射不可用，已保存记录仅供查看'})
        for s in result.get('sessions',[]):
            if s.get('resource'):workspaces.add(s['resource'])
            if workspace and s.get('resource')!=workspace:continue
            if q.lower() not in ((s.get('name') or '')+' '+s['id']).lower():continue
            rows.append({**s,'instance_id':row['id'],'instance_name':row['name'],'agent_type':row['agent_type'],
                'agent_pid':current_agent_pid(row),
                'generation':row.get('generation'),'policy_state':'active' if row.get('active') and not s.get('historical') else 'uncontrolled' if row['mode']=='observed' else 'not_verified',
                'executor_shared':bool(result.get('executor_shared'))})
    rows.sort(key=lambda s:(s['instance_id'],s['id']))
    return {'records':rows[cursor:cursor+limit],'next_cursor':cursor+limit if len(rows)>cursor+limit else None,
        'total':len(rows),'count_complete':not errors,'connections':connections,'errors':errors,
        'workspaces':sorted(workspaces),'workspace_available':bool(workspaces)}

def session_context(ident,sid,generation=None):
    from . import controller as c
    row=c.detail(ident);result=native_sessions(row)
    found=next((s for s in result.get('sessions',[]) if s['id']==sid),None)
    if found is None:raise ValueError('会话不属于此连接，或尚无可信原生映射')
    selected=generation or row.get('generation')
    if selected and selected!=row.get('generation'):
        with db.connect() as con:known=con.execute('SELECT 1 FROM instance_policy_receipts WHERE instance_id=? AND generation=?',(ident,selected)).fetchone()
        if not known:raise ValueError('运行代次不属于此连接')
    active=bool(row.get('active') and selected==row.get('generation') and not found.get('historical'))
    return row,found,selected,active

def legacy_records(row,active):
    compiled=row.get('runtime',{}).get('compile',{});rules=compiled.get('rules',[]);groups={}
    for rule in rules:
        if not rule.get('source_text') or not rule.get('clause_hash'):continue
        key=(rule.get('name'),rule.get('source_hash'));groups.setdefault(key,[]).append(rule)
    out=[]
    for (name,source_hash),refs in groups.items():
        clauses=list(dict.fromkeys(r.get('clause_text','') for r in refs))
        out.append({'id':'legacy:'+str(source_hash),'rule_name':name,'statement':'；'.join(c.strip() for c in clauses),
            'statement_origin':'dsl_summary','effects':list(dict.fromkeys(r['effect'] for r in refs)),
            'event_types':['cross_event' if any(r.get('semantics',{}).get('condition_kind') in ('after','lineage') or r.get('semantics',{}).get('gate_index') is not None for r in refs) else 'per_event'],
            'context_requirement':'project' if any(r.get('target_kind')=='file' for r in refs) else 'self_contained',
            'scope_type':'agent','scope_id':row['id'],'source_kind':'legacy_generated','original_dsl':None,
            'effective_dsl':refs[0]['source_text'],'compiled_refs':refs,'compile_status':'compiled','loaded':True,'active':active,
            'context_reason':'既有启动编译器生成的规则；用户原始 DSL 未记录','editable':False})
    return out

def policies(ident,sid,generation=None):
    row,session,gen,active=session_context(ident,sid,generation);saved=dsl_policy.receipt(ident,gen)
    records=dsl_policy.policy_records(saved['artifact'],active=active) if saved else []
    # Older starts have compiler source spans, but no user-authored source document.
    if not saved and gen==row.get('generation'):records.extend(legacy_records(row,active))
    if saved:
        # The fixed/legacy clauses are also real ActPlane rules, not mount grants.
        compat={**row,'runtime':{'compile':saved['artifact']['compile']}}
        user_names={r['compiled_name'] for d in saved['artifact'].get('documents',[]) for r in d['rules']}
        records.extend(r for r in legacy_records(compat,active) if r['rule_name'] not in user_names)
    attach_hits(records,row,gen)
    with db.connect() as con:
        binding=con.execute('SELECT * FROM instance_session_task_bindings WHERE instance_id=? AND generation=? AND session_id=?',(ident,gen,sid)).fetchone()
        generations=[dict(r) for r in con.execute('SELECT generation,created_at FROM instance_policy_receipts WHERE instance_id=? ORDER BY created_at DESC',(ident,))]
    if row.get('generation') and row['generation'] not in [g['generation'] for g in generations]:generations.insert(0,{'generation':row['generation'],'created_at':'既有运行记录'})
    if binding:
        from ..managed import controller as managed
        from ..managed.records import workbench
        with db.connect() as con:state=managed.load(con,binding['task_id'])
        if state.get('session_id')==binding['managed_session_id'] and state.get('binding',{}).get('domain_id')==row.get('domain_id'):
            for record in workbench(binding['task_id']).get('records',[]):
                records.append({**record,'scope_type':'session','scope_id':sid,'context_requirement':record.get('context_scope','task'),'editable':False})
    return {'session':session,'instance':{'id':ident,'name':row['name'],'mode':row['mode'],'agent_type':row['agent_type']},
        'generation':gen,'generations':generations,'active':active,'executor_shared':True,'pid':row.get('pid') if active else None,
        'agent_pid':current_agent_pid(row),
        'domain_id':row.get('domain_id') if active else None,'records':records,'bundle_hash':saved['bundle_hash'] if saved else None,
        'effective_dsl':saved['artifact']['effective_dsl'] if saved else None,'task_binding_available':bool(binding)}

def attach_hits(records,row,generation):
    saved=dsl_policy.receipt(row['id'],generation)
    with db.connect() as con:raws=con.execute('SELECT * FROM instance_kernel_events WHERE instance_id=? AND generation=? ORDER BY id DESC LIMIT 300',(row['id'],generation)).fetchall()
    events=[project_kernel(row,saved,r) for r in raws]
    for record in records:
        if saved and record.get('bundle_hash') and record['bundle_hash']!=saved['bundle_hash']:
            record['hits']=[]
            continue
        refs={(r.get('source_ref'),r.get('clause_hash')) for r in record.get('compiled_refs',[])}
        record['hits']=[e for e in events if any((r['source_ref'],r['clause_hash']) in refs for r in e['source_refs'])][:20]
        record['hit_coverage']='当前 Agent 运行期间最近 300 条已采集事件中，最多展示本策略 20 条命中。'
        record['generation']=generation
        if saved:
            record['loaded_document']=saved['artifact']['effective_dsl']
            record.setdefault('bundle_hash',saved['bundle_hash'])
            record.setdefault('bindings',[{**saved['artifact'].get('binding',{}),'active':bool(record.get('active')),'bundle_hash':saved['bundle_hash']}])

def domains(ident,sid,generation=None):
    data=policies(ident,sid,generation)
    nodes=[{'id':scope,'title':title,'kind':'configuration_scope','count':sum(r.get('scope_type')==scope for r in data['records'])} for scope,title in (('system','系统策略'),('agent','Agent 专属策略'),('session','会话策略'))]
    return {**{k:data[k] for k in ('generation','active','executor_shared','pid','domain_id','bundle_hash')},'nodes':nodes,
        'edges':[{'from':'system','to':'agent'},{'from':'agent','to':'session'}],
        'notice':'上方为配置继承关系。原生会话共用执行器，不代表三个独立的内核域。'}

_collection_lock=threading.RLock()

def collect_kernel(row):
    # Serialize cursor reads and writes, including simultaneous UI refreshes and
    # the background observer. A stale reader must never rewind a cursor.
    with _collection_lock:return _collect_kernel(row)

def _collect_kernel(row):
    if row.get('mode')!='controlled' or not row.get('generation'):return {'available':False}
    gen=row['generation']
    with db.connect() as con:cursor=con.execute('SELECT cursor_json FROM instance_kernel_cursors WHERE instance_id=? AND generation=?',(row['id'],gen)).fetchone()
    try:result=broker({'action':'agent-instance-kernel-events','instance_id':row['id'],'generation':gen,'cursor':json.loads(cursor[0]) if cursor else None},timeout=3)
    except (OSError,RuntimeError,ValueError,TimeoutError):return {'available':False,'error':'当前内核事件采集不可用'}
    if result.get('generation')!=gen:return {'available':False,'error':'采集代次已变化'}
    if result.get('cursor'):
        with db.connect() as con:
            for record in result.get('events',[]):
                raw=record['event']
                con.execute('INSERT OR IGNORE INTO instance_kernel_events(instance_id,generation,source_key,bundle_hash,domain_id,event_json,created_at) VALUES(?,?,?,?,?,?,?)',
                    (row['id'],gen,result['cursor']['file']+':'+str(record['offset']),result.get('bundle_hash'),result.get('domain_id'),json.dumps(raw),db.now()))
            con.execute('INSERT OR REPLACE INTO instance_kernel_cursors VALUES(?,?,?)',(row['id'],gen,json.dumps(result['cursor'])))
    return {'available':True}

def project_kernel(row,saved,raw):
    event=json.loads(raw['event_json']);rule=event.get('rule',{});matched=[]
    if saved and raw['generation']==saved['generation'] and raw['bundle_hash']==saved['bundle_hash'] and event.get('process_domain_id')==raw['domain_id']==saved['artifact'].get('binding',{}).get('domain_id'):
        for ref in saved['artifact']['compile'].get('rules',[]):
            if rule.get('source_ref')==ref.get('source_ref') and rule.get('clause_hash') and rule['clause_hash']==ref.get('clause_hash') and rule.get('effect')==ref.get('effect') and rule.get('target_pattern')==ref.get('target_pattern'):
                matched.append({'source_ref':ref['source_ref'],'compiler_rule_id':ref['rule_id'],'kernel_rule_id':event.get('rule_id'),'clause_hash':ref['clause_hash']})
    call_id=None;sid=None;tag=str(event.get('tool_call_tag') or '')
    if tag and tag!='0':
        with db.connect() as con:starts=con.execute("SELECT session_id,call_id,detail_json FROM instance_events WHERE instance_id=? AND generation=? AND kind='tool_start'",(row['id'],raw['generation'])).fetchall()
        links=[r for r in starts if str(json.loads(r['detail_json']).get('kernel_call_tag',''))==tag and json.loads(r['detail_json']).get('domain_id')==event.get('process_domain_id')]
        if len({(r['session_id'],r['call_id']) for r in links})==1:sid,call_id=links[0]['session_id'],links[0]['call_id']
    return {'id':raw['id'],'time':event.get('timestamp_unix_ns') or raw['created_at'],'instance_id':row['id'],'generation':raw['generation'],
        'session_id':sid,'call_id':call_id,'attribution':'trusted_tool_tag' if sid else 'shared_executor_unattributed',
        'operation':event.get('op'),'syscall':event.get('syscall'),'target':event.get('target'),'pid':event.get('pid'),
        'domain_id':event.get('process_domain_id',event.get('domain_id')),'rule_domain_id':event.get('domain_id'),
        'effect':event.get('effect'),'actual_action':event.get('action'),'blocked':event.get('blocked',False),'killed':event.get('killed',False),
        'rule_name':rule.get('name'),'rule_id':event.get('rule_id'),'source_refs':matched,'bundle_hash':raw['bundle_hash'],
        'reason':rule.get('reason'),'origin':event.get('causal_chain') or event.get('provenance'),'feedback_delivered':None}

def kernel_page(ident,sid,generation=None,before=None,limit=30):
    row,session,gen,active=session_context(ident,sid,generation)
    collection=collect_kernel(row) if gen==row.get('generation') else {'available':True,'historical':True}
    saved=dsl_policy.receipt(ident,gen)
    with db.connect() as con:rows=con.execute('SELECT * FROM instance_kernel_events WHERE instance_id=? AND generation=? AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT ?', (ident,gen,before,before,limit+1)).fetchall()
    records=[project_kernel(row,saved,r) for r in rows[:limit]]
    records=[r for r in records if r['session_id'] in (None,sid)]
    return {'records':records,'generation':gen,'next_cursor':rows[limit-1]['id'] if len(rows)>limit else None,'collection':collection,
        'coverage':'仅采集内核策略匹配事件，不代表全量系统调用。共享进程中的未关联事件不归属于当前会话。'}

def traces(ident,sid,generation=None,before=None,limit=30):
    row,session,gen,active=session_context(ident,sid,generation);collect_kernel(row)
    with db.connect() as con:
        groups=con.execute("SELECT call_id,MAX(seq) AS last_seq FROM instance_events WHERE instance_id=? AND generation=? AND session_id=? AND call_id IS NOT NULL GROUP BY call_id HAVING (? IS NULL OR MAX(seq)<?) ORDER BY last_seq DESC LIMIT ?",(ident,gen,sid,before,before,limit+1)).fetchall()
        saved=dsl_policy.receipt(ident,gen)
        kernels=[project_kernel(row,saved,r) for r in con.execute('SELECT * FROM instance_kernel_events WHERE instance_id=? AND generation=? ORDER BY id DESC LIMIT 1000',(ident,gen))]
        records=[]
        for g in groups[:limit]:
            events=[dict(e) for e in con.execute('SELECT * FROM instance_events WHERE instance_id=? AND generation=? AND session_id=? AND call_id=? ORDER BY seq',(ident,gen,sid,g['call_id']))]
            steps=[{'id':e['seq'],'kind':e['kind'],'time':e['created_at'],'tool':e['tool'],'detail':json.loads(e['detail_json'])} for e in events]
            linked=[e for e in kernels if e['call_id']==g['call_id'] and e['session_id']==sid]
            records.append({'id':g['call_id'],'session_id':sid,'generation':gen,'tool':events[0]['tool'],'time':events[0]['created_at'],'steps':steps,'kernel_events':linked,
                'result':'tool_denied' if any(e['kind']=='tool_denied' for e in events) else 'kernel_match' if linked else 'success' if any(e['kind']=='tool_result' and json.loads(e['detail_json']).get('succeeded') for e in events) else 'failure' if any(e['kind']=='tool_result' for e in events) else 'started','feedback_delivered':None})
    return {'records':records,'next_cursor':groups[limit-1]['last_seq'] if len(groups)>limit else None,'generation':gen,
        'coverage':'工具结果、内核处置与反馈送达分别记录；缺少可信工具标签时不关联系统调用。'}
