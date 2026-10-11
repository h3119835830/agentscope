"""Versioned system configuration library. Saving never grants execution authority."""
import json
import re
import uuid
from pathlib import Path
from .. import db
from . import dsl_policy as dsl, system_policy as system
from .policy import digest
from dsl_documents import canonical_documents,prepare

CATALOG = json.loads(Path(__file__).with_name('system_policy_catalog.json').read_text())
SCHEMA = '''
CREATE TABLE IF NOT EXISTS system_policy_library(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,
 payload_json TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS system_policy_library_versions(id TEXT NOT NULL,revision INTEGER NOT NULL,
 payload_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(id,revision));
CREATE TABLE IF NOT EXISTS system_policy_library_proposals(proposal_id TEXT PRIMARY KEY,
 selections_json TEXT NOT NULL,removals_json TEXT NOT NULL);
'''

def init(con):
    con.executescript(SCHEMA)
    import_existing(con)


def import_existing(con):
    # One-time import by stable document ID. Never replace user text with a preset.
    base=dsl.current('system',con)
    for doc in base['documents']:
        if con.execute('SELECT 1 FROM system_policy_library WHERE id=?',(doc['id'],)).fetchone():continue
        p={'name':doc['name'],'kind':'dsl','document':doc,'origin':'已有系统 DSL','category':'自定义策略'}
        now=db.now();encoded=json.dumps(p,ensure_ascii=False)
        con.execute('INSERT INTO system_policy_library VALUES(?,1,?,0,?,?)',(doc['id'],encoded,now,now))
        con.execute('INSERT INTO system_policy_library_versions VALUES(?,1,?,?)',(doc['id'],encoded,now))

def unpack(row):
    if not row:raise ValueError('配置不存在，请刷新列表')
    r=dict(row);r.update(json.loads(r.pop('payload_json')));return r

def get(ident,con=None):
    if con is None:
        with db.connect() as connection:return get(ident,connection)
    return unpack(con.execute('SELECT * FROM system_policy_library WHERE id=?',(ident,)).fetchone())

def lines(text):return [v.strip() for v in text.splitlines() if v.strip()]

