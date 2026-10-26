"""Bounded workspace evidence for template parameters; never execution authority."""
import grp
import json
import os
import pwd
import re
import subprocess
import sys
import threading
import uuid
import time
from contextvars import ContextVar
from pathlib import Path,PurePosixPath
from fastapi import HTTPException
from .. import db
from ..workspaces.scene_read import public_text
from . import store,dsl_policy as dsl,system_policy as system
from .mapping import resource_records,translate
from .policy import digest
from reference_reader_channel import ReaderUnavailable,inherited_client

SCHEMA='''CREATE TABLE IF NOT EXISTS template_workspace_reads(
 id TEXT PRIMARY KEY,instance_id TEXT NOT NULL,request_key TEXT NOT NULL,request_hash TEXT NOT NULL,
 snapshot_json TEXT NOT NULL,snapshot_hash TEXT NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(instance_id,request_key));'''
SLOTS=threading.BoundedSemaphore(2)
READ_DEADLINE=ContextVar('policy_reference_deadline',default=None)
WORKER=Path(__file__).resolve().parents[2]/'reference_file_reader.py'
READER_CHANNEL=inherited_client()
TEXT_EXTENSIONS={'.md','.txt','.rst','.json','.yaml','.yml','.toml','.ini','.cfg','.py','.js','.jsx','.ts','.tsx','.sh','.sql','.xml','.csv','.dsl',
 '.go','.rs','.java','.c','.h','.cc','.cpp','.hpp','.vue','.svelte','.css','.scss','.html','.cs','.rb','.php','.kt','.kts','.gradle','.properties'}
SENSITIVE=re.compile(r'(?i)(?:^|[._-])(?:credentials?|secrets?|tokens?|private|id_rsa|id_ed25519)(?:$|[._-])')
EXCLUDED={'.git','.dsh','.actplane','.ssh','.aws','.azure','.gnupg','.venv','node_modules','__pycache__'}

def sanitized_text(value):
 value=public_text(value)
 value=re.sub(r'(?s)-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z]+ )?PRIVATE KEY-----','[PRIVATE KEY OMITTED]',value)
 keys=r'api[_-]?key|access[_-]?token|password|passwd|secret[_-]?access[_-]?key|authorization|refresh[_-]?token|credential|token|secret'
 return re.sub(r'''(?i)(["']?(?:'''+keys+r''')["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}]+)''',r'\1[REDACTED]',value)

def init(con):con.executescript(SCHEMA)

def reader_identity():
 # Pinned instance_runtime.prepare_home / instance_runner.sandbox use this UID,
 # this primary GID and no supplementary groups. No caller chooses an identity.
 user=os.getenv('AGENTSCOPE_REFERENCE_READER_USER','happy')
 group=os.getenv('AGENTSCOPE_REFERENCE_READER_GROUP',os.getenv('AGENTSCOPE_TASK_GROUP','agentscope-task'))
 return pwd.getpwnam(user).pw_uid,grp.getgrnam(group).gr_gid

def context(ident):
 row=store.get(ident)
 if row['mode']!='controlled':raise ValueError('仅支持已登记的受控 Agent 工作区')
 system.ensure_ready(ident)
 if row['gate'] not in ('closed','open'):raise ValueError('Agent 配置或运行身份待核验，请恢复后重新读取')
 shared=system.current()
 if row['policy'].get('resource_views'):
  from .resource_views import validate
  validate(row['policy']['resource_views'],row['resources'])
 uid,gid=reader_identity()
 binding={'instance_id':ident,'generation':row['generation'],'resources':row['resources'],'policy_hash':row['policy_hash'],
  'local_policy_hash':digest(row['local_policy']),'system_policy_hash':shared['policy_hash'],
  'system_dsl_hash':dsl.current('system')['document_hash'],'agent_dsl_hash':dsl.current(ident)['document_hash'],'uid':uid,'gid':gid}
 return row,binding

def directory(ident):
 row,_=context(ident)
 return {'instance_id':ident,'workspaces':[{'id':digest([ident,m['source']])[:32],'name':Path(m['source']).name,
  'path':m['source'],'execution_path':m['execution'],'source':'registered_resource','readable':True} for m in resource_records(row['resources'],views=row['policy'].get('resource_views'))],
  'limits':{'files':10,'file_bytes':65536,'total_bytes':196608},
  'message':'仅从此 Agent 已登记资源目录选择参考文本；每个文件仍须通过当前读取权限校验。'}

