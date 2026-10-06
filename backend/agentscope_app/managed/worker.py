import json,os,threading,time
from pathlib import Path
from .. import db
from ..scope import pi
from . import controller as c

class Worker:
    def __init__(self):self.halt=threading.Event();self.threads=[];self.log_signatures={};self.binding_checks={}
    def start(self):
        if os.getenv('AGENTSCOPE_SCOPE_WORKER')!='1':return
        self.halt.clear()
        with db.connect() as con:
            rows=con.execute("SELECT task_id FROM managed_jobs WHERE status='running'").fetchall()
            con.execute("UPDATE managed_jobs SET status='interrupted',token_hash=NULL,error='API restart interrupted policy analysis' WHERE status='running'")
            for r in rows:
                s=c.load(con,r[0]);s.update(gate='failed',phase='failed',error='API restart interrupted policy analysis');c.save(con,r[0],s)
        for r in rows:self.fail(r[0],'API restart interrupted policy analysis')
        for target in (self.run,self.collect,self.deliver_feedback):
            thread=threading.Thread(target=target,daemon=True);thread.start();self.threads.append(thread)
    def stop(self):
        self.halt.set()
        for thread in self.threads:thread.join(timeout=2)
        self.threads=[]
    def fail(self,task_id,error,expected_revision=None,expected_policy=None):
        from ..main import revoke_task_tokens
        with c.lifecycle(task_id):
            with c.lock(task_id),db.connect() as con:
                s=c.load(con,task_id)
                if s['phase']=='ended' or expected_revision is not None and s['revision']!=expected_revision or expected_policy is not None and s['policy_hash']!=expected_policy:return
                s.update(phase='failed',gate='failed',error=str(error)[:1500]);c.save(con,task_id,s)
            try:c.broker({'action':'stop','task_id':task_id},timeout=20)
            except Exception as stop_error:error=str(error)+'; cleanup: '+str(stop_error)
            revoke_task_tokens(task_id)
            with db.connect() as con:
                s=c.load(con,task_id);s['error']=str(error)[:1500];c.save(con,task_id,s)
                con.execute("UPDATE tasks SET status='failed',active_pid=NULL,active_domain_id=NULL,watch_pid=NULL,updated_at=? WHERE id=?",(db.now(),task_id))
                c.event(con,task_id,'failure',__import__('uuid').uuid4().hex,{'error':str(error)[:1500]})
    def run(self):
        while not self.halt.is_set():
            with db.connect() as con:tasks=[(r['task_id'],json.loads(r['state_json'])) for r in con.execute('SELECT * FROM managed_tasks')]
            for task_id,state in tasks:
                if state['phase']=='recovering':
                    try:c.recover(task_id)
                    except Exception as e:self.fail(task_id,e)
                if state['phase']=='generating':
                    try:c.complete_start(task_id)
                    except Exception as e:self.fail(task_id,e)
            with db.connect() as con:
                row=con.execute("SELECT * FROM managed_jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
                if row:
                    job=dict(row);s=c.load(con,job['task_id'])
                    if s['phase']!='running' or s['revision']!=job['revision'] or s['policy_hash']!=job['policy_hash']:
                        con.execute("UPDATE managed_jobs SET status='stale',token_hash=NULL WHERE id=?",(job['id'],));row=None
                    else:con.execute("UPDATE managed_jobs SET status='running' WHERE id=?",(job['id'],))
            if row:
                try:
                    pi.generate({**job,'managed':True});c.finish_job(job)
                    with db.connect() as con:con.execute("UPDATE managed_jobs SET status='completed',token_hash=NULL WHERE id=?",(job['id'],))
                except Exception as e:
                    with db.connect() as con:
                        s=c.load(con,job['task_id']);stale=s['phase']!='running' or s['revision']!=job['revision'] or s['policy_hash']!=job['policy_hash']
                        con.execute("UPDATE managed_jobs SET status=?,token_hash=NULL,error=? WHERE id=?",('stale' if stale else 'failed',str(e)[:1500],job['id']))
                    if not stale:self.fail(job['task_id'],e,job['revision'],job['policy_hash'])
            self.halt.wait(.4)
    def collect(self):
        while not self.halt.is_set():
            with db.connect() as con:tasks=[(r['task_id'],json.loads(r['state_json'])) for r in con.execute('SELECT * FROM managed_tasks')]
            for task_id,state in tasks:
                try:
                    if state['phase']=='running' and state['gate']!='applying' and time.monotonic()-self.binding_checks.get(task_id,0)>3:
                        self.binding_checks[task_id]=time.monotonic()
                        binding=c.broker({'action':'status','task_id':task_id},timeout=10)
                        if binding.get('status')!='running' or binding.get('domain_verified') is False:
                            self.fail(task_id,'Native DSH process/domain binding lost',state['revision'],state['policy_hash']);continue
                    with db.connect() as con:task=c.task_row(con,task_id)
                    p=Path(task['workspace'])/'.actplane/events.jsonl'
                    if not p.exists():continue
                    st=p.lstat()
                    if p.is_symlink() or st.st_uid!=0 or st.st_mode&0o022:raise ValueError('Kernel event log ownership invalid')
                    signature=(st.st_ino,st.st_size,st.st_mtime_ns)
                    if self.log_signatures.get(task_id)==signature:continue
                    for line in p.read_text().splitlines():
                        try:raw=json.loads(line)
                        except ValueError:continue
                        if not raw.get('blocked'):continue
                        domain=raw.get('process_domain_id',raw.get('domain_id'));version=next((b['version'] for b in state.get('binding_history',[]) if b['domain_id']==domain),None)
                        if version is None:continue
                        key=c.digest(raw)
                        with c.lock(task_id),db.connect() as con:
                            if con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='kernel' AND event_key=?",(task_id,key)).fetchone():continue
                            s=c.load(con,task_id)
                            registry=p.with_name('probes.jsonl')
                            registered=[]
                            if registry.exists():
                                rst=registry.lstat()
                                if registry.is_symlink() or rst.st_uid!=0 or rst.st_mode&0o022:raise ValueError('Probe registry ownership invalid')
                                registered=[json.loads(line) for line in registry.read_text().splitlines()]
                            is_probe=raw.get('pid') in s.get('probe_pids',[]) or any(x['pid']==raw.get('pid') and x['domain_id']==domain for x in registered)
                            call_id=None if is_probe else c.correlate_tool(con,task_id,raw)
                            start=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='tool_start' AND event_key=?",(task_id,call_id)).fetchone() if call_id else None
                            call=json.loads(start[0]) if start else {}
                            c.event(con,task_id,'kernel',key,{'event':raw,'session_id':call.get('session_id',s['session_id']),'turn':call.get('started',{}).get('turn'),'tool_call_id':call_id,'correlation':'exact_process_domain; inherited_kernel_call_identity' if call_id else 'exact_process_domain; tool_unresolved','version':version,'verification_probe':is_probe,'native_sdk_verification':call.get('native_sdk_verification',False),'authority':'root_owned_kernel_event'})
                            con.execute("INSERT OR IGNORE INTO runtime_events(id,task_id,kind,operation,target,decision,reason,occurred_at,raw_json,dedupe_key) VALUES(?,?,?,?,?,?,?,?,?,?)",(key,task_id,'kernel',raw.get('op'),raw.get('target'),'block',str(raw.get('rule',{}).get('reason','')),db.now(),json.dumps(raw),key))
                            if not is_probe and s['phase']=='running' and s['gate'] in ('open','waiting_policy') and domain==s['binding'].get('domain_id'):
                                c.enqueue(con,task_id,s,'A real kernel denial was observed. Check whether the existing safety boundary is correct; denial alone does not authorize a grant. '+json.dumps({k:raw.get(k) for k in ('op','target','pid')}),'kernel:'+key+':'+s['policy_hash'],kind='guidance',actor='kernel')
                    self.log_signatures[task_id]=signature
                except Exception as e:
                    if state['phase']=='running':self.fail(task_id,e,state['revision'],state['policy_hash'])
            self.halt.wait(.5)

    def deliver_feedback(self):
        # Post hooks handle immediate events. This durable outbox catches denials
        # from background descendants after the originating tool has returned.
        while not self.halt.is_set():
            with db.connect() as con:
                tasks=[(r['task_id'],json.loads(r['state_json'])) for r in con.execute('SELECT * FROM managed_tasks')]
            for task_id,state in tasks:
                if state['phase']!='running' or state['gate']=='applying':continue
                try:
                    with db.connect() as con:
                        delivered={ident for r in con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='feedback_delivery'",(task_id,)) for ident in json.loads(r[0]).get('event_ids',[])}
                        pending=[(r['id'],json.loads(r['payload_json'])) for r in con.execute("SELECT * FROM managed_events WHERE task_id=? AND kind='kernel' AND (julianday('now')-julianday(occurred_at))*86400>2 ORDER BY id",(task_id,)) if r['id'] not in delivered]
                        pending=[(ident,p) for ident,p in pending if not p.get('verification_probe') and p.get('tool_call_id') and con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='tool_result' AND event_key=?",(task_id,p['tool_call_id'])).fetchone()]
                    for ident,payload in pending:
                        raw=payload['event']
                        from .feedback import operation_feedback
                        with db.connect() as con:task=c.task_row(con,task_id)
                        feedback='[ActPlane operation feedback] '+json.dumps(operation_feedback(ident,raw,task))
                        acknowledgement=c.broker({'action':'native-session','task_id':task_id,'operation':'resume','session_id':state['session_id'],'text':feedback},timeout=10)
                        if not acknowledgement.get('persisted'):raise ValueError('Native feedback has no durable session acknowledgement')
                        with c.lock(task_id),db.connect() as con:c.event(con,task_id,'feedback_delivery','late:'+str(ident),{'session_id':state['session_id'],'call_id':payload['tool_call_id'],'event_ids':[ident],'feedback':feedback,'source':'durable_background_outbox','authority':'native_context_persisted'})
                except Exception:
                    # An unavailable/replacing native process does not lose the
                    # durable event. Retry after recovery; never invent delivery.
                    pass
            self.halt.wait(.5)

worker=Worker()
