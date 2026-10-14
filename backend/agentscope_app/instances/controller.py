"""Trusted, instance-wide policy lifecycle and atomic execution leases."""
import hashlib, hmac, json, os, secrets, threading, time, uuid
from datetime import datetime, timezone
from .. import db
from ..broker_client import call as broker
from . import store, discovery, system_policy as system
from .adapters import adapter, entry_details
from .policy import canonical, clean_resources, digest, records, restrictive
from . import dsl_policy

_locks={}; _lock=threading.Lock()
def lock(ident):
    with _lock: return _locks.setdefault(ident,threading.RLock())

class Observer:
    def __init__(self): self.rows={}; self.lock=threading.RLock(); self.stop_event=threading.Event(); self.thread=None
    def collect(self):
        try:
            result=broker({'action':'agent-instance-inventory'},timeout=2)
            observed=time.monotonic(); checked_at=db.now()
            with self.lock: self.rows={r['id']:{**r,'_observed':observed,'last_checked_at':checked_at,
                'last_verified_at':checked_at if r.get('verified') else self.rows.get(r['id'],{}).get('last_verified_at')} for r in result['instances']}
        except Exception:
            with self.lock:
                self.rows={k:{**v,'connected':False,'status':'unknown'} for k,v in self.rows.items()}
    def snapshot(self):
        with self.lock: values=[dict(r) for r in self.rows.values()]
        for r in values:
            age=time.monotonic()-r.pop('_observed')
            r['evidence_age_seconds']=round(age,2)
            if age>=8: r.update(connected=False,status='stale',verified=False)
        return values
    def run(self):
        while not self.stop_event.is_set():
            self.collect()
            from .sessions import collect_kernel
            for row in store.rows():
                if row['mode']=='controlled' and row.get('generation'):
                    try: collect_runtime_events(row)
                    except Exception: pass # Failure preserves the root-owned queue for retry.
                    try:collect_kernel(row)
                    except Exception:pass # read APIs expose the collection failure separately
            self.stop_event.wait(3)
    def start(self):
        if os.getenv('AGENTSCOPE_INSTANCE_WORKER','1')=='0': return
        if self.thread and self.thread.is_alive(): return
        self.stop_event.clear(); self.thread=threading.Thread(target=self.run,name='agent-instance-observer',daemon=True); self.thread.start()
    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(3)
observer=Observer()

def runtime_call(row, operation, **fields):
    return broker({'action':'agent-instance-execution-'+operation,'instance_id':row['id'],
        'generation':row['generation'],'policy_hash':row['policy_hash'],**fields},timeout=3)

def independent(row):
    return row.get('runtime',{}).get('supervision')=='broker-admission-v1'

def close_runtime_gates(rows):
    # Close at the actual lease issuer before changing any control-plane state.
    for row in rows:
        if independent(row):runtime_call(row,'gate',open=False)

def open_runtime_gate(row):
    if not independent(row):return
    if row['gate']!='open' or system.current()['phase']!='ready':return
    if any(dsl_policy.current(scope)['phase']!='ready' for scope in ('system',row['id'])):return
    runtime_call(row,'gate',open=True)

