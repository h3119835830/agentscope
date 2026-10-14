"""Native workspace projection. File listing runs inside the Agent's own sandbox."""
from pathlib import PurePosixPath
from . import controller
from .mapping import translate
from ..broker_client import call as broker

def current(ident):
    row=controller.detail(ident)
    if row['mode']!='controlled' or not row.get('active'):raise ValueError('请先打开并核验此 Agent')
    return row

def project(row,workspace):
    path=workspace.get('path','')
    host=translate(path,row['resources'],reverse=True) if path.startswith('/') else path
    allowed=any(host==base or host.startswith(base+'/') for base in row['resources'])
    display=PurePosixPath(host).name if workspace.get('name')==PurePosixPath(path).name and path!=host else workspace.get('name')
    return {**workspace,'display_name':display,'path':host,'execution_path':translate(host,row['resources']) if host.startswith('/') else host,
            'instance_id':row['id'],'readable':allowed,'reason':'' if allowed else '超出安全配置的文件访问范围'}

def directory(ident):
    row=current(ident)
    result=broker({'action':'agent-instance-workspaces','instance_id':ident})
    return {**result,'instance_id':ident,'generation':row['generation'],
            'workspaces':[project(row,w) for w in result.get('workspaces',[])]}

def files(ident,workspace_id,path=''):
    row=current(ident)
    if not workspace_id or len(workspace_id)>200:raise ValueError('工作区身份无效')
    if not isinstance(path,str) or path.startswith('/') or any(p in ('.','..') for p in path.split('/')) or len(path)>2000:
        raise ValueError('目录路径不合法')
    result=broker({'action':'agent-instance-workspace-files','instance_id':ident,'workspace_id':workspace_id,'path':path})
    if result['workspace']['id']!=workspace_id:raise ValueError('工作区返回身份不一致')
    return {**result,'instance_id':ident,'generation':row['generation'],'workspace':project(row,result['workspace'])}
