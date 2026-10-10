"""User-managed common constraints; typed policy, reviewed rollout, fail-closed gates."""
import functools
import json
import threading
import time
import uuid
from pathlib import Path
from .. import db
from .policy import canonical, default_policy, digest, records

LOCK = threading.RLock()
CONTEXT = threading.local()
SCHEMA = """
CREATE TABLE IF NOT EXISTS system_security_policy (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), policy_json TEXT NOT NULL,
 policy_hash TEXT NOT NULL, revision INTEGER NOT NULL, phase TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS instance_local_policies (instance_id TEXT PRIMARY KEY, policy_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS instance_proposal_locals (proposal_id TEXT PRIMARY KEY, policy_json TEXT NOT NULL, system_revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS system_security_proposals (
 id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL,
 base_hash TEXT NOT NULL, revision INTEGER NOT NULL, policy_json TEXT NOT NULL,
 targets_json TEXT NOT NULL, proposal_hash TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL);
"""

def init(con):
    con.executescript(SCHEMA)
    policy = default_policy()
    con.execute('INSERT OR IGNORE INTO system_security_policy VALUES(1,?,?,0,?,?)',
                (json.dumps(policy), digest(policy), 'ready', db.now()))
    con.execute('INSERT OR IGNORE INTO instance_local_policies SELECT id,policy_json FROM agent_instances')
    # A controller loss during rollout never turns an incomplete update into ready.
    con.execute("UPDATE system_security_policy SET phase='blocked' WHERE phase='updating'")

def current(con=None):
    if con is None:
        with db.connect() as connection: return current(connection)
    row = dict(con.execute('SELECT * FROM system_security_policy WHERE singleton=1').fetchone())
    row['policy'] = json.loads(row.pop('policy_json'))
    return row

def lifecycle(fn):
    @functools.wraps(fn)
    def run(*args, **kwargs):
        with LOCK: return fn(*args, **kwargs)
    return run

def ensure_ready(instance_id=None):
    if current()['phase'] != 'ready' and not getattr(CONTEXT, 'applying', False):
        raise ValueError('系统规则更新尚未完成，执行保持暂停；请重新确认系统规则')
    from . import dsl_policy
    if not getattr(dsl_policy.APPLYING,'value',False):dsl_policy.ensure_ready(instance_id)

def applicable(rules, resources):
    return [rule for rule in rules if rule['action'] not in ('read','write') or
            any(Path(rule['target']) == Path(root) or Path(root) in Path(rule['target']).parents for root in resources)]

def compose(local, resources, shared=None):
    shared = current()['policy'] if shared is None else shared
    rules = local['rules'] + applicable(shared['rules'], resources)
    network = 'disabled' if 'disabled' in (local['network'], shared['network']) else 'model_only'
    return canonical({'rules':rules,'network':network}, resources)

def local_candidate(row, value, actor):
    candidate = canonical(value, row['resources'])
    if actor == 'agent':
        inherited = applicable(current()['policy']['rules'],row['resources'])
        candidate['rules'] = [r for r in candidate['rules'] if r not in inherited or r in row['local_policy']['rules']]
    return candidate

def canonical_system(value):
    from . import store
    resources = sorted({p for row in store.rows() if row['mode']=='controlled' for p in row['resources']})
    if not isinstance(value,dict) or not isinstance(value.get('rules',[]),list) or any(not isinstance(r,dict) for r in value.get('rules',[])):
        raise ValueError('策略规则必须是记录数组')
    if any(r.get('effect') == 'allow' for r in value.get('rules', [])):
        raise ValueError('系统规则用于共同限制；具体授权请在当前 Agent 配置中设置')
    if any(r.get('action') in ('read','write') and str(r.get('target','')).startswith('/w/') for r in value.get('rules', [])):
        raise ValueError('系统文件规则请使用已登记资源的主机绝对路径')
    return canonical(value,resources)

def plan(policy):
    from . import store
    result=[]
    blocked=current()['phase'] != 'ready'
    for row in store.rows():
        if row['mode'] != 'controlled': continue
        effective=compose(row['local_policy'],row['resources'],policy)
        result.append({'id':row['id'],'name':row['name'],'generation':row['generation'],
            'base_hash':row['policy_hash'],'gate':row['gate'],'resources':row['resources'],
            'local_hash':digest(row['local_policy']),'effective_hash':digest(effective),
            'affected':blocked or digest(effective)!=row['policy_hash']})
    return result

def unpack_proposal(row):
    result=dict(row)
    result['policy']=json.loads(result.pop('policy_json'))
    result['targets']=json.loads(result.pop('targets_json'))
    result['classification']='system'
    return result

def detail():
    from . import controller as c, store
    shared=current()
    rows=[row for row in c.listing()['instances'] if row['mode']=='controlled']
    with db.connect() as con:
        pending=[unpack_proposal(p) for p in con.execute("SELECT * FROM system_security_proposals WHERE state='pending' AND revision=? ORDER BY created_at DESC LIMIT 30",(shared['revision'],))]
    rule_records=[]
    for rule in shared['policy']['rules']:
        targets=[r for r in rows if applicable([rule],r['resources'])]
        count=sum(bool(r['active']) for r in targets)
        record=records({'rules':[rule],'network':shared['policy']['network']},[],False)[-1]
        record.update(source='系统规则',result='行为约定' if rule['action']=='behavior' else f'已核验 {count} / {len(targets)} 个连接' if targets else '等待匹配的工作区')
        rule_records.append(record)
    return {**shared,'id':'system','generation':str(shared['revision']),
        'mode':'controlled','resources':sorted({p for r in rows for p in r['resources']}),
        'active':bool(rows) and all(r['active'] for r in rows),'policy_records':rule_records,
        'proposals':pending,'connection_count':len(rows),'active_count':sum(bool(r['active']) for r in rows),
        'network_result':f'已核验 {sum(bool(r["active"]) for r in rows)} / {len(rows)} 个连接' if shared['phase']=='ready' else '应用未完成'}

