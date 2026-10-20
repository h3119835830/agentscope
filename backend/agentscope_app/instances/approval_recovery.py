"""Create a fresh unapproved candidate; never repair or consume an old approval."""
import json
from fastapi import HTTPException
from .. import db
from . import dsl_policy as dsl, policy_library as library, system_policy as system
from .policy import digest

SCHEMA='''CREATE TABLE IF NOT EXISTS policy_approval_revalidations(
 source_id TEXT NOT NULL,request_key TEXT NOT NULL,plan_hash TEXT NOT NULL,
 child_key TEXT NOT NULL UNIQUE,body_json TEXT NOT NULL,new_approval_id TEXT,
 created_at TEXT NOT NULL,PRIMARY KEY(source_id,request_key));
 CREATE INDEX IF NOT EXISTS revalidation_child ON policy_approval_revalidations(new_approval_id);'''

def init(con):con.executescript(SCHEMA)

def load(ident):
    with db.connect() as con:raw=con.execute('SELECT * FROM instance_dsl_proposals WHERE id=?',(ident,)).fetchone()
    if not raw:raise HTTPException(404,'此记录没有可重新校验的 DSL 候选')
    p=dsl.unpack(raw)
    from .approval_views import scopes
    if p['scope_id'] not in scopes():raise HTTPException(404,'审批记录不存在')
    return p

def completed(p):
    if not p['request_key'].startswith('rv:'):return True
    with db.connect() as con:
        return bool(con.execute('SELECT 1 FROM policy_approval_revalidations WHERE child_key=? AND new_approval_id=?',
                                (p['request_key'],p['id'])).fetchone())

def hint(row):
    if row['status'] not in ('stale','invalid','failed','blocked'):return None
    target=row.get('target',{})
    destination={'page':'strategies','systemTab':'policies','policyScope':'system','policyAgent':'','approvalId':''} if row['scope_type']=='system' else {
        'page':'workbench','policyAgent':row['scope_id'],'policyScope':row['scope_type'],
        'policyWorkspace':target.get('workspace_id') or '', 'policySession':target.get('session_id') or '',
        'agentPolicyTab':'assistant','approvalId':''}
    if row['scope_type']=='agent':
        docs=row.get('documents',[])
        destination={'page':'strategies','systemTab':'policies','policyScope':'agent',
                     'policyAgent':row['scope_id'],'configurationId':docs[0]['id'] if len(docs)==1 else '',
                     'approvalId':''}
    if row['scope_type']=='session':
        destination={'page':'sessions','sessionInstance':row['scope_id'],'sessionId':target.get('session_id') or '',
                     'sessionTab':'policies','approvalId':''}
    available=row['kind']=='dsl' and row['scope_type'] in ('system','agent') and not any(d.get('generation_binding') for d in row.get('documents',[]))
    reason='重新核对当前配置、策略基线与执行目标，生成新的待审批记录。' if available else (
        row.get('reason') or '请回到所属配置起草新版本；不能扩大原候选的作用范围。')
    return {'available':available,'reason':reason,'destination':destination}

def baseline(p,base):
    if p['base_hash']==base['document_hash']:return base['documents']
    if p['base_hash']==digest([]):return []
    with db.connect() as con:
        receipt=con.execute('SELECT evidence_json FROM policy_approval_decisions WHERE approval_id=?',(p['id'],)).fetchone()
        if receipt:
            docs=json.loads(receipt[0]).get('previous_documents')
            if docs is not None and digest(docs)==p['base_hash']:return docs
        for row in con.execute("SELECT * FROM instance_dsl_proposals WHERE scope_id=? AND state='applied' AND base_revision=?",
                               (p['scope_id'],p['base_revision']-1)):
            docs=json.loads(row['documents_json'])
            if digest(docs)==p['base_hash']:return docs
    raise ValueError('旧记录缺少修改前的配置，无法安全合并；请返回所属配置重新编辑。')

def summary(payload):
    config=payload.get('config') or {}
    if not config:return '原始 DSL，展开查看完整内容'
    effects={'notify':'记录通知','block':'阻断操作','kill':'终止触发进程'}
    verbs={'open':'打开','write':'写入','unlink':'删除','exec':'执行','connect':'连接'}
    return ' · '.join([config.get('values',''),'、'.join(verbs.get(op,op) for op in config.get('ops',[])),effects.get(config.get('effect'),config.get('effect',''))])

