"""Managed native DSH sessions: immutable safety baseline and evidence-bound updates."""
import hashlib, json, threading, time, uuid, os, stat, re
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from .. import db
from ..broker_client import call as broker
from ..bootstrap.scene import context, create_scene, digest
from ..services.policy import make_dsl, quote_dsl
from ..scope.manager import lock

class IdentifiedStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=3,max_length=2000)
    context_required: bool
    context_reason: str = Field(min_length=3,max_length=500)
    policy_type: Literal["per_event","cross_event","content","semantic_only"]
    evidence_ids: list[str] = Field(min_length=1,max_length=30)

class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["restrict", "expand", "guidance_only", "no_change"]
    allowed_write_dirs: list[str] = Field(max_length=1)
    allow_output: bool
    protected_paths: list[str] | None = Field(default=None,max_length=30)
    evidence_ids: list[str] = Field(min_length=1, max_length=30)
    explanation: str = Field(min_length=4, max_length=2000)
    unresolved_requests: list[str] = Field(default_factory=list,max_length=30)
    identified_statements: list[IdentifiedStatement] = Field(default_factory=list,max_length=20)


def save(con, task_id, state):
    con.execute("INSERT INTO managed_tasks VALUES(?,?,?) ON CONFLICT(task_id) DO UPDATE SET state_json=excluded.state_json,updated_at=excluded.updated_at", (task_id,json.dumps(state,ensure_ascii=False),db.now()))

def load(con, task_id):
    row=con.execute("SELECT state_json FROM managed_tasks WHERE task_id=?",(task_id,)).fetchone()
    if not row: raise ValueError("任务没有启用受管 DSH 网页")
    return json.loads(row[0])

def exists(task_id):
    with db.connect() as con:return bool(con.execute("SELECT 1 FROM managed_tasks WHERE task_id=?",(task_id,)).fetchone())

def event(con, task_id, kind, key, payload):
    con.execute("INSERT OR IGNORE INTO managed_events(task_id,kind,event_key,payload_json,occurred_at) VALUES(?,?,?,?,?)",(task_id,kind,key,json.dumps(payload,ensure_ascii=False),db.now()))

def create(case):
    result=create_scene(case, workspace_leaf="r", compact_paths=True)
    task_id=result["id"]
    with db.connect() as con:
        ctx=context(task_id,con)
        ctx["dsh"]["surface"]="managed-native-web"
        ctx["dsh"]["executor_sandbox"]={'version':2,'filesystem':'project,temporary,output and public runtime only','network':'isolated','policy_visibility':'operation_feedback_only'}
        old_python=ctx['dsh'].get('python_runtime',{}).get('python')
        if old_python:ctx['environment']=ctx['environment'].replace(old_python,'/opt/task-python/bin/python')
        ctx['environment_hash']=digest(ctx['environment'])
        con.execute("UPDATE bootstrap_sources SET text=?,content_hash=? WHERE task_id=? AND role='environment'",(ctx['environment'],ctx['environment_hash'],task_id))
        ctx["evaluation"]="Engineering extension: task plus registered project evidence; independent evaluator excluded"
        con.execute("UPDATE bootstrap_contexts SET context_json=?,context_hash=? WHERE task_id=?",(json.dumps(ctx),digest(ctx),task_id))
        cfg=json.dumps(ctx["dsh"],sort_keys=True)
        con.execute("UPDATE bootstrap_sources SET text=?,content_hash=? WHERE task_id=? AND role='dsh_config'",(cfg,digest(cfg),task_id))
        con.execute("UPDATE tasks SET dsh_profile='web' WHERE id=?",(task_id,))
        save(con,task_id,{"phase":"prepared","gate":"closed","revision":0,"version":0,"session_id":None,"turn":0,"allow_output":False,"allowed_write_dirs":["."],"policy_hash":"","startup_job":None,"binding":{},"protected":[],"pending_expansion":None})
        event(con,task_id,"created",task_id,{"workspace":ctx["workspace"],"context_hash":digest(ctx)})
    return {**result,"context_hash":digest(ctx),"managed":True}

def get(task_id):
    with db.connect() as con:
        state=load(con,task_id)
        events=[db.row_dict(r) for r in con.execute("SELECT * FROM managed_events WHERE task_id=? ORDER BY id DESC LIMIT 300",(task_id,))]
        jobs=[db.row_dict(r) for r in con.execute("SELECT id,status,revision,proposal_json,error,created_at FROM managed_jobs WHERE task_id=? ORDER BY created_at DESC LIMIT 40",(task_id,))]
    try: execution=broker({"action":"status","task_id":task_id})
    except Exception:execution={"status":"unavailable"}
    effective=state["phase"]=="running" and state["gate"]=="open" and execution.get("status")=="running" and execution.get("domain_id")==state["binding"].get("domain_id")
    return {"state":state,"events":events,"jobs":jobs,"execution":execution,"effective":effective}

def policy_details(task_id):
    with db.connect() as con:
        state=load(con,task_id);task=task_row(con,task_id)
    dsl,yaml=render(task,state,state['allowed_write_dirs'],state['allow_output'])
    if digest(yaml)!=state['policy_hash']:raise ValueError('Policy source does not match the confirmed loaded hash')
    return {'version':state['version'],'policy_hash':state['policy_hash'],'baseline_hash':state['baseline_hash'],'dsl':dsl,'policy_yaml':yaml,'binding':state['binding'],'verification':state['verification'],'session_id':state['session_id'],'historical':state['phase']=='ended','authority':'serialized_policy_matches_confirmed_loaded_hash'}

AUDIT_KINDS=('kernel','request','candidate','policy_active','tool_result','feedback_delivery','agent_response','failure','closed','operation_verified','agent_refusal','agent_deferral','control_pause')

def audit_history(task_id,category='all',before=None):
    predicates=["task_id=?","kind IN ("+','.join('?' for _ in AUDIT_KINDS)+")","NOT (kind='kernel' AND COALESCE(json_extract(payload_json,'$.verification_probe'),0)=1)"]
    params=[task_id,*AUDIT_KINDS]
    if category=='allowed':
        predicates.extend(["kind='operation_verified'","json_extract(payload_json,'$.classification')='correct_allow'"])
    elif category!='all':predicates.append('kind=?');params.append(category)
    if before is not None:predicates.append('id<?');params.append(before)
    with db.connect() as con:
        load(con,task_id)
        rows=[db.row_dict(r) for r in con.execute('SELECT * FROM managed_events WHERE '+' AND '.join(predicates)+' ORDER BY id DESC LIMIT 51',params)]
    return {'events':rows[:50],'next_cursor':rows[49]['id'] if len(rows)>50 else None,'category':category}

def clarify_startup(task_id,text,key):
    """Register a real startup clarification while retaining the original task."""
    with lock(task_id),db.connect() as con:
        state=load(con,task_id)
        if state['phase']!='failed' or state['version']!=0:raise ValueError('Startup clarification requires a paused task with no loaded policy')
        previous=state.get('startup_job')
        if previous:
            con.execute("UPDATE history_jobs SET status='interrupted' WHERE id=? AND status IN ('queued','running')",(previous,))
        con.execute('UPDATE bootstrap_credentials SET revoked_at=?,expires_at=0 WHERE task_id=? AND revoked_at IS NULL',(db.now(),task_id))
        ctx=context(task_id,con);ctx.pop('context_hash',None)
        clarifications=ctx.setdefault('startup_clarifications',[])
        if any(x['request_key']==key for x in clarifications):raise ValueError('Clarification already registered')
        source_id=uuid.uuid4().hex
        clarifications.append({'source_id':source_id,'text':text,'request_key':key,'authority':'authenticated_administrator'})
        payload='Authenticated startup clarification (supplements the original task; does not weaken platform constraints):\n'+text
        con.execute('INSERT INTO bootstrap_sources VALUES(?,?,?,?,?,?,?)',(source_id,task_id,'task','',payload,digest(payload),json.dumps({'authority':'authenticated_administrator','request_key':key})))
        con.execute('UPDATE bootstrap_contexts SET context_json=?,context_hash=? WHERE task_id=?',(json.dumps(ctx),digest(ctx),task_id))
        state.update(phase='prepared',gate='closed',startup_job=None,revision=state['revision']+1)
        state.pop('error',None);save(con,task_id,state)
        con.execute("UPDATE tasks SET status='prepared',updated_at=? WHERE id=?",(db.now(),task_id))
        event(con,task_id,'startup_clarification',key,{'source_id':source_id,'context_hash':digest(ctx),'revision':state['revision'],'text':text})
    return start(task_id)

