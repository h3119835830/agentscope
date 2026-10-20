"""Versioned source catalogue. Registration never touches execution authority."""
import json
import re
import uuid
from fastapi import HTTPException
from .. import db
from .policy import digest

DEFINITIONS = [
    {'name':'AGENT','description':'受控 Agent 的执行身份，由可信启动流程赋予并继承。',
     'subjects':'受控进程及其后代','assignment':'可信启动流程','reserved':True},
    {'name':'SECRET','description':'敏感来源标记；传播后可被策略条件引用。标记本身不禁止读取或外发。',
     'subjects':'登记文件、派生文件和接触来源的进程','assignment':'获批配置引用的文件来源及运行时传播','reserved':False},
]
SCHEMA = '''
CREATE TABLE IF NOT EXISTS label_sources(
 id TEXT PRIMARY KEY,scope_id TEXT NOT NULL,revision INTEGER NOT NULL,
 archived INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS label_source_versions(
 id TEXT NOT NULL REFERENCES label_sources(id),version INTEGER NOT NULL,
 snapshot_json TEXT NOT NULL,signature TEXT NOT NULL,created_at TEXT NOT NULL,
 PRIMARY KEY(id,version));
CREATE INDEX IF NOT EXISTS label_source_signature ON label_source_versions(signature);
CREATE TABLE IF NOT EXISTS label_source_requests(
 request_key TEXT PRIMARY KEY,request_hash TEXT NOT NULL,result_json TEXT NOT NULL);
'''


def init(con):
    con.executescript(SCHEMA)


def specification(scope_id, matcher, value):
    from .template_configurations import target, path_parameter
    row = target(scope_id, 'system' if scope_id == 'system' else 'agent')
    if matcher not in ('exact','directory','pattern','suffix'):
        raise ValueError('来源支持精确文件、目录、路径匹配或文件后缀')
    if matcher == 'suffix':
        if scope_id != 'system':
            raise ValueError('指定 Agent 的来源必须位于其登记资源内，请使用完整路径')
        if not isinstance(value,str) or not re.fullmatch(r'\.[^/\\*?\[\]\x00-\x20"]{1,60}',value):
            raise ValueError('后缀填写 .env 这样的字面值')
        patterns = ['**/*' + value]
    else:
        value = path_parameter(value, row)
        if matcher in ('exact','directory') and re.search(r'[*?\[]',value):
            raise ValueError('精确文件和目录不接受通配符')
        patterns = [value, value.rstrip('/') + '/**'] if matcher == 'directory' else [value]
        if any(len(p.encode()) > 63 for p in patterns):
            raise ValueError('来源执行模式最多 63 字节')
    return {'label':'SECRET','scope_id':scope_id,'matcher':matcher,'value':value,'patterns':patterns}


def snapshot(ident, version, spec):
    value = {'id':ident,'version':version,**spec}
    return {**value,'snapshot_hash':digest(value)}


def read(con, ident, version=None):
    row = con.execute('SELECT * FROM label_sources WHERE id=?',(ident,)).fetchone()
    if not row:
        raise HTTPException(404,'标签来源不存在')
    saved = con.execute('SELECT snapshot_json FROM label_source_versions WHERE id=? AND version=?',
                        (ident,version or row['revision'])).fetchone()
    if not saved:
        raise HTTPException(404,'标签来源版本不存在')
    return {**json.loads(saved['snapshot_json']),'archived':bool(row['archived']),'latest_version':row['revision']}


def reusable(con, spec):
    row = con.execute('''SELECT v.snapshot_json FROM label_source_versions v
        JOIN label_sources s ON s.id=v.id AND s.revision=v.version
        WHERE v.signature=? AND s.archived=0 ORDER BY s.created_at,s.id LIMIT 1''',(digest(spec),)).fetchone()
    return json.loads(row['snapshot_json']) if row else None


def resolve(scope_id, refs, specs=(), *, allow_archived=False):
    if not isinstance(refs,list) or len(refs)>16:
        raise ValueError('一次最多引用 16 个标签来源')
    result = []
    with db.connect() as con:
        for ref in refs:
            if not isinstance(ref,dict) or set(ref)!={'id','version'} or type(ref['version']) is not int or ref['version']<1:
                raise ValueError('标签来源必须固定 ID 与版本')
            value = read(con,ref['id'],ref['version'])
            if value['scope_id']!=scope_id:
                raise ValueError('不能引用其他 Agent 或其他范围的来源')
            if value['archived'] and not allow_archived:
                raise ValueError('来源已归档，不能新增引用')
            result.append({k:v for k,v in value.items() if k not in ('archived','latest_version')})
        for spec in specs:
            if any(all(existing[k]==v for k,v in spec.items()) for existing in result):
                continue
            result.append(reusable(con,spec) or snapshot('ls_'+uuid.uuid4().hex,1,spec))
    unique = {}
    for value in result:
        unique[(value['id'],value['version'])] = value
    if len(unique)>16:
        raise ValueError('一次最多引用 16 个标签来源')
    return list(unique.values())


