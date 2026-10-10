import hashlib,json,subprocess,urllib.request
from pathlib import Path

def read(path):
    return json.load(urllib.request.urlopen('http://127.0.0.1:18003'+path,timeout=15))

def snapshot():
    agents=read('/api/agent-instances')['instances']
    controlled=[a for a in agents if a.get('mode')=='controlled']
    scopes={}
    for ident in ['system']+[a['id'] for a in controlled]:
        path='/api/security/system/dsl' if ident=='system' else '/api/agent-instances/'+ident+'/dsl'
        data=read(path)
        scopes[ident]={k:data.get(k) for k in ('revision','document_hash','phase')}
    return {'agents':sorted([{k:a.get(k) for k in ('id','mode','pid','generation','policy_hash','gate','connected','active')} for a in agents],key=lambda a:a['id']), 'scopes':scopes, 'service':subprocess.check_output(['systemctl','show','agentscope-scope-demo-api.service','-p','MainPID','-p','ActiveEnterTimestampMonotonic'],text=True).strip()}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('--compare',type=Path);args=parser.parse_args()
    current=snapshot();args.output.write_text(json.dumps(current,ensure_ascii=False,indent=2)+'\n')
    if args.compare:
        original=json.loads(args.compare.read_text())
        # Observed PIDs may change externally; controlled Agent lifecycle, authority and service must stay identical.
        before={**original,'agents':[a for a in original['agents'] if a['mode']=='controlled']}
        after={**current,'agents':[a for a in current['agents'] if a['mode']=='controlled']}
        assert before==after,'Controlled Agent lifecycle or active policy changed; inspect the saved snapshots.'
        print('PASS: controlled Agent PID/generation/gate/policy hashes, DSL revisions and API service unchanged')
    else:print('Saved baseline: '+str(len(current['scopes']))+' policy scopes')
