"""Durable instance-scoped Pi assessments and evidence-bound post-run audits."""
import json
import os
import threading
import uuid
from .. import db
from . import store,sessions,dsl_policy,workspace_references as refs
from .policy import digest

SCHEMA='''
CREATE TABLE IF NOT EXISTS instance_lifecycle_configs(instance_id TEXT PRIMARY KEY,config_json TEXT NOT NULL,config_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS instance_policy_jobs(id TEXT PRIMARY KEY,instance_id TEXT NOT NULL,generation TEXT NOT NULL,
 session_id TEXT NOT NULL,stage TEXT NOT NULL,event_key TEXT NOT NULL,input_json TEXT NOT NULL,input_hash TEXT NOT NULL,
 state TEXT NOT NULL,result_json TEXT,error TEXT,created_at TEXT NOT NULL,finished_at TEXT,UNIQUE(instance_id,event_key));
CREATE TABLE IF NOT EXISTS instance_audit_reviews(id INTEGER PRIMARY KEY,job_id TEXT NOT NULL,finding_id TEXT NOT NULL,
 disposition TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL);
'''
def init(con):
    con.executescript(SCHEMA)
    con.execute("UPDATE instance_policy_jobs SET state='failed',error='服务重启中断分析，请重试' WHERE state='running'")

def config(ident):
    with db.connect() as con:row=con.execute('SELECT * FROM instance_lifecycle_configs WHERE instance_id=?',(ident,)).fetchone()
    return json.loads(row['config_json']) if row else None

def configure(ident,body):
    row=store.get(ident)
    if row['mode']!='controlled':raise ValueError('仅受控实例支持策略生命周期')
    if set(body)!={'enabled','requirements','workspace_id','integrity_paths'} or type(body['enabled'])is not bool:
        raise ValueError('生命周期配置不合法')
    if not isinstance(body['requirements'],str) or not 5<=len(body['requirements'])<=8000:raise ValueError('请填写明确的场景要求')
    value=refs.snapshot(ident,body['workspace_id'],body['integrity_paths']) if body['enabled'] else {'files':[]}
    with db.connect() as con:cursor=con.execute('SELECT COALESCE(MAX(seq),0) FROM instance_events WHERE instance_id=?',(ident,)).fetchone()[0]
    saved={**body,'requirements':refs.sanitized_text(body['requirements']),
           'baseline':{f['relative_path']:f['sha256'] for f in value['files']},'baseline_at':db.now(),
           'resource_hash':digest(row['resources']),'after_seq':cursor}
    with db.connect() as con:con.execute('INSERT OR REPLACE INTO instance_lifecycle_configs VALUES(?,?,?)',(ident,json.dumps(saved),digest(saved)))
    return {**saved,'config_hash':digest(saved)}

def evidence(row,sid,configuration):
    generation=row['generation'];saved=dsl_policy.receipt(row['id'],generation)
    with db.connect() as con:
        starts=list(reversed([dict(r) for r in con.execute('SELECT * FROM instance_events WHERE instance_id=? AND generation=? AND session_id=? ORDER BY seq DESC LIMIT 500',(row['id'],generation,sid))]))
        raw=[dict(r) for r in con.execute('SELECT * FROM instance_kernel_events WHERE instance_id=? AND generation=? ORDER BY id DESC LIMIT 2000',(row['id'],generation))]
    kernels=[sessions.project_kernel(row,saved,r) for r in raw]
    kernels=[r for r in kernels if r['session_id']==sid and r['attribution']=='trusted_tool_tag' and r['source_refs']]
    records=[{'id':'tool:'+str(e['seq']),'kind':e['kind'],'call_id':e['call_id'],'tool':e['tool'],
              'time':e['created_at'],'detail':json.loads(e['detail_json'])} for e in starts]
    records.extend({'id':'kernel:'+str(k['id']),'kind':'kernel','value':k} for k in kernels)
    return {'instance_id':row['id'],'generation':generation,'session_id':sid,'policy_hash':row['policy_hash'],
            'bundle_hash':saved['bundle_hash'] if saved else None,'requirements':configuration['requirements'],
            'records':records,'coverage':{'kernel':'matched violations only; exact tool tags required','tools_truncated':len(starts)>=500,'kernel_truncated':len(raw)>=2000}}

