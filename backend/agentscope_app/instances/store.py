"""Instance state is separate from immutable legacy tasks."""
import json, uuid
from .. import db
from .policy import default_policy, digest
SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_instances (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, agent_type TEXT NOT NULL,
 environment TEXT NOT NULL, mode TEXT NOT NULL, resources_json TEXT NOT NULL,
 policy_json TEXT NOT NULL, policy_hash TEXT NOT NULL, generation TEXT,
 gate TEXT NOT NULL DEFAULT 'closed', token_hash TEXT, runtime_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS instance_proposals (
 id TEXT PRIMARY KEY, instance_id TEXT NOT NULL, request_key TEXT NOT NULL,
 generation TEXT, base_hash TEXT NOT NULL, policy_json TEXT NOT NULL, proposal_hash TEXT NOT NULL,
 actor TEXT NOT NULL, classification TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(instance_id,request_key));
CREATE TABLE IF NOT EXISTS instance_events (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, instance_id TEXT NOT NULL, generation TEXT,
 kind TEXT NOT NULL, session_id TEXT, call_id TEXT, tool TEXT, detail_json TEXT NOT NULL,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS instance_leases (
 instance_id TEXT NOT NULL, generation TEXT NOT NULL, call_id TEXT NOT NULL,
 session_id TEXT NOT NULL, tool TEXT NOT NULL, started_at TEXT NOT NULL,
 PRIMARY KEY(instance_id,generation,call_id));
"""
def init():
    with db.connect() as con:
        con.executescript(SCHEMA)
        from . import system_policy
        system_policy.init(con)
def unpack(row):
    if not row: raise ValueError('实例不存在')
    r=dict(row)
    for key in ('resources','policy','runtime'): r[key]=json.loads(r.pop(key+'_json'))
    with db.connect() as con: local=con.execute('SELECT policy_json FROM instance_local_policies WHERE instance_id=?',(r['id'],)).fetchone()
    r['local_policy']=json.loads(local['policy_json']) if local else r['policy']
    r.pop('token_hash',None)
    return r
def get(ident):
    with db.connect() as con: return unpack(con.execute('SELECT * FROM agent_instances WHERE id=?',(ident,)).fetchone())
def rows():
    with db.connect() as con: return [unpack(r) for r in con.execute('SELECT * FROM agent_instances ORDER BY created_at')]
def create(name,agent_type,resources,mode='controlled',environment='wsl'):
    from . import system_policy
    system_policy.ensure_ready()
    ident='instance-'+uuid.uuid4().hex[:16]; local=default_policy()
    policy=system_policy.compose(local,resources) if mode=='controlled' else local
    with db.connect() as con:
        con.execute('INSERT INTO agent_instances(id,name,agent_type,environment,mode,resources_json,policy_json,policy_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,name,agent_type,environment,mode,json.dumps(resources),json.dumps(policy),digest(policy),db.now(),db.now()))
        con.execute('INSERT INTO instance_local_policies VALUES(?,?)',(ident,json.dumps(local)))
    event(ident,'registered',{'mode':mode})
    return get(ident)
def update(ident,**fields):
    if set(fields)-{'name','resources','policy','policy_hash','generation','gate','token_hash','runtime','local_policy'}: raise ValueError('Invalid instance update')
    local=fields.pop('local_policy',fields.get('policy'))
    values=[]; columns=[]
    for key,value in fields.items():
        column=key+'_json' if key in ('resources','policy','runtime') else key
        columns.append(column+'=?'); values.append(json.dumps(value,ensure_ascii=False) if column.endswith('_json') else value)
    with db.connect() as con:
        if columns: con.execute('UPDATE agent_instances SET '+','.join(columns)+',updated_at=? WHERE id=?',(*values,db.now(),ident))
        if local is not None: con.execute('INSERT OR REPLACE INTO instance_local_policies VALUES(?,?)',(ident,json.dumps(local)))
def event(ident,kind,detail=None,generation=None,session_id=None,call_id=None,tool=None):
    with db.connect() as con:
        con.execute('INSERT INTO instance_events(instance_id,generation,kind,session_id,call_id,tool,detail_json,created_at) VALUES(?,?,?,?,?,?,?,?)',(ident,generation,kind,session_id,call_id,tool,json.dumps(detail or {},ensure_ascii=False),db.now()))
def events(ident,before=None):
    with db.connect() as con: rows=con.execute('SELECT * FROM instance_events WHERE instance_id=? AND (? IS NULL OR seq<?) ORDER BY seq DESC LIMIT 100',(ident,before,before)).fetchall()
    return [{k:v for k,v in dict(r).items() if k!='detail_json'}|{'detail':json.loads(r['detail_json'])} for r in rows]
