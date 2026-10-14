"""Administrator-owned display names, keyed by exact native session identity.

Metadata only: no native session resume, prompt, execution binding or permission
change. Native names remain available for provenance and search.
"""
import re
from .. import db

SCHEMA='''CREATE TABLE IF NOT EXISTS instance_session_display_names(
 instance_id TEXT NOT NULL,session_id TEXT NOT NULL,name TEXT NOT NULL,
 native_name TEXT,revision INTEGER NOT NULL,updated_at TEXT NOT NULL,
 PRIMARY KEY(instance_id,session_id));'''


def init(con):con.executescript(SCHEMA)


def project(ident,result):
    with db.connect() as con:
        saved={r['session_id']:dict(r) for r in con.execute('SELECT * FROM instance_session_display_names WHERE instance_id=?',(ident,))}
    sessions=[]
    for item in result.get('sessions',[]):
        name=saved.get(item['id'])
        sessions.append({**item,'native_name':item.get('native_name',item.get('name')),
                         **({'name':name['name'],'name_revision':name['revision'],'name_source':'administrator'} if name else {})})
    return {**result,'sessions':sessions}


def rename(ident,sid,name,expected_name):
    from .sessions import session_context
    name=name.strip()
    if not name or len(name)>120 or re.search(r'[\x00-\x1f\x7f]',name):raise ValueError('会话名称须为 1–120 字的单行文本')
    row,session,_,_=session_context(ident,sid)
    if session.get('name')!=expected_name:raise ValueError('会话名称已经变化，请刷新后重试')
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        old=con.execute('SELECT * FROM instance_session_display_names WHERE instance_id=? AND session_id=?',(ident,sid)).fetchone()
        current=old['name'] if old else session.get('native_name',session.get('name'))
        if current!=expected_name:raise ValueError('会话名称已经变化，请刷新后重试')
        if old and old['name']==name:return {'name':name,'revision':old['revision'],'idempotent':True}
        revision=(old['revision'] if old else 0)+1
        con.execute('INSERT INTO instance_session_display_names VALUES(?,?,?,?,?,?) ON CONFLICT(instance_id,session_id) DO UPDATE SET name=excluded.name,revision=excluded.revision,updated_at=excluded.updated_at',
                    (ident,sid,name,session.get('native_name'),revision,db.now()))
        db.audit(con,None,'session_display_name_changed','administrator',{'instance_id':ident,'session_id':sid,'name':name,'revision':revision})
    return {'name':name,'revision':revision,'metadata_only':True}