def start(task_id):
    from ..bootstrap.api import bootstrap
    with lock(task_id),db.connect() as con:
        state=load(con,task_id)
        if state["phase"]=="failed" and state["version"]>0:
            if state.get('execution_role_version')!=2:raise ValueError('This legacy session contains policy context. Create a fresh task sandbox; historical evidence is retained.')
            state.update(phase="recovering",gate="waiting_policy");save(con,task_id,state)
            event(con,task_id,"recovery_requested",uuid.uuid4().hex,{"session_id":state["session_id"],"version":state["version"]})
            return {"status":"recovering_verified_session"}
        if state["phase"]=="failed" and state["version"]==0 and state.get("startup_job"):
            job=con.execute("SELECT status FROM history_jobs WHERE id=?",(state["startup_job"],)).fetchone()
            if job and job["status"]=="completed":
                state.update(phase="generating",gate="waiting_policy");save(con,task_id,state)
                return {"job_id":state["startup_job"],"status":"retrying_validated_startup"}
        if state["phase"]!="prepared":raise ValueError("任务已启动或需要重新创建")
        con.execute("UPDATE tasks SET status='prepared',updated_at=? WHERE id=?",(db.now(),task_id))
    job=bootstrap(task_id)
    with db.connect() as con:
        state.update(phase="generating",gate="waiting_policy",startup_job=job["id"])
        save(con,task_id,state)
        event(con,task_id,"startup_generation",job["id"],{"job_id":job["id"]})
    return {"job_id":job["id"],"status":"generating"}

def protected_files(ctx, atoms):
    paths=[]
    for asset in ctx["assets"]:
        path=asset["mapped_path"]
        if any(path==p or (p.endswith('/**') and path.startswith(p[:-2])) for atom in atoms for p in atom['paths']):paths.append(path)
    return sorted(set(paths))

def control_rules(task):
    ws=task['workspace'];home=str(Path(ws).parent/'.dsh')
    paths=[ws,ws+'/.actplane',ws+'/.actplane/**',home+'/profiles',home+'/profiles/web',home+'/profiles/web/node_modules',home+'/settings.yaml',home+'/.credentials.yaml',home+'/cordis.patch.yml',home+'/profiles/web/package.json',home+'/profiles/web/cordis.patch.yml',home+'/profiles/web/node_modules/**']
    source_root=str(Path(__file__).resolve().parents[3]);probe_code=source_root+'/backend/broker/managed_*'
    # Kernel matchers lower absolute internal globs to a prefix. Resolve service
    # roots/files first, so a DB suffix cannot silently block public runtimes.
    state_roots={Path('/var/lib/agentscope-scope-demo'),Path('/var/lib/agentscope-rq5-v1'),Path(db.DB_PATH).parent}
    state_roots.update(p for p in Path('/var/lib').glob('agentscope-*') if p.is_dir())
    private_reads=['  block read file '+quote_dsl('/opt/agentscope/actplane/**')+' if AGENT']
    for base in sorted(state_roots):
        # These are dedicated control-state directories, not project roots.
        # The separately published Python runtime is the only public subtree.
        runtime=base/'task-python' if base==Path('/var/lib/agentscope-rq5-v1') else None
        exception=' unless target '+quote_dsl(str(runtime)+'/**') if runtime else ''
        private_reads.append('  block read file '+quote_dsl(str(base)+'/**')+' if AGENT'+exception)
    return '\n'.join(['rule managed-control-assets:',f'  block read file {quote_dsl(source_root+"/**")} if AGENT unless target {quote_dsl(probe_code)}',*private_reads,'  block read file '+quote_dsl(ws+'/.actplane/**')+' if AGENT',*[f'  block {op} file {quote_dsl(p)} if AGENT' for p in paths for op in ('write','unlink')],'  block read file '+quote_dsl(str(Path(ws).parent.parent)+'/**')+' if AGENT unless target '+quote_dsl(str(Path(ws).parent)+'/**'),'  because "Execution gates, credentials and kernel evidence are immutable; other tasks are isolated."'])

def identity_guards(workspace,targets):
    root=Path(workspace);parents=set()
    for target in targets:
        directory=str(target).endswith('/**')
        path=Path(str(target)[:-3] if directory else str(target))
        current=path if directory else path.parent
        while current!=root and root in current.parents:
            parents.add(str(current));current=current.parent
    if not parents:return ''
    return '\nrule managed-path-identity:\n'+'\n'.join(f'  block {op} file {quote_dsl(p)} if AGENT' for p in sorted(parents) for op in ('write','unlink'))+'\n  because "Preserve protected object identity by preventing ancestor directory replacement; adjacent file operations remain available."\n'

def render(task,state,dirs,output,protected_paths=None):
    if len(dirs)>1:raise ValueError('本版本运行时允许一个连续可写子树')
    extra=state['baseline_extra']
    targets=state.get('runtime_protected',[]) if protected_paths is None else protected_paths
    extra+=identity_guards(task['workspace'],state.get('protected',[])+[task['workspace']+'/'+p for p in targets])
    if targets:
        extra+='\nrule runtime-file-protection:\n'+'\n'.join(f'  block {op} file {quote_dsl(task["workspace"]+"/"+p)} if AGENT' for p in targets for op in ('write','unlink'))+'\n  because "Runtime task evidence requires preserving these registered objects."\n'
    if dirs!=['.']:
        target=task['workspace']+'/'+dirs[0]+'/**' if dirs else None
        exception=' unless target '+quote_dsl(target) if target else ''
        extra+='\nrule managed-write-scope:\n'+ '\n'.join(f'  block {op} file {quote_dsl(task["workspace"]+"/**")} if AGENT{exception}' for op in ('write','unlink'))+'\n  because "Runtime task writes are restricted to the confirmed subtree."\n'
    return make_dsl(task['workspace'],task['output_dir'],{'allow_task_output':output},extra)

def task_row(con,task_id):return dict(con.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone())

_lifecycle_locks={}
def lifecycle(task_id):return _lifecycle_locks.setdefault(task_id,threading.RLock())

def install(task_id,state,dirs,output,initial=False,protected_paths=None):
    with lifecycle(task_id):
        with db.connect() as con:current=load(con,task_id)
        if current['phase'] not in (('generating','recovering') if initial else ('running',)) or current['revision']!=state['revision'] or current['version']!=state['version']:
            raise ValueError('stale: task changed or ended before policy installation')
        return _install(task_id,state,dirs,output,initial,protected_paths)

