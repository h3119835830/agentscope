"""Human-authored DSL lifecycle, separate from legacy mount/tool permissions."""
import json
import time
import uuid
from .. import db
from ..broker_client import call as broker
from . import store, system_policy as system
from .policy import digest
from dsl_documents import canonical_documents, fingerprint

SCHEMA='''
CREATE TABLE IF NOT EXISTS instance_dsl_scopes(scope_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,
 documents_json TEXT NOT NULL,document_hash TEXT NOT NULL,phase TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS instance_dsl_proposals(id TEXT PRIMARY KEY,scope_id TEXT NOT NULL,request_key TEXT NOT NULL,
 request_hash TEXT NOT NULL,base_hash TEXT NOT NULL,base_revision INTEGER NOT NULL,documents_json TEXT NOT NULL,
 targets_json TEXT NOT NULL,result_json TEXT NOT NULL,proposal_hash TEXT NOT NULL,state TEXT NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(scope_id,request_key));
CREATE TABLE IF NOT EXISTS instance_policy_receipts(instance_id TEXT NOT NULL,generation TEXT NOT NULL,
 dsl_hash TEXT,bundle_hash TEXT,artifact_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(instance_id,generation));
'''

def init(con):
    con.executescript(SCHEMA)
    con.execute("UPDATE instance_dsl_scopes SET phase='blocked' WHERE phase='updating'")

def current(scope_id,con=None):
    if con is None:
        with db.connect() as conn:return current(scope_id,conn)
    row=con.execute('SELECT * FROM instance_dsl_scopes WHERE scope_id=?',(scope_id,)).fetchone()
    if not row:return {'scope_id':scope_id,'revision':0,'documents':[],'document_hash':digest([]),'phase':'ready'}
    result=dict(row);result['documents']=json.loads(result.pop('documents_json'));return result

def ensure_ready(scope_id=None):
    with db.connect() as con:
        if con.execute("SELECT 1 FROM instance_dsl_scopes WHERE scope_id IN ('system',?) AND phase!='ready'",(scope_id,)).fetchone():raise ValueError('DSL 策略应用未完成，执行保持暂停；请重新校验并确认恢复')

def documents_for(ident,override_scope=None,override=None):
    out=[]
    for scope in ('system',ident):
        values=override if scope==override_scope else current(scope)['documents']
        out.extend({**d,'scope_id':scope} for d in values)
    return out

def launch_spec(row):
    docs=documents_for(row['id'])
    return {'dsl_documents':docs,'dsl_hash':fingerprint(docs,row['resources'])}

def live_matches(row,live):
    expected=launch_spec(row)['dsl_hash']
    return (not expected and not live.get('dsl_hash') or expected==live.get('dsl_hash')) and all(current(s)['phase']=='ready' for s in ('system',row['id']))

def validate_scope(scope):
    if scope!='system' and store.get(scope)['mode']!='controlled':raise ValueError('仅受控连接支持 DSL 配置')

def target_snapshot(scope,documents):
    from . import controller as c
    rows=[r for r in store.rows() if r['mode']=='controlled' and (scope=='system' or r['id']==scope)]
    live={r['id']:r for r in c.listing()['instances']}
    from ..console import hidden
    retained=hidden('agent')
    targets=[]
    for row in rows:
        docs=documents_for(row['id'],scope,documents)
        targets.append({'id':row['id'],'console_retained':row['id'] in retained,'name':row['name'],'agent_type':row['agent_type'],'resources':row['resources'],'generation':row['generation'],
            'gate':row['gate'],'base_hash':row['policy_hash'],'current_dsl_hash':launch_spec(row)['dsl_hash'],
            'pid':live.get(row['id'],{}).get('pid'),'domain_id':live.get(row['id'],{}).get('domain_id'),
            'next_dsl_hash':fingerprint(docs,row['resources']),'system_revision':system.current()['revision'],
            'system_dsl_revision':current('system')['revision'],'agent_dsl_revision':current(row['id'])['revision'],
            'active':bool(live.get(row['id'],{}).get('active'))})
    return targets