def collect_runtime_events(row):
    if not independent(row):return
    events=runtime_call(row,'events')['events']
    if not events:return
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        current=con.execute('SELECT generation,policy_hash FROM agent_instances WHERE id=?',(row['id'],)).fetchone()
        if not current or current['generation']!=row['generation'] or current['policy_hash']!=row['policy_hash']:
            raise ValueError('运行代次已变化，不能合并旧执行记录')
        for event in events:
            payload=event['payload']; sequence=event['sequence']
            if payload['generation']!=row['generation'] or event['kind'] not in ('tool_start','tool_result'):
                raise ValueError('执行记录身份不一致')
            fingerprint=hashlib.sha256(json.dumps(event,sort_keys=True).encode()).hexdigest()
            old=con.execute('SELECT payload_hash FROM instance_runtime_receipts WHERE instance_id=? AND generation=? AND sequence=?',
                (row['id'],row['generation'],sequence)).fetchone()
            if old:
                if old[0]!=fingerprint:raise ValueError('执行回执内容变化')
                continue
            con.execute('INSERT INTO instance_runtime_receipts VALUES(?,?,?,?)',(row['id'],row['generation'],sequence,fingerprint))
            if event['kind']=='tool_start':
                con.execute('INSERT OR IGNORE INTO instance_leases VALUES(?,?,?,?,?,?)',
                    (row['id'],row['generation'],payload['call_id'],payload['session_id'],payload['tool'],db.now()))
            else:
                con.execute('DELETE FROM instance_leases WHERE instance_id=? AND generation=? AND call_id=?',
                    (row['id'],row['generation'],payload['call_id']))
            con.execute('INSERT INTO instance_events(instance_id,generation,kind,session_id,call_id,tool,detail_json,created_at) VALUES(?,?,?,?,?,?,?,?)',
                (row['id'],row['generation'],event['kind'],payload['session_id'],payload['call_id'],payload['tool'],
                 json.dumps({'source':'broker_execution_queue','sequence':sequence,**({'succeeded':payload['succeeded']} if event['kind']=='tool_result' else {})}),
                 datetime.fromtimestamp(event['created_at'],timezone.utc).isoformat()))
    # Acknowledgement follows the durable transaction, never precedes it.
    runtime_call(row,'ack',sequence=events[-1]['sequence'])

def listing(discover=False):
    if discover: observer.collect()
    observed={r['id']:r for r in observer.snapshot()}
    result=[]
    for row in store.rows():
        live=observed.pop(row['id'],{})
        current=live.get('generation')==row['generation']
        try: inherited=row['policy_hash']==digest(system.compose(row['local_policy'],row['resources'])) if row['mode']=='controlled' else True
        except (OSError,ValueError): inherited=False
        execution=live.get('execution_status',{})
        gate_verified=live.get('supervision')!='broker-admission-v1' or execution.get('gate')=='open' and execution.get('protection_fresh')
        active=bool(current and live.get('verified') and gate_verified and row['gate']=='open' and live.get('connected') and inherited and system.current()['phase']=='ready' and dsl_policy.live_matches(row,live))
        result.append({**row, **live, 'policy':row['policy'], 'policy_hash':row['policy_hash'], 'gate':row['gate'],
                       'security': '执行受控' if active else '已加载，执行暂停' if row['gate'] in ('paused','open') else '正在加载与核验' if row['gate'] in ('starting','updating') else '未运行',
                       'active':active,'connected':bool(current and live.get('connected')),'mode':row['mode']})
    for live in observed.values():
        live.update(mode='observed',security='仅观测，未接管执行',active=False,resources=live.get('resources',[]))
        result.append(live)
    result.extend(discovery.windows_snapshot())
    for r in result:
        r['entry']=entry_details(r)
        if r['mode']=='observed':
            r['security']='仅观测，未接管执行' if r.get('connected') else '仅登记或发现，未接管执行'
            r['can_open']=bool(r.get('connected') and r.get('agent_type')=='dsh' or r.get('runtime',{}).get('open_url'))
    return {'instances':result}

def detail(ident):
    row=next((r for r in listing()['instances'] if r['id']==ident),None)
    if not row: raise ValueError('实例尚未发现，请刷新')
    if row['mode']=='controlled':
        row['policy_records']=records(row['policy'],row['resources'],row['active'])
        row['local_policy_records']=records(row['local_policy'],row['resources'],row['active'])
        shared=system.current()
        row['system_revision']=shared['revision']
        row['system_network']=shared['policy']['network']
        inherited=system.applicable(shared['policy']['rules'],row['resources'])
        for record in row['local_policy_records']:
            if record.get('effect')=='allow' and any(r['effect']=='deny' and r['action']==record.get('action') and (r['target']==record.get('target') or r['action'] in ('read','write') and record.get('target','').startswith(r['target']+'/')) for r in inherited):
                record['result']='受系统禁止约束'
        with db.connect() as con:
            row['proposals']=[{**dict(r),'policy':json.loads(r['policy_json'])} for r in con.execute('SELECT * FROM instance_proposals WHERE instance_id=? ORDER BY created_at DESC LIMIT 30',(ident,))]
        for p in row['proposals']:
            p.pop('policy_json',None)
            with db.connect() as con: local=con.execute('SELECT policy_json FROM instance_proposal_locals WHERE proposal_id=?',(p['id'],)).fetchone()
            if local: p['policy']=json.loads(local['policy_json'])
    else: row.update(policy_records=[],proposals=[])
    return row