def _install(task_id,state,dirs,output,initial=False,protected_paths=None):
    from ..main import issue_task_token,revoke_task_tokens
    with db.connect() as con:task=task_row(con,task_id)
    runtime_protected=state.get('runtime_protected',[]) if protected_paths is None else protected_paths
    dsl,yaml=render(task,state,dirs,output,runtime_protected)
    resume_text=None
    if not initial:
        native_state=broker({'action':'native-session','task_id':task_id,'operation':'inspect','session_id':state['session_id']},timeout=15)
        if native_state.get('status')=='running':
            with db.connect() as con:
                rows=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='request' ORDER BY id DESC",(task_id,)).fetchall()
                request=next((json.loads(r[0]) for r in rows if json.loads(r[0]).get('actor')=='native_user'),None)
                if request:resume_text=request['text']
        broker({'action':'native-session','task_id':task_id,'operation':'cancel','session_id':state['session_id']},timeout=15)
        broker({'action':'native-session','task_id':task_id,'operation':'flush','session_id':state['session_id']},timeout=35)
        broker({'action':'stop','task_id':task_id},timeout=20)
        revoke_task_tokens(task_id)
    token,_=issue_task_token(task_id)
    version=state['version']+1
    try:
        receipt=broker({'action':'launch','task_id':task_id,'version':10000+version,'workspace':task['workspace'],'output_dir':task['output_dir'],'prompt':task['prompt'],'dsl_text':dsl,'policy_yaml':yaml,'dsh_profile':'web','task_token':token,'agentscope_url':__import__('agentscope_app.config',fromlist=['PUBLIC_BASE_URL']).PUBLIC_BASE_URL,'scope_mode':'managed-web','protected_files':state['protected'],'baseline_dsl':make_dsl(task['workspace'],task['output_dir'],{'allow_task_output':True},state['baseline_extra']+identity_guards(task['workspace'],state.get('protected',[])))[0]},timeout=60)
        native=broker({'action':'native-session','task_id':task_id,'operation':'create','session_id':state['session_id']},timeout=35)
        verify=broker({'action':'managed-verify','task_id':task_id,'protected_files':sorted(set(state['protected']+[str(p) for target in runtime_protected for p in Path(task['workspace']).glob(target) if p.is_file()])),'allow_path':task['workspace']+'/'+(dirs[0]+'/' if dirs and dirs!=['.'] else '')+'.managed-allow-probe'},timeout=45)
        binding=broker({'action':'status','task_id':task_id})
        if not verify['passed'] or binding['status']!='running' or binding['domain_id']!=receipt['domain_id']:
            with db.connect() as con:event(con,task_id,'verification_failed',uuid.uuid4().hex,{'verification':verify,'binding':binding})
            raise ValueError('进程域或实际文件权限核验失败')
    except Exception as error:
        try:broker({'action':'stop','task_id':task_id},timeout=20)
        finally:
            revoke_task_tokens(task_id)
            with lock(task_id),db.connect() as con:
                current=load(con,task_id)
                if current['phase']!='ended':
                    current.update(phase='failed',gate='failed',error=str(error)[:1500]);save(con,task_id,current)
                    con.execute("UPDATE tasks SET status='failed',active_pid=NULL,active_domain_id=NULL,watch_pid=NULL,updated_at=? WHERE id=?",(db.now(),task_id))
                    event(con,task_id,'failure',uuid.uuid4().hex,{'error':current['error'],'replacement_stopped':True,'before_native_admission':True})
        raise
    state.setdefault('binding_history',[]).append({'domain_id':receipt['domain_id'],'version':version})
    state.setdefault('probe_pids',[]).append(verify['probe']['pid'])
    state.pop('error',None)
    recovery=state['phase']=='recovering'
    if recovery and state.get('pending_expansion'):
        prior=state['pending_expansion'];proposal=prior['proposal']
        state['pending_expansion_intent']={'prior_hash':prior['hash'],'proposed_snapshot':{k:proposal.get(k) for k in ('allowed_write_dirs','allow_output','protected_paths')},'authority':'unapproved_candidate; never_a_grant','reason':'Native recovery invalidates a candidate hash but does not withdraw the authenticated pending request; revalidate before confirmation.'}
    state.update(execution_role_version=2,phase='running',gate='waiting_policy' if recovery else 'open',version=version,policy_hash=digest(yaml),allowed_write_dirs=dirs,allow_output=output,runtime_protected=runtime_protected,binding=receipt,verification=verify,session_id=native['sessionId'],web_url=receipt['web_url'],pending_expansion=None)
    with lock(task_id),db.connect() as con:
        current=load(con,task_id)
        if current['revision']!=state['revision'] or current['phase']=='ended':
            broker({'action':'stop','task_id':task_id},timeout=20);revoke_task_tokens(task_id)
            if current['phase']!='ended':
                current.update(phase='failed',gate='failed',error='Public input changed during domain replacement; reassess the latest input before recovery.');save(con,task_id,current)
                con.execute("UPDATE tasks SET status='failed',active_pid=NULL,active_domain_id=NULL,watch_pid=NULL,updated_at=? WHERE id=?",(db.now(),task_id))
                event(con,task_id,'failure',uuid.uuid4().hex,{'error':current['error'],'revision':current['revision'],'replacement_stopped':True})
            con.commit()  # retain fail-closed state when propagating the stale error
            raise ValueError('stale: context changed while replacing the process domain')
        save(con,task_id,state)
        con.execute("UPDATE tasks SET status='running',active_pid=?,active_domain_id=?,watch_pid=?,active_version=?,updated_at=? WHERE id=?",(receipt['runner_pid'],receipt['domain_id'],receipt['watch_pid'],version,db.now(),task_id))
        event(con,task_id,'policy_active',str(version),{'version':version,'policy_hash':state['policy_hash'],'binding':receipt,'verification':verify,'session_id':state['session_id'],'baseline_hash':state['baseline_hash']})
    if resume_text:
        broker({'action':'native-session','task_id':task_id,'operation':'resume','session_id':state['session_id'],'text':'[Execution resumed] Continue the interrupted task request. Original request: '+resume_text},timeout=20)
        with db.connect() as con:event(con,task_id,'session_resumed',str(version),{'session_id':state['session_id'],'version':version,'source':'context','original_request_preserved':True})
    return state

def recover(task_id):
    with lock(task_id),db.connect() as con:
        state=load(con,task_id)
        if state['phase']!='recovering':return
    # Previous failed domain was stopped and credentials revoked. Restore only
    # its already-confirmed scope, with the sealed startup manifest unchanged.
    installed=install(task_id,state,state['allowed_write_dirs'],state['allow_output'],initial=True)
    with lock(task_id),db.connect() as con:
        current=load(con,task_id)
        rows=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='request' ORDER BY id DESC",(task_id,)).fetchall()
        latest=next((json.loads(r[0])['text'] for r in rows if json.loads(r[0]).get('actor')=='native_user'),task_row(con,task_id)['prompt'])
        enqueue(con,task_id,current,latest,'recovery:'+uuid.uuid4().hex,kind='message',actor='recovery')
        event(con,task_id,'recovery_reassessment',str(current['revision']),{'session_id':current['session_id'],'revision':current['revision'],'gate':'waiting_policy'})
    ctext='[Execution resumed] The task execution environment recovered. Continue the latest task request after execution resumes. Latest request: '+latest
    broker({'action':'native-session','task_id':task_id,'operation':'resume','session_id':installed['session_id'],'text':ctext},timeout=20)