def selected_workspace(row,workspace_id):
 for mount in resource_records(row['resources'],views=row['policy'].get('resource_views')):
  if digest([row['id'],mount['source']])[:32]==workspace_id:return mount
 raise ValueError('工作区不属于此 Agent 当前登记的资源范围')

def paths_checked(paths):
 if not isinstance(paths,list) or not 1<=len(paths)<=10 or any(not isinstance(p,str) for p in paths) or len(set(paths))!=len(paths):raise ValueError('请选择 1 至 10 个不同的参考文件')
 for value in paths:
  if not isinstance(value,str) or not value or len(value)>1000 or re.search(r'[\x00-\x1f\\]',value):raise ValueError('参考文件路径不合法')
  path=PurePosixPath(value)
  if path.is_absolute() or str(path)!=value or any(p in ('.','..','') for p in value.split('/')):raise ValueError('只能填写工作区内的相对文件路径')
  if any(p in EXCLUDED or p=='.env' or p.startswith('.env.') or SENSITIVE.search(p) for p in path.parts) or path.suffix.lower() in {'.pem','.key','.p12','.pfx'}:raise ValueError('凭据、私钥和运行私有目录不能作为策略参考材料')
  if path.suffix.lower() not in TEXT_EXTENSIONS and path.name not in {'AGENTS','Dockerfile','Makefile'}:raise ValueError('仅支持已声明的 UTF-8 文本文件类型')
 return sorted(paths)

def could_match(pattern,value):
 # A conservative superset of exact/prefix/suffix/contains matching. Unknown
 # glob syntax cannot prove readability. Conditions/exceptions never relax this.
 if re.search(r'[?\[\]{}\\]',pattern):return True
 parts=pattern.split('*')
 if len(parts)==1:return pattern==value
 if parts[0] and not value.startswith(parts[0]):return False
 if parts[-1] and not value.endswith(parts[-1]):return False
 offset=0
 for part in parts:
  if part:
   offset=value.find(part,offset)
   if offset<0:return False
   offset+=len(part)
 return True

def permission_guard(row,mount):
 shared=system.current()['policy']
 rules=row['policy']['rules']+system.applicable(shared['rules'],row['resources'])
 from dsl_documents import prepare
 # Parsing only: every potentially matching deny applies regardless of labels.
 # No synthetic source is installed or claimed as a verified runtime source.
 parsed=prepare(dsl.documents_for(row['id']),row['resources'],'**/reference-read',resource_views=row['policy'].get('resource_views'))
 def allowed(relative):
  host=str(Path(mount['source'])/relative);execution=translate(host,row['resources'],views=row['policy'].get('resource_views'))
  for rule in rules:
   if rule['action']=='read' and rule['effect']=='deny' and (host==rule['target'] or host.startswith(rule['target']+'/')):raise ValueError('系统或 Agent 策略禁止读取所选文件')
  for document in parsed:
   for rule in document['rules']:
    for clause in rule['clauses']:
     pattern=translate(clause['target'],row['resources'],views=row['policy'].get('resource_views')) if clause['target'].startswith('/') else clause['target']
     if clause['effect'] in ('block','kill') and clause['operation'] in ('read','open') and any(could_match(pattern,v) for v in (host,execution)):
      raise ValueError('已有 ActPlane 读取约束可能匹配所选文件，请选择其他参考资料')
 return allowed

def check_permissions(row,mount,paths):
 guard=permission_guard(row,mount)
 for relative in paths:guard(relative)

def run_reader(payload,uid,gid):
 deadline=READ_DEADLINE.get()
 if deadline is None:deadline=time.monotonic()+5
 remaining=deadline-time.monotonic()
 if remaining<=0:raise ValueError('场景分析读取期限已到，请重新分析或缩小场景')
 if not SLOTS.acquire(timeout=min(5,remaining)):raise ReaderUnavailable()
 try:
  # subprocess's built-in identity drop is safe from this threaded API. No
  # preexec_fn, user commands, shell, tools, runtime cgroup or native Agent call.
  identity={'user':uid,'group':gid,'extra_groups':[]} if os.geteuid()==0 else {}
  remaining=deadline-time.monotonic()
  if remaining<=0:raise ReaderUnavailable()
  if os.geteuid()!=0 and (os.geteuid()!=uid or os.getegid()!=gid or os.getgroups()):
   if READER_CHANNEL is None:raise ReaderUnavailable()
   return READER_CHANNEL.read(payload,uid,gid,min(5,remaining))
  result=subprocess.run([sys.executable,'-I',str(WORKER)],input=json.dumps(payload),capture_output=True,text=True,
   timeout=min(5,remaining),env={'LANG':'C.UTF-8'},cwd='/',**identity)
  if result.returncode or len(result.stdout.encode())>1600000:raise ValueError('所选文件无读取权限、格式不支持、超过限额或读取期间发生变化')
  value=json.loads(result.stdout)
  if 'error' in value:raise ValueError('参考文件读取失败，请重新选择')
  return value
 except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError):raise ValueError('参考文件读取未完成，请稍后重新读取') from None
 finally:SLOTS.release()

