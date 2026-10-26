"""Explicit, resumable conversion of unapproved grouped template proposals."""
import json
from fastapi import HTTPException
from .. import db
from .policy import digest
from .system_policy import lifecycle

SCHEMA='''CREATE TABLE IF NOT EXISTS policy_approval_splits(
 parent_id TEXT NOT NULL,child_id TEXT NOT NULL UNIQUE,configuration_id TEXT NOT NULL,
 revision INTEGER NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(parent_id,configuration_id));'''

def init(con):con.executescript(SCHEMA)

def replacements(ident):
    with db.connect() as con:
        return [dict(row) for row in con.execute('SELECT child_id AS id,configuration_id,revision FROM policy_approval_splits WHERE parent_id=? ORDER BY rowid',(ident,))]

def completed(proposal):
    if not proposal['request_key'].startswith('template:split-'):return True
    with db.connect() as con:
        return bool(con.execute('SELECT 1 FROM policy_approval_splits WHERE child_id=?',(proposal['id'],)).fetchone())

@lifecycle
def split_pending(ident):
    from . import dsl_policy as dsl,template_configurations as configurations
    from .approval_views import scopes
    existing=replacements(ident)
    if existing:return {'source_id':ident,'records':existing,'idempotent':True}
    with db.connect() as con:
        raw=con.execute('SELECT * FROM instance_dsl_proposals WHERE id=?',(ident,)).fetchone()
        binding=con.execute('SELECT selections_json FROM template_configuration_proposals WHERE proposal_id=?',(ident,)).fetchone()
        receipt=con.execute("SELECT 1 FROM policy_approval_decisions WHERE approval_id=? AND state IN ('approved','applying','applied')",(ident,)).fetchone()
    if not raw or raw['scope_id'] not in scopes():raise HTTPException(404,'审批记录不存在')
    p=dsl.unpack(raw)
    if p['state'] not in ('pending','splitting') or receipt:raise ValueError('只能拆分尚未批准或应用的记录')
    selections=json.loads(binding[0]) if binding else []
    if len(selections)<2:raise ValueError('此记录已经是单项策略审批')
    base=dsl.current(p['scope_id'])
    if p['base_hash']!=base['document_hash'] or p['base_revision']!=base['revision']:
        raise ValueError('原审批基线已经变化，请逐项重新提交')
    configurations.verify_proposal(ident)
    if dsl.target_snapshot(p['scope_id'],p['documents'])!=p['targets']:
        raise ValueError('原审批执行目标已经变化，请逐项重新提交')
    # Freeze the old object before creating children. A partial conversion has
    # no approvable parent, and children remain blocked until the final mapping.
    with db.connect() as con:
        con.execute("UPDATE instance_dsl_proposals SET state='splitting' WHERE id=?",(ident,))
    children=[]
    for selection in selections:
        row=configurations.load(selection['id'],selection['revision'])
        if row['scope_id']!=p['scope_id'] or digest(row['document'])!=selection['document_hash']:
            raise ValueError('原审批配置绑定不一致')
        child=configurations.propose(row['id'],{'revision':row['revision'],'operation':selection.get('operation','apply'),
            'acknowledge_coverage':selection.get('acknowledge_coverage',False),
            'request_key':'split-'+ident+'-'+row['id']})
        if child['state']!='pending':raise ValueError('独立策略未通过编译，拆分保留待重试')
        children.append((ident,child['id'],row['id'],row['revision'],db.now()))
    with db.connect() as con:
        con.executemany('INSERT OR IGNORE INTO policy_approval_splits VALUES(?,?,?,?,?)',children)
        con.execute("UPDATE instance_dsl_proposals SET state='superseded' WHERE id=?",(ident,))
        db.audit(con,None,'policy_approval_split','authenticated_operator',{'source_id':ident,'child_ids':[row[1] for row in children]})
    return {'source_id':ident,'records':replacements(ident),'idempotent':False}
