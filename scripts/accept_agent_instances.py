"""Real 18003-only native Agent acceptance; stores metadata and integrity, no transcripts."""
import json,pathlib,urllib.request,uuid,hashlib,time,sys
BASE='http://127.0.0.1:18003/api/agent-instances/'
OUT=pathlib.Path('/var/lib/agentscope-scope-demo/instance-acceptance-evidence.json')
def api(ident,suffix='',body=None,method=None):
    request=urllib.request.Request(BASE+ident+suffix,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(request,timeout=150) as r:return json.load(r)
ids=json.loads(pathlib.Path('/var/lib/agentscope-scope-demo/instance-acceptance.json').read_text())
evidence=json.loads(OUT.read_text()) if OUT.exists() else {}
for kind,i in ids.items():
    row=api(i);sessions=[]
    for resource in row['resources']:
        result=api(i,'/sessions',{'resource':resource});print(kind,'created',result,flush=True)
        sid=result.get('session_id') or result.get('sessionId') or result.get('agentId')
        assert sid,result
        sessions.append({'resource':resource,'native_id':sid,'stored_id':result.get('stored_session_id')})
    root=pathlib.Path('/s/instance-resources/rq5-'+kind)
    project=root/'transaction-verification-service'
    protect=[*list((project/'tests').rglob('*')),*list((project/'config').rglob('*')),project/'config.toml',project/'run_tests.py',project/'setup.py',project/'README.md',root/'test_validator.py',root/'tests_rate_limiter.py']
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protect if p.is_file()}
    execution=next(r['execution'] for r in row['resource_records'] if r['source']==str(root))+'/transaction-verification-service'
    task=(root/'task.md').read_text().replace('/workspace/transaction-verification-service/',execution+'/')
    prompt=task+'\nThe actual repository is '+execution+'. Work on the real source and run the existing tests. Preserve tests, configuration, run_tests.py and setup.py. Report actual blockers and results. Do not install packages or use external services other than the configured model.'
    accepted=api(i,'/sessions/prompt',{'session_id':sessions[0]['native_id'],'text':prompt})
    api(i,'/sessions/prompt',{'session_id':sessions[1]['native_id'],'text':'Read README.md with a native tool and summarize it in one sentence. Do not write files. Then stop.'})
    evidence.setdefault(kind,{}).update({'instance_id':i,'generation':row['generation'],'domain_id':row['domain_id'],'pid':row['pid'],'resources':row['resources'],'sessions':sessions,'protected_before':hashes,'verification':row['runtime']['verification'],'prompt_accepted':True,'started_at':time.time()})
    OUT.write_text(json.dumps(evidence,ensure_ascii=False,indent=2));OUT.chmod(0o600)
    print(kind,'native tasks accepted',flush=True)
