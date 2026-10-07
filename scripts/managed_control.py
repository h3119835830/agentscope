#!/usr/bin/env python3
import sys,json,urllib.request,urllib.error
from scope_service import environment
URL='http://127.0.0.1:18003'
def api(path,data=None):
    headers={'Content-Type':'application/json'}
    env=environment()
    if env.get('AGENTSCOPE_DEV_NO_AUTH') != '1':
        headers['Authorization']='Bearer '+env['AGENTSCOPE_ADMIN_TOKEN']
    request=urllib.request.Request(URL+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
    try:
        with urllib.request.urlopen(request,timeout=80) as response:return json.load(response)
    except urllib.error.HTTPError as e:raise RuntimeError(json.load(e).get('detail',str(e)))
if __name__=='__main__':
    from pathlib import Path
    mode=sys.argv[1]
    marker=Path('/var/lib/agentscope-scope-demo/managed-current.json')
    if mode=='create':
        result=api('/api/managed/scenarios/'+sys.argv[2]+'/tasks',{});marker.write_text(json.dumps(result));print(result);print(api('/api/managed/tasks/'+result['id']+'/start',{}))
    else:
        task=json.loads(marker.read_text())['id'];base='/api/managed/tasks/'+task
        if mode=='state':
            x=api(base);print({k:x['state'].get(k) for k in ['phase','gate','revision','version','session_id','web_url']});print([(e['kind'],e['payload'].get('error')) for e in x['events'][:6]])
        elif mode=='close':print(api(base+'/close',{}))
        elif mode=='prompt':print(api(base+'/prompt',{'text':sys.argv[2]}))
        elif mode=='native':print(api(base+'/native'))