def read_files(root,paths,uid,gid,max_total_bytes=None):
 return run_reader({'root':root,'paths':paths,**({'max_total_bytes':max_total_bytes} if max_total_bytes is not None else {})},uid,gid)

def directory_path(path):
 if not isinstance(path,str) or len(path)>1000 or re.search(r'[\x00-\x1f\\]',path) or path.startswith('/') or path and (str(PurePosixPath(path))!=path or any(p in ('','.','..') for p in path.split('/'))):
  raise ValueError('只能浏览工作区内的规范相对目录')
 if any(p in EXCLUDED or p=='.env' or p.startswith('.env.') or SENSITIVE.search(p) for p in PurePosixPath(path).parts):
  raise ValueError('运行私有目录和凭据目录不能作为场景资料')
 return path

def list_files(ident,workspace_id,path='',cursor=0):
 row,binding=context(ident);mount=selected_workspace(row,workspace_id);path=directory_path(path)
 if type(cursor) is not int or not 0<=cursor<=1000:raise ValueError('目录分页参数不合法')
 guard=permission_guard(row,mount);guard(path)
 result=run_reader({'operation':'list','root':mount['source'],'path':path,'cursor':cursor},binding['uid'],binding['gid'])
 entries=[];omitted=0
 for entry in result['entries']:
  try:
   if not entry['readable']:raise ValueError('unreadable')
   if entry['kind']=='directory':directory_path(entry['relative_path'])
   elif entry['kind']=='file':paths_checked([entry['relative_path']])
   else:raise ValueError('unsupported')
   guard(entry['relative_path'])
  except ValueError:omitted+=1;continue
  entries.append({k:entry[k] for k in ('name','relative_path','kind','byte_size')})
 if context(ident)[1]!=binding:raise ValueError('浏览期间 Agent、资源或策略发生变化，请重新分析场景')
 return {'instance_id':ident,'workspace_id':workspace_id,'path':path,
  'execution_path':translate(str(Path(mount['source'])/path),row['resources'],views=row['policy'].get('resource_views')),
  'entries':[{**entry,'execution_path':translate(str(Path(mount['source'])/entry['relative_path']),row['resources'],views=row['policy'].get('resource_views'))} for entry in entries],'omitted_count':omitted,
  'next_cursor':result['next_cursor'],'truncated':result['truncated'],'read_only':True}

def snapshot(ident,workspace_id,paths,max_total_bytes=None):
 row,binding=context(ident);paths=paths_checked(paths);mount=selected_workspace(row,workspace_id)
 check_permissions(row,mount,paths)
 value=read_files(mount['source'],paths,binding['uid'],binding['gid'],**({'max_total_bytes':max_total_bytes} if max_total_bytes is not None else {}))
 for source in value['files']:
  source['text']=sanitized_text(source['text']);source['execution_path']=translate(str(Path(mount['source'])/source['relative_path']),row['resources'],views=row['policy'].get('resource_views'))
  source['text_hash']=digest(source['text'])
 if context(ident)[1]!=binding:raise ValueError('读取期间 Agent、资源或策略发生变化，请重新读取')
 return {'binding':binding,'workspace_id':workspace_id,'workspace_name':Path(mount['source']).name,'root_identity':value['root_identity'],'files':value['files']}

def load(ident,read_id):
 with db.connect() as con:row=con.execute('SELECT * FROM template_workspace_reads WHERE instance_id=? AND id=?',(ident,read_id)).fetchone()
 if not row:raise HTTPException(404,'参考资料读取记录不存在或不属于此 Agent')
 row=dict(row);row['snapshot']=json.loads(row.pop('snapshot_json'))
 if digest(row['snapshot'])!=row['snapshot_hash']:raise ValueError('参考资料校验失败，请重新读取')
 return row