def merge(p,base):
    old={d['id']:d for d in baseline(p,base)};next_docs={d['id']:d for d in p['documents']}
    current={d['id']:d for d in base['documents']}
    for ident in old.keys()|next_docs.keys():
        before=old.get(ident);after=next_docs.get(ident)
        if before==after:continue
        if current.get(ident) not in (before,after):
            raise ValueError('策略“'+(after or before)['name']+'”已被其他变更修改，请返回所属配置核对后重新编辑。')
        if after:current[ident]=after
        else:current.pop(ident,None)
    return list(current.values())

def plan(ident):
    p=load(ident)
    if not completed(p):raise ValueError('原重新校验请求尚未完成，请回到原记录重试；不能跳过配置来源绑定。')
    if p['state'] in ('applied','rejected','applying'):raise ValueError('此记录已处理或正在应用，不能重新校验')
    base=dsl.current(p['scope_id'])
    if base['phase']!='ready' or system.current()['phase']!='ready':
        raise ValueError('上次应用尚未恢复，执行保持暂停；请先核验所属配置的恢复状态。')
    if any(d.get('generation_binding') for d in p['documents']):
        raise ValueError('生成候选绑定了旧场景，请返回策略助手重新读取材料并生成新版本；不能直接替换执行绑定。')
    with db.connect() as con:
        binding=con.execute('SELECT * FROM system_policy_library_proposals WHERE proposal_id=?',(ident,)).fetchone()
        template_binding=con.execute('SELECT * FROM template_configuration_proposals WHERE proposal_id=?',(ident,)).fetchone()
    comparisons=[]
    if template_binding:
        from . import template_configurations as configurations, template_catalog
        docs={d['id']:d for d in base['documents']};previous={d['id']:d for d in p['documents']};selections=[]
        for chosen in json.loads(template_binding['selections_json']):
            item=configurations.load(chosen['id'])
            configurations.verify_current(item,read_source=chosen.get('operation','apply')!='disable')
            if item['archived'] or item['scope_id']!=p['scope_id']:raise ValueError('子配置已删除或目标不一致，请返回策略与模板核对')
            if digest(template_catalog.get(item['template_id'],item['template_version']))!=item['template_hash']:raise ValueError('模板合同已经变化，请先编辑并保存子配置的新版本')
            removal=chosen.get('operation')=='disable'
            before=docs.get(item['id']) if removal else previous.get(item['id'])
            if before is None:raise ValueError('原子配置来源不完整，请返回策略与模板重新提交')
            after=None if removal else item['document']
            comparisons.append({'name':item['name'],'before_version':chosen['revision'],'after_version':item['revision'],
                'removal':removal,'same_content':before==after if not removal else True,
                'before_dsl':before['original_dsl'],'after_dsl':after['original_dsl'] if after else '',
                'before_summary':'原子配置，展开核对','after_summary':item['coverage_warning'] or item['note'] or item['name']})
            if removal:docs.pop(item['id'])
            else:docs[item['id']]=after
            selections.append({'id':item['id'],'revision':item['revision'],'document_hash':digest(item['document']),
                               'operation':'disable' if removal else 'apply','acknowledge_coverage':bool(item['coverage_warning'])})
        documents=list(docs.values());kind='template'
        body={'selections':selections,'documents':documents,'base_hash':base['document_hash'],'base_revision':base['revision']}
    elif binding:
        if p['scope_id']!='system':raise ValueError('系统配置来源与审批范围不一致')
        docs={d['id']:d for d in base['documents']};old={d['id']:d for d in p['documents']};selections=[]
        for chosen in json.loads(binding['selections_json']):
            item=library.get(chosen['id'])
            if item['archived']:raise ValueError('配置“'+item['name']+'”已删除，请返回配置库重新创建并提交。')
            if chosen['id'] not in old:raise ValueError('原候选的配置来源不完整，请返回配置库核对')
            previous=old[chosen['id']];current=item['document'];same=previous==current
            with db.connect() as con:version=con.execute('SELECT payload_json FROM system_policy_library_versions WHERE id=? AND revision=?',(chosen['id'],chosen['revision'])).fetchone()
            original=json.loads(version[0]) if version else {}
            comparisons.append({'name':item['name'],'before_version':chosen['revision'],'after_version':item['revision'],
                'same_content':same,'before_dsl':previous['original_dsl'],'after_dsl':current['original_dsl'],
                'before_summary':summary(original) if original.get('document')==previous else '原始 DSL，展开查看完整内容',
                'after_summary':summary(item)})
            docs[item['id']]=current;selections.append({'id':item['id'],'revision':item['revision']})
        removals=json.loads(binding['removals_json'])
        for key in removals:
            if key not in docs:raise ValueError('原停用目标已不在当前策略中，无需再次移除；请检查当前配置。')
            comparisons.append({'name':docs[key]['name'],'removal':True,'same_content':True})
            del docs[key]
        body={'selections':selections,'removals':removals,'base_hash':base['document_hash'],'base_revision':base['revision']}
        kind='library';documents=list(docs.values())
    else:
        documents=merge(p,base);kind='dsl'
        body={'documents':documents,'base_hash':base['document_hash'],'base_revision':base['revision']}
        original={d['id']:d for d in baseline(p,base)}
        for doc in p['documents']:
            if original.get(doc['id'])!=doc:comparisons.append({'name':doc['name'],'same_content':True,'before_dsl':doc['original_dsl'],'after_dsl':doc['original_dsl']})
        for doc in original.values():
            if not any(d['id']==doc['id'] for d in p['documents']):comparisons.append({'name':doc['name'],'removal':True,'same_content':True})
    from dsl_documents import canonical_documents
    documents=canonical_documents(documents)
    if kind in ('dsl','template'):body['documents']=documents
    targets=dsl.target_snapshot(p['scope_id'],documents)
    frozen={'source_id':ident,'scope_id':p['scope_id'],'kind':kind,'body':body,'documents':documents,'targets':targets}
    return {**frozen,'plan_hash':digest(frozen),'comparisons':comparisons,'target_count':len(targets),
            'changed_content':any(not c['same_content'] for c in comparisons),
            'scope_label':'全部受控 Agent' if p['scope_id']=='system' else '此 Agent 的全部工作区与会话',
            'message':'采用下列当前配置重新校验，保留其余已生效文档。旧记录和旧批准不改写，新候选需要重新批准并单独应用。'}

