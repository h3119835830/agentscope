"""Versioned user drafts. Evidence is frozen data and never grants authority."""
import json
import uuid
from fastapi import HTTPException
from .. import db
from .policy import digest
from .system_policy import lifecycle

SCHEMA = '''
CREATE TABLE IF NOT EXISTS policy_drafts(
 id TEXT PRIMARY KEY, instance_id TEXT NOT NULL, scope TEXT NOT NULL,
 workspace_id TEXT, revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS policy_draft_versions(
 draft_id TEXT NOT NULL, revision INTEGER NOT NULL, input_json TEXT NOT NULL,
 input_hash TEXT NOT NULL, request_key TEXT NOT NULL, state TEXT NOT NULL,
 run_id TEXT, approval_id TEXT, created_at TEXT NOT NULL,
 PRIMARY KEY(draft_id,revision), UNIQUE(draft_id,request_key));
CREATE INDEX IF NOT EXISTS policy_drafts_target ON policy_drafts(instance_id,scope,workspace_id);
CREATE TABLE IF NOT EXISTS policy_draft_creations(
 instance_id TEXT NOT NULL, request_key TEXT NOT NULL, request_hash TEXT NOT NULL,
 draft_id TEXT NOT NULL, PRIMARY KEY(instance_id,request_key));
'''


def init(con):
    con.executescript(SCHEMA)
    columns={r[1] for r in con.execute('PRAGMA table_info(policy_draft_versions)')}
    for name in ('input_version_id','submission_json'):
        if name not in columns:
            con.execute('ALTER TABLE policy_draft_versions ADD COLUMN '+name+' TEXT')


def owner(ident):
    from . import store
    row = store.get(ident)
    if row['mode'] != 'controlled':
        raise ValueError('仅受控 Agent 支持策略草案')
    return row


def load(ident, draft_id, revision=None):
    with db.connect() as con:
        draft = con.execute('SELECT * FROM policy_drafts WHERE id=? AND instance_id=?', (draft_id, ident)).fetchone()
        if not draft:
            raise HTTPException(404, '草案不存在或不属于当前 Agent')
        version = con.execute('SELECT * FROM policy_draft_versions WHERE draft_id=? AND revision=?',
                              (draft_id, revision or draft['revision'])).fetchone()
    if not version:
        raise HTTPException(404, '草案版本不存在')
    return {**dict(draft), **dict(version), 'id': draft_id,
            'latest_revision': draft['revision'], 'input': json.loads(version['input_json'])}


def view(row):
    out = {k: row.get(k) for k in ('id', 'instance_id', 'scope', 'workspace_id', 'revision',
                                  'latest_revision', 'input_hash', 'state', 'run_id', 'approval_id', 'created_at')}
    out.update(row['input'])
    if row.get('approval_id'):
        from .approval_views import detail
        try:
            approval = detail(row['approval_id'])
            out['approval'] = {k: approval.get(k) for k in ('id','status','can_approve','can_apply','approval_status','application_status')}
        except HTTPException:
            out['approval'] = None
    return out


def directory(ident, scope='agent', workspace_id=None):
    owner(ident)
    if scope not in ('agent','workspace'):
        raise ValueError('未知草案范围')
    with db.connect() as con:
        rows = con.execute('SELECT id FROM policy_drafts WHERE instance_id=? AND scope=? AND workspace_id IS ? ORDER BY updated_at DESC,id DESC',
                           (ident, scope, workspace_id if scope == 'workspace' else None)).fetchall()
    return {'records': [view(load(ident, r['id'])) for r in rows]}


def input_values(body):
    values = {k: body.get(k) for k in ('text','materials','document')}
    if body.get('scene_id'):
        if body['scope']!='workspace':
            raise ValueError('工作区场景不能作为 Agent 长期基线的生成环境')
        values['scene_id']=body['scene_id']
    values['text'] = (values['text'] or '').strip()
    values['materials'] = values['materials'] or []
    if values['document']:
        from dsl_documents import canonical_documents
        values['document'] = canonical_documents([values['document']])[0]
        if values['document'].get('generation_binding'):
            raise ValueError('生成候选必须使用服务端产物，不可作为手工文档保存')
    return values