def enqueue(row,sid,stage,key,trigger=None):
    configuration=config(row['id'])
    if not configuration or not configuration['enabled']:return None
    if digest(row['resources'])!=configuration['resource_hash']:raise ValueError('场景资源已变化，请重新登记')
    snapshot=evidence(row,sid,configuration)
    if stage=='postrun':
        try:
            after=refs.snapshot(row['id'],configuration['workspace_id'],configuration['integrity_paths'])
            snapshot['integrity']=[{'path':f['relative_path'],'before_sha256':configuration['baseline'][f['relative_path']],
                'after_sha256':f['sha256'],'unchanged':configuration['baseline'][f['relative_path']]==f['sha256']} for f in after['files']]
        except (OSError,ValueError,RuntimeError):
            # Missing/deleted/unreadable files must not silently erase the audit.
            # No fallback to the API identity or widening of reader permissions.
            snapshot['integrity']=[{'path':p,'before_sha256':configuration['baseline'][p],
                'after_sha256':None,'unchanged':None,'error':'登记文件无法通过只读通道完成核对，完整性未知'} for p in configuration['integrity_paths']]
        snapshot['integrity_coverage']={'before':configuration.get('baseline_at'),'after':db.now(),'continuous_monitoring':False}
        snapshot['records'].extend({'id':'integrity:'+f['path'],'kind':'integrity','value':f} for f in snapshot['integrity'])
    snapshot['trigger']=trigger
    ident=uuid.uuid4().hex
    with db.connect() as con:
        con.execute('INSERT OR IGNORE INTO instance_policy_jobs VALUES(?,?,?,?,?,?,?,?,\'queued\',NULL,NULL,?,NULL)',
            (ident,row['id'],row['generation'],sid,stage,key,json.dumps(snapshot),digest(snapshot),db.now()))
        item=con.execute('SELECT id FROM instance_policy_jobs WHERE instance_id=? AND event_key=?',(row['id'],key)).fetchone()
    return item['id']

def discover(row):
    if os.getenv('AGENTSCOPE_POLICY_LIFECYCLE_WORKER')!='1':return
    configuration=config(row['id'])
    if not configuration or not configuration['enabled'] or row['gate']!='open':return
    with db.connect() as con:
        events=[dict(r) for r in con.execute("SELECT * FROM instance_events WHERE instance_id=? AND generation=? AND seq>? AND kind IN ('tool_result','turn_end') AND (julianday('now')-julianday(created_at))*86400>2 ORDER BY seq",(row['id'],row['generation'],configuration.get('after_seq',0)))]
    for event in events:
        stage='postrun' if event['kind']=='turn_end' else 'runtime'
        key=stage+':'+row['generation']+':'+str(event['seq'])
        with db.connect() as con:
            if con.execute('SELECT 1 FROM instance_policy_jobs WHERE instance_id=? AND event_key=?',(row['id'],key)).fetchone():continue
        if stage=='runtime':
            snapshot=evidence(row,event['session_id'],configuration)
            if not any(r['kind']=='kernel' and r['value']['call_id']==event['call_id'] for r in snapshot['records']):continue
        else:
            with db.connect() as con:
                if con.execute('SELECT 1 FROM instance_leases WHERE instance_id=? AND generation=? AND session_id=?',(row['id'],row['generation'],event['session_id'])).fetchone():continue
        enqueue(row,event['session_id'],stage,key,{'seq':event['seq'],'call_id':event['call_id']})
    worker.start()