def structured(ident,config):
    allowed={'name','mode','values','ops','effect','reason','template_id'}
    if not isinstance(config,dict) or set(config)-allowed:raise ValueError('策略配置字段不合法')
    name=config.get('name','');mode=config.get('mode');effect=config.get('effect')
    if not isinstance(name,str) or not isinstance(mode,str) or not isinstance(effect,str):raise ValueError('策略名称、匹配方式和动作必须为文本')
    name=name.strip()
    values=config.get('values','');reason=config.get('reason','');ops=config.get('ops',[])
    if not name or len(name)>120:raise ValueError('请填写不超过 120 字的策略名称')
    if not isinstance(values,str) or len(values)>10000 or not isinstance(reason,str) or not reason.strip() or len(reason)>600:raise ValueError('请填写保护对象和反馈说明')
    if re.search(r'[\x00-\x1f"\\]',reason):raise ValueError('反馈说明不能包含控制字符、双引号或反斜杠')
    if effect not in ('block','notify','kill'):raise ValueError('请选择 block、notify 或 kill')
    permitted=['exec'] if mode in ('exec','remote') else ['connect'] if mode in ('endpoint','flow') else ['open','write','unlink']
    if mode not in ('suffix','filename','tail','directory','exact','exec','endpoint','flow','remote'):raise ValueError('匹配方式不支持')
    if not isinstance(ops,list) or not ops or any(not isinstance(op,str) or op not in permitted for op in ops) or len(ops)!=len(set(ops)):raise ValueError('请选择与保护对象对应的操作')
    targets=lines(values)
    if not targets or len(targets)>16:raise ValueError('请填写 1 至 16 个保护对象')
    patterns=[]
    for v in targets:
        if re.search(r'[\x00-\x1f"\\]',v):raise ValueError('保护对象含有不支持的字符')
        if mode in ('suffix','flow'):
            if not v.startswith('.') or len(v)<2 or re.search(r'[/*?]',v):raise ValueError('后缀填写 .env 这样的字面值，无需添加目录或通配符')
            if len(v.encode())>63:raise ValueError('文件后缀最多 63 字节')
            patterns.append('**/*'+v)
        elif mode in ('filename','tail'):
            if v.startswith('/') or re.search(r'[?*]',v) or '..' in v.split('/') or (mode=='filename' and '/' in v):raise ValueError('请填写文件名或相对路径后缀，无需添加通配符')
            if len(('/'+v).encode())>63:raise ValueError('路径后缀连同边界斜杠最多 63 字节')
            patterns.append('**/'+v)
        elif mode in ('directory','exact'):
            if not v.startswith('/') or re.search(r'[?*]',v) or any(x in ('.','..') for x in v.split('/')):raise ValueError('请填写规范的实际绝对路径')
            patterns.extend([v.rstrip('/') or '/',v.rstrip('/')+'/**'] if mode=='directory' else [v])
        elif mode in ('exec','remote'):
            if v!='*' and not re.fullmatch(r'[\w./-]+',v,re.ASCII):raise ValueError('填写程序名或路径，不填写命令行参数')
            patterns.append(v)
        else:
            if v!='*':
                parts=v.rstrip('.').split('.');partial=v.endswith('.')
                if not (1<=len(parts)<=3 if partial else len(parts)==4) or any(not p.isascii() or not p.isdigit() or len(p)>3 or int(p)>255 for p in parts):raise ValueError('填写 IPv4 地址、地址前缀或 *')
            patterns.append(v)
    rule='system-'+ident;result=[]
    if mode=='flow':result.extend('source SENSITIVE = file '+json.dumps(p) for p in patterns)
    if mode=='remote':result.append('source REMOTE = endpoint "*"')
    result.append('rule '+rule+':')
    for op in ops:
        for p in (['*'] if mode=='flow' else patterns):
            result.append('  '+effect+' '+op+' '+('' if op=='exec' else 'endpoint ' if op=='connect' else 'file ')+json.dumps(p)+' if AGENT'+(' and SENSITIVE' if mode=='flow' else ' and REMOTE' if mode=='remote' else ''))
    result.append('  because '+json.dumps(reason,ensure_ascii=False))
    # AGENT is a reserved identity binding supplied by the trusted launch profile.
    document={'id':ident,'name':name,'original_dsl':'\n'.join(result),'metadata':{rule:{'statement':name,'context_requirement':'self_contained','context_reason':''}},'managed_identity':True}
    return document,patterns

@system.lifecycle
def save(body,ident=None):
    ident=ident or 'policy-'+uuid.uuid4().hex
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',ident):raise ValueError('配置标识不合法')
    kind=body['kind'];config=body.get('config') or {};template=next((t for t in CATALOG if t['id']==config.get('template_id')),None)
    if kind=='structured':
        doc,patterns=structured(ident,config)
        payload={'kind':kind,'name':doc['name'],'config':config,'document':doc,'patterns':patterns,'origin':template['origin'] if template else '用户自定义策略','source':template.get('source','') if template else '', 'category':template['category'] if template else '自定义策略'}
    else:
        raw=body.get('document') or {}
        if raw.get('managed_identity'):raise ValueError('DSL 导入不能自行声明托管身份，请保留完整来源声明')
        doc=canonical_documents([{**raw,'id':ident}])[0]
        payload={'kind':'dsl','name':doc['name'],'document':doc,'origin':'用户导入 DSL','category':'自定义策略'}
        try:
            payload['rules']=prepare([{**doc,'scope_id':'system'}],[])[0]['rules']
            payload['validation_error']=''
        except ValueError as e:
            payload['rules']=[];payload['validation_error']=str(e)
    canonical_documents([payload['document']])
    with db.connect() as con:
        old=con.execute('SELECT * FROM system_policy_library WHERE id=?',(ident,)).fetchone();revision=old['revision'] if old else 0
        if body['base_revision']!=revision:raise ValueError('配置已被修改，请刷新后编辑')
        if old and old['archived']:raise ValueError('此配置已归档')
        revision+=1;encoded=json.dumps(payload,ensure_ascii=False);now=db.now()
        con.execute('INSERT INTO system_policy_library VALUES(?,?,?,0,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload_json=excluded.payload_json,updated_at=excluded.updated_at',(ident,revision,encoded,now,now))
        con.execute('INSERT INTO system_policy_library_versions VALUES(?,?,?,?)',(ident,revision,encoded,now))
        db.audit(con,None,'system_policy_configuration_saved','administrator',{'id':ident,'revision':revision,'kind':kind})
    return get(ident)