def complete_start(task_id):
    from ..bootstrap.api import version as make_version
    from ..bootstrap.models import VersionRequest
    from ..main import approve_version,ReviewRequest
    with lock(task_id),db.connect() as con:
        state=load(con,task_id)
        job=con.execute('SELECT status,error FROM history_jobs WHERE id=?',(state['startup_job'],)).fetchone()
        if not job or job['status'] in ('queued','running'):return
        if job['status']!='completed':raise ValueError('启动 Pi 作业失败: '+str(job['error']))
        proposal=con.execute("SELECT * FROM bootstrap_proposals WHERE job_id=? AND state='validated'",(state['startup_job'],)).fetchone()
        if not proposal:raise ValueError('启动策略未通过校验或仍需澄清')
        proposal=dict(proposal);ctx=context(task_id,con);task=task_row(con,task_id)
    built=make_version(task_id,proposal['id'],VersionRequest(condition='B'))
    approve_version(task_id,built['version'],ReviewRequest(decision='approve',reviewed_by='预授权控制面',expected_context_hash=ctx['context_hash'],expected_proposal_hash=proposal['content_hash']))
    data=json.loads(proposal['proposal_json'])
    state.update(baseline_extra=data['actplane_dsl']+'\n'+control_rules(task),protected=protected_files(ctx,data['draft']['atoms']),baseline_hash=digest({'extra':data['actplane_dsl'],'context':ctx['context_hash'],'controls':control_rules(task)}),startup_proposal=proposal['id'],startup_summary=data['draft']['summary'])
    with db.connect() as con:save(con,task_id,state)
    installed=install(task_id,state,['.'],False,initial=True)
    # Admission uses the native SessionController; no headless substitute session.
    broker({'action':'native-session','task_id':task_id,'operation':'prompt','session_id':installed['session_id'],'text':ctx['environment']+'\n[Workspace paths]\n'+json.dumps({'workspace':task['workspace'],'output':task['output_dir'],'temporary':str(Path(task['workspace']).parent/'tmp')})+'\n[Platform constraints]\n'+ctx['platform_constraints']+'\n[Registered project files]\n'+json.dumps([a['mapped_path'] for a in ctx['assets']])+'\n[Execution environment]\nUse the task workspace, temporary and output paths, and the published Python runtime. Host files and network access are unavailable. Respond to operation feedback while completing the task.\n[Original task description]\n'+task['prompt']+'\n[Authenticated startup clarifications]\n'+json.dumps(ctx.get('startup_clarifications',[]),ensure_ascii=False)+'\n[Admission request]\nRead the task and relevant registered project materials first. Summarize the constraints and proposed work; wait for the next real user message before modifying files.'},timeout=20)

def gate(task_id):
    with db.connect() as con:s=load(con,task_id)
    return {'gate':s['gate'],'phase':s['phase']}

