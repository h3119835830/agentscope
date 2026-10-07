"""Task-scoped, read-only topology from load receipts and owned policy artifacts.

No process arguments, environment, model private stream or arbitrary file reads.
Missing artifacts remain missing; a regenerated policy is never called loaded.
"""
import json,os,re,stat
from pathlib import Path
import yaml
from .. import db
from ..config import POLICY_ROOT
from . import controller as c


def owned_text(path,root):
    path,root=Path(path),Path(root)
    if not path.is_relative_to(root) or path.resolve()!=path:raise ValueError('Untrusted policy artifact path')
    for parent in [root,*path.relative_to(root).parents]:
        directory=parent if parent==root else root/parent
        st=directory.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:raise ValueError('Untrusted policy artifact directory')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022 or st.st_size>250000:raise ValueError('Untrusted policy artifact file')
        with os.fdopen(fd,'r',encoding='utf-8',closefd=False) as stream:return stream.read(250001)
    finally:os.close(fd)


def receipt(con,task_id,version):
    row=con.execute("SELECT payload_json FROM managed_events WHERE task_id=? AND kind='policy_active' AND json_extract(payload_json,'$.version')=? ORDER BY id DESC LIMIT 1",(task_id,version)).fetchone()
    return json.loads(row[0]) if row else None


def domain_sources(task,version,loaded):
    """Domain IDs are local to the task's watch engine, never a global D0."""
    result=[];binding=loaded['binding'];domain=binding.get('domain_id')
    if not isinstance(domain,int):return result
    root=POLICY_ROOT/task['id']
    try:
        text=owned_text(root/f'v{10000+version}'/'policy.yaml',root)
        if c.digest(text)!=loaded['policy_hash']:raise ValueError('Loaded policy hash mismatch')
        dsl=yaml.safe_load(text)['policy']
        if not isinstance(dsl,str):raise ValueError('Missing loaded DSL')
        source={'dsl':dsl,'policy_hash':loaded['policy_hash'],'source':'confirmed_policy_hash','available':True}
    except (OSError,ValueError,KeyError,yaml.YAMLError):source={'available':False,'source':'missing_or_unverified_artifact'}
    result.append({'key':f'v{version}:task','kind':'domain','role':'task','domain_id':domain,'version':version,'title':f'任务域 D{domain}',**source})
    control_root=Path(task['workspace']).parent/'.runtime-control'
    for directory in sorted(control_root.glob(f'v{10000+version}-*')):
        try:
            control=json.loads(owned_text(directory/'.actplane/control.json',control_root))
            if control.get('schema')!='actplane.control.v1' or control.get('pid')!=binding.get('watch_pid'):continue
            parent=control['parent_domain_id']
            if not isinstance(parent,int) or parent==domain:continue
            text=owned_text(directory/'watch.yaml',control_root)
            expected=(binding.get('baseline_binding') or {}).get('bundle_hash')
            if expected and c.digest(text)!=expected:raise ValueError('Parent policy hash mismatch')
            dsl=yaml.safe_load(text)['policy']
            if not isinstance(dsl,str):raise ValueError('Missing parent DSL')
            result.insert(0,{'key':f'v{version}:baseline','kind':'domain','role':'baseline','domain_id':parent,'version':version,
                'title':f'启动底线域 D{parent}','dsl':dsl,'policy_hash':c.digest(text),'source':'root_owned_watch_artifact','available':True})
            break
        except (OSError,ValueError,KeyError,yaml.YAMLError):continue
    for node in result:
        node['labels']=list(dict.fromkeys(re.findall(r'^source\s+([A-Za-z_][A-Za-z_0-9]*)\s*=',node.get('dsl',''),re.M)))
    return result


def graph(task_id,version=None):
    from .records import workbench
    observation=workbench(task_id)
    with db.connect() as con:
        state=c.load(con,task_id);task=c.task_row(con,task_id)
        versions=[dict(r) for r in con.execute("SELECT DISTINCT json_extract(payload_json,'$.version') AS version,json_extract(payload_json,'$.binding.domain_id') AS domain_id FROM managed_events WHERE task_id=? AND kind='policy_active' ORDER BY version DESC",(task_id,))]
        selected=version if version is not None else state['version'];loaded=receipt(con,task_id,selected)
    if version is not None and loaded is None:raise ValueError('Domain version does not belong to this task')
    nodes=domain_sources(task,selected,loaded) if loaded else []
    live=bool(loaded and observation['execution']['verified'] and selected==state['version'] and observation['state']['version']==state['version']
        and observation['execution'].get('domain_id')==loaded['binding'].get('domain_id')==state.get('binding',{}).get('domain_id'))
    for node in nodes:
        node.pop('dsl',None);node.update(live=bool(live),labels=node.get('labels',[]))
    edges=[]
    baseline=next((n for n in nodes if n['role']=='baseline'),None);domain=next((n for n in nodes if n['role']=='task'),None)
    if baseline and domain:edges.append({'from':baseline['key'],'to':domain['key'],'kind':'inherits','label':'继承底线'})
    # These bounded process samples came from the trusted status cgroup.
    if live:
        processes=observation['execution'].get('processes',[])
        by_pid={p['pid']:p for p in processes}
        for p in processes:
            if p['ppid'] in by_pid:edges.append({'from':by_pid[p['ppid']]['key'],'to':p['key'],'kind':'spawn','label':'父子进程'})
            elif domain:edges.append({'from':domain['key'],'to':p['key'],'kind':'membership','label':'任务进程'})
        nodes.extend(processes)
    with db.connect() as con:final=c.load(con,task_id)
    if any(final.get(k)!=state.get(k) for k in ('version','phase','binding','session_id')):
        nodes=[{**n,'live':False} for n in nodes if n['kind']=='domain'];edges=[e for e in edges if e['kind']=='inherits'];live=False
    return {'task_id':task_id,'version':selected,'versions':versions,'nodes':nodes,'edges':edges,'live':bool(live),
        'checked_at':observation['execution']['checked_at'],'coverage':'registered_task_domains_and_task_cgroup_processes',
        'notice':None if baseline else '未取得底线域的可信加载源；不补画全局 D0。'}


def domain_detail(task_id,key):
    match=re.fullmatch(r'v([1-9][0-9]*):(task|baseline)',key)
    if not match:raise ValueError('Invalid domain key')
    with db.connect() as con:
        state=c.load(con,task_id);task=c.task_row(con,task_id);loaded=receipt(con,task_id,int(match[1]))
    if not loaded:raise ValueError('Domain does not belong to this task')
    node=next((n for n in domain_sources(task,int(match[1]),loaded) if n['key']==key),None)
    if not node:raise ValueError('No verified loaded source for this domain')
    return {**node,'historical':state['phase']!='running' or state['version']!=int(match[1]),
        'loading_verification_passed':loaded.get('verification',{}).get('passed') is True,
        'label_semantics':'DSL source declarations; not a live kernel taint inventory'}
