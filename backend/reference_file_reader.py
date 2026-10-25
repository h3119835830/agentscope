"""Fixed stdin/stdout reader. Launched with the controlled runtime UID/GID, no shell."""
import hashlib
import json
import os
import stat
import sys

MAX_FILE=64*1024
MAX_TOTAL=192*1024

def identity(info):
 return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_mode,info.st_nlink]

def directory(path,handles):
 fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);handles.append(fd)
 for part in path.split('/')[1:]:
  if not part or part in ('.','..'):raise ValueError('invalid root')
  fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);handles.append(fd)
 return fd

def list_directory(root,relative='',cursor=0):
 if not isinstance(relative,str) or relative.startswith('/') or relative and any(p in ('','.','..') for p in relative.split('/')):raise ValueError('invalid directory')
 if type(cursor) is not int or not 0<=cursor<=1000:raise ValueError('invalid cursor')
 handles=[]
 try:
  fd=directory(root,handles);root_identity=identity(os.fstat(fd))[:2]
  for part in relative.split('/') if relative else []:
   fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);handles.append(fd)
  before=identity(os.fstat(fd));names=[]
  with os.scandir(fd) as entries:
   for entry in entries:
    names.append(entry.name)
    if len(names)>1000:break
  truncated=len(names)>1000;names=sorted(names[:1000]);items=[]
  for name in names[cursor:cursor+100]:
   info=os.stat(name,dir_fd=fd,follow_symlinks=False)
   kind='directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) and info.st_nlink==1 else 'unsupported'
   readable=kind!='unsupported' and os.access(name,os.R_OK|(os.X_OK if kind=='directory' else 0),dir_fd=fd,effective_ids=True,follow_symlinks=False)
   items.append({'name':name,'relative_path':relative+'/'+name if relative else name,'kind':kind,'readable':readable,'byte_size':info.st_size if kind=='file' else None})
  if identity(os.fstat(fd))!=before:raise ValueError('directory changed')
  fresh=[]
  try:
   parent=directory(root,fresh)
   if identity(os.fstat(parent))[:2]!=root_identity:raise ValueError('root changed')
   for part in relative.split('/') if relative else []:
    parent=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);fresh.append(parent)
   if identity(os.fstat(parent))!=before:raise ValueError('directory replaced')
  finally:
   for handle in reversed(fresh):os.close(handle)
  return {'entries':items,'next_cursor':cursor+100 if cursor+100<len(names) else None,'truncated':truncated}
 finally:
  for handle in reversed(handles):os.close(handle)

def metadata_selection(root,paths):
 if not isinstance(paths,list) or not 1<=len(paths)<=10:raise ValueError('invalid selection')
 files=[];handles=[]
 try:
  fd=directory(root,handles);root_identity=identity(os.fstat(fd))[:2]
  for relative in paths:
   if not isinstance(relative,str) or relative.startswith('/') or any(p in ('','.','..') for p in relative.split('/')):raise ValueError('invalid path')
   current=[]
   try:
    parent=directory(root,current)
    if identity(os.fstat(parent))[:2]!=root_identity:raise ValueError('root changed')
    for part in relative.split('/')[:-1]:
     parent=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);current.append(parent)
    name=relative.split('/')[-1];info=os.stat(name,dir_fd=parent,follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not os.access(name,os.R_OK,dir_fd=parent,effective_ids=True,follow_symlinks=False):raise ValueError('unreadable file')
    files.append({'relative_path':relative,'identity':identity(info)})
   finally:
    for handle in reversed(current):os.close(handle)
  return {'root_identity':root_identity,'files':files}
 finally:
  for handle in reversed(handles):os.close(handle)

def read_selection(root,paths,max_total_bytes=MAX_TOTAL):
 if not isinstance(root,str) or not root.startswith('/') or not isinstance(paths,list) or not 1<=len(paths)<=10:raise ValueError('invalid selection')
 if type(max_total_bytes) is not int or not 0<=max_total_bytes<=MAX_TOTAL:raise ValueError('invalid budget')
 files=[];total=0
 for relative in paths:
  if not isinstance(relative,str) or relative.startswith('/') or any(p in ('','.','..') for p in relative.split('/')):raise ValueError('invalid path')
  handles=[]
  try:
   fd=directory(root,handles);root_identity=identity(os.fstat(fd))[:2]
   for part in relative.split('/')[:-1]:
    fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);handles.append(fd)
   file=os.open(relative.split('/')[-1],os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW,dir_fd=fd);handles.append(file)
   before=os.fstat(file)
   if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>MAX_FILE or total+before.st_size>max_total_bytes:raise ValueError('unsupported file or budget')
   data=b''
   while len(data)<=MAX_FILE:
    chunk=os.read(file,min(8192,MAX_FILE+1-len(data),max_total_bytes-total+1-len(data)))
    if not chunk:break
    data+=chunk
   if len(data)>MAX_FILE or total+len(data)>max_total_bytes or identity(before)!=identity(os.fstat(file)):raise ValueError('file changed or budget')
   # Re-open every component from /, rejecting ancestor symlink/move swaps.
   fresh=[]
   try:
    parent=directory(root,fresh)
    if identity(os.fstat(parent))[:2]!=root_identity:raise ValueError('root changed')
    for part in relative.split('/')[:-1]:
     parent=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);fresh.append(parent)
    current=os.stat(relative.split('/')[-1],dir_fd=parent,follow_symlinks=False)
    if identity(current)!=identity(before):raise ValueError('file replaced')
   finally:
    for handle in reversed(fresh):os.close(handle)
   text=data.decode('utf-8-sig')
   if '\x00' in text:raise ValueError('binary file')
   total+=len(data)
   if total>max_total_bytes:raise ValueError('selection too large')
   files.append({'relative_path':relative,'sha256':hashlib.sha256(data).hexdigest(),'byte_size':len(data),'identity':identity(before),'text':text})
  finally:
   for handle in reversed(handles):os.close(handle)
 return {'root_identity':root_identity,'files':files}

if __name__=='__main__':
 try:
  # Exec resets dumpability; protect read buffers in this process as well.
  import ctypes,resource
  resource.setrlimit(resource.RLIMIT_CORE,(0,0))
  libc=ctypes.CDLL(None,use_errno=True)
  if libc.prctl(38,1,0,0,0) or libc.prctl(4,0,0,0,0):raise ValueError('reader isolation unavailable')
  raw=sys.stdin.buffer.read(30001)
  if len(raw)>30000:raise ValueError('request too large')
  body=json.loads(raw)
  operation=body.get('operation','read')
  if operation=='list':result=list_directory(body['root'],body.get('path',''),body.get('cursor',0))
  elif operation=='metadata':result=metadata_selection(body['root'],body['paths'])
  elif operation=='read':result=read_selection(body['root'],body['paths'],body.get('max_total_bytes',MAX_TOTAL))
  else:raise ValueError('unsupported operation')
  print(json.dumps(result,ensure_ascii=False))
 except Exception:
  # Never return partially read bytes, credential text or host diagnostics.
  print(json.dumps({'error':'文件不可读取、格式不支持、超过限额或读取期间发生变化。'},ensure_ascii=False));sys.exit(1)
