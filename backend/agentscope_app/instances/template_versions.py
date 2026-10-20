"""Human-edited template versions; never mutate saved configuration authority."""
import copy
import json
import re
from fastapi import HTTPException
from .. import db
from .policy import digest

SCHEMA = '''
CREATE TABLE IF NOT EXISTS policy_template_versions(
 template_id TEXT NOT NULL,version INTEGER NOT NULL,definition_json TEXT NOT NULL,
 description TEXT NOT NULL,request_key TEXT NOT NULL UNIQUE,request_hash TEXT NOT NULL,
 created_at TEXT NOT NULL,PRIMARY KEY(template_id,version));
'''


def init(con):
    con.executescript(SCHEMA)
    publish_fixed_git(con)
    publish_secret_sources(con)


def publish_secret_sources(con):
    """Append, never relabel historical SENSITIVE definitions or approvals."""
    from . import template_catalog as catalog
    for built_in in catalog.CATALOG:
        if built_in['id'] not in ('SECRET-EGRESS','SYS-secret-egress'):
            continue
        row=con.execute('SELECT * FROM policy_template_versions WHERE template_id=? ORDER BY version DESC LIMIT 1',(built_in['id'],)).fetchone()
        previous=unpack(row) if row else {'definition':built_in,'description':catalog.DESCRIPTIONS[built_in['id']]}
        definition=copy.deepcopy(previous['definition'])
        if definition.get('label_contract')=='explicit-secret-sources.v1':
            continue
        definition.update(version=definition['version']+1,label_contract='explicit-secret-sources.v1',source_label='SECRET')
        con.execute('INSERT INTO policy_template_versions VALUES(?,?,?,?,?,?,?)',
                    (definition['id'],definition['version'],json.dumps(definition,ensure_ascii=False),previous['description'],
                     'builtin:explicit-secret-sources.v1:'+definition['id']+':'+str(definition['version']),digest(definition),db.now()))
        db.audit(con,None,'template.contract_published','system',
                 {'template_id':definition['id'],'version':definition['version'],'contract':definition['label_contract']})


def publish_fixed_git(con):
    """Append a new contract, including after custom versions; never rewrite one."""
    from . import template_catalog as catalog
    from .template_dsl import fixed_git_definition
    if not con.in_transaction:con.execute('BEGIN IMMEDIATE')
    for built_in in catalog.CATALOG:
        row=con.execute('SELECT * FROM policy_template_versions WHERE template_id=? ORDER BY version DESC LIMIT 1',(built_in['id'],)).fetchone()
        previous=unpack(row) if row else {'definition':built_in,'description':catalog.DESCRIPTIONS[built_in['id']]}
        base=previous['definition']
        if base.get('contract')=='git-fixed-command.v1':continue
        definition=fixed_git_definition(base)
        if definition is None:continue
        definition['version']=base['version']+1
        key='builtin:git-fixed-command.v1:'+built_in['id']+':'+str(base['version'])
        con.execute('INSERT INTO policy_template_versions VALUES(?,?,?,?,?,?,?)',
            (base['id'],definition['version'],json.dumps(definition,ensure_ascii=False),previous['description'],key,digest(definition),db.now()))
        db.audit(con,None,'template.contract_published','system',{'template_id':base['id'],'version':definition['version'],'contract':definition['contract']})


def unpack(row):
    return {'definition':json.loads(row['definition_json']),'description':row['description']}


def get(ident,version):
    with db.connect() as con:
        row=con.execute('SELECT * FROM policy_template_versions WHERE template_id=? AND version=?',(ident,version)).fetchone()
    return unpack(row) if row else None


def latest():
    with db.connect() as con:
        rows=con.execute('SELECT v.* FROM policy_template_versions v JOIN (SELECT template_id,MAX(version) version FROM policy_template_versions GROUP BY template_id) n USING(template_id,version)').fetchall()
    return {r['template_id']:unpack(r) for r in rows}


def text(value,label,limit,paragraph=False):
    forbidden=r'[\x00-\x08\x0b\x0c\x0e-\x1f]' if paragraph else r'[\x00-\x1f]'
    if not isinstance(value,str) or not value.strip() or len(value)>limit or re.search(forbidden,value):
        raise ValueError('请填写有效的'+label)
    return value.strip()