def persist(con, sources):
    """Run in the configuration transaction; failed saves leave no registrations."""
    result=[]
    for source in sources:
        spec={k:source[k] for k in ('label','scope_id','matcher','value','patterns')}
        existing=con.execute('SELECT 1 FROM label_sources WHERE id=?',(source['id'],)).fetchone()
        if existing:
            stored=read(con,source['id'],source['version'])
            if stored['archived']:
                raise ValueError('来源已归档，不能新增引用')
            if stored['snapshot_hash']!=source['snapshot_hash']:
                raise ValueError('来源快照不一致')
            result.append(source)
            continue
        source=reusable(con,spec) or source
        if not con.execute('SELECT 1 FROM label_sources WHERE id=?',(source['id'],)).fetchone():
            con.execute('INSERT INTO label_sources VALUES(?,?,1,0,?)',(source['id'],source['scope_id'],db.now()))
            con.execute('INSERT INTO label_source_versions VALUES(?,?,?,?,?)',
                        (source['id'],1,json.dumps(source,ensure_ascii=False),digest(spec),db.now()))
            db.audit(con,None,'label_source_registered','authenticated_operator',
                     {'id':source['id'],'version':1,'scope_id':source['scope_id'],'runtime_policy_changed':False})
        result.append(source)
    return list({(s['id'],s['version']):s for s in result}.values())


def save(body, ident=None):
    if body.get('label','SECRET')!='SECRET':
        raise ValueError('AGENT 是系统保留身份，不能手工赋予；本期仅开放 SECRET 来源')
    spec=specification(body['scope_id'],body['matcher'],body['value'])
    request_hash=digest({'id':ident,**{k:v for k,v in body.items() if k!='request_key'}})
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        previous=con.execute('SELECT * FROM label_source_requests WHERE request_key=?',(body['request_key'],)).fetchone()
        if previous:
            if previous['request_hash']!=request_hash:
                raise HTTPException(409,'幂等键已用于另一来源或范围')
            return json.loads(previous['result_json'])
        if ident:
            old=read(con,ident)
            if old['scope_id']!=body['scope_id']:
                raise ValueError('来源不能更改归属范围')
            if old['archived'] or old['version']!=body['base_version']:
                raise HTTPException(409,'来源已变化，请刷新')
            duplicate=reusable(con,spec)
            if duplicate and duplicate['id']!=ident:
                raise ValueError('同范围已有相同来源，请直接选用该来源')
            value=snapshot(ident,old['version']+1,spec)
            con.execute('UPDATE label_sources SET revision=? WHERE id=?',(value['version'],ident))
            con.execute('INSERT INTO label_source_versions VALUES(?,?,?,?,?)',
                        (ident,value['version'],json.dumps(value,ensure_ascii=False),digest(spec),db.now()))
        else:
            if body.get('base_version',0)!=0:
                raise ValueError('新来源的基准版本应为零')
            value=persist(con,[snapshot('ls_'+uuid.uuid4().hex,1,spec)])[0]
        con.execute('INSERT INTO label_source_requests VALUES(?,?,?)',
                    (body['request_key'],request_hash,json.dumps(value,ensure_ascii=False)))
        db.audit(con,None,'label_source_saved','authenticated_operator',
                 {'id':value['id'],'version':value['version'],'runtime_policy_changed':False})
    return value


def archive(ident, version):
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        old=read(con,ident)
        if old['version']!=version:
            raise HTTPException(409,'来源已变化，请刷新')
        con.execute('UPDATE label_sources SET archived=1 WHERE id=?',(ident,))
        db.audit(con,None,'label_source_archived','authenticated_operator',{'id':ident,'version':version,'runtime_policy_changed':False})
    return {'id':ident,'archived':True}


def directory(scope_id=None):
    from . import dsl_policy
    with db.connect() as con:
        rows=con.execute('SELECT id FROM label_sources'+(' WHERE scope_id=?' if scope_id else '')+' ORDER BY created_at,id',
                         (scope_id,) if scope_id else ()).fetchall()
        sources=[read(con,r['id']) for r in rows]
        configs=con.execute('''SELECT c.id,c.scope_id,c.revision,v.revision configuration_version,v.payload_json
            FROM template_configurations c JOIN template_configuration_versions v ON v.id=c.id''').fetchall()
        active={}
        applied_versions={}
        references=[]
        historical=[]
        for row in configs:
            payload=json.loads(row['payload_json'])
            if scope_id and row['scope_id']!=scope_id:
                continue
            if row['scope_id'] not in active:
                current=dsl_policy.current(row['scope_id'],con)
                active[row['scope_id']]={d['id']:d for d in current['documents']}
                applied_versions[row['scope_id']]=current['revision']
            applied=active[row['scope_id']].get(row['id'])==payload.get('document')
            for source in payload.get('label_sources',[]):
                references.append({'source_id':source['id'],'source_version':source['version'],'configuration_id':row['id'],
                                   'configuration_version':row['configuration_version'],'name':payload['name'],
                                   'scope_id':row['scope_id'],'latest':row['revision']==row['configuration_version'],
                                   'applied_revision':applied_versions[row['scope_id']] if applied else None})
            if not payload.get('label_sources'):
                labels=re.findall(r'^source (SENSITIVE|REMOTE|CODE) =',payload.get('document',{}).get('original_dsl',''),re.M)
                if labels:
                    historical.append({'name':payload['name'],'labels':sorted(set(labels)),'configuration_id':row['id'],
                                       'configuration_version':row['configuration_version'],'historical':True})
        for source in sources:
            source['references']=[r for r in references if r['source_id']==source['id']]
            source['status']='referenced' if source['references'] else 'registered'
    definitions=[{**d,'source_count':sum(s['label']==d['name'] and not s['archived'] for s in sources),
                  'configuration_count':len({r['configuration_id'] for r in references}) if d['name']=='SECRET' else 0}
                 for d in DEFINITIONS]
    return {'labels':definitions,'sources':sources,'historical_references':historical,
            'notice':'登记仅保存资料。来源须被具体配置引用、批准并应用后才进入执行规则。来源更新不改变既有引用或运行策略。'}