@lifecycle
def propose(body):
    candidate=canonical_system(body['policy'])
    request_hash=digest({'policy':candidate,'base_hash':body['base_hash'],'revision':body['revision']})
    with db.connect() as con:
        old=con.execute('SELECT * FROM system_security_proposals WHERE request_key=?',(body['request_key'],)).fetchone()
        if old:
            if old['request_hash']!=request_hash: raise ValueError('幂等键已用于其他系统规则候选')
            return unpack_proposal(old)
    shared=current()
    if body['base_hash']!=shared['policy_hash'] or body['revision']!=shared['revision']:
        raise ValueError('系统规则已有更新，请刷新后重新编辑')
    targets=plan(candidate)
    proposal_hash=digest({'request_hash':request_hash,'targets':targets})
    pid=uuid.uuid4().hex
    with db.connect() as con:
        con.execute('INSERT INTO system_security_proposals VALUES(?,?,?,?,?,?,?,?,?,?)',
            (pid,body['request_key'],request_hash,shared['policy_hash'],shared['revision'],json.dumps(candidate),json.dumps(targets),proposal_hash,'pending',db.now()))
        row=con.execute('SELECT * FROM system_security_proposals WHERE id=?',(pid,)).fetchone()
    return unpack_proposal(row)

@lifecycle
def apply(pid, expected_hash):
    from . import controller as c, store
    with db.connect() as con: raw=con.execute('SELECT * FROM system_security_proposals WHERE id=?',(pid,)).fetchone()
    if not raw or raw['proposal_hash']!=expected_hash: raise ValueError('系统候选确认内容不一致')
    proposal=unpack_proposal(raw)
    if proposal['state']=='applied': return {'id':pid,'state':'applied','idempotent':True}
    shared=current()
    if proposal['state']!='pending' or proposal['base_hash']!=shared['policy_hash'] or proposal['revision']!=shared['revision']:
        raise ValueError('系统候选已经过期，请重新提交')
    candidate=canonical_system(proposal['policy'])
    if plan(candidate)!=proposal['targets']: raise ValueError('受影响的连接或规则已有变化，请重新提交')
    affected=[target for target in proposal['targets'] if target['affected']]
    resume=[]
    for target in affected:
        row=store.get(target['id'])
        live=c.adapter(row).observe(row) if row['gate']=='open' else {}
        if row['gate']=='open' and live.get('connected') and live.get('verified') and live.get('generation')==row['generation']:
            resume.append(row['id'])
    with db.connect() as con:
        con.execute("UPDATE system_security_policy SET phase='updating',updated_at=? WHERE singleton=1",(db.now(),))
        con.execute("UPDATE system_security_proposals SET state='applying' WHERE id=?",(pid,))
        for target in affected: con.execute("UPDATE agent_instances SET gate='updating',updated_at=? WHERE id=?",(db.now(),target['id']))
    CONTEXT.applying=True
    try:
        deadline=time.monotonic()+8
        while affected and time.monotonic()<deadline:
            with db.connect() as con:
                count=sum(con.execute('SELECT COUNT(*) FROM instance_leases WHERE instance_id=?',(t['id'],)).fetchone()[0] for t in affected)
            if not count: break
            time.sleep(.05)
        # Stop every old executor before committing any new shared authority.
        for target in affected:
            row=store.get(target['id'])
            c.adapter(row).stop(row)
            store.event(row['id'],'system_policy_quiesced',{'proposal_id':pid},row['generation'])
        with db.connect() as con:
            con.execute('UPDATE system_security_policy SET policy_json=?,policy_hash=?,revision=revision+1,updated_at=? WHERE singleton=1',
                (json.dumps(candidate),digest(candidate),db.now()))
            for target in proposal['targets']:
                row=store.get(target['id'])
                effective=compose(row['local_policy'],row['resources'],candidate)
                con.execute('UPDATE agent_instances SET policy_json=?,policy_hash=?,updated_at=? WHERE id=?',
                    (json.dumps(effective),digest(effective),db.now(),row['id']))
            for target in affected:
                con.execute("UPDATE agent_instances SET gate='closed',token_hash=NULL,runtime_json='{}' WHERE id=?",(target['id'],))
                con.execute('DELETE FROM instance_leases WHERE instance_id=?',(target['id'],))
            con.execute("UPDATE instance_proposals SET state='superseded' WHERE state='pending'")
        for ident in resume:
            result=c.start(ident)
            if not result.get('runtime',{}).get('verified'): raise ValueError('系统规则实际加载尚未核验')
        with db.connect() as con:
            con.execute("UPDATE system_security_policy SET phase='ready' WHERE singleton=1")
            con.execute("UPDATE system_security_proposals SET state='applied' WHERE id=?",(pid,))
        for target in affected: store.event(target['id'],'system_policy_applied',{'proposal_id':pid,'system_revision':current()['revision']})
        c.observer.collect()
        return {'id':pid,'state':'applied','affected_count':len(affected),'resumed_count':len(resume)}
    except Exception:
        for target in affected:
            store.update(target['id'],gate='paused')
            try: c.adapter(store.get(target['id'])).stop(store.get(target['id']))
            except Exception: pass
            store.event(target['id'],'system_policy_failed',{'proposal_id':pid})
        with db.connect() as con:
            con.execute("UPDATE system_security_policy SET phase='blocked' WHERE singleton=1")
            con.execute("UPDATE system_security_proposals SET state='failed' WHERE id=?",(pid,))
        raise
    finally:
        CONTEXT.applying=False