def read_project_content(task,path):
    path=Path(path);relative=path.relative_to(Path(task['workspace']))
    if not relative.parts or any(p in ('.','..','.actplane','.git','.dsh') for p in relative.parts):raise ValueError('Source path outside project material')
    directory=None
    try:
        directory=os.open(task['workspace'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        for part in relative.parts[:-1]:
            next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory);directory=next_fd
        fd=os.open(relative.parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        with os.fdopen(fd,'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('Source must be a regular file')
            raw=stream.read(16*1024*1024+1)
        if len(raw)>16*1024*1024:raise ValueError('Source is too large')
        return {'hash':hashlib.sha256(raw).hexdigest(),'content':raw.decode('utf-8',errors='replace')[:8000]}
    except PermissionError:
        return broker({'action':'managed-source-read','task_id':task['id'],'path':str(relative)},timeout=10)
    finally:
        if directory is not None:os.close(directory)

def project_source(task,path):
    path=Path(path);value=read_project_content(task,path)
    return {'id':str(path.relative_to(Path(task['workspace']))),'path':str(path),'hash':value['hash'],'content':value['content'],'authority':'untrusted_project_context'}

def restriction_authorizations(requests,unassessed,files,directories,workspace):
    """Bind automatic restrictions to explicit authenticated OS-target clauses.

    Project reads resolve identities, but never authorize a new restriction.
    Semantic-only requests may remain guidance; necessary unresolved OS constraints hold tools.
    """
    protections={};scopes=set()
    directive=re.compile(r'(?<![不受已被])保护|(?<![不已])保留|不得(?:写|删|修)|禁止(?:写|删|修)|不要(?:写|删|修)|\b(?:protect|preserve|retain)\b|(?:must not|do not|never)\s+(?:write|delete|modify)',re.I)
    withdraw=re.compile(r'不(?:再|要|用|需要)(?:保护|保留)|无需(?:保护|保留)|取消保护|解除保护|do not (?:protect|preserve|retain)|remove (?:the )?protection',re.I)
    scope_directive=re.compile(r'写入范围|只允许写|只能写|仅可写|restrict.*writ|writ.*only|only.*writ',re.I)
    tree_directive=re.compile(r'目录|文件夹|整个|directory|folder|subtree|tree|/\*\*',re.I)
    def mentions(text,path):
        return bool(re.search(r'(?<![A-Za-z0-9_])'+re.escape(path)+r'(?![A-Za-z0-9_/.-])',text))
    for request in requests:
        if request.get('actor') not in ('native_user','administrator') or request['evidence_id'] not in unassessed:continue
        for clause in re.split(r'[\n。；;，,]|\.(?=\s|$)',request['text']):
            if withdraw.search(clause):continue
            if scope_directive.search(clause):
                scopes.update(d for d in directories if d!='.' and (mentions(clause,d) or mentions(clause,workspace+'/'+d)))
            if not directive.search(clause):continue
            for path in files:
                explicit=mentions(clause,path) or mentions(clause,workspace+'/'+path)
                basename=Path(path).name
                unambiguous=sum(Path(other).name==basename for other in files)==1
                if explicit or unambiguous and mentions(clause,basename):
                    protections.setdefault(path,[]).append({'request_id':request['evidence_id'],'quote':clause.strip(),'authority':'explicit_authenticated_target_clause'})
            if tree_directive.search(clause):
                for directory in directories:
                    if directory!='.' and (mentions(clause,directory) or mentions(clause,workspace+'/'+directory) or mentions(clause,directory+'/**') or mentions(clause,workspace+'/'+directory+'/**')):
                        protections.setdefault(directory+'/**',[]).append({'request_id':request['evidence_id'],'quote':clause.strip(),'authority':'explicit_authenticated_subtree_clause'})
    return protections,sorted(scopes)

def runtime_projection(frozen):
    current=frozen['base_snapshot']['payload']
    resolved=set(frozen.get('resolved_request_ids',[]))
    public=[{**item,'assessment_status':'resolved' if item['evidence_id'] in resolved else 'unassessed','authority':'authenticated_request' if item.get('actor') in ('native_user','administrator') else 'agent_report_at_observed_revision; not_current_state_or_authorization'} for item in frozen.get('public_task_context',[])]
    return {'schema':frozen['schema'],'effective_policy':{'authority':'controller_verified_loaded_snapshot','revision':frozen['revision'],'policy_hash':frozen['policy_hash'],'binding':frozen.get('current_binding'),'snapshot':current,'execution_targets':frozen['capabilities'].get('execution_targets',[])},
            **frozen,'public_task_context':public,'project_sources':[{k:v for k,v in source.items() if k!='content'} for source in frozen.get('project_sources',[])]}

def enqueue(con,task_id,state,text,key,kind='message',actor='native_user'):
    if state['phase'] not in ('running','generating'):raise ValueError('任务尚未运行或已经结束')
    old=con.execute('SELECT id FROM managed_jobs WHERE task_id=? AND request_key=?',(task_id,key)).fetchone()
    if old:return {'id':old[0]}
    state['revision']+=1
    if actor in ('native_user','administrator'):state.pop('pending_expansion_intent',None)
    elif state.get('pending_expansion'):
        prior=state['pending_expansion'];proposal=prior['proposal']
        state['pending_expansion_intent']={'prior_hash':prior['hash'],'origin_revision':state['revision']-1,'proposed_snapshot':{k:proposal.get(k) for k in ('allowed_write_dirs','allow_output','protected_paths')},'authority':'unapproved_candidate; never_a_grant','reason':'Operational feedback or a DSH permission request invalidates the candidate hash, but does not withdraw the pending review intent.'}
    state['pending_expansion']=None
    con.execute("UPDATE managed_jobs SET status='stale',token_hash=NULL WHERE task_id=? AND status IN ('queued','running')",(task_id,))
    ident=uuid.uuid4().hex
    event(con,task_id,'request',key,{'text':text,'kind':kind,'actor':actor,'session_id':state['session_id'],'turn':state['turn'],'revision':state['revision']})
    events=[db.row_dict(r) for r in con.execute('SELECT * FROM managed_events WHERE task_id=? ORDER BY id DESC LIMIT 35',(task_id,))]
    task=task_row(con,task_id);ctx=context(task_id,con)
    directories=['.']+sorted(str(p.relative_to(Path(task['workspace']))) for p in Path(task['workspace']).rglob('*') if p.is_dir() and '.actplane' not in p.parts and '.git' not in p.parts)
    public_requests=[db.row_dict(r) for r in con.execute("SELECT * FROM managed_events WHERE task_id=? AND kind='request' ORDER BY id",(task_id,)) if json.loads(r['payload_json']).get('actor') in ('native_user','administrator','DSH')]
    resolved={ident for r in con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='request_resolved'",(task_id,)) for ident in json.loads(r[0]).get('evidence_ids',[])}
    unassessed=[str(r['id']) for r in public_requests if str(r['id']) not in resolved]
    events=events+[r for r in public_requests if r['id'] not in {e['id'] for e in events}]
    evidence=[{'evidence_id':str(e['id']),'source':e['kind'],'content':e['payload']} for e in reversed(events) if e['kind'] in ('request','kernel','tool_result','agent_response') and not e['payload'].get('verification_probe')]
    request_id=next(e['evidence_id'] for e in evidence if e['source']=='request' and e['content']['revision']==state['revision'])
    frozen={'schema':'ManagedRuntimeContext/1','task_id':task_id,'task':task['prompt'],'change':{'kind':kind,'text':text},'request_evidence_id':request_id,'sources':evidence,'baseline':{'hash':state['baseline_hash'],'protected_files':state['protected'],'immutable':True,'declared_constraints':ctx.get('declared_constraints',[])},'base_snapshot':{'payload':{'allowed_write_dirs':state['allowed_write_dirs'],'allow_output':state['allow_output'],'protected_paths':state.get('runtime_protected',[])}},'revision':state['revision'],'policy_hash':state['policy_hash'],'session_id':state['session_id'],'path_mapping':{'workspace':task['workspace'],'output':task['output_dir'],'temporary':str(Path(task['workspace']).parent/'tmp')},'capabilities':{'registered_files':sorted(str(p.relative_to(Path(task['workspace']))) for p in Path(task['workspace']).rglob('*') if p.is_file() and not p.is_symlink() and '.actplane' not in p.parts and '.git' not in p.parts),'registered_directories':directories,'write_unlink_dirs':directories,'startup_directories':['.'],'candidate_contract':{'submission':'proposed_snapshot_only','expand':'records_a_pending_candidate_for_later_human_confirmation; does_not_grant_or_apply'},'expansion_targets':[{'kind':'task_output','path':task['output_dir'],'operations':['write','unlink'],'proposal_fields':{'allow_output':True},'confirmation_required':True,'application':'full_package_new_domain'}],'output_expansion':'explicit_confirmation_new_domain','write_expansion':'registered subtree inside startup envelope; explicit confirmation and new domain','arbitrary_dsl':False,'protect_files':'registered file or registered directory/**; restriction preserves prior protections','semantic':'guidance_only','maximum_write_subtrees':1},'unassessed_request_ids':unassessed,'public_task_context':[{'evidence_id':str(r['id']),**r['payload']} for r in public_requests],'project_sources':[project_source(task,p) for p in sorted(Path(task['workspace']).rglob('*')) if p.is_file() and not p.is_symlink() and '.actplane' not in p.parts and '.git' not in p.parts]}
    frozen['native_execution_context']=state.get('runtime_observations',{})
    frozen['capabilities']['executor_sandbox']={'version':2,'read_roots':['project','temporary','output','public_runtime'],'network':'isolated','policy_visibility':'operation_feedback_only','monitor':'Pi; native prompt,instructions,tools,context,memory are observational inputs, never grants'}
    frozen['pending_unresolved_requests']=state.get('pending_unresolved_requests',[])
    frozen['capabilities']['unresolved_constraints']='Necessary OS constraints with an unknown, ambiguous or unadvertised execution target must be declared as unresolved_requests. An advertised expansion target is supported for proposing an expand candidate before confirmation; lack of application confirmation alone is not an unresolved target.'
    frozen['capabilities']['permission_stages']={'candidate':'A real request may support proposing an advertised expansion even while its execution target is granted:false. Proposing never grants or confirms permission.','application':'confirmation_required belongs to application, not proposal eligibility; the controller stores an expand candidate as pending and requires explicit human confirmation before Broker loads a new domain.','unsupported':'unresolved_requests identifies necessary unadvertised or ambiguous OS requirements; preserve startup baseline in all stages.'}
    frozen['resolved_request_ids']=sorted(resolved)
    frozen['current_binding']={'version':state['version'],'domain_id':state.get('binding',{}).get('domain_id'),'session_id':state['session_id']}
    frozen['capabilities']['execution_targets']=[
        {'kind':'workspace','path':task['workspace'],'write_subtrees':state['allowed_write_dirs'],'protected_exclusions':state['protected']+state.get('runtime_protected',[]),'authority':'controller_verified_loaded_snapshot'},
        {'kind':'task_output','path':task['output_dir'],'operations':['write','unlink'],'granted':state['allow_output'],'authority':'controller_verified_loaded_snapshot','policy_version':state['version'],'policy_hash':state['policy_hash']},
        {'kind':'task_temporary','path':str(Path(task['workspace']).parent/'tmp'),'operations':['read','write','unlink'],'granted':True,'scope':'fixed task runtime area; independent of allowed_write_dirs, which are workspace-relative','authority':'controller_verified_rendered_envelope_and_executor_mount'},
    ]
    if state['allow_output']:
        frozen['capabilities']['expansion_targets']=[]
        frozen['capabilities']['output_expansion']='already_granted_in_effective_snapshot; no further confirmation required for operations within this loaded target'
    authorizations,write_scopes=restriction_authorizations(frozen['public_task_context'],unassessed,frozen['capabilities']['registered_files'],directories,task['workspace'])
    inherited={str(Path(p).relative_to(task['workspace'])) for p in state['protected'] if Path(p).is_relative_to(task['workspace'])}
    frozen['capabilities']['authorized_protection_targets']={p:bindings for p,bindings in authorizations.items() if p not in state.get('runtime_protected',[]) and p not in inherited and not (p.endswith('/**') and any(t.startswith(p[:-2]) for t in inherited))}
    frozen['capabilities']['authorized_write_scopes']=write_scopes
    frozen['capabilities']['protection_semantics']='Every protected path blocks OS write and unlink, including every descendant of /**. Read receipts do not authorize restrictions. Automatic additions require authorized_protection_targets, bound to an explicit unassessed authenticated target clause; semantic-only requests may stay guidance, but necessary abstract or ambiguous OS constraints require unresolved_requests and a clarification pause. Retain already confirmed protections.'
    frozen['capabilities']['automatic_protection_subtrees']=[d+'/**' for d in directories if d!='.' and d+'/**' in frozen['capabilities']['authorized_protection_targets']]
    frozen['capabilities']['protect_files']='Exact registered files or automatic_protection_subtrees; preserve prior protections. Existing startup file collections do not authorize a broader parent tree or derived artifacts.'
    frozen['pending_expansion_review']=state.get('pending_expansion_intent')
    frozen['capabilities']['tool_budget']=max(20,min(60,len(frozen['project_sources'])+8))
    con.execute('INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,created_at) VALUES(?,?,?,?,?,?,?)',(ident,task_id,key,state['revision'],state['policy_hash'],json.dumps(frozen,ensure_ascii=False),db.now()))
    # No tool starts while a new user constraint is still unresolved.
    state['gate']='waiting_policy';save(con,task_id,state)
    event(con,task_id,'control_pause',key,{'reason':'等待 Pi 评估本轮上下文','session_id':state['session_id'],'turn':state['turn'],'revision':state['revision'],'version':state['version'],'authority':'control_plane_gate'})
    return {'id':ident,'status':'queued'}

def ingest(task_id,args):
    from ..agent_bridge.api import clean
    kind=str(args.get('kind',''))
    if kind not in ('native_event','tool_result','tool_start','feedback_delivery','agent_decision','user_question_answer','user_message_accepted','runtime_observation','feedback_offer','feedback_received'):raise ValueError('未登记的原生事件')
    with lock(task_id),db.connect() as con:
        s=load(con,task_id)
        if s['phase'] not in ('running','generating'):raise ValueError('任务不再运行')
        sid=str(args.get('session_id',''))
        if s['session_id'] and sid and sid!=s['session_id']:raise ValueError('其他会话不能使用本任务域')
        key=str(args.get('event_key',''))[:180]
        if not key:raise ValueError('事件缺少幂等标识')
        if kind=='feedback_received':
            feedback=str(args.get('feedback',''))
            offer=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='feedback_offer' AND json_extract(payload_json,'$.feedback')=? ORDER BY id DESC LIMIT 1",(task_id,feedback)).fetchone()
            if not offer:
                from .feedback import operation_feedback
                try:reported=json.loads(feedback.removeprefix('[ActPlane operation feedback] '));ident=int(reported['id'])
                except (ValueError,KeyError,TypeError):raise ValueError('Native feedback receipt has no matching kernel feedback offer')
                raw=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='kernel' AND id=?",(task_id,ident)).fetchone()
                kernel=json.loads(raw[0]) if raw else None
                if not kernel or reported!=operation_feedback(ident,kernel['event'],task_row(con,task_id)):raise ValueError('Native feedback receipt has no matching kernel feedback offer')
                payload={'call_id':kernel.get('tool_call_id'),'event_ids':[ident],'feedback':feedback,'source':'late_kernel_feedback'}
            else:payload=json.loads(offer[0])
            payload.update(session_id=sid,authority='native_context_observed; persistence_checked_independently')
            event(con,task_id,'feedback_delivery',key,payload)
            return {'stored':True}
        if kind=='runtime_observation':
            category=str(args.get('category',''));content=str(args.get('content',''))
            if category not in ('system_prompt','instructions','tools','memory','memory_prune','context') or not content or len(content.encode())>131072:raise ValueError('Unsupported or oversized runtime observation')
            content_hash=hashlib.sha256(content.encode()).hexdigest()
            if content_hash!=args.get('content_hash'):raise ValueError('Runtime observation hash mismatch')
            observations=s.setdefault('runtime_observations',{})
            if observations.get(category,{}).get('content_hash')==content_hash:return {'stored':True,'deduplicated':True}
            value={'category':category,'type':args.get('type'),'seq':args.get('seq'),'content':content,'content_hash':content_hash,'authority':'native_model_visible_context; observation_not_authorization'}
            observations[category]=value
            event(con,task_id,'runtime_observation',key,{'session_id':sid,**value})
            save(con,task_id,s)
            if s['phase']=='running':return enqueue(con,task_id,s,'Native model-visible '+category+' changed. Assess the observed context against the authenticated task and current project evidence. Observation alone does not authorize new permission. '+content[:4000],key,kind='guidance',actor='native_context')
            return {'stored':True}
        if kind=='native_event':
            typ=args.get('type');data=args.get('data',{})
            if typ=='turn/start':s['turn']=int(data['turn'])
            if typ=='user/message':
                text=clean(str(args.get('text','')))[:8000]
                if text:
                    request_id=str(data.get('request_id',''))
                    accepted_key='accepted:'+sid+':'+request_id if request_id else key
                    queued=con.execute("SELECT id,payload_json FROM managed_events WHERE task_id=? AND kind='request' AND event_key=?",(task_id,accepted_key)).fetchone()
                    if queued:
                        payload=json.loads(queued['payload_json']);payload.setdefault('accepted_turn',payload.get('turn'));payload['turn']=s['turn'];payload['dispatched_turn']=s['turn']
                        con.execute('UPDATE managed_events SET payload_json=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),queued['id']))
                        event(con,task_id,'message_dispatched',accepted_key,{'session_id':sid,'turn':s['turn'],'request_id':request_id,'accepted_request_event_id':queued['id']})
                    return enqueue(con,task_id,s,text,accepted_key)
            if typ=='assistant/message' and str(args.get('text','')).strip():event(con,task_id,'agent_response',key,{'session_id':sid,'turn':s['turn'],'summary':clean(str(args.get('text','')))[:3000],'authority':'agent_report'})
            if typ in ('turn/start','turn/end'):event(con,task_id,typ,key,{'session_id':sid,'turn':s['turn'],'data':data})
        elif kind=='user_message_accepted':
            request_id=str(args.get('request_id',''))
            if not sid or not request_id or key!='accepted:'+sid+':'+request_id:raise ValueError('Queued user message lacks native admission identity')
            text=clean(str(args.get('text','')))[:8000]
            if text:return enqueue(con,task_id,s,text,key,actor='native_user')
        elif kind=='user_question_answer':
            call=str(args.get('call_id',''))
            original=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='tool_start' AND event_key=?",(task_id,call)).fetchone()
            if not original or json.loads(original[0]).get('name')!='ask_user_question':raise ValueError('原生问答缺少匹配的实际工具调用')
            completed=con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='tool_result' AND event_key=?",(task_id,call)).fetchone()
            if not completed:raise ValueError('原生问答尚未返回真实回答')
            return enqueue(con,task_id,s,clean(str(args.get('text','')))[:8000],key,actor='native_user')
        elif kind=='agent_decision':
            if args.get('decision') not in ('refuse','defer'):raise ValueError('未登记的 Agent 决定')
            event(con,task_id,'agent_refusal' if args['decision']=='refuse' else 'agent_deferral',key,{'session_id':sid,'turn':s['turn'],'version':s['version'],'domain_id':s['binding'].get('domain_id'),'decision':args['decision'],'operation':clean(str(args.get('operation','')))[:100],'target':clean(str(args.get('target','')))[:500],'reason':clean(str(args.get('reason','')))[:1200],'authority':'agent_report; not_kernel_enforcement'})
        else:
            call_binding={}
            if kind=='tool_start' and s['gate']!='open':raise ValueError('Control plane paused: pending policy analysis')
            if kind in ('tool_start','tool_result'):
                call_binding=broker({'action':'managed-call','task_id':task_id,'operation':'start' if kind=='tool_start' else 'end','pid':int(args['pid']),'call_id':args['call_id']},timeout=10)
            payload={k:args.get(k) for k in ('session_id','call_id','name','succeeded','target','pid','started','feedback','event_ids','serialized','native_sdk_verification')}
            if kind=='tool_start':payload['started']={'version':s['version'],'turn':s['turn']}
            payload.update(call_binding)
            payload.update(turn=s['turn'],version=s['version'],domain_id=s['binding'].get('domain_id'),authority='native_hook_metadata; broker_kernel_call_identity')
            event(con,task_id,kind,key,payload)
        save(con,task_id,s)
    return {'stored':True}

def change(task_id,text,key,kind='message',actor='administrator'):
    with lock(task_id),db.connect() as con:return enqueue(con,task_id,load(con,task_id),text,key,kind,actor)

def validate_candidate(job,args):
    p=Candidate.model_validate(args);ctx=json.loads(job['context_json'])
    ids={e['evidence_id'] for e in ctx['sources']}
    with db.connect() as con:
        for source in ctx.get('project_sources',[]):
            if con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='pi_source' AND event_key=?",(job['task_id'],job['id']+':'+source['id'])).fetchone():ids.add('project:'+source['id'])
        history=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='pi_history' AND event_key=?",(job['task_id'],job['id'])).fetchone()
        for entry in json.loads(history[0]).get('versions',[]) if history else []:
            if entry['id'] not in p.evidence_ids and 'history:'+entry['id'] not in p.evidence_ids:continue
            row=con.execute("SELECT record_json,content_hash,reviewed_hash,status,source_kind FROM bootstrap_history WHERE id=?",(entry['id'],)).fetchone()
            if not row or row['status']!='approved' or row['content_hash']!=entry['hash'] or row['reviewed_hash']!=entry['hash']:raise ValueError('历史模板版本已过期或未获审核')
            from ..history.pipeline import digest as history_digest
            record=json.loads(row['record_json']);actual=history_digest(record) if row['source_kind']=='statement_version' else digest(record)
            if actual!=entry['hash']:raise ValueError('历史模板哈希不匹配')
            ids.update([entry['id'],'history:'+entry['id']])
    if not set(p.evidence_ids)<=ids or ctx['request_evidence_id'] not in p.evidence_ids:raise ValueError('候选必须引用已读取的本轮证据: '+json.dumps({'required_request_id':ctx['request_evidence_id'],'received':p.evidence_ids,'unknown':sorted(set(p.evidence_ids)-ids),'readable_evidence_ids':sorted(ids),'unread_project_sources':[value.removeprefix('project:') for value in sorted(set(p.evidence_ids)-ids) if value.startswith('project:')],'read_tool':'read_runtime_source'}))
    for statement in p.identified_statements:
        if not set(statement.evidence_ids)<=set(p.evidence_ids):raise ValueError('Identified statement must cite candidate evidence')
    pending=set(ctx.get('unassessed_request_ids',[]))
    if not set(p.unresolved_requests)<=pending:raise ValueError('Unresolved constraints must identify unassessed authenticated request IDs')
    if p.unresolved_requests and p.decision not in ('no_change','guidance_only'):raise ValueError('An unresolved necessary constraint cannot accompany a permission application')
    if not pending<=set(p.evidence_ids):raise ValueError('未覆盖尚未评估的公开请求: '+json.dumps(sorted(pending-set(p.evidence_ids))))
    with db.connect() as con:source_task=task_row(con,job['task_id'])
    for source in ctx.get('project_sources',[]):
        if source.get('path'):
            actual=read_project_content(source_task,source['path'])['hash'] if Path(source['path']).is_file() else None
            if actual!=source['hash']:raise ValueError('stale: 项目证据在分析期间变化')
    if ctx.get('pending_expansion_review') and p.decision in ('no_change','guidance_only'):raise ValueError('Operational feedback does not withdraw a pending review-only permission proposal. Revalidate an expand candidate against the current snapshot/evidence for later human confirmation; submission does not approve, grant, or apply it. A new authoritative user message may change or withdraw this intent.')
    old=ctx['base_snapshot']['payload'];dirs=p.allowed_write_dirs
    previous=old.get('protected_paths',[])
    immutable_targets={str(Path(x).relative_to(ctx['path_mapping']['workspace'])) for x in ctx.get('baseline',{}).get('protected_files',[]) if Path(x).is_relative_to(ctx.get('path_mapping',{}).get('workspace','/nonexistent'))}
    if p.protected_paths is None:p.protected_paths=previous
    for target in set(p.protected_paths)-set(previous):
        if target.endswith('/**') and any(x.startswith(target[:-2]) for x in immutable_targets):raise ValueError('overbroad registered object collection: startup registered files must not be broadened to future derived artifacts. Use exact new registered targets; immutable baseline targets are already protected.')
    redundant=(set(p.protected_paths)-set(previous)) & immutable_targets
    if redundant:raise ValueError('Objects already protected by the immutable startup baseline must not be added as new runtime restrictions: '+json.dumps(sorted(redundant))+'; keep the current runtime snapshot, or propose only an effective new restriction')
    registered=set(ctx['capabilities'].get('registered_files',[]))|{d+'/**' for d in ctx['capabilities']['registered_directories'] if d!='.'}
    if not set(p.protected_paths)<=registered|set(previous):raise ValueError('未登记的保护对象')
    for target in set(p.protected_paths)-set(previous):
        if 'authorized_protection_targets' in ctx['capabilities']:
            bindings=ctx['capabilities']['authorized_protection_targets'].get(target,[])
            if not any(b['request_id'] in p.evidence_ids for b in bindings):raise ValueError('New protection has no explicit authenticated OS-target authorization: '+target+'. Project reads resolve facts but cannot authorize restrictions. Use only authorized_protection_targets, or keep the current snapshot with no_change/guidance_only.')
        candidates=[x['id'] for x in ctx.get('project_sources',[]) if x['id']==target or target.endswith('/**') and x['id'].startswith(target[:-2])]
        if not any('project:'+ident in p.evidence_ids for ident in candidates):raise ValueError('新保护对象必须引用已读取项目材料: '+json.dumps({'target':target,'source_ids':candidates}))
    if p.decision!='expand' and not set(previous)<=set(p.protected_paths):raise ValueError('收紧或无变更不得移除已确认保护对象')
    if not set(dirs)<=set(ctx['capabilities']['registered_directories']):raise ValueError('未登记的路径')
    if p.decision in ('no_change','guidance_only'):
        if dirs!=old['allowed_write_dirs'] or p.allow_output!=old['allow_output'] or p.protected_paths!=previous:raise ValueError('无需变更或指导不能修改权限')
    elif p.decision=='restrict':
        if dirs!=old['allowed_write_dirs'] and 'authorized_write_scopes' in ctx['capabilities'] and (not dirs or not set(dirs)<=set(ctx['capabilities']['authorized_write_scopes'])):raise ValueError('No explicit authenticated write-scope restriction authorizes these directories; a procedural read/test instruction does not authorize changing the persistent scope')
        if dirs==old['allowed_write_dirs'] and p.allow_output==old['allow_output'] and p.protected_paths==previous:raise ValueError('No OS restriction changed; choose no_change or guidance_only with the current snapshot')
        if p.allow_output and not old['allow_output']:raise ValueError('收紧不能授予输出权限')
        if any(not any(o=='.' or d==o or d.startswith(o+'/') for o in old['allowed_write_dirs']) for d in dirs):raise ValueError('收紧不能扩展路径')
    elif p.decision=='expand':
        if p.allow_output and not old['allow_output'] and not any(x.get('kind')=='task_output' for x in ctx['capabilities'].get('expansion_targets',[])):raise ValueError('Unadvertised output expansion target')
        if not set(p.protected_paths)<=set(previous):raise ValueError('扩权不能混入新的收紧对象')
        if p.allow_output==old['allow_output'] and dirs==old['allowed_write_dirs'] and p.protected_paths==previous:raise ValueError('扩权没有增加权限')
        if not p.allow_output and old['allow_output']:raise ValueError('扩权不得隐式撤销输出授权')
    with db.connect() as con:
        s=load(con,job['task_id']);task=task_row(con,job['task_id'])
        if s['revision']!=job['revision'] or s['policy_hash']!=job['policy_hash']:raise ValueError('stale: 上下文或策略已变化')
    dsl,yaml=render(task,s,dirs,p.allow_output,p.protected_paths)
    from ..main import compile_policy
    status,diagnostic,error=compile_policy(yaml,task['id'],12000+s['revision'])
    if status!='compiled':raise ValueError('候选编译失败: '+str(error))
    return {**p.model_dump(),'hash':digest({'proposal':p.model_dump(),'context':ctx}),'compile':diagnostic,'compiled_dsl':dsl,'compiled_dsl_hash':hashlib.sha256(dsl.encode()).hexdigest()}

def finish_job(job):
    with lock(job['task_id']),db.connect() as con:
        s=load(con,job['task_id']);row=con.execute('SELECT proposal_json FROM managed_jobs WHERE id=?',(job['id'],)).fetchone()
        if not row or not row[0]:raise ValueError('Pi 未提交经校验候选')
        if s['phase']!='running' or s['revision']!=job['revision'] or s['policy_hash']!=job['policy_hash']:raise ValueError('stale: 候选已过期或任务已结束')
        p=json.loads(row[0]);event(con,job['task_id'],'candidate',job['id'],{'proposal':p,'revision':s['revision']})
        if p.get('unresolved_requests'):
            s['gate']='waiting_clarification';s['pending_unresolved_requests']=p['unresolved_requests'];save(con,job['task_id'],s)
            event(con,job['task_id'],'control_pause','unresolved:'+job['id'],{'reason':'必要 OS 约束尚未解决，等待澄清','request_ids':p['unresolved_requests'],'version':s['version']})
            return
        s.pop('pending_unresolved_requests',None)
        if p['decision']=='expand':
            s['pending_expansion']={'job_id':job['id'],'hash':p['hash'],'proposal':p};s.pop('pending_expansion_intent',None)
        if p['decision']!='restrict':
            s['gate']='open';save(con,job['task_id'],s)
            if p['decision'] in ('no_change','guidance_only'):event(con,job['task_id'],'request_resolved',job['id'],{'evidence_ids':p['evidence_ids'],'decision':p['decision'],'version':s['version']})
            return
        s['gate']='applying';save(con,job['task_id'],s)
    # Quiesce native turn and subprocesses before changing scope. Fresh process
    # trees revoke old writable mmap/FD capabilities; preserve native Session ID.
    installed=install(job['task_id'],s,p['allowed_write_dirs'],p['allow_output'],protected_paths=p['protected_paths'])
    with lock(job['task_id']),db.connect() as con:
        event(con,job['task_id'],'request_resolved',job['id'],{'evidence_ids':p['evidence_ids'],'decision':'restrict','version':installed['version']})
        current=load(con,job['task_id'])
        if current.get('pending_expansion_intent') and current['phase']=='running':enqueue(con,job['task_id'],current,'Reassess the still-unapproved permission proposal after the confirmed restriction. No permission has been granted.','pending-review:'+job['id'],kind='guidance',actor='control_review')

def confirm_expansion(task_id,expected_hash):
    with lock(task_id),db.connect() as con:
        s=load(con,task_id);p=s.get('pending_expansion')
        if s['phase']!='running' or s['gate']!='open':raise ValueError('控制面正在暂停或应用策略，不能重复确认')
        if not p or p['hash']!=expected_hash:raise ValueError('扩权候选已变化')
        j=con.execute('SELECT revision,policy_hash,context_json FROM managed_jobs WHERE id=?',(p['job_id'],)).fetchone()
        if j['revision']!=s['revision'] or j['policy_hash']!=s['policy_hash']:raise ValueError('扩权输入已过期')
        for source in json.loads(j['context_json']).get('project_sources',[]):
            actual=read_project_content(task_row(con,task_id),source['path'])['hash'] if Path(source['path']).is_file() else None
            if actual!=source['hash']:raise ValueError('扩权输入已过期: 项目证据改变')
        s['gate']='applying';save(con,task_id,s)
        event(con,task_id,'expansion_confirmed',p['hash'],{'actor':'authenticated_administrator','hash':p['hash']})
    s.pop('pending_expansion_intent',None)
    installed=install(task_id,s,p['proposal']['allowed_write_dirs'],p['proposal']['allow_output'],protected_paths=p['proposal']['protected_paths'])
    with db.connect() as con:event(con,task_id,'request_resolved',p['job_id'],{'evidence_ids':p['proposal']['evidence_ids'],'decision':'expand','version':installed['version'],'confirmation':p['hash']})
    return installed

def close(task_id):
    from ..main import revoke_task_tokens
    with lifecycle(task_id),lock(task_id):
        receipt=broker({'action':'stop','task_id':task_id},timeout=20);revoke_task_tokens(task_id)
        with db.connect() as con:
            s=load(con,task_id);s.update(phase='ended',gate='closed',pending_expansion=None);save(con,task_id,s)
            con.execute("UPDATE managed_jobs SET status='interrupted',token_hash=NULL WHERE task_id=? AND status IN ('queued','running')",(task_id,))
            if s.get('startup_job'):
                con.execute("UPDATE history_jobs SET status='interrupted',error='Managed task ended' WHERE id=? AND status IN ('queued','running')",(s['startup_job'],))
            con.execute("UPDATE bootstrap_credentials SET revoked_at=?,expires_at=0 WHERE task_id=? AND revoked_at IS NULL",(db.now(),task_id))
            con.execute("UPDATE tasks SET status='completed',active_pid=NULL,active_domain_id=NULL,watch_pid=NULL,ended_at=?,updated_at=? WHERE id=?",(db.now(),db.now(),task_id))
            event(con,task_id,'closed',str(s['version']),{'receipt':receipt,'temporary_grants':'revoked'})
        return receipt

def correlate_tool(con,task_id,raw):
    tag=str(raw.get('tool_call_tag') or '')
    if not tag or tag=='0':return None
    domain=raw.get('process_domain_id',raw.get('domain_id'))
    candidates=[]
    for row in con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='tool_start' ORDER BY id DESC",(task_id,)):
        start=json.loads(row[0])
        if str(start.get('kernel_call_tag'))==tag and start.get('domain_id')==domain:candidates.append(start['call_id'])
    return candidates[0] if len(set(candidates))==1 else None

def tool_feedback(task_id,call_id):
    deadline=time.monotonic()+1
    while True:
        with db.connect() as con:
            start=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='tool_start' AND event_key=?",(task_id,call_id)).fetchone()
            if not start:return {'events':[]}
            delivered={ident for row in con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='feedback_delivery'",(task_id,)) for ident in json.loads(row[0]).get('event_ids',[])}
            events=[]
            for row in con.execute("SELECT id,payload_json FROM managed_events WHERE task_id=? AND kind='kernel' ORDER BY id DESC LIMIT 150",(task_id,)):
                payload=json.loads(row[1])
                if payload.get('verification_probe') or row[0] in delivered:continue
                if correlate_tool(con,task_id,payload['event'])==call_id:
                    from .feedback import operation_feedback
                    events.append(operation_feedback(row[0],payload['event'],task_row(con,task_id)))
        if events or time.monotonic()>=deadline:return {'events':list(reversed(events))}
        time.sleep(.1)