def edited_definition(base,body):
    from . import template_configurations as configurations,policy_library
    definition=copy.deepcopy(base)
    definition['name']=text(body['name'],'模板名称',120)
    description=text(body['description'],'模板说明',3000,paragraph=True)
    effect=body['effect']
    if effect not in base.get('allowed_effects', ('block','notify','kill')):
        raise ValueError('请选择有效的默认动作')
    fields=body['parameters']
    if not isinstance(fields,list) or len(fields)!=len(base['parameters']) or {p.get('key') for p in fields}!={p['key'] for p in base['parameters']}:
        raise ValueError('暂不支持新增、删除或更改参数键')
    by_key={p['key']:p for p in fields}
    if len(by_key)!=len(fields):
        raise ValueError('配置项不能重复')
    for parameter in definition['parameters']:
        value=by_key[parameter['key']]
        if set(value)!={'key','label','default'}:
            raise ValueError('暂不支持更改填写类型或执行定义')
        parameter['label']=text(value['label'],'配置项名称',120)
        default=value['default']
        if not isinstance(default,str) or len(default)>10000 or '\x00' in default:
            raise ValueError('请填写有效的配置项默认值')
        kind=parameter['type']
        if kind in ('choices','integer'):
            from .git_templates import validate_parameter
            validate_parameter(parameter,default)
        elif kind=='effect':
            if default!=effect:raise ValueError('匹配动作默认值须与模板默认动作一致')
        elif kind=='operations':
            operations=default.split(',')
            if not operations or len(set(operations))!=len(operations) or any(op not in definition.get('allowed_operations',('write','unlink')) for op in operations):
                raise ValueError('请选择模板支持的默认触发操作')
        elif default:
            if kind=='path':configurations.path_parameter(default,None)
            elif kind=='program' and not re.fullmatch(r'[a-zA-Z0-9_./-]{1,63}',default) and not (default=='*' and definition['id']=='EXEC-AUDIT'):
                raise ValueError('默认程序仅支持程序名或路径')
            elif kind=='endpoint':policy_library.structured('validation',{'name':'连接','mode':'endpoint','values':default,'ops':['connect'],'effect':'notify','reason':'模板参数校验'})
            elif kind not in ('lines','program','endpoint'):configurations.text_parameter(default,parameter['label'])
        parameter['default']=default
    definition['effect']=effect
    return definition,description


def save(ident,body):
    from . import template_catalog as catalog
    allowed={'name','description','parameters','effect','base_version','request_key'}
    if not isinstance(body,dict) or set(body)!=allowed:
        raise ValueError('模板编辑不能包含 DSL、执行器或作用范围')
    request_key=body['request_key']
    if not isinstance(request_key,str) or not 8<=len(request_key)<=100:
        raise ValueError('模板保存请求标识无效')
    if type(body['base_version']) is not int or body['base_version']<2:
        raise ValueError('请刷新后编辑当前模板版本')
    built_in=next((t for t in catalog.CATALOG if t['id']==ident),None)
    if not built_in:raise ValueError('模板不存在')
    request_hash=digest({'template_id':ident,**{k:v for k,v in body.items() if k!='request_key'}})
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        prior=con.execute('SELECT * FROM policy_template_versions WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if prior['request_hash']!=request_hash:raise HTTPException(409,'同一保存请求不能更改模板内容')
            saved=unpack(prior)
        else:
            row=con.execute('SELECT * FROM policy_template_versions WHERE template_id=? ORDER BY version DESC LIMIT 1',(ident,)).fetchone()
            base=unpack(row)['definition'] if row else copy.deepcopy(built_in)
            if base['version']!=body['base_version']:raise HTTPException(409,'模板已有新版本，请刷新后重新编辑')
            from .template_support import ensure_editable
            ensure_editable(base)
            definition,description=edited_definition(base,body)
            definition['version']=base['version']+1
            con.execute('INSERT INTO policy_template_versions VALUES(?,?,?,?,?,?,?)',(ident,definition['version'],json.dumps(definition,ensure_ascii=False),description,request_key,request_hash,db.now()))
            db.audit(con,None,'template.version_saved','admin',{'template_id':ident,'version':definition['version']})
            saved={'definition':definition,'description':description}
    return catalog.public_definition(saved['definition'], saved['description'])