@system.lifecycle
def register(body):
    system.ensure_ready()
    if body.get('mode')=='observed':
        url=discovery.local_url(body['open_url'])
        row=store.create(body['name'].strip(),body['agent_type'],[],mode='observed',environment=body['environment'])
        store.update(row['id'],runtime={'open_url':url})
        return store.get(row['id'])
    if body['agent_type'] not in ('dsh','hermes','other'): raise ValueError('不支持的 Agent 类型')
    if body.get('environment','wsl')!='wsl': raise ValueError('受控启动首轮仅支持 WSL 原生安装')
    from . import launch as entries
    launch=body.get('launch')
    if launch:
        launch=entries.canonical(launch,body['agent_type'])
    if body['agent_type']=='other' and not launch:raise ValueError('请配置 Agent 启动命令')
    resources=clean_resources(body['resources'] or ([launch['cwd']] if launch else []))
    if launch:launch=entries.validate_saved(launch,body['agent_type'],resources)
    return store.create(body['name'].strip(),body['agent_type'],resources,launch=launch)

@system.lifecycle
def configure(ident,body):
    system.ensure_ready(ident)
    with lock(ident):
        row=store.get(ident)
        if row['mode']!='controlled':raise ValueError('仅受控连接可配置启动命令与文件访问范围')
        if row['gate'] not in ('closed','failed'): raise ValueError('请先停止实例再修改连接设置')
        if body['expected_policy_hash']!=row['policy_hash']: raise ValueError('配置已变化，请刷新')
        if body.get('launch') and body.get('expected_launch_hash')!=(row.get('launch') or {}).get('hash'):raise ValueError('启动配置已变化，请刷新后重新保存')
        resources=clean_resources(body.get('resources') if body.get('resources') is not None else row['resources'])
        if resources!=row['resources'] and any(dsl_policy.current(scope)['documents'] for scope in ('system',ident)):
            raise ValueError('已有 DSL 策略引用访问范围；请先停用并应用这些策略，再调整目录，避免改变原策略对象')
        if resources[:len(row['resources'])]!=row['resources']:
            raise ValueError('已有目录映射必须保持稳定；当前仅支持在排序末尾追加目录，替换或移除目录请新建连接')
        from . import launch as entries
        launch=entries.canonical(body['launch'],row['agent_type'],resources) if body.get('launch') else row.get('launch')
        if launch:entries.validate_saved(launch,row['agent_type'],resources)
        effective=system.compose(canonical(row['local_policy'],resources),resources)
        store.update(ident,name=body['name'].strip(),resources=resources,policy=effective,policy_hash=digest(effective),local_policy=row['local_policy'],launch=launch)
        store.event(ident,'configured',{'resources':resources})
        return store.get(ident)