def preview(ident):
    data=plan(ident)
    # Frozen execution identities and canonical documents stay on the server.
    return {k:data[k] for k in ('source_id','plan_hash','comparisons','target_count','changed_content','scope_label','message')}

@system.lifecycle
def revalidate(ident,plan_hash,request_key):
    p=load(ident)
    with db.connect() as con:
        saved=con.execute('SELECT * FROM policy_approval_revalidations WHERE source_id=? AND request_key=?',(ident,request_key)).fetchone()
    if saved and saved['plan_hash']!=plan_hash:raise ValueError('幂等键已用于其他校验内容，请重新打开预览')
    if saved and saved['new_approval_id']:
        return {'id':saved['new_approval_id'],'source_approval_id':ident,'idempotent':True}
    fresh=plan(ident)
    if fresh['plan_hash']!=plan_hash:raise ValueError('配置、策略基线或执行目标已经变化，请重新打开校验预览')
    child_key='rv:'+digest({'source':ident,'request_key':request_key})
    body={**fresh['body'],'request_key':child_key}
    with db.connect() as con:
        con.execute('INSERT OR IGNORE INTO policy_approval_revalidations VALUES(?,?,?,?,?,NULL,?)',
                    (ident,request_key,plan_hash,child_key,json.dumps(body),db.now()))
    if fresh['kind']=='template':
        from .template_configurations import revalidate_proposal
        result=revalidate_proposal(p['scope_id'],body)
    else:
        result=library.propose(body) if fresh['kind']=='library' else dsl.propose(p['scope_id'],body)
    if result['targets']!=fresh['targets']:raise ValueError('校验期间执行目标已经变化，请重新读取预览并提交新校验请求')
    with db.connect() as con:
        con.execute('UPDATE policy_approval_revalidations SET new_approval_id=? WHERE source_id=? AND request_key=?',
                    (result['id'],ident,request_key))
        db.audit(con,None,'policy_approval_revalidated','administrator',{'source_approval_id':ident,'new_approval_id':result['id'],'plan_hash':plan_hash,'scope_id':p['scope_id']})
    return {'id':result['id'],'source_approval_id':ident,'idempotent':False,'state':result['state']}

def lineage(ident):
    with db.connect() as con:
        row=con.execute('SELECT source_id,created_at FROM policy_approval_revalidations WHERE new_approval_id=? OR child_key=(SELECT request_key FROM instance_dsl_proposals WHERE id=?)',(ident,ident)).fetchone()
        children=con.execute('SELECT new_approval_id,created_at FROM policy_approval_revalidations WHERE source_id=? AND new_approval_id IS NOT NULL ORDER BY created_at DESC LIMIT 10',(ident,)).fetchall()
    return {'revalidated_from':dict(row) if row else None,'revalidated_versions':[dict(c) for c in children]}
