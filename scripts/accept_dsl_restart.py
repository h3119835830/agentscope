#!/usr/bin/env python3
"""Verify all three fixed DSL probe events survive an isolated restart."""
import json,os,subprocess,sys,urllib.request
from pathlib import Path
def api(path,body=None):
    req=urllib.request.Request('http://127.0.0.1:18003'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)
if os.getuid()!=0 or len(sys.argv)!=2:raise SystemExit('Run as root: accept_dsl_restart.py ISOLATED_FIXTURE_INSTANCE')
ident=sys.argv[1];row=api('/api/agent-instances/'+ident)
assert row.get('active') and all('/dsl-acceptance-' in p for p in row['resources']),'Only an already-active synthetic acceptance connection may restart'
reports=[]
for i in range(2):
    if i:
        api('/api/agent-instances/'+ident+'/stop',{})
        assert api('/api/agent-instances/'+ident+'/start',{})['active']
    subprocess.run([sys.executable,str(Path(__file__).with_name('resume_dsl_acceptance.py')),ident],check=True)
    reports.append(json.loads(Path('/var/lib/agentscope-scope-demo/report/dsl-runtime-acceptance.json').read_text()))
assert reports[0]['generation']!=reports[1]['generation'] and reports[0]['bundle_hash']==reports[1]['bundle_hash']
summary={'passed':True,'instance_id':ident,'generations':[{'generation':r['generation'],'bundle_hash':r['bundle_hash'],'probes':r['probes'],'mapped_events':sum(bool(e['source_refs']) for e in r['kernel_events'])} for r in reports]}
path=Path('/var/lib/agentscope-scope-demo/report/dsl-restart-acceptance.json');path.write_text(json.dumps(summary,indent=2));path.chmod(0o600)
print(json.dumps(summary))