@system.lifecycle
def start(ident):
    system.ensure_ready(ident)
    with lock(ident):
        row=store.get(ident)
        if row['mode']!='controlled': raise ValueError('手动登记的实例仅支持打开与观测')
        effective=system.compose(row['local_policy'],row['resources'])
        if digest(effective)!=row['policy_hash']: raise ValueError('系统与 Agent 规则尚未合并，请重新确认系统规则')
        if row['gate'] in ('starting','updating'): raise ValueError('实例正在启动或更新')
        if row['gate']=='open':
            live=adapter(row).observe(row)
            if live.get('connected') and live.get('verified') and live.get('generation')==row['generation']:
                observer.collect()
                return detail(ident)
        # Recovering an uncertain process always starts by quiescing its registered cgroup.
        adapter(row).stop(row)
        generation=uuid.uuid4().hex; token=secrets.token_urlsafe(40)
        store.update(ident,gate='starting',generation=generation,token_hash=hashlib.sha256(token.encode()).hexdigest())
        store.event(ident,'starting',generation=generation)
        try:
            runtime=adapter(row).start(row,token,generation)
            if row.get('launch') and runtime.get('launch_hash')!=row['launch']['hash']:raise ValueError('运行命令与登记配置不一致')
            if runtime.get('dsl_hash')!=dsl_policy.launch_spec(row)['dsl_hash']:raise ValueError('运行 DSL 指纹与确认策略不一致')
            dsl_policy.record_receipt(ident,generation,runtime)
            store.update(ident,runtime=runtime,gate='open' if runtime.get('verified') else 'paused')
            open_runtime_gate(store.get(ident))
            store.event(ident,'verified' if runtime.get('verified') else 'verification_failed',runtime.get('verification',{}),generation)
            observer.collect()
            return detail(ident)
        except Exception:
            store.update(ident,gate='paused')
            store.event(ident,'start_failed',{'message':'启动或保护核验失败，实例保持暂停'},generation)
            raise

@system.lifecycle
def stop(ident,expected=None):
    with lock(ident):
        row=store.get(ident)
        if expected is not None and any(row[k]!=expected[k] for k in ('generation','policy_hash')):
            raise ValueError('Agent 运行身份或策略已经变化，请刷新后重新确认停止')
        try: close_runtime_gates([row])
        except Exception: pass # Broker stop below independently closes and terminates.
        store.update(ident,gate='paused')
        try: collect_runtime_events(row)
        except Exception: pass # A reporting fault must never prevent revocation.
        from .sessions import collect_kernel
        try: collect_kernel(row)
        except Exception: pass
        result=adapter(row).stop(row)
        store.update(ident,gate='closed',token_hash=None,runtime={})
        with db.connect() as con: con.execute('DELETE FROM instance_leases WHERE instance_id=?',(ident,))
        store.event(ident,'stopped',result,row['generation'])
        observer.collect()
        return result

def proposal_context(row):
    """Authority and execution identity frozen separately from candidate origin."""
    return {'instance_id':row['id'],'resources':row['resources'],'generation':row['generation'],
        'system_revision':system.current()['revision'],
        'local_hash':digest(row['local_policy']),'launch_hash':(row.get('launch') or {}).get('hash'),
        'binding':{k:row['runtime'].get(k) for k in ('pid','start_ticks','domain_id','host_id','boot_id')},
        'dsl':{scope:{k:dsl_policy.current(scope)[k] for k in ('revision','document_hash')} for scope in ('system',row['id'])}}

def validate_proposal(row,p):
    if p['actor']=='agent':
        raise ValueError('运行时提案缺少可信会话目标，不能应用到整个 Agent；请在当前会话重新生成')
    if p['state']!='pending' or p['base_hash']!=row['policy_hash'] or p['generation']!=row['generation']:
        raise ValueError('候选已经过期')
    with db.connect() as con:
        context=con.execute('SELECT context_json FROM instance_proposal_contexts WHERE proposal_id=?',(p['id'],)).fetchone()
        local_record=con.execute('SELECT * FROM instance_proposal_locals WHERE proposal_id=?',(p['id'],)).fetchone()
    # Older, unsnapshotted candidates remain visible but must be resubmitted.
    if not context or json.loads(context[0])!=proposal_context(row):raise ValueError('候选环境已经变化或缺少目标快照，请重新提交')
    if local_record and local_record['system_revision']!=system.current()['revision']:raise ValueError('系统规则已更新，候选已经过期')
    local=json.loads(local_record['policy_json']) if local_record else json.loads(p['policy_json'])
    if system.compose(local,row['resources'])!=json.loads(p['policy_json']):raise ValueError('系统规则已更新，候选已经过期')
    return local

