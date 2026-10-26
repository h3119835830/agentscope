#!/usr/bin/env python3
"""Export compact public evidence; credentials, raw logs and model reasoning excluded."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path('/var/lib/agentscope-memory-20261026/evidence')
def main():
    dest=Path(sys.argv[1]);dest.mkdir(exist_ok=True,parents=True)
    def read(name):return json.loads((ROOT/(name+'.json')).read_text())
    def write(name,value):(dest/name).write_text(json.dumps(value,ensure_ascii=False,indent=2))
    result=read('acceptance-result');write('acceptance-result.json',result)
    sessions=[]
    for name in ['session-a-complete','session-c-before','session-c-complete']:
        d=read(name);s=d['state']['state'];memory=s['persistent_memory']
        sessions.append({'snapshot':name,'session_id':s['session_id'],'domain_id':s['binding']['domain_id'],
            'version':s['version'],'baseline_hash':s['baseline_hash'],'runtime_protected':s['runtime_protected'],
            'memory':{k:memory.get(k) for k in ['provider','source_ref','category','type','seq','content_hash','session_id']},
            'public_messages':[e for e in d['native']['events'] if e['type'] in ['user/message','assistant/message'] and e.get('text')]})
    write('cross-session.json',sessions)
    d=read('session-c-complete');write('runtime-records.json',{'records':d['details'],'os_audit':d['os'],'tool_audit':d['tools']})
    probes=[json.loads(p.read_text()) for p in ROOT.glob('c7ae28357e224c7d-probe-*.json')]
    write('probes.json',probes)
    write('failed-trials.json',[{'snapshot':name,'phase':read(name)['state']['state']['phase'],
        'error':read(name)['state']['state'].get('error'),'policy_version':read(name)['state']['state']['version']}
        for name in ['session-a-recall','session-b-delta-failed']])
    files=[p for p in dest.iterdir() if p.is_file() and p.suffix in ['.json','.png'] and p.name!='manifest.json']
    write('manifest.json',{'files':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(files)]})
    print(json.dumps({'result':result['result'],'exported':len(files),'directory':str(dest)},ensure_ascii=False))
if __name__=='__main__':main()
