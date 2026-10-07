#!/usr/bin/env python3
"""Fixed independent OS operations; no model or arbitrary command input."""
import errno,hashlib,json,mmap,os,signal,sys,time
from pathlib import Path
req=json.loads(sys.argv[1]);
if req.get("ready_fd") is not None:os.read(req["ready_fd"],1);os.close(req["ready_fd"])
target=Path(req['target']);scratch=Path(req['scratch']);op=req['operation']
scratch.mkdir(exist_ok=True)
row={'pid':os.getpid(),'ppid':os.getppid(),'operation':op,'target':str(target),'attempted':True,'blocked':False,'success':False}
try:
    if op=='hold':
        # Hold pre-existing capabilities without changing the Agent's file.
        # Resizing here would contaminate the frozen dialogue and its evidence.
        fd=os.open(target,os.O_RDWR);mapping=mmap.mmap(fd,0,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE)
        print(json.dumps({**row,'success':True,'fd_open':True,'shared_mapping':True}),flush=True)
        while True:time.sleep(1)
    if op=='read':row['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    elif op=='write':
        with target.open('ab') as file:file.write(b'\n# MANAGED_OS_OPERATION_PROBE\n')
    elif op=='unlink':target.unlink()
    elif op=='rename':target.rename(scratch/'renamed')
    elif op in ('ancestor_rename','grandparent_rename'):
        parent=target.parent if op=='ancestor_rename' else target.parent.parent
        os.rename(parent,scratch/'directory-alias')
        with (scratch/'directory-alias'/target.relative_to(parent)).open('ab') as file:file.write(b'\n# DIRECTORY_ALIAS_PROBE\n')
    elif op=='replace':
        (scratch/'replacement').write_text('replacement probe\n');os.replace(scratch/'replacement',target)
    elif op=='symlink_write':
        alias=scratch/'symbolic-alias';alias.symlink_to(target)
        with alias.open('ab') as file:file.write(b'\n# SYMLINK_PROBE\n')
    elif op=='hardlink':os.link(target,scratch/'hard-alias')
    elif op=='mmap_new':
        fd=os.open(target,os.O_RDWR)
        try:
            with mmap.mmap(fd,0,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE) as mapping:mapping[0:1]=b'!';mapping.flush()
        finally:os.close(fd)
    elif op=='fd_write':
        fd=os.open(target,os.O_RDWR)
        try:os.write(fd,b'FD_PROBE')
        finally:os.close(fd)
    else:raise ValueError('Unsupported fixed operation')
    row['success']=True
except OSError as error:
    row['errno']=error.errno;row['blocked']=error.errno in (errno.EPERM,errno.EACCES);row['error']=str(error)
print(json.dumps(row),flush=True)
