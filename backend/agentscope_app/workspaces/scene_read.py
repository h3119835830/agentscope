"""Bounded, evidence-based Pi scene reading. This module never executes a task."""
import hashlib
import json
import os
import re
import secrets
import tempfile
import time
import uuid
from pathlib import Path
from fastapi import HTTPException
from .. import db
from ..bootstrap.scene import digest
from ..bootstrap.runner import INTEGRATION
from ..config import PUBLIC_BASE_URL, STATE_DIR
from ..agent_bridge.api import clean
from . import registry

TOOLS = ('list_scene_sources', 'read_scene_source', 'submit_scene_draft')
BUDGET = 40
SCHEMA = '''
CREATE TABLE IF NOT EXISTS workspace_scene_reads(
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, job_id TEXT NOT NULL UNIQUE,
 manifest_hash TEXT NOT NULL, manifest_json TEXT NOT NULL, source_generation TEXT,
 source_json TEXT NOT NULL, draft_json TEXT, draft_hash TEXT, task_id TEXT UNIQUE REFERENCES tasks(id),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workspace_scene_sources(
 id TEXT PRIMARY KEY, read_id TEXT NOT NULL REFERENCES workspace_scene_reads(id),
 relative_path TEXT NOT NULL, sha256 TEXT NOT NULL, kind TEXT NOT NULL,
 byte_size INTEGER NOT NULL, text TEXT, public_sha256 TEXT,
 UNIQUE(read_id,relative_path));
CREATE TABLE IF NOT EXISTS scene_read_credentials(
 read_id TEXT PRIMARY KEY REFERENCES workspace_scene_reads(id), job_id TEXT NOT NULL,
 token_hash TEXT NOT NULL, expires_at REAL NOT NULL, calls INTEGER NOT NULL DEFAULT 0, revoked_at TEXT);
CREATE TABLE IF NOT EXISTS scene_read_events(
 id INTEGER PRIMARY KEY AUTOINCREMENT, read_id TEXT NOT NULL REFERENCES workspace_scene_reads(id),
 tool TEXT NOT NULL, metadata_json TEXT NOT NULL, occurred_at TEXT NOT NULL);
'''


def init():
    with db.connect() as con:con.executescript(SCHEMA)


def public_text(value):
    value=re.sub(r'(?is)<(?:think|thinking|reasoning)>.*?</(?:think|thinking|reasoning)>','[PRIVATE CONTENT OMITTED]',value)
    value=clean(value)
    value=re.sub(r'(?i)\b(token|secret|credential|authorization|refresh[_-]?token)\s*[:=]\s*[^\s,;]+',r'\1=[REDACTED]',value)
    value=re.sub(r'(?i)(https?://)[^/@\s]+:[^/@\s]+@',r'\1[REDACTED]@',value)
    return re.sub(r'\bsk-[A-Za-z0-9_-]{12,}\b','[REDACTED]',value)


def excluded(relative):
    fn=getattr(registry,'excluded_scene_source',None)
    if fn:return fn(relative)
    parts=Path(relative).parts
    return any(p in ('.git','.dsh','.actplane','.venv','node_modules','__pycache__','.env','.credentials.yaml') or p.startswith('.env.') or re.fullmatch(r'(?i)(oracle|evaluator)(?:[._-].*)?',p) for p in parts)


def frozen_sources(con,read_id):
    rows=con.execute('SELECT * FROM workspace_scene_sources WHERE read_id=? ORDER BY relative_path',(read_id,)).fetchall()
    for row in rows:
        if row['text'] is not None and digest(row['text'])!=row['public_sha256']:raise ValueError('scene_source_integrity_failed')
    owner=con.execute('SELECT source_json FROM workspace_scene_reads WHERE id=?',(read_id,)).fetchone()
    expected=json.loads(owner[0]).get('sources_hash') if owner else None
    actual=digest([{k:r[k] for k in ('id','relative_path','sha256','kind','byte_size','public_sha256')} for r in rows])
    if not expected or expected!=actual:raise ValueError('scene_source_integrity_failed')
    return rows


