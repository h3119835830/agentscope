import os
import json
import sys
import time
import subprocess
from pathlib import Path

root=Path(sys.argv[1]);target=root/sys.argv[2];records=[]
records.append({'name':'legal-read','illegal':False,'ok':bool(target.read_bytes()),'pid':os.getpid()})
allowed=root/'history-legal.tmp';allowed.write_text('legal');allowed.unlink()
records.append({'name':'legal-write-and-unlink','illegal':False,'ok':True,'pid':os.getpid()})
cache=root/'.cache/disposable/history-probe-cache.tmp'
if cache.exists():
    cache.unlink();records.append({'name':'legal-disposable-cache-cleanup','illegal':False,'ok':not cache.exists(),'pid':os.getpid()})
for indirect in (False,True):
    for operation in ('write','unlink','rename'):
        start=time.time_ns();denied=False;child_pid=None
        if indirect:
            code="import os,json,pathlib,sys;p=pathlib.Path(sys.argv[1]);print(json.dumps({'pid':os.getpid()}),flush=True);"
            code+={'write':"p.write_text('tampered')",'unlink':"p.unlink()",'rename':"p.rename(p.with_suffix('.moved'))"}[operation]
            r=subprocess.run([sys.executable,'-c',code,str(target)],capture_output=True,text=True)
            child_pid=json.loads(r.stdout.splitlines()[0])['pid'];denied=r.returncode!=0 and 'Operation not permitted' in r.stderr
        else:
            try:
                if operation=='write':target.write_text('tampered')
                elif operation=='unlink':target.unlink()
                else:target.rename(target.with_suffix('.moved'))
            except OSError as e:denied=e.errno==1
        records.append({'name':('script-' if indirect else 'direct-')+operation,'illegal':True,'denied':denied,'pid':os.getpid(),'child_pid':child_pid,'start_ns':start,'end_ns':time.time_ns()})
print(json.dumps({'records':records}))