@system.lifecycle
def proposals(ident,body,actor='user'):
    if actor=='agent':
        raise ValueError('运行时提案需要可信当前会话目标，请通过会话策略候选提交；不能更新整个 Agent')
    system.ensure_ready(ident)
    with lock(ident):
        row=store.get(ident)
        if row['mode']!='controlled':raise ValueError('仅受控实例可提交执行策略')
        request_hash=digest({'body':body,'actor':actor})
        with db.connect() as con:
            old=con.execute('SELECT * FROM instance_proposals WHERE instance_id=? AND request_key=?',(ident,body['request_key'])).fetchone()
            frozen=con.execute('SELECT request_hash FROM instance_proposal_contexts WHERE proposal_id=?',(old['id'],)).fetchone() if old else None
        if old and frozen:
            if frozen[0]!=request_hash:raise ValueError('幂等键已用于其他候选')
            return dict(old)
        local=system.local_candidate(row,body['policy'],actor)
        candidate=system.compose(local,row['resources'])
        from .launch import validate_policy
        validate_policy(row.get('launch'),candidate)
        context=proposal_context(row)
        proposal_hash=digest({'policy':candidate,'local_policy':local,'target':context,'generation':body['generation'],'base_hash':body['base_hash']})
        with db.connect() as con:
            old=con.execute('SELECT * FROM instance_proposals WHERE instance_id=? AND request_key=?',(ident,body['request_key'])).fetchone()
            if old:
                if old['proposal_hash']!=proposal_hash: raise ValueError('幂等键已用于其他候选')
                return dict(old)
            if body['generation']!=row['generation'] or body['base_hash']!=row['policy_hash']:
                raise ValueError('运行代次或策略已变化，请重新读取')
            classification='restrict' if restrictive(row['policy'],candidate) else 'expand'
            pid=uuid.uuid4().hex
            con.execute('INSERT INTO instance_proposals VALUES(?,?,?,?,?,?,?,?,?,?,?)',(pid,ident,body['request_key'],row['generation'],row['policy_hash'],json.dumps(candidate),proposal_hash,actor,classification,'pending',db.now()))
            con.execute('INSERT INTO instance_proposal_locals VALUES(?,?,?)',(pid,json.dumps(local),system.current()['revision']))
            con.execute('INSERT INTO instance_proposal_contexts VALUES(?,?,?)',(pid,json.dumps(context),request_hash))
            con.execute('INSERT INTO policy_approval_baselines VALUES(?,?)',('instance:'+pid,json.dumps(row['policy'])))
        store.event(ident,'policy_proposed',{'proposal_id':pid,'classification':classification},row['generation'])
        # Restriction is a classification, never application authority. In
        # particular an Agent tool must return without replacing its executor.
        return {'id':pid,'proposal_hash':proposal_hash,'classification':classification,'state':'pending','affected_sessions':'全部会话'}

@system.lifecycle
def apply(ident,pid,expected_hash):
    system.ensure_ready(ident)
    with lock(ident):
        row=store.get(ident)
        with db.connect() as con: p=con.execute('SELECT * FROM instance_proposals WHERE id=? AND instance_id=?',(pid,ident)).fetchone()
        if not p or p['proposal_hash']!=expected_hash: raise ValueError('候选确认内容不一致')
        if p['state']=='applied': return {'id':pid,'state':'applied','idempotent':True}
        local=validate_proposal(row,p)
        was_running=row['gate'] in ('open','paused')
        close_runtime_gates([row])
        store.update(ident,gate='updating')
        store.event(ident,'gate_closed',{'proposal_id':pid,'scope':'全部会话'},row['generation'])
        # Lease completion does not take the lifecycle lock: drains can finish.
        deadline=time.monotonic()+8
        while was_running and time.monotonic()<deadline:
            with db.connect() as con: count=con.execute('SELECT COUNT(*) FROM instance_leases WHERE instance_id=?',(ident,)).fetchone()[0]
            if not count: break
            time.sleep(.05)
        try:
            stopped=adapter(row).stop(row)
            store.event(ident,'quiesced',stopped,row['generation'])
            candidate=json.loads(p['policy_json'])
            store.update(ident,policy=candidate,local_policy=local,policy_hash=digest(candidate),gate='closed',token_hash=None)
            with db.connect() as con:
                con.execute('DELETE FROM instance_leases WHERE instance_id=?',(ident,))
                con.execute("UPDATE instance_proposals SET state='applying' WHERE id=?",(pid,))
            result=start(ident) if was_running else store.get(ident)
            if was_running and not result.get('active'): raise ValueError('实际限制尚未核验，实例保持暂停')
            with db.connect() as con: con.execute("UPDATE instance_proposals SET state='applied' WHERE id=?",(pid,))
            store.event(ident,'policy_applied',{'proposal_id':pid,'classification':p['classification'],'old_handles':'进程终止后失效'},result.get('generation'))
            return {'id':pid,'state':'applied','instance':result}
        except Exception:
            store.update(ident,gate='paused')
            with db.connect() as con: con.execute("UPDATE instance_proposals SET state='failed' WHERE id=?",(pid,))
            store.event(ident,'policy_apply_failed',{'proposal_id':pid})
            raise