def jobs(ident,sid=None):
    store.get(ident)
    with db.connect() as con:
        rows=con.execute('SELECT * FROM instance_policy_jobs WHERE instance_id=? AND (? IS NULL OR session_id=?) ORDER BY created_at DESC LIMIT 50',(ident,sid,sid)).fetchall()
        reviews=[dict(r) for r in con.execute('SELECT r.* FROM instance_audit_reviews r JOIN instance_policy_jobs j ON j.id=r.job_id WHERE j.instance_id=? ORDER BY r.id',(ident,))]
    return {'configuration':config(ident),'records':[{**{k:r[k] for k in ('id','generation','session_id','stage','state','input_hash','error','created_at','finished_at')},
        'result':json.loads(r['result_json']) if r['result_json'] else None} for r in rows],'reviews':reviews}

def review(ident,job_id,body):
    store.get(ident)
    with db.connect() as con:
        row=con.execute("SELECT * FROM instance_policy_jobs WHERE id=? AND instance_id=? AND stage='postrun' AND state='completed'",(job_id,ident)).fetchone()
        if not row or row['input_hash']!=body['input_hash']:raise ValueError('审计目标或证据已变化')
        finding=next((f for f in json.loads(row['result_json'])['findings'] if f['id']==body['finding_id']),None)
        if not finding:raise ValueError('审计发现不存在')
        con.execute('INSERT INTO instance_audit_reviews(job_id,finding_id,disposition,note,created_at) VALUES(?,?,?,?,?)',
            (job_id,body['finding_id'],body['disposition'],refs.sanitized_text(body['note']),db.now()))
        db.audit(con,None,'instance_audit_review','user',{'instance_id':ident,'job_id':job_id,'finding_id':body['finding_id'],
            'input_hash':row['input_hash'],'disposition':body['disposition']})
    return {'recorded':True,'original_evidence_changed':False,'policy_changed':False}

def retry(ident,job_id,input_hash):
    store.get(ident)
    with db.connect() as con:
        changed=con.execute("UPDATE instance_policy_jobs SET state='queued',error=NULL,finished_at=NULL WHERE id=? AND instance_id=? AND input_hash=? AND state='failed'",(job_id,ident,input_hash)).rowcount
        if not changed:raise ValueError('只能重试同一证据快照的失败分析')
    worker.start()
    return {'queued':True}

class AuditAgent:
    enabled=False;catalog=[];references=[];runs=[];scope='audit'
    def __init__(self,snapshot):
        self.snapshot=snapshot;self.read=set();self.runs=[];self.calls=0
        self.native_tools=[{'name':'read_evidence','description':'读取一个已登记的真实工具或内核证据，禁止虚构引用。',
            'input_schema':{'type':'object','properties':{'evidence_id':{'type':'string'}},'required':['evidence_id'],'additionalProperties':False}}]
        finding={'type':'object','properties':{'evidence_ids':{'type':'array','items':{'type':'string'},'minItems':1},
            'category':{'type':'string','enum':['integrity','confidentiality','availability','workflow','uncertain']},
            'severity':{'type':'string','enum':['low','medium','high','uncertain']},'explanation':{'type':'string','maxLength':2000}},
            'required':['evidence_ids','category','severity','explanation'],'additionalProperties':False}
        self.final_schema={'type':'object','properties':{'summary':{'type':'string'},'findings':{'type':'array','items':finding}},
                           'required':['summary','findings'],'additionalProperties':False}
    def check_basis(self):pass # Audit is explicitly historical and bound to its immutable input hash.
    def execute(self,call):
        self.calls+=1
        if self.calls>30:raise ValueError('审计证据读取达到上限')
        if call['tool']!='read_evidence' or set(call['arguments'])!={'evidence_id'}:raise ValueError('只允许审计证据读取')
        ident=call['arguments']['evidence_id']
        item=next((r for r in self.snapshot['records'] if r['id']==ident),None)
        if not item:raise ValueError('审计证据不存在')
        self.read.add(ident);return item
    def validate_final(self,value):
        if not isinstance(value,dict) or set(value)!={'summary','findings'} or not isinstance(value['summary'],str) or len(value['summary'])>4000:
            raise ValueError('审计结论格式不合法')
        if not isinstance(value['findings'],list) or len(value['findings'])>30:raise ValueError('审计发现数量不合法')
        for f in value['findings']:
            if not isinstance(f,dict) or set(f)!={'evidence_ids','category','severity','explanation'}:raise ValueError('审计发现字段不合法')
            if f['category'] not in ('integrity','confidentiality','availability','workflow','uncertain') or f['severity'] not in ('low','medium','high','uncertain'):
                raise ValueError('审计分类不合法')
            if not isinstance(f['explanation'],str) or len(f['explanation'])>2000 or not isinstance(f['evidence_ids'],list) or not f['evidence_ids'] or any(not isinstance(i,str) for i in f['evidence_ids']) or not set(f['evidence_ids'])<=self.read:
                raise ValueError('审计必须引用实际已读取的证据')