@system.lifecycle
def archive(ident,revision):
    if any(d['id']==ident for d in dsl.current('system')['documents']):raise ValueError('请先停用当前已应用策略，再归档配置')
    with db.connect() as con:
        item=get(ident,con)
        if item['revision']!=revision:raise ValueError('配置版本已经变化')
        con.execute('UPDATE system_policy_library SET archived=1,revision=revision+1,updated_at=? WHERE id=?',(db.now(),ident))
    return {'id':ident,'archived':True}

def directory():
    base=dsl.detail('system');applied={d['id']:d for d in base['documents']}
    with db.connect() as con:
        # Legacy pending approvals may introduce complete DSL documents after startup.
        # Import missing IDs only, preserving any independently edited library version.
        import_existing(con)
        rows=[unpack(r) for r in con.execute('SELECT * FROM system_policy_library WHERE archived=0 ORDER BY created_at,id')]
        for item in rows:
            document=applied.get(item['id']);item['applied']=document is not None;item['has_changes']=document is not None and document!=item['document']
            item['records']=[r for r in base['records'] if r['document_id']==item['id']]
            versions=con.execute('SELECT revision,payload_json FROM system_policy_library_versions WHERE id=? ORDER BY revision DESC',(item['id'],)).fetchall()
            item['applied_revision']=next((v['revision'] for v in versions if json.loads(v['payload_json'])['document']==document),None)
    return {'catalog':CATALOG,'items':rows,'base_revision':base['revision'],'base_hash':base['document_hash'],'phase':base['phase'],'targets':base['targets']}

def verify_proposal(proposal_id):
    with db.connect() as con:
        binding=con.execute('SELECT * FROM system_policy_library_proposals WHERE proposal_id=?',(proposal_id,)).fetchone()
        if not binding:return
        for chosen in json.loads(binding['selections_json']):
            current=get(chosen['id'],con)
            if current['archived'] or current['revision']!=chosen['revision']:raise ValueError('配置库版本已变化，请重新选择并校验')

@system.lifecycle
def propose(body):
    base=dsl.current('system')
    if base['revision']!=body['base_revision'] or base['document_hash']!=body['base_hash']:raise ValueError('系统策略已经变化，请刷新后重试')
    docs={d['id']:d for d in base['documents']};selections=body['selections'];removals=body['removals']
    if not selections and not removals:raise ValueError('请选择配置或明确停用的文档')
    selected_ids=[s['id'] for s in selections]
    if len(set(selected_ids))!=len(selected_ids) or set(selected_ids)&set(removals):raise ValueError('选择项重复或与停用项冲突')
    for selected in selections:
        item=get(selected['id'])
        if item['archived'] or item['revision']!=selected['revision']:raise ValueError('所选配置已经变化，请刷新列表')
        docs[item['id']]=item['document']
    for ident in removals:
        if ident not in docs:raise ValueError('停用目标已不在当前系统策略中')
        del docs[ident]
    result=dsl.propose('system',{'documents':list(docs.values()),'base_hash':body['base_hash'],'base_revision':body['base_revision'],'request_key':body['request_key']})
    with db.connect() as con:
        prior=con.execute('SELECT * FROM system_policy_library_proposals WHERE proposal_id=?',(result['id'],)).fetchone()
        values=(json.dumps(selections,sort_keys=True),json.dumps(removals,sort_keys=True))
        if prior and (prior['selections_json'],prior['removals_json'])!=values:raise ValueError('此请求已用于其他配置版本，请重新校验')
        con.execute('INSERT OR IGNORE INTO system_policy_library_proposals VALUES(?,?,?)',(result['id'],*values))
    return result