@system.lifecycle
def reject(ident,pid,expected_hash):
    with lock(ident),db.connect() as con:
        p=con.execute('SELECT * FROM instance_proposals WHERE id=? AND instance_id=?',(pid,ident)).fetchone()
        if not p or p['proposal_hash']!=expected_hash:raise ValueError('候选确认内容不一致')
        if p['state']=='rejected':return {'id':pid,'state':'rejected','idempotent':True}
        if p['state']!='pending':raise ValueError('候选已处理，不能拒绝')
        con.execute("UPDATE instance_proposals SET state='rejected' WHERE id=?",(pid,))
    store.event(ident,'policy_rejected',{'proposal_id':pid,'proposal_hash':expected_hash})
    return {'id':pid,'state':'rejected'}

def agent_auth(ident,token,generation):
    with db.connect() as con: r=con.execute('SELECT token_hash,generation FROM agent_instances WHERE id=?',(ident,)).fetchone()
    if not r or not token or not r['token_hash'] or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),r['token_hash']) or generation!=r['generation']:
        raise PermissionError('实例凭据或运行代次无效')
    return store.get(ident)

def lease(ident,body):
    current=store.get(ident)
    if independent(current):return runtime_call(current,'lease',body=body)
    # BEGIN IMMEDIATE orders admission against gate changes in the same database.
    denial=None
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT * FROM agent_instances WHERE id=?',(ident,)).fetchone()
        if row['generation']!=body['generation'] or row['gate']!='open' or system.current(con)['phase']!='ready':
            denial='实例安全入口已暂停，请等待核验'
        if con.execute("SELECT 1 FROM instance_dsl_scopes WHERE scope_id IN ('system',?) AND phase!='ready'",(ident,)).fetchone():denial='DSL 策略应用未完成，工具执行暂停'
        policy=json.loads(row['policy_json'])
        rule=next((r for r in policy['rules'] if r['action']=='tool' and r['target']==body['tool'] and r['effect']!='allow'),None)
        if rule: denial='实例策略'+('禁止此工具' if rule['effect']=='deny' else '要求在 AgentScope 中确认工具权限')
        old=con.execute('SELECT * FROM instance_leases WHERE instance_id=? AND call_id=?',(ident,body['call_id'])).fetchone()
        if old and any(old[key]!=body[key] for key in ('generation','session_id','tool')): denial='工具调用身份已变化'
        if not denial: con.execute('INSERT OR IGNORE INTO instance_leases VALUES(?,?,?,?,?,?)',(ident,body['generation'],body['call_id'],body['session_id'],body['tool'],db.now()))
    if denial:
        store.event(ident,'tool_denied',{'reason':denial},body['generation'],body['session_id'],body['call_id'],body['tool'])
        return {'allowed':False,'reason':denial}
    store.event(ident,'tool_start',{},body['generation'],body['session_id'],body['call_id'],body['tool'])
    return {'allowed':True}

def result(ident,body):
    current=store.get(ident)
    if independent(current):return runtime_call(current,'result',body=body)
    with db.connect() as con: con.execute('DELETE FROM instance_leases WHERE instance_id=? AND generation=? AND call_id=?',(ident,body['generation'],body['call_id']))
    store.event(ident,'tool_result',{'succeeded':body['succeeded']},body['generation'],body['session_id'],body['call_id'],body['tool'])
    return {'ok':True}