def bound_read(con,workspace_id,read_id):
    row=con.execute("SELECT s.*,j.status,j.error,j.input_json,j.started_at,j.finished_at FROM workspace_scene_reads s JOIN history_jobs j ON j.id=s.job_id AND j.kind='workspace_scene_read' WHERE s.id=? AND s.workspace_id=?",(read_id,workspace_id)).fetchone()
    if not row:raise HTTPException(404,'scene_read_not_found')
    manifest=json.loads(row['manifest_json'])
    if digest(manifest['files'])!=row['manifest_hash']:raise ValueError('scene_manifest_integrity_failed')
    frozen_sources(con,read_id)
    if row['draft_json'] and digest(json.loads(row['draft_json']))!=row['draft_hash']:raise ValueError('scene_draft_integrity_failed')
    return row


def create(workspace_id,expected_manifest_hash,supplement=''):
    if not isinstance(supplement,str) or len(supplement)>8000:raise ValueError('invalid_scene_supplement')
    source=registry.get_workspace(workspace_id)
    from .observer import observer
    if source['agent_id']!='dsh':
        observer.collect(source['agent_id'])
        source=registry.get_workspace(workspace_id)
    generation=source.get('instance_generation')
    manifest,payloads=registry.scan(source['path'],with_bytes=True)
    if source['agent_id']!='dsh':observer.collect(source['agent_id'])
    fresh=registry.get_workspace(workspace_id)
    if fresh.get('instance_generation')!=generation or fresh['agent_id']!=source['agent_id'] or fresh['path']!=source['path']:raise ValueError('scene_source_generation_changed')
    if manifest['manifest_hash']!=expected_manifest_hash:raise ValueError('scene_manifest_changed')
    ident=uuid.uuid4().hex;now=db.now()
    identity={k:source.get(k) for k in ('id','agent_id','name','path','origin','native_workspace_id','instance_generation')}
    prepared=[]
    for entry in manifest['files']:
        relative=entry['relative_path']
        if excluded(relative):continue
        raw=payloads[relative]
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('scene_source_integrity_failed')
        text=public_text(raw.decode('utf-8')) if entry['kind']=='text' else None
        prepared.append((uuid.uuid4().hex,ident,relative,entry['sha256'],entry['kind'],len(raw),text,digest(text) if text is not None else None))
    if not prepared:raise ValueError('scene_has_no_project_sources')
    if supplement.strip():
        text=public_text(supplement.strip())
        prepared.append((uuid.uuid4().hex,ident,'user:supplement',digest(supplement.strip()),'user',len(supplement.strip().encode()),text,digest(text)))
    keys=('id','read_id','relative_path','sha256','kind','byte_size','text','public_sha256')
    identity['sources_hash']=digest([{k:r[k] for k in ('id','relative_path','sha256','kind','byte_size','public_sha256')} for r in sorted((dict(zip(keys,x)) for x in prepared),key=lambda r:r['relative_path'])])
    with db.connect() as con:
        con.execute('INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)',(ident,'workspace_scene_read','queued',json.dumps({'read_id':ident}),now))
        con.execute('INSERT INTO workspace_scene_reads(id,workspace_id,job_id,manifest_hash,manifest_json,source_generation,source_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(ident,workspace_id,ident,expected_manifest_hash,json.dumps(manifest),generation,json.dumps(identity),now,now))
        con.executemany('INSERT INTO workspace_scene_sources VALUES(?,?,?,?,?,?,?,?)',prepared)
    from ..history.jobs import worker
    worker.wake.set()
    return get(workspace_id,ident)


def get(workspace_id,read_id):
    with db.connect() as con:
        row=bound_read(con,workspace_id,read_id)
        receipts=[json.loads(r['metadata_json'])|{'read_at':r['occurred_at']} for r in con.execute("SELECT metadata_json,occurred_at FROM scene_read_events WHERE read_id=? AND tool='read_scene_source' ORDER BY id",(read_id,)) if json.loads(r['metadata_json']).get('status')=='ok']
        draft=json.loads(row['draft_json']) if row['draft_json'] else None
        runtime=safe_runtime(json.loads(row['input_json']).get('runtime'))
    # Worker exceptions must never disclose process output or model content.
    error='scene_read_interrupted' if row['status']=='interrupted' else 'scene_read_failed' if row['status']=='failed' else None
    return {'id':read_id,'workspace_id':workspace_id,'status':row['status'],'manifest_hash':row['manifest_hash'],'source_generation':row['source_generation'],'created_at':row['created_at'],'updated_at':max(x for x in (row['updated_at'],row['started_at'],row['finished_at']) if x),'read_only':True,'task_id':row['task_id'],'error':error,'draft':draft,'draft_hash':row['draft_hash'],'evidence':receipts,'runtime':runtime}


def adoption_preview(workspace_id,read_id,draft_hash,expected_manifest_hash):
    with db.connect() as con:
        row=bound_read(con,workspace_id,read_id)
        if row['task_id']:raise ValueError('scene_read_already_adopted')
        if row['status']!='completed' or not row['draft_json'] or row['draft_hash']!=draft_hash or row['manifest_hash']!=expected_manifest_hash:raise ValueError('scene_adoption_stale_or_incomplete')
        draft=json.loads(row['draft_json'])
        if draft['state']!='ready':raise ValueError('scene_requires_clarification')
        source=json.loads(row['source_json'])
    current=registry.get_workspace(workspace_id)
    if current.get('instance_generation')!=row['source_generation'] or current['agent_id']!=source['agent_id'] or current['path']!=source['path']:raise ValueError('scene_source_generation_changed')
    return {'id':read_id,'read_id':read_id,'workspace_id':workspace_id,'evidence':get(workspace_id,read_id)['evidence'],'draft':draft,'draft_hash':draft_hash,'manifest_hash':expected_manifest_hash,'source_generation':row['source_generation'],'source':source}


def bind_adoption(con,read_id,workspace_id,draft_hash,expected_manifest_hash,source_generation,task_id):
    row=bound_read(con,workspace_id,read_id)
    if row['status']!='completed' or not row['draft_json'] or json.loads(row['draft_json']).get('state')!='ready':raise ValueError('scene_adoption_stale_or_incomplete')
    changed=con.execute('UPDATE workspace_scene_reads SET task_id=?,updated_at=? WHERE id=? AND workspace_id=? AND draft_hash=? AND manifest_hash=? AND source_generation IS ? AND task_id IS NULL',(task_id,db.now(),read_id,workspace_id,draft_hash,expected_manifest_hash,source_generation)).rowcount
    if not changed:raise ValueError('scene_adoption_stale_or_already_bound')


def issue(read_id):
    token=secrets.token_urlsafe(36)
    with db.connect() as con:
        row=con.execute("SELECT job_id FROM workspace_scene_reads s JOIN history_jobs j ON j.id=s.job_id WHERE s.id=? AND j.kind='workspace_scene_read' AND j.status='running'",(read_id,)).fetchone()
        if not row:raise ValueError('scene_read_not_running')
        con.execute('INSERT INTO scene_read_credentials(read_id,job_id,token_hash,expires_at) VALUES(?,?,?,?)',(read_id,row['job_id'],digest(token),time.time()+240))
    return token


def revoke(read_id):
    with db.connect() as con:con.execute('UPDATE scene_read_credentials SET revoked_at=? WHERE read_id=? AND revoked_at IS NULL',(db.now(),read_id))


def event(con,read_id,tool,metadata):
    con.execute('INSERT INTO scene_read_events(read_id,tool,metadata_json,occurred_at) VALUES(?,?,?,?)',(read_id,tool,json.dumps(metadata),db.now()))


def validate_draft(con,read_id,value):
    if not isinstance(value,dict) or set(value)!={'name','goal','state','constraints','clarification','evidence'}:raise ValueError('invalid_scene_draft_schema')
    for key,maximum in (('name',120),('goal',8000),('clarification',2000)):
        if not isinstance(value[key],str) or len(value[key])>maximum:raise ValueError('invalid_scene_draft_text')
    if value['state'] not in ('ready','needs_clarification') or not value['name'].strip():raise ValueError('invalid_scene_draft_state')
    if not isinstance(value['constraints'],list) or len(value['constraints'])>30 or any(not isinstance(x,str) or not 1<=len(x)<=1000 for x in value['constraints']):raise ValueError('invalid_scene_constraints')
    if not isinstance(value['evidence'],list) or len(value['evidence'])>30:raise ValueError('invalid_scene_evidence')
    if value['state']=='ready' and (len(value['goal'].strip())<3 or not value['evidence']):raise ValueError('ready_scene_requires_goal_and_evidence')
    if value['state']=='needs_clarification' and len(value['clarification'].strip())<3:raise ValueError('scene_clarification_required')
    if not con.execute("SELECT 1 FROM scene_read_events WHERE read_id=? AND tool='list_scene_sources' AND json_extract(metadata_json,'$.status')='ok'",(read_id,)).fetchone():raise ValueError('list_scene_sources_first')
    sources={r['id']:r for r in frozen_sources(con,read_id)}
    receipts=[json.loads(r[0]) for r in con.execute("SELECT metadata_json FROM scene_read_events WHERE read_id=? AND tool='read_scene_source'",(read_id,))]
    if value['state']=='needs_clarification' and any(r['text'] is not None for r in sources.values()) and not value['evidence']:raise ValueError('scene_clarification_requires_read_evidence')
    evidence=[]
    for entry in value['evidence']:
        if not isinstance(entry,dict) or set(entry)!={'source_id','relative_path','sha256','quote'}:raise ValueError('invalid_scene_evidence_schema')
        source=sources.get(entry['source_id'])
        if not source or source['text'] is None or entry['relative_path']!=source['relative_path'] or entry['sha256']!=source['sha256']:raise ValueError('scene_evidence_source_mismatch')
        if not isinstance(entry['quote'],str) or not 1<=len(entry['quote'])<=2000:raise ValueError('invalid_scene_evidence_quote')
        quote=public_text(entry['quote']);raw=source['text'].encode();verified=False
        for receipt in receipts:
            if receipt.get('status')!='ok' or receipt.get('source_id')!=source['id'] or receipt.get('sha256')!=source['sha256']:continue
            chunk=raw[receipt['offset']:receipt['end_offset']]
            if hashlib.sha256(chunk).hexdigest()!=receipt['excerpt_sha256']:raise ValueError('scene_receipt_integrity_failed')
            if quote in chunk.decode('utf-8'):verified=True;break
        if not verified:raise ValueError('scene_quote_not_in_actual_read')
        evidence.append({**entry,'quote':quote})
    return {'name':public_text(value['name'].strip()),'goal':public_text(value['goal'].strip()),'state':value['state'],'constraints':[public_text(x) for x in value['constraints']],'clarification':public_text(value['clarification'].strip()),'evidence':evidence}


def invoke(read_id,tool,args,token):
    if tool not in TOOLS:raise HTTPException(404,'scene_tool_not_allowed')
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        credential=con.execute("SELECT c.* FROM scene_read_credentials c JOIN workspace_scene_reads s ON s.id=c.read_id JOIN history_jobs j ON j.id=s.job_id AND j.kind='workspace_scene_read' WHERE c.read_id=? AND c.token_hash=? AND c.revoked_at IS NULL AND c.expires_at>? AND j.status='running'",(read_id,digest(token),time.time())).fetchone()
        if not credential:raise HTTPException(401,'invalid_scene_read_credential')
        if not con.execute('UPDATE scene_read_credentials SET calls=calls+1 WHERE read_id=? AND calls<?',(read_id,BUDGET)).rowcount:raise HTTPException(429,'scene_tool_budget_exhausted')
        try:
            if not isinstance(args,dict):raise ValueError('invalid_scene_tool_arguments')
            if tool=='list_scene_sources':
                if args:raise ValueError('invalid_scene_tool_arguments')
                rows=frozen_sources(con,read_id)
                result={'sources':[{'source_id':r['id'],'relative_path':r['relative_path'],'sha256':r['sha256'],'kind':r['kind'],'bytes':r['byte_size'],'readable_bytes':len(r['text'].encode()) if r['text'] is not None else 0,'readable':r['text'] is not None} for r in rows],'read_only':True}
                event(con,read_id,tool,{'status':'ok','source_count':len(rows)})
            elif tool=='read_scene_source':
                if 'source_id' not in args or set(args)-{'source_id','offset','limit'}:raise ValueError('invalid_scene_tool_arguments')
                row=con.execute('SELECT * FROM workspace_scene_sources WHERE read_id=? AND id=?',(read_id,args['source_id'])).fetchone()
                if not row or row['text'] is None:raise ValueError('scene_source_not_readable')
                frozen_sources(con,read_id);raw=row['text'].encode();offset=args.get('offset',0);limit=args.get('limit',64000)
                if type(offset) is not int or type(limit) is not int or not 0<=offset<=len(raw) or not 1<=limit<=128000:raise ValueError('invalid_scene_read_range')
                end=min(offset+limit,len(raw));chunk=raw[offset:end]
                try:content=chunk.decode('utf-8')
                except UnicodeDecodeError:
                    content=None
                    for trim in range(1,min(4,len(chunk))):
                        try:content=chunk[:-trim].decode('utf-8');end-=trim;chunk=chunk[:-trim];break
                        except UnicodeDecodeError:pass
                    if content is None:raise ValueError('invalid_utf8_scene_read_boundary')
                metadata={'status':'ok','source_id':row['id'],'relative_path':row['relative_path'],'sha256':row['sha256'],'offset':offset,'end_offset':end,'byte_count':len(chunk),'excerpt_sha256':hashlib.sha256(chunk).hexdigest()}
                event(con,read_id,tool,metadata)
                result={**metadata,'content':content,'readable_bytes':len(raw),'eof':end==len(raw),'read_only':True}
            else:
                if set(args)!={'draft'}:raise ValueError('invalid_scene_tool_arguments')
                draft=validate_draft(con,read_id,args['draft']);hash_=digest(draft)
                if not con.execute('UPDATE workspace_scene_reads SET draft_json=?,draft_hash=?,updated_at=? WHERE id=? AND draft_json IS NULL',(json.dumps(draft,ensure_ascii=False),hash_,db.now(),read_id)).rowcount:raise ValueError('scene_draft_already_submitted')
                event(con,read_id,tool,{'status':'ok','draft_hash':hash_})
                result={'valid':True,'draft_hash':hash_,'state':draft['state'],'read_only':True}
        except (ValueError,KeyError,TypeError) as error:
            code=str(error) if isinstance(error,ValueError) and re.fullmatch(r'[a-z_]+',str(error)) else 'invalid_scene_tool_arguments'
            event(con,read_id,tool,{'status':'rejected','code':code})
            return {'valid':False,'diagnostic':code,'read_only':True}
    return result


def safe_runtime(value):
    if not isinstance(value,dict):return None
    constants={'package':'@earendil-works/pi-coding-agent','version':'1.0.1','model':'deepseek-flash','thinking':'off','workflow_version':'workspace-scene-read/1','sandbox':'bwrap; no project, oracle, database or task filesystem mount'}
    out={k:v for k,v in constants.items() if value.get(k)==v}
    out.update({k:value[k] for k in ('extension_hash','system_hash','lock_hash') if isinstance(value.get(k),str) and re.fullmatch('[a-f0-9]{64}',value[k])})
    if value.get('allowed_tools')==list(TOOLS):out['allowed_tools']=list(TOOLS)
    life=value.get('lifecycle',{})
    if isinstance(life,dict):
        safe={}
        if type(life.get('continuations')) is int and 0<=life['continuations']<=2:safe['continuations']=life['continuations']
        if life.get('protocol')=='Pi RPC agent_settled; server submission verified':safe['protocol']=life['protocol']
        if safe:out['lifecycle']=safe
    return out


def runtime_manifest():
    return {'package':'@earendil-works/pi-coding-agent','version':'1.0.1','model':'deepseek-flash','thinking':'off','workflow_version':'workspace-scene-read/1','extension_hash':digest((INTEGRATION/'scene-read-extension.ts').read_text()),'system_hash':digest((INTEGRATION/'scene-read-system.md').read_text()),'lock_hash':digest((INTEGRATION/'package-lock.json').read_text()),'allowed_tools':list(TOOLS),'sandbox':'bwrap; no project, oracle, database or task filesystem mount'}


def run(read_id):
    try:return _run(read_id)
    except Exception:raise ValueError('scene_read_failed') from None
    finally:revoke(read_id)


def _run(read_id):
    runtime=runtime_manifest()
    with db.connect() as con:
        row=con.execute('SELECT workspace_id,job_id FROM workspace_scene_reads WHERE id=?',(read_id,)).fetchone()
        if not row:raise ValueError('scene_read_not_found')
        bound_read(con,row['workspace_id'],read_id)
        con.execute('UPDATE history_jobs SET input_json=? WHERE id=?',(json.dumps({'read_id':read_id,'runtime':runtime}),row['job_id']))
    package=json.loads((INTEGRATION/'node_modules/@earendil-works/pi-coding-agent/package.json').read_text())
    if package['version']!='1.0.1':raise ValueError('scene_pi_runtime_mismatch')
    key=os.getenv('AGENTSCOPE_HISTORY_LLM_KEY') or os.getenv('DEEPSEEK_API_KEY')
    if not key:raise ValueError('scene_pi_credential_not_configured')
    token=issue(read_id);root=STATE_DIR/'pi-scene-jobs';root.mkdir(mode=0o700,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=read_id+'-',dir=root) as directory:
        agent=Path(directory)/'agent';agent.mkdir(mode=0o700)
        model={'providers':{'agentscope-deepseek':{'baseUrl':os.getenv('AGENTSCOPE_HISTORY_LLM_URL','https://api.deepseek.com'),'api':'openai-completions','apiKey':'${DEEPSEEK_API_KEY}','models':[{'id':'deepseek-flash','reasoning':False,'contextWindow':1000000,'maxTokens':12000,'compat':{'supportsStore':False,'supportsDeveloperRole':False,'supportsReasoningEffort':False}}]}}}
        (agent/'models.json').write_text(json.dumps(model));(agent/'settings.json').write_text(json.dumps({'packages':[],'defaultThinkingLevel':'off','checkForUpdates':False}))
        environment={'PATH':'/usr/bin:/bin','HOME':'/home/pi','PI_CODING_AGENT_DIR':'/home/pi/agent','LANG':'C.UTF-8','DEEPSEEK_API_KEY':key,'AGENTSCOPE_SCENE_READ_TOKEN':token,'AGENTSCOPE_SCENE_READ_ID':read_id,'AGENTSCOPE_SCENE_READ_URL':PUBLIC_BASE_URL}
        cli=['/runtime/node','/pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js','--mode','rpc','--no-session','--provider','agentscope-deepseek','--model','deepseek-flash','--thinking','off','--no-builtin-tools','--tools',','.join(TOOLS),'--no-extensions','--extension','/pi/scene-read-extension.ts','--no-skills','--no-context-files','--no-prompt-templates','--no-themes','--no-approve','--offline','--system-prompt','/pi/scene-read-system.md']
        command=['/usr/bin/bwrap','--die-with-parent','--unshare-pid','--unshare-ipc','--unshare-uts','--ro-bind','/usr','/usr','--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64','--ro-bind','/etc/ssl','/etc/ssl','--ro-bind','/etc/resolv.conf','/etc/resolv.conf','--ro-bind','/etc/hosts','/etc/hosts','--ro-bind','/opt/agentscope/bin/node','/runtime/node','--dir','/pi','--ro-bind',str(INTEGRATION/'scene-read-extension.ts'),'/pi/scene-read-extension.ts','--ro-bind',str(INTEGRATION/'scene-read-system.md'),'/pi/scene-read-system.md','--ro-bind',str((INTEGRATION/'node_modules').resolve(strict=True)),'/pi/node_modules','--bind',directory,'/home/pi','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--chdir','/home/pi','--',*cli]
        def status():
            with db.connect() as con:
                job=con.execute('SELECT status FROM history_jobs WHERE id=?',(read_id,)).fetchone();draft=con.execute('SELECT draft_hash FROM workspace_scene_reads WHERE id=?',(read_id,)).fetchone();calls=con.execute('SELECT calls FROM scene_read_credentials WHERE read_id=?',(read_id,)).fetchone()
            return {'cancelled':not job or job[0]!='running','submitted':bool(draft and draft[0]),'submission':'present' if draft and draft[0] else 'absent','remaining_tool_calls':BUDGET-(calls[0] if calls else BUDGET)}
        def trace(value):
            # pi_rpc offers raw args/diagnostics: retain none of those strings.
            metadata={'kind':value.get('kind') if value.get('kind') in ('tool_start','tool_end','workflow_continuation') else 'unknown','status':'error' if value.get('error') else 'recorded'}
            if value.get('tool') in TOOLS:metadata['tool']=value['tool']
            with db.connect() as con:event(con,read_id,'rpc_lifecycle',metadata)
        from ..pi_rpc import drive
        lifecycle=drive(command,environment,'Read the registered workspace evidence with your three tools, identify only a supported task goal, and submit one public scene draft. If the goal is not explicit, ask for clarification. Do not execute anything.',status,trace)
        runtime['lifecycle']={k:v for k,v in lifecycle.items() if k in ('continuations','protocol') and (type(v) is int or (k=='protocol' and v=='Pi RPC agent_settled; server submission verified'))}
    if runtime_manifest()!= {k:v for k,v in runtime.items() if k!='lifecycle'}:raise ValueError('scene_pi_integration_changed')
    with db.connect() as con:
        row=con.execute('SELECT draft_hash FROM workspace_scene_reads WHERE id=?',(read_id,)).fetchone()
        if not row or not row[0]:raise ValueError('scene_pi_no_submission')
        con.execute('UPDATE history_jobs SET input_json=? WHERE id=?',(json.dumps({'read_id':read_id,'runtime':runtime}),read_id))
    return {'draft_hash':row[0],'read_only':True,'runtime':runtime}