def verify(ident,read_id):
 row=load(ident,read_id);value=row['snapshot']
 if context(ident)[1]!=value['binding']:raise ValueError('场景依据中的 Agent、资源或策略已经变化，请重新读取')
 fresh=snapshot(ident,value['workspace_id'],[f['relative_path'] for f in value['files']])
 if digest(fresh)!=row['snapshot_hash']:raise ValueError('项目文件已经变化，请重新读取参考资料')
 return row

def verify_metadata(ident,read_id):
 # Approval directory polling checks metadata only through the fixed identity.
 # Exact byte hashes and DAC are rechecked at generate/propose/apply boundaries.
 row=load(ident,read_id);value=row['snapshot'];owner,binding=context(ident)
 if binding!=value['binding']:raise ValueError('场景依据中的 Agent、资源或策略已经变化，请重新读取')
 mount=selected_workspace(owner,value['workspace_id'])
 if READER_CHANNEL is not None:
  fresh=run_reader({'operation':'metadata','root':mount['source'],'paths':[f['relative_path'] for f in value['files']]},binding['uid'],binding['gid'])
  if fresh['root_identity']!=value['root_identity'] or fresh['files']!=[{k:f[k] for k in ('relative_path','identity')} for f in value['files']]:raise ValueError('项目文件已经变化，请重新读取参考资料')
  return row
 from reference_file_reader import directory as anchored_directory,identity
 for source in value['files']:
  handles=[]
  try:
   parent=anchored_directory(mount['source'],handles)
   if identity(os.fstat(parent))[:2]!=value['root_identity']:raise ValueError('项目工作区已经变化，请重新读取')
   for part in source['relative_path'].split('/')[:-1]:
    parent=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);handles.append(parent)
   if identity(os.stat(source['relative_path'].split('/')[-1],dir_fd=parent,follow_symlinks=False))!=source['identity']:
    raise ValueError('项目文件已经变化，请重新读取参考资料')
  except OSError:raise ValueError('项目文件不可核验，请重新读取参考资料') from None
  finally:
   for handle in reversed(handles):os.close(handle)
 return row

def public(row):
 value=row['snapshot']
 return {'id':row['id'],'instance_id':row['instance_id'],'created_at':row['created_at'],'snapshot_hash':row['snapshot_hash'],
  'workspace_name':value['workspace_name'],'workspace_id':value['workspace_id'],'files':[{k:f[k] for k in ('relative_path','execution_path','byte_size','text')} for f in value['files']],
  'read_only':True,'applied':False}

def create(ident,body,max_total_bytes=None):
 paths=paths_checked(body['paths']);request_hash=digest([body['workspace_id'],paths])
 with db.connect() as con:prior=con.execute('SELECT id,request_hash FROM template_workspace_reads WHERE instance_id=? AND request_key=?',(ident,body['request_key'])).fetchone()
 if prior:
  if prior['request_hash']!=request_hash:raise ValueError('读取请求已用于其他文件选择')
  return public(verify(ident,prior['id']))
 value=snapshot(ident,body['workspace_id'],paths,**({'max_total_bytes':max_total_bytes} if max_total_bytes is not None else {}));read_id=uuid.uuid4().hex
 with db.connect() as con:
  con.execute('INSERT OR IGNORE INTO template_workspace_reads VALUES(?,?,?,?,?,?,?)',(read_id,ident,body['request_key'],request_hash,json.dumps(value,ensure_ascii=False),digest(value),db.now()))
  winner=con.execute('SELECT id,request_hash FROM template_workspace_reads WHERE instance_id=? AND request_key=?',(ident,body['request_key'])).fetchone()
  if winner['request_hash']!=request_hash:raise ValueError('读取请求已用于其他文件选择')
  db.audit(con,None,'template_workspace_read','authenticated_operator',{'instance_id':ident,'read_id':winner['id'],'file_count':len(paths),'snapshot_hash':digest(value)})
 return public(load(ident,winner['id']))

def for_model(ident,read_id):
 if not read_id:return None
 row=verify(ident,read_id);value=row['snapshot']
 return {'read_id':read_id,'snapshot_hash':row['snapshot_hash'],'workspace':value['workspace_name'],
  'untrusted_project_files':[{k:f[k] for k in ('relative_path','execution_path','text')} for f in value['files']]}