@lifecycle
def save(ident, body, draft_id=None):
    owner(ident)
    values = input_values(body)
    scope = body['scope']
    workspace_id = body.get('workspace_id') if scope == 'workspace' else None
    if scope == 'agent' and body.get('workspace_id'):
        raise ValueError('Agent 基线不属于某个工作区')
    if workspace_id:
        from ..history.agent_context import scoped_snapshot
        scoped_snapshot(ident, 'workspace', workspace_id)
    now = db.now()
    creation_hash=digest({'scope':scope,'workspace_id':workspace_id,'input':values})
    if not draft_id:
        with db.connect() as con:
            retry=con.execute('SELECT * FROM policy_draft_creations WHERE instance_id=? AND request_key=?',
                              (ident,body['request_key'])).fetchone()
        if retry:
            if retry['request_hash']!=creation_hash:
                raise ValueError('幂等键已用于另一草案或目标')
            return view(load(ident,retry['draft_id'],1))
    if draft_id:
        old = load(ident, draft_id)
        if old['scope'] != scope or old['workspace_id'] != workspace_id:
            raise ValueError('修改范围须新建草案，不能改变已有版本归属')
        with db.connect() as con:
            retry = con.execute('SELECT revision,input_hash FROM policy_draft_versions WHERE draft_id=? AND request_key=?',
                                (draft_id,body['request_key'])).fetchone()
        if retry:
            if retry['input_hash'] != digest(values):
                raise ValueError('幂等键已用于另一草案内容')
            return view(load(ident,draft_id,retry['revision']))
        if body['base_revision'] != old['latest_revision']:
            raise ValueError('草案已被修改，请刷新后重试')
        revision = old['latest_revision'] + 1
    else:
        draft_id = uuid.uuid4().hex
        revision = 1
    with db.connect() as con:
        if revision == 1:
            con.execute('INSERT INTO policy_drafts VALUES(?,?,?,?,?,?,?)',
                        (draft_id,ident,scope,workspace_id,revision,now,now))
            con.execute('INSERT INTO policy_draft_creations VALUES(?,?,?,?)',
                        (ident,body['request_key'],creation_hash,draft_id))
        else:
            changed = con.execute('UPDATE policy_drafts SET revision=?,updated_at=? WHERE id=? AND revision=?',
                                  (revision,now,draft_id,revision-1)).rowcount
            if changed != 1:
                raise ValueError('草案已被修改，请刷新后重试')
        con.execute('INSERT INTO policy_draft_versions(draft_id,revision,input_json,input_hash,request_key,state,run_id,approval_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                    (draft_id,revision,json.dumps(values),digest(values),body['request_key'],'draft',None,None,now))
        db.audit(con,None,'policy_draft_saved','authenticated_operator',
                 {'draft_id':draft_id,'revision':revision,'instance_id':ident,'scope':scope})
    return view(load(ident,draft_id))


def bind_context(context, draft_id, revision):
    draft = load(context['instance_id'],draft_id,revision)
    if context['policy_target']['scope'] != draft['scope'] or context['policy_target'].get('workspace_id') != draft['workspace_id']:
        raise ValueError('草案与核验目标不一致')
    if draft['latest_revision'] != revision and not draft['approval_id']:
        raise ValueError('草案材料或需求已变化，请重新生成')
    if digest(draft['input']) != draft['input_hash']:
        raise ValueError('草案快照校验失败')
    context['draft_binding'] = {'id':draft_id,'revision':revision,'input_hash':draft['input_hash']}
    context['material_evidence'] = [{'name':m['name'],'text':m['text'],'sha256':digest(m)} for m in draft['input']['materials']]
    if draft['input'].get('scene_id'):
        from ..history.agent_scene import bind
        context=bind(context,draft['input']['scene_id'])
    return context


@lifecycle
def generate(ident,draft_id,revision,request_key):
    from ..history import agent_context, inputs, generations
    draft=load(ident,draft_id,revision)
    if draft['latest_revision']!=revision:
        raise ValueError('草案已变化，请刷新后生成')
    if draft['run_id']:
        return {'id':draft['run_id'],'draft':view(draft),'idempotent':True}
    if draft['approval_id']:
        raise ValueError('此草案已经提交，请创建新版本')
    if len(draft['input']['text'])<5:
        raise ValueError('请填写至少五个字符的策略需求')
    key='policy-draft-generate:'+draft_id+':'+str(revision)
    with db.connect() as con:
        existing=con.execute('SELECT id FROM history_generations WHERE request_key=?',(key,)).fetchone()
    if existing:
        run={'id':existing['id']}
    else:
        version_id=draft.get('input_version_id')
        if not version_id:
            context=agent_context.scoped_snapshot(ident,draft['scope'],draft['workspace_id'])
            if not context['ready']:
                raise ValueError(context['message'])
            selection={'instance_id':ident,'scope':draft['scope'],'workspace_id':draft['workspace_id'],
                       'context_hash':context['context_hash'],'draft_id':draft_id,'draft_revision':revision}
            version=inputs.create_input({'text':draft['input']['text'],'enforcement_level':'per_event',
                                        'context_requirement':'project','agent_context':selection},'authenticated_operator')
            version_id=version['id']
            with db.connect() as con:
                con.execute('UPDATE policy_draft_versions SET input_version_id=? WHERE draft_id=? AND revision=?',(version_id,draft_id,revision))
        run=generations.create({'statement_version_id':version_id,'request_key':key})
    with db.connect() as con:
        con.execute("UPDATE policy_draft_versions SET state='generated',run_id=? WHERE draft_id=? AND revision=?",
                    (run['id'],draft_id,revision))
    return {'id':run['id'],'draft':view(load(ident,draft_id,revision))}


@lifecycle
def submit(ident,draft_id,body):
    from ..history.agent_context import selected_candidate
    from . import dsl_policy, local_policy_proposals
    draft=load(ident,draft_id,body['revision'])
    selection={'artifact_id':body.get('artifact_id')}
    if draft.get('submission_json') and json.loads(draft['submission_json'])!=selection:
        raise ValueError('此版本已选择另一候选，请创建新版本后提交')
    if draft['approval_id']:
        return {'id':draft['approval_id'],'idempotent':True}
    if draft['latest_revision']!=body['revision']:
        raise ValueError('草案已变化，请重新生成后提交')
    artifact=body.get('artifact_id')
    key='policy-draft-submit:'+draft_id+':'+str(draft['revision'])
    with db.connect() as con:
        old=con.execute('SELECT id FROM instance_dsl_proposals WHERE scope_id=? AND request_key=?',(ident,key)).fetchone()
        local=con.execute('SELECT id FROM local_policy_proposals WHERE instance_id=? AND request_key=?',(ident,key)).fetchone()
    if old or local:
        proposed={'id':old['id'] if old else 'local:'+local['id'],'idempotent':True}
        with db.connect() as con:
            con.execute("UPDATE policy_draft_versions SET state='submitted',approval_id=? WHERE draft_id=? AND revision=?",(proposed['id'],draft_id,draft['revision']))
        return proposed
    if artifact:
        candidate=selected_candidate(ident,artifact)
        binding=candidate.get('draft_binding')
        if binding != {'id':draft_id,'revision':draft['revision'],'input_hash':draft['input_hash']}:
            raise ValueError('候选不属于此草案版本')
        if candidate['target']['scope']!=draft['scope']:
            raise ValueError('候选范围不一致')
        with db.connect() as con:
            con.execute('UPDATE policy_draft_versions SET submission_json=? WHERE draft_id=? AND revision=?',(json.dumps(selection),draft_id,draft['revision']))
        if candidate['scopeType']!='agent':
            proposed=local_policy_proposals.submit(ident,artifact,{'candidate_hash':candidate['candidate_hash'],'request_key':key})
        else:
            base=dsl_policy.current(ident)
            documents=[d for d in base['documents'] if d['id']!=candidate['document']['id']]+[candidate['document']]
            proposed=dsl_policy.propose(ident,{'documents':documents,'base_hash':base['document_hash'],
                                              'base_revision':base['revision'],'request_key':key})
    else:
        document=draft['input']['document']
        if draft['scope']!='agent' or not document:
            raise ValueError('请先生成并选择可核验的策略候选')
        from ..history.agent_context import scoped_snapshot
        context=scoped_snapshot(ident,'agent')
        if not context['ready']:
            raise ValueError(context['message'])
        with db.connect() as con:
            con.execute('UPDATE policy_draft_versions SET submission_json=? WHERE draft_id=? AND revision=?',(json.dumps(selection),draft_id,draft['revision']))
        base=dsl_policy.current(ident)
        proposed=dsl_policy.propose(ident,{'documents':[d for d in base['documents'] if d['id']!=document['id']]+[document],
                                          'base_hash':base['document_hash'],'base_revision':base['revision'],'request_key':key})
    with db.connect() as con:
        con.execute("UPDATE policy_draft_versions SET state='submitted',approval_id=? WHERE draft_id=? AND revision=?",
                    (proposed['id'],draft_id,draft['revision']))
    return proposed