def run(job):
    snapshot=json.loads(job['input_json'])
    if digest(snapshot)!=job['input_hash']:raise ValueError('分析输入摘要不一致')
    if job['stage']=='runtime':
        row=store.get(job['instance_id'])
        if row['generation']!=job['generation'] or row['policy_hash']!=snapshot['policy_hash']:raise ValueError('运行代次已变化，评估已过期')
        from . import template_configurations as tc
        result=tc.generate(row['id'],{'scope':'agent','text':'根据已认证场景要求和本次真实内核拒绝评估是否需要新增策略。拒绝不授予权限；没有必要变更则返回空配置。场景：'+snapshot['requirements'],
            'stage':'runtime','runtime_event_seq':snapshot['trigger']['seq'],'runtime_evidence':snapshot,
            'context_mode':'auto','materials':[{'name':'runtime-evidence.json','text':json.dumps(snapshot,ensure_ascii=False)}],
            'request_key':'lifecycle:'+job['id']})
        return {'decision':'needs_approval' if result['items'] else 'no_change','generation':result,'evidence_hash':job['input_hash'],'applied':False}
    from .pi_provider import NativePiProvider
    agent=AuditAgent(snapshot)
    public={**snapshot,'records':[{'id':r['id'],'kind':r['kind']} for r in snapshot['records']]}
    result,metadata=NativePiProvider().run_agent(agent,'你是只读运行后审计 Agent。读取证据后评估风险。策略命中不等于恶意或实际损害。'
        '区分工具报告、内核真实处置和完整性比较。只引用实际证据；不足时明确不确定。没有策略审批、修改或执行权限。',public)
    for i,f in enumerate(result['findings']):
        matches=[r['value'] for r in snapshot['records'] if r['id'] in f['evidence_ids'] and r['kind']=='kernel']
        f.update(id=str(i),outcome='blocked_attempt' if any(m['blocked'] for m in matches) else 'process_killed' if any(m['killed'] for m in matches) else 'needs_review',review_status='unreviewed')
    return {**result,'integrity':snapshot.get('integrity',[]),'integrity_coverage':snapshot.get('integrity_coverage'),
            'coverage':snapshot['coverage'],'evidence_read_ids':sorted(agent.read),
            'metadata':metadata,'evidence_hash':job['input_hash'],'policy_changed':False}

class Worker:
    def __init__(self):self.thread=None;self.lock=threading.Lock()
    def start(self):
        if os.getenv('AGENTSCOPE_POLICY_LIFECYCLE_WORKER')!='1':return
        with self.lock:
            if self.thread and self.thread.is_alive():return
            self.thread=threading.Thread(target=self.loop,daemon=True,name='instance-policy-pi');self.thread.start()
    def loop(self):
        while True:
            with db.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                row=con.execute("SELECT * FROM instance_policy_jobs WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
                if row:con.execute("UPDATE instance_policy_jobs SET state='running' WHERE id=?",(row['id'],))
            if not row:return
            try:
                result=run(dict(row));state='completed';error=None
            except Exception as e:result=None;state='failed';error=refs.sanitized_text(str(e))[:2000]
            with db.connect() as con:con.execute('UPDATE instance_policy_jobs SET state=?,result_json=?,error=?,finished_at=? WHERE id=?',
                (state,json.dumps(result,ensure_ascii=False) if result else None,error,db.now(),row['id']))
worker=Worker()