def unpack(raw):
    p=dict(raw)
    for key in ('documents','targets','result'):p[key]=json.loads(p.pop(key+'_json'))
    return p

@system.lifecycle
def propose(scope,body):
    validate_scope(scope)
    if system.current()['phase']!='ready':raise ValueError('请先恢复系统共享权限配置')
    docs=canonical_documents(body['documents']);base=current(scope)
    request_hash=digest({'documents':docs,'base_hash':body['base_hash'],'base_revision':body['base_revision']})
    with db.connect() as con:
        old=con.execute('SELECT * FROM instance_dsl_proposals WHERE scope_id=? AND request_key=?',(scope,body['request_key'])).fetchone()
    if old:
        if old['request_hash']!=request_hash:raise ValueError('幂等键已用于其他 DSL 候选')
        return unpack(old)
    if body['base_hash']!=base['document_hash'] or body['base_revision']!=base['revision']:raise ValueError('DSL 版本已经变化，请刷新后编辑')
    targets=target_snapshot(scope,docs);results=[];error=None
    if not targets and docs:error='尚无受控连接，无法验证实际资源与运行后端；可保存草案，接入后重新校验'
    for target in targets:
        try:
            row=store.get(target['id'])
            result=broker({'action':'agent-instance-dsl-compile','instance_id':row['id'],'resources':row['resources'],
                'policy':row['policy'],'dsl_documents':documents_for(row['id'],scope,docs)},timeout=60)
            results.append({'instance_id':row['id'],**result})
        except (OSError,TimeoutError,ValueError,RuntimeError) as e:
            error=str(e)[:4000];break
    state='invalid' if error else 'pending';result={'compilations':results,'error':error}
    proposal_hash=digest({'request_hash':request_hash,'targets':targets,'compilations':results})
    pid=uuid.uuid4().hex
    with db.connect() as con:
        con.execute('INSERT INTO instance_dsl_proposals VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(pid,scope,body['request_key'],request_hash,base['document_hash'],base['revision'],json.dumps(docs),json.dumps(targets),json.dumps(result),proposal_hash,state,db.now()))
        raw=con.execute('SELECT * FROM instance_dsl_proposals WHERE id=?',(pid,)).fetchone()
    return unpack(raw)

@system.lifecycle
def apply(scope,pid,expected_hash):
    from . import controller as c
    validate_scope(scope)
    if system.current()['phase']!='ready':raise ValueError('请先恢复系统共享权限配置')
    with db.connect() as con:raw=con.execute('SELECT * FROM instance_dsl_proposals WHERE id=? AND scope_id=?',(pid,scope)).fetchone()
    if not raw or raw['proposal_hash']!=expected_hash:raise ValueError('DSL 候选确认内容不一致')
    p=unpack(raw)
    if p['state']=='applied':return {'id':pid,'state':'applied','idempotent':True}
    base=current(scope)
    if p['state']!='pending' or p['base_hash']!=base['document_hash'] or p['base_revision']!=base['revision']:raise ValueError('DSL 候选已过期或尚未通过编译')
    if target_snapshot(scope,p['documents'])!=p['targets']:raise ValueError('连接、资源、运行代次或继承策略已经变化，请重新校验')
    # Recompile the same frozen effective policy before any process is stopped.
    for target,previous in zip(p['targets'],p['result']['compilations']):
        row=store.get(target['id'])
        check=broker({'action':'agent-instance-dsl-compile','instance_id':row['id'],'resources':row['resources'],'policy':row['policy'],'dsl_documents':documents_for(row['id'],scope,p['documents'])},timeout=60)
        if check['bundle_hash']!=previous['bundle_hash']:raise ValueError('确认后的编译内容不一致，请重新校验')
    affected=p['targets'];resume=[t['id'] for t in affected if t['active']]
    with db.connect() as con:
        con.execute("INSERT INTO instance_dsl_scopes VALUES(?,?,?,?,?,?) ON CONFLICT(scope_id) DO UPDATE SET phase='updating'",(scope,base['revision'],json.dumps(base['documents']),base['document_hash'],'updating',db.now()))
        con.execute("UPDATE instance_dsl_proposals SET state='applying' WHERE id=?",(pid,))
        for t in affected:con.execute("UPDATE agent_instances SET gate='updating' WHERE id=?",(t['id'],))
    try:
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            with db.connect() as con:n=sum(con.execute('SELECT COUNT(*) FROM instance_leases WHERE instance_id=?',(t['id'],)).fetchone()[0] for t in affected)
            if not n:break
            time.sleep(.05)
        from .sessions import collect_kernel
        for t in affected:
            row=store.get(t['id']);collect_kernel(row);c.adapter(row).stop(row)
        with db.connect() as con:
            con.execute("UPDATE instance_dsl_scopes SET documents_json=?,document_hash=?,revision=revision+1,updated_at=? WHERE scope_id=?",(json.dumps(p['documents']),digest(p['documents']),db.now(),scope))
            for t in affected:
                con.execute("UPDATE agent_instances SET gate='closed',token_hash=NULL,runtime_json='{}' WHERE id=?",(t['id'],))
                con.execute('DELETE FROM instance_leases WHERE instance_id=?',(t['id'],))
                con.execute("UPDATE instance_proposals SET state='superseded' WHERE instance_id=? AND state='pending'",(t['id'],))
        # Keep every gate closed until all restarts pass. Only this trusted thread
        # may start under an updating DSL scope; leases remain denied throughout.
        APPLYING.value=True
        for ident in resume:
            result=c.start(ident)
            if not result.get('runtime',{}).get('verified'):raise ValueError('DSL 加载或绑定核验失败')
        with db.connect() as con:
            con.execute("UPDATE instance_dsl_scopes SET phase='ready' WHERE scope_id=?",(scope,))
            con.execute("UPDATE instance_dsl_proposals SET state='applied' WHERE id=?",(pid,))
        for t in affected:store.event(t['id'],'dsl_applied',{'proposal_id':pid,'scope_id':scope},store.get(t['id'])['generation'])
        c.observer.collect()
        return {'id':pid,'state':'applied','affected_count':len(affected),'resumed_count':len(resume)}
    except Exception:
        for t in affected:
            store.update(t['id'],gate='paused')
            try:c.adapter(store.get(t['id'])).stop(store.get(t['id']))
            except Exception:pass
        with db.connect() as con:
            con.execute("UPDATE instance_dsl_scopes SET phase='blocked' WHERE scope_id=?",(scope,))
            con.execute("UPDATE instance_dsl_proposals SET state='failed' WHERE id=?",(pid,))
        raise
    finally:APPLYING.value=False

import threading
APPLYING=threading.local()

def record_receipt(ident,generation,runtime):
    artifact=runtime.get('policy_artifact')
    if not artifact:return
    artifact={**artifact,'binding':{'generation':generation,'domain_id':runtime.get('domain_id'),'pid':runtime.get('pid')}}
    with db.connect() as con:con.execute('INSERT OR REPLACE INTO instance_policy_receipts VALUES(?,?,?,?,?,?)',(ident,generation,runtime.get('dsl_hash'),artifact['bundle_hash'],json.dumps(artifact),db.now()))

def receipt(ident,generation):
    with db.connect() as con:row=con.execute('SELECT * FROM instance_policy_receipts WHERE instance_id=? AND generation=?',(ident,generation)).fetchone()
    return {**dict(row),'artifact':json.loads(row['artifact_json'])} if row else None

def policy_records(artifact,scope_filter=None,active=False):
    out=[]
    for doc in artifact.get('documents',[]):
        if scope_filter and doc['scope_id']!=scope_filter:continue
        for rule in doc['rules']:
            meta=doc.get('metadata',{}).get(rule['rule_name'],{})
            refs=[r for r in artifact.get('compile',{}).get('rules',[]) if r.get('source_ref')==rule['source_ref'] and r.get('name')==rule['compiled_name']]
            # A DSL-derived statement includes the complete conditions verbatim.
            summary='；'.join(c['effective_clause'].strip() for c in rule['clauses'])
            out.append({**rule,'id':doc['scope_id']+':'+doc['id']+':'+rule['rule_name'],'document_id':doc['id'],
                'document_name':doc['name'],'original_document':doc['original_dsl'],'statement':meta.get('statement') or summary,
                'statement_origin':'original' if meta.get('statement') else 'dsl_summary','context_requirement':meta.get('context_requirement','self_contained'),
                'context_reason':meta.get('context_reason',''),'scope_id':doc['scope_id'],'scope_type':'system' if doc['scope_id']=='system' else 'agent',
                'effective_dsl':'\n'.join([f"rule {rule['compiled_name']}:",*[c['effective_clause'] for c in rule['clauses']], '  because '+json.dumps(rule['reason'],ensure_ascii=False)]),
                'compile_status':'compiled' if refs else 'not_recorded','compiled_refs':refs,'bundle_hash':artifact.get('bundle_hash'),
                'loaded':bool(artifact.get('loaded')),'active':bool(active and refs and artifact.get('loaded'))})
    return out

def detail(scope):
    from . import controller as c
    validate_scope(scope);base=current(scope)
    with db.connect() as con:proposals=[unpack(p) for p in con.execute('SELECT * FROM instance_dsl_proposals WHERE scope_id=? ORDER BY created_at DESC LIMIT 20',(scope,))]
    records=[]
    # Candidate compilation is never described as a loading receipt.
    latest=next((p for p in proposals if p['state'] in ('applied','failed','applying') and digest(p['documents'])==base['document_hash']),None)
    if latest and latest['result']['compilations']:
        records=policy_records(latest['result']['compilations'][0],scope)
    instances=c.listing()['instances'];targets=[r for r in instances if r['mode']=='controlled' and (scope=='system' or r['id']==scope)]
    for r in records:
        bindings=[]
        for target in targets:
            saved=receipt(target['id'],target['generation'])
            expected=launch_spec(store.get(target['id']))['dsl_hash']
            matches=[x for x in policy_records(saved['artifact']) if x['source_ref']==r['source_ref'] and x['compiled_name']==r['compiled_name'] and x['original_document']==r['original_document']] if saved else []
            if saved and saved['dsl_hash']==expected and matches and matches[0]['compiled_refs']:
                bindings.append({'instance_id':target['id'],'generation':target['generation'],'domain_id':target.get('domain_id'),
                    'pid':target.get('pid'),'bundle_hash':saved['bundle_hash'],'compiled_refs':matches[0]['compiled_refs'],'active':bool(target.get('active'))})
        r.update(bindings=bindings,loaded=bool(bindings),active=bool(targets) and len(bindings)==len(targets) and all(b['active'] for b in bindings),
            application_state=latest['state'] if base['phase']=='ready' else base['phase'],
            coverage={'verified_count':sum(b['active'] for b in bindings),'total_count':len(targets),'loaded_count':len(bindings)})
    if scope!='system' and targets:
        from .sessions import legacy_records,attach_hits
        target=targets[0];row=store.get(scope);saved=receipt(scope,row['generation'])
        compat={**row,'runtime':{'compile':saved['artifact']['compile']}} if saved else row
        user_names={r['compiled_name'] for d in saved['artifact'].get('documents',[]) for r in d['rules']} if saved else set()
        records.extend({**r,'bundle_hash':saved['bundle_hash'] if saved else None} for r in legacy_records(compat,bool(target.get('active'))) if r['rule_name'] not in user_names)
        attach_hits(records,row,row['generation'])
    for record in records:record['scope_revision']=base['revision'] if record.get('document_id') else None
    return {**base,'records':records,'proposals':proposals,'targets':[{'id':t['id'],'name':t['name'],'active':t['active']} for t in targets]}
