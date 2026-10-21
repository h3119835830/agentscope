"""Explicit policy ownership; never infer an Agent baseline from a native session."""
import json
import re
from pathlib import Path, PurePosixPath
from .pipeline import digest
from ..instances.mapping import resource_records, translate


class AmbiguousObject(ValueError):
    pass


def snapshot(ident, scope, workspace_id=None):
    from . import agent_context as legacy
    from ..instances import controller, dsl_policy, system_policy, policy_targets
    from .capabilities import translation_capabilities
    if scope not in ('agent','workspace'):
        raise ValueError('未知策略范围')
    registered=controller.detail(ident)
    if registered['mode']!='controlled':
        raise ValueError('请选择具体受控 Agent')
    target={'scope':scope,'instance_id':ident,'workspace_id':workspace_id if scope=='workspace' else None,'session_id':None}
    if scope=='agent' and workspace_id:
        raise ValueError('Agent 基线不能绑定工作区')
    try:
        row=legacy.live_row(ident)
    except (ValueError,OSError) as error:
        return {'ready':False,'target':target,'scope':scope,'message':str(error),'workspaces':[],
                'application_capability':policy_targets.capability(target)}
    if scope=='workspace':
        from ..instances.sessions import native_workspace_info
        sessions=legacy.choices(row)
        choices={}
        selected=None
        for session in sessions:
            info=native_workspace_info(row,session)
            if info and info.get('id'):
                choices[info['id']]={'id':info['id'],'name':info.get('name') or '已登记工作区','path':info['path']}
                if info['id']==workspace_id:
                    selected=session
        if workspace_id and not selected:
            raise ValueError('工作区不属于此 Agent 或身份尚未核验')
        if not selected:
            return {'ready':False,'target':target,'scope':scope,'workspaces':list(choices.values()),
                    'message':'请选择已核验的工作区；身份缺失时只能保存草案。',
                    'application_capability':policy_targets.capability(target)}
        result=legacy.snapshot(ident,selected['id'])
        if not result['ready']:
            return result
        ctx=result['resolved_context']
        ctx['policy_scope']='workspace'
        ctx['policy_target']=policy_targets.generated_target(ctx)
        result.update(target=ctx['policy_target'],scope=scope,workspaces=list(choices.values()),
                      application_capability=policy_targets.capability(ctx['policy_target']))
        return result
    mounts=resource_records(row['resources'],views=row.get('policy',{}).get('resource_views'))
    if not mounts:
        raise ValueError('请先登记 Agent 可访问的资源范围')
    for mount in mounts:
        path=Path(mount['source'])
        if not path.is_dir() or str(path.resolve())!=mount['source']:
            raise ValueError('登记资源路径需要重新核验')
    scopes={s:{k:dsl_policy.current(s)[k] for k in ('revision','document_hash','phase')} for s in ('system',ident)}
    if any(s['phase']!='ready' for s in scopes.values()) or system_policy.current()['phase']!='ready':
        raise ValueError('当前策略配置未就绪，请先恢复配置')
    source=legacy.source_for(row)
    runtime=row['runtime']
    values={'schema':'agentscope.agent-baseline/v1','instance_id':ident,'agent_type':row['agent_type'],
            'resources':sorted(row['resources']),'resource_views':row.get('policy',{}).get('resource_views'),'mounts':mounts,'source':source,'policy_scopes':scopes,
            'workspace':{'execution':'/w','host':None,'native_workspace_id':None},
            'runtime':{k:runtime[k] for k in ('generation','pid','start_ticks','domain_id','host_id','boot_id')},
            'permission_hash':row.get('policy_hash'),'system_permission_revision':system_policy.current()['revision'],
            'capabilities':translation_capabilities(agent_source=source['pattern'])}
    binding={'values':values,'hash':digest(values)}
    ctx={'kind':'agent','policy_scope':'agent','instance_id':ident,'session_id':None,'session_name':None,
         'workspace':'/w','allowed_paths':[m['execution'] for m in mounts],
         'verified_targets':[{'absolute_path':m['execution'],'kind':'directory'} for m in mounts],
         'environment_binding':binding,'policy_target':target}
    return {'ready':True,'scope':'agent','target':target,'session_id':None,'sessions':[],
            'context_hash':binding['hash'],'resolved_context':ctx,'resources':mounts,
            'application_capability':policy_targets.capability(target),
            'environment':{'workspace':None,'product':row['agent_type'],'source':source['pattern']}}


def check_pattern(pattern,ctx):
    path=PurePosixPath(pattern)
    if not path.is_absolute() or '..' in path.parts or str(path)!=pattern:
        raise ValueError('策略对象必须是登记资源内的规范绝对路径')
    mounts=ctx['environment_binding']['values']['mounts']
    mount=next((m for m in mounts if pattern==m['execution'] or pattern.startswith(m['execution']+'/')),None)
    if not mount:
        raise ValueError('策略对象超出此 Agent 登记的资源范围')
    relative=pattern[len(mount['execution']):].lstrip('/')
    literal=re.split(r'[*?\[]',relative,maxsplit=1)[0].rstrip('/')
    target=Path(mount['source'])/literal
    if target.resolve()!=target:
        raise ValueError('策略对象经过符号链接，请重新核验实际路径')


def bind_targets(context,requests):
    ctx=json.loads(json.dumps(context))
    values=ctx['environment_binding']['values']
    mounts=values['mounts']
    targets=[];facts=[]
    for request in requests:
        raw=request['path']
        if not isinstance(raw,str) or not raw or len(raw)>1000 or any(c in raw for c in '\r\n\x00'):
            raise ValueError('策略操作对象无效')
        if not raw.startswith('/'):
            if len(mounts)!=1:
                raise AmbiguousObject('存在多个登记资源，请补充操作对象的完整路径；不能借用某个会话的工作目录。')
            path=mounts[0]['execution']+'/'+raw
        else:
            path=translate(raw,values['resources'],views=values.get('resource_views'))
        check_pattern(path,ctx)
        host=translate(re.split(r'[*?\[]',path,maxsplit=1)[0].rstrip('/'),values['resources'],reverse=True,views=values.get('resource_views'))
        disk=Path(host)
        stat=disk.stat() if disk.exists() else None
        fact={'path':path,'exists':stat is not None,'device':stat.st_dev if stat else None,
              'inode':stat.st_ino if stat else None,'kind':'directory' if stat and disk.is_dir() else 'file' if stat else 'future_path'}
        facts.append(fact);targets.append({'absolute_path':path,'kind':fact['kind'],'exists':fact['exists']})
    values['target_paths']=facts
    ctx['target_requests']=requests
    ctx['verified_targets']=targets or ctx['verified_targets']
    ctx['allowed_paths']=[] if targets else ctx['allowed_paths']
    ctx['environment_binding']['hash']=digest(values)
    return ctx
