"""Trusted, instance-wide policy lifecycle and atomic execution leases."""
import hashlib, hmac, json, os, secrets, threading, time, uuid
from .. import db
from ..broker_client import call as broker
from . import store, discovery, system_policy as system
from .adapters import adapter, entry_details
from .policy import canonical, clean_resources, digest, records, restrictive

_locks={}; _lock=threading.Lock()
def lock(ident):
    with _lock: return _locks.setdefault(ident,threading.RLock())

class Observer:
    def __init__(self): self.rows={}; self.lock=threading.RLock(); self.stop_event=threading.Event(); self.thread=None
    def collect(self):
        try:
            result=broker({'action':'agent-instance-inventory'},timeout=2)
            observed=time.monotonic()
            with self.lock: self.rows={r['id']:{**r,'_observed':observed} for r in result['instances']}
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
            self.collect(); self.stop_event.wait(3)
    def start(self):
        if os.getenv('AGENTSCOPE_INSTANCE_WORKER','1')=='0': return
        if self.thread and self.thread.is_alive(): return
        self.stop_event.clear(); self.thread=threading.Thread(target=self.run,name='agent-instance-observer',daemon=True); self.thread.start()
    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(3)
observer=Observer()

def listing(discover=False):
    if discover: observer.collect()
    observed={r['id']:r for r in observer.snapshot()}
    result=[]
    for row in store.rows():
        live=observed.pop(row['id'],{})
        current=live.get('generation')==row['generation']
        try: inherited=row['policy_hash']==digest(system.compose(row['local_policy'],row['resources'])) if row['mode']=='controlled' else True
        except (OSError,ValueError): inherited=False
        active=bool(current and live.get('verified') and row['gate']=='open' and live.get('connected') and inherited and system.current()['phase']=='ready')
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
    if body['agent_type'] not in ('dsh','hermes'): raise ValueError('受控启动支持 DSH 和 WSL 原生 Hermes')
    if body.get('environment','wsl')!='wsl': raise ValueError('受控启动首轮仅支持 WSL 原生安装')
    return store.create(body['name'].strip(),body['agent_type'],clean_resources(body['resources']))

@system.lifecycle
def configure(ident,body):
    system.ensure_ready()
    with lock(ident):
        row=store.get(ident)
        if row['gate'] not in ('closed','failed'): raise ValueError('请先停止实例再修改连接设置')
        if body['expected_policy_hash']!=row['policy_hash']: raise ValueError('配置已变化，请刷新')
        resources=clean_resources(body['resources'])
        effective=system.compose(canonical(row['local_policy'],resources),resources)
        store.update(ident,name=body['name'].strip(),resources=resources,policy=effective,policy_hash=digest(effective),local_policy=row['local_policy'])
        store.event(ident,'configured',{'resources':resources})
        return store.get(ident)

@system.lifecycle
def start(ident):
    system.ensure_ready()
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
            store.update(ident,runtime=runtime,gate='open' if runtime.get('verified') else 'paused')
            store.event(ident,'verified' if runtime.get('verified') else 'verification_failed',runtime.get('verification',{}),generation)
            observer.collect()
            return detail(ident)
        except Exception:
            store.update(ident,gate='paused')
            store.event(ident,'start_failed',{'message':'启动或保护核验失败，实例保持暂停'},generation)
            raise

@system.lifecycle
def stop(ident):
    with lock(ident):
        row=store.get(ident); store.update(ident,gate='paused')
        result=adapter(row).stop(row)
        store.update(ident,gate='closed',token_hash=None,runtime={})
        with db.connect() as con: con.execute('DELETE FROM instance_leases WHERE instance_id=?',(ident,))
        store.event(ident,'stopped',result,row['generation'])
        observer.collect()
        return result

@system.lifecycle
def proposals(ident,body,actor='user'):
    system.ensure_ready()
    with lock(ident):
        row=store.get(ident)
        local=system.local_candidate(row,body['policy'],actor)
        candidate=system.compose(local,row['resources'])
        proposal_hash=digest({'policy':candidate,'local_policy':local,'system_revision':system.current()['revision'],'generation':body['generation'],'base_hash':body['base_hash']})
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
        store.event(ident,'policy_proposed',{'proposal_id':pid,'classification':classification},row['generation'])
        if classification=='restrict':
            if actor=='agent' and row['gate']=='open':
                # Return the typed receipt so the proposing tool can release
                # its lease before rebuilding the executor that called us.
                def queued():
                    try: apply(ident,pid,proposal_hash)
                    except Exception: pass # apply records failure and keeps the gate paused
                threading.Thread(target=queued,name='instance-policy-update',daemon=True).start()
                return {'id':pid,'proposal_hash':proposal_hash,'classification':classification,'state':'queued','affected_sessions':'全部会话'}
            return apply(ident,pid,proposal_hash)
        return {'id':pid,'proposal_hash':proposal_hash,'classification':classification,'state':'pending','affected_sessions':'全部会话'}

@system.lifecycle
def apply(ident,pid,expected_hash):
    system.ensure_ready()
    with lock(ident):
        row=store.get(ident)
        with db.connect() as con: p=con.execute('SELECT * FROM instance_proposals WHERE id=? AND instance_id=?',(pid,ident)).fetchone()
        if not p or p['proposal_hash']!=expected_hash: raise ValueError('候选确认内容不一致')
        if p['state']=='applied': return {'id':pid,'state':'applied','idempotent':True}
        if p['state']!='pending' or p['base_hash']!=row['policy_hash'] or p['generation']!=row['generation']: raise ValueError('候选已经过期')
        with db.connect() as con: local_record=con.execute('SELECT * FROM instance_proposal_locals WHERE proposal_id=?',(pid,)).fetchone()
        if local_record and local_record['system_revision']!=system.current()['revision']: raise ValueError('系统规则已更新，候选已经过期')
        local=json.loads(local_record['policy_json']) if local_record else json.loads(p['policy_json'])
        if system.compose(local,row['resources'])!=json.loads(p['policy_json']): raise ValueError('系统规则已更新，候选已经过期')
        was_running=row['gate'] in ('open','paused')
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

def agent_auth(ident,token,generation):
    with db.connect() as con: r=con.execute('SELECT token_hash,generation FROM agent_instances WHERE id=?',(ident,)).fetchone()
    if not r or not token or not r['token_hash'] or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),r['token_hash']) or generation!=r['generation']:
        raise PermissionError('实例凭据或运行代次无效')
    return store.get(ident)

def lease(ident,body):
    # BEGIN IMMEDIATE orders admission against gate changes in the same database.
    denial=None
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT * FROM agent_instances WHERE id=?',(ident,)).fetchone()
        if row['generation']!=body['generation'] or row['gate']!='open' or system.current(con)['phase']!='ready':
            denial='实例安全入口已暂停，请等待核验'
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
    with db.connect() as con: con.execute('DELETE FROM instance_leases WHERE instance_id=? AND generation=? AND call_id=?',(ident,body['generation'],body['call_id']))
    store.event(ident,'tool_result',{'succeeded':body['succeeded']},body['generation'],body['session_id'],body['call_id'],body['tool'])
    return {'ok':True}
