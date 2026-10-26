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
                error=s.get('error') if s['phase']=='failed' and s.get('error') else str(error) or type(error).__name__
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
            with db.connect() as con:tasks=[(r['task_id'],json.loads(r['state_json'])) for r in con.execute("SELECT * FROM managed_tasks WHERE json_extract(state_json,'$.phase') IN ('recovering','generating')")]
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
            self.collect_once()
            self.halt.wait(.2)

    def collect_once(self):
        with db.connect() as con:
            active={r['task_id']:json.loads(r['state_json']) for r in con.execute("SELECT * FROM managed_tasks WHERE json_extract(state_json,'$.phase')='running'")}
            logs=con.execute('SELECT m.task_id,t.workspace FROM managed_tasks m JOIN tasks t ON t.id=m.task_id').fetchall()
        for row in logs:
            if self.halt.is_set():return
            task_id=row['task_id'];state=active.get(task_id)
            try:
                path=Path(row['workspace'])/'.actplane/events.jsonl'
                try:
                    info=path.lstat();signature=(info.st_ino,info.st_size,info.st_mtime_ns,info.st_uid,info.st_mode)
                except FileNotFoundError:signature=None
                # Closed archives still get a final drain, and another drain if
                # their root log changes. Do not decode MB-sized historical state
                # on every 200ms tick after its log is unchanged.
                if task_id not in self.log_signatures or self.log_signatures[task_id]!=signature:
                    self.collect_task(task_id)
                    self.log_signatures[task_id]=signature
                if state and state['gate']!='applying' and time.monotonic()-self.binding_checks.get(task_id,0)>3:
                    self.binding_checks[task_id]=time.monotonic()
                    binding=c.broker({'action':'status','task_id':task_id},timeout=10)
                    if binding.get('status')!='running' or binding.get('domain_verified') is False:
                        self.fail(task_id,'Native DSH process/domain binding lost; supervisor retained kernel evidence',state['revision'],state['policy_hash'])
            except Exception as error:
                if state:self.fail(task_id,error,state['revision'],state['policy_hash'])

    def collect_task(self,task_id):
        from .feedback import operation_feedback
        with db.connect() as con:
            task=c.task_row(con,task_id);state=c.load(con,task_id)
            cursor=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='kernel_cursor' AND event_key='cursor'",(task_id,)).fetchone()
        p=Path(task['workspace'])/'.actplane/events.jsonl'
        if not p.exists():return
        st=p.lstat()
        if p.is_symlink() or st.st_uid!=0 or st.st_mode&0o022:raise ValueError('Kernel event log ownership invalid')
        prior=json.loads(cursor[0]) if cursor else {}
        epoch=state.get('recovery_bundle',{}).get('process_epoch')
        offset=prior.get('offset',0) if prior.get('inode')==st.st_ino and prior.get('process_epoch')==epoch and prior.get('offset',0)<=st.st_size else 0
        with p.open('rb') as stream:
            stream.seek(offset);content=stream.read()
        # Never consume an incomplete trailing record.
        end=content.rfind(b'\n')+1
        if not end:return
        for line in content[:end].splitlines():
            try:raw=json.loads(line)
            except ValueError:continue
            if not(raw.get('blocked') or raw.get('killed') or raw.get('effect')=='notify'):continue
            domain=raw.get('process_domain_id',raw.get('domain_id'))
            versions=[b['version'] for b in state.get('binding_history',[]) if b['domain_id']==domain]
            version=max(versions) if versions else None
            if version is None:continue
            key=c.digest(raw)
            with c.lock(task_id),db.connect() as con:
                if con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='kernel' AND event_key=?",(task_id,key)).fetchone():continue
                s=c.load(con,task_id)
                row=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='feedback_bundle' AND event_key=?",(task_id,str(version))).fetchone()
                bundle=json.loads(row[0]) if row else s.get('recovery_bundle')
                engine=(bundle or {}).get('engine',{})
                if engine.get('session_root') and raw.get('session_root')!=engine['session_root']:continue
                registry=p.with_name('probes.jsonl');registered=[]
                if registry.exists():
                    rst=registry.lstat()
                    if registry.is_symlink() or rst.st_uid!=0 or rst.st_mode&0o022:raise ValueError('Probe registry ownership invalid')
                    registered=[json.loads(line) for line in registry.read_text().splitlines()]
                is_probe=raw.get('pid') in s.get('probe_pids',[]) or any(x['pid']==raw.get('pid') and x['domain_id']==domain for x in registered)
                call_id=None if is_probe else c.correlate_tool(con,task_id,raw)
                start=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='tool_start' AND event_key=?",(task_id,call_id)).fetchone() if call_id else None
                call=json.loads(start[0]) if start else {}
                payload={'event':raw,'session_id':call.get('session_id',s['session_id']),
                         'turn':call.get('started',{}).get('turn'),'tool_call_id':call_id,
                         'correlation':'exact_process_domain; inherited_kernel_call_identity' if call_id else 'exact_process_domain; tool_unresolved',
                         'version':version,'verification_probe':is_probe,
                         'native_sdk_verification':call.get('native_sdk_verification',False),'authority':'root_owned_kernel_event'}
                c.event(con,task_id,'kernel',key,payload)
                ident=con.execute("SELECT id FROM managed_events WHERE task_id=? AND kind='kernel' AND event_key=?",(task_id,key)).fetchone()[0]
                f=operation_feedback(ident,raw,task,bundle=bundle,payload=payload)
                payload['feedback']=f
                con.execute("UPDATE managed_events SET payload_json=? WHERE id=?",(json.dumps(payload,ensure_ascii=False),ident))
                con.execute("INSERT OR IGNORE INTO runtime_events(id,task_id,kind,operation,target,decision,reason,occurred_at,raw_json,dedupe_key) VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (key,task_id,'kernel',raw.get('op'),raw.get('target'),f['result'],f['because'],db.now(),json.dumps(raw),key))
                if not is_probe:
                    c.event(con,task_id,'feedback_pending',str(ident),{'event_ids':[ident],'feedback_ids':[f['feedback_id']],'session_id':payload['session_id'],'process_epoch':f['identity']['process_epoch'],'authority':'kernel_fact; not_context_admission'})
                    if not call_id:c.event(con,task_id,'feedback_unresolved',str(ident),{'reason':'No unique kernel tool identity; no arbitrary session injection','event_ids':[ident]})
        with db.connect() as con:
            payload=json.dumps({'inode':st.st_ino,'offset':offset+end,'process_epoch':epoch,'authority':'durable_root_log_cursor'})
            con.execute("INSERT INTO managed_events(task_id,kind,event_key,payload_json,occurred_at) VALUES(?,?,?,?,?) ON CONFLICT(task_id,kind,event_key) DO UPDATE SET payload_json=excluded.payload_json,occurred_at=excluded.occurred_at",
                        (task_id,'kernel_cursor','cursor',payload,db.now()))

    def deliver_task_feedback(self,task_id):
        from .feedback import pending_events,offer
        with c.lock(task_id),db.connect() as con:
            state=c.load(con,task_id)
            if state['phase']!='running' or state['gate']=='applying':return
            pending=pending_events(con,task_id,state)
            ready=[]
            for f in pending:
                ident=f['id']
                kernel=con.execute("SELECT (julianday('now')-julianday(occurred_at))*86400 FROM managed_events WHERE id=?",(ident,)).fetchone()
                if not kernel or kernel[0]<2:continue
                if not con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='tool_result' AND event_key=?",(task_id,f['identity']['call_id'])).fetchone():continue
                # A persisted message still needs observed context admission.
                previous=con.execute("SELECT (julianday('now')-julianday(occurred_at))*86400 FROM managed_events WHERE task_id=? AND (kind='feedback_persisted' OR (kind='feedback_offer' AND json_extract(payload_json,'$.channel')='immediate')) AND EXISTS(SELECT 1 FROM json_each(json_extract(payload_json,'$.event_ids')) WHERE value=?) ORDER BY id DESC LIMIT 1",(task_id,ident)).fetchone()
                if previous and previous[0]<10:continue
                if previous:c.event(con,task_id,'feedback_delivery_failed',str(ident),{'event_ids':[ident],'reason':'Context admission not observed within 10 seconds; execution remains paused'})
                ready.append(f)
            if not ready:return
            response=offer(con,task_id,state,ready,channel='background')
        acknowledgement=c.broker({'action':'native-session','task_id':task_id,'operation':'resume','session_id':state['session_id'],'text':response['message']},timeout=10)
        if not acknowledgement.get('persisted'):raise ValueError('Native feedback has no durable session acknowledgement')
        with c.lock(task_id),db.connect() as con:
            c.event(con,task_id,'feedback_persisted',response['offer_id'],{'session_id':state['session_id'],'event_ids':[f['id'] for f in ready],'feedback_ids':[f['feedback_id'] for f in ready],'authority':'native_context_persisted; not_context_admission'})

    def deliver_feedback(self):
        while not self.halt.is_set():
            with db.connect() as con:tasks=[r[0] for r in con.execute("SELECT task_id FROM managed_tasks WHERE json_extract(state_json,'$.phase')='running' AND json_extract(state_json,'$.gate')!='applying'")]
            for task_id in tasks:
                try:self.deliver_task_feedback(task_id)
                except Exception:
                    # Durable events survive transport errors and process replacement.
                    # Neither an offer nor a persistence acknowledgement clears the gate.
                    pass
            self.halt.wait(.5)

worker=Worker()
