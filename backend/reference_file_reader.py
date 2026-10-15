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

def read_selection(root,paths):
 if not isinstance(root,str) or not root.startswith('/') or not isinstance(paths,list) or not 1<=len(paths)<=10:raise ValueError('invalid selection')
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
   if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>MAX_FILE:raise ValueError('unsupported file')
   data=b''
   while len(data)<=MAX_FILE:
    chunk=os.read(file,min(8192,MAX_FILE+1-len(data)))
    if not chunk:break
    data+=chunk
   if len(data)>MAX_FILE or identity(before)!=identity(os.fstat(file)):raise ValueError('file changed')
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
   if total>MAX_TOTAL:raise ValueError('selection too large')
   files.append({'relative_path':relative,'sha256':hashlib.sha256(data).hexdigest(),'byte_size':len(data),'identity':identity(before),'text':text})
  finally:
   for handle in reversed(handles):os.close(handle)
 return {'root_identity':root_identity,'files':files}

if __name__=='__main__':
 try:
  raw=sys.stdin.buffer.read(30001)
  if len(raw)>30000:raise ValueError('request too large')
  body=json.loads(raw)
  print(json.dumps(read_selection(body['root'],body['paths']),ensure_ascii=False))
 except Exception:
  # Never return partially read bytes, credential text or host diagnostics.
  print(json.dumps({'error':'文件不可读取、格式不支持、超过限额或读取期间发生变化。'},ensure_ascii=False));sys.exit(1)
