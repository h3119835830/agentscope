"""Customer approval reads over the existing DSL proposal/confirm lifecycle."""
from fastapi import HTTPException
from .. import db
from . import dsl_policy as dsl, store


def scopes():
    from ..console import hidden
    retained=hidden('agent')
    return {'system':'全部受控 Agent',**{r['id']:r['name'] for r in store.rows() if r['mode']=='controlled' and r['id'] not in retained}}


def pending_count():
    visible=scopes()
    with db.connect() as con:
        return sum(r[1] for r in con.execute("SELECT scope_id,COUNT(*) FROM instance_dsl_proposals WHERE state='pending' GROUP BY scope_id") if r[0] in visible)


def project(p,names,full=False):
    from ..console import hidden
    base=dsl.current(p['scope_id'])
    status=p['state'];reason=''
    if status=='pending':
        try:
            if p['base_revision']!=base['revision'] or p['base_hash']!=base['document_hash']:
                raise ValueError('策略配置已经变化，请重新校验')
            if dsl.target_snapshot(p['scope_id'],p['documents'])!=p['targets']:
                raise ValueError('Agent 连接或运行环境已经变化，请重新校验')
            from ..history.agent_context import validate_documents
            validate_documents(p['scope_id'],p['documents'],base['documents'])
        except (ValueError,RuntimeError,OSError):
            status='stale';reason='Agent 环境或策略配置已经变化，需要重新校验。'
    elif status=='invalid':reason='候选未通过运行环境校验，请调整配置后重新提交。'
    elif status=='failed':reason='上次应用未完成，请检查配置并重新校验。'
    visible_targets=[t for t in p['targets'] if t['id'] not in hidden('agent')]
    row={'id':p['id'],'scope_id':p['scope_id'],'scope_type':'system' if p['scope_id']=='system' else 'agent',
         'target_name':names[p['scope_id']],'name':'、'.join(d['name'] for d in p['documents']) or '移除本层策略',
         'status':status,'created_at':p['created_at'],'document_count':len(p['documents']),
         'can_apply':status=='pending','reason':reason,
         'affected_count':len(visible_targets),'total_affected_count':len(p['targets'])}
    if full:
        compilation=next((c for c in p['result'].get('compilations',[]) if c['instance_id'] in {t['id'] for t in visible_targets}),None)
        records=dsl.policy_records(compilation,p['scope_id']) if compilation else []
        row.update(documents=p['documents'],records=records,targets=visible_targets,proposal_hash=p['proposal_hash'],
                   previous_documents=base['documents'] if p['base_hash']==base['document_hash'] else None)
    return row


def directory():
    names=scopes()
    with db.connect() as con:
        rows=[dsl.unpack(p) for p in con.execute("SELECT * FROM instance_dsl_proposals ORDER BY created_at DESC,id DESC") if p['scope_id'] in names]
    records=[project(p,names) for p in rows]
    return {'records':records,'pending_count':sum(r['status']=='pending' for r in records)}


def detail(ident):
    names=scopes()
    with db.connect() as con:p=con.execute('SELECT * FROM instance_dsl_proposals WHERE id=?',(ident,)).fetchone()
    if not p or p['scope_id'] not in names:raise HTTPException(404,'审批记录不存在')
    return project(dsl.unpack(p),names,full=True)
