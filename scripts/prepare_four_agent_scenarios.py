#!/usr/bin/env python3
"""Prepare only disposable experiment dependencies; never restart production.

Run as WSL root. Existing source pins and the first production baseline are
preserved. No access keys are emitted or included in the source manifest.
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, urllib.request
from pathlib import Path
from accept_four_agent_scenarios import ROOT, STATE, OAS, BINARY, guard

PINS={
 'OpenAgentSafety.git':('https://github.com/Open-Agent-Safety/OpenAgentSafety.git','2fdd4057c8dae6e776999a55a5766a862e96f174',True),
 'mini-swe-agent':('https://github.com/SWE-agent/mini-swe-agent.git','04d809ceab9df28f9adaed044884180159172930',False),
 'flask':('https://github.com/pallets/flask.git','d8c37f43724cd9fb0870f77877b7c4c7e38a19e0',False),
}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    assert os.geteuid()==0
    os.umask(0o077);STATE.mkdir(mode=0o755,exist_ok=True)
    research=STATE/'research';research.mkdir(exist_ok=True);research.chmod(0o755)
    baseline=STATE/'production-before.json'
    if not baseline.exists():
        import deploy_policy_semantics as d
        baseline.write_text(json.dumps({'api':d.service(d.UNIT),'broker':d.service('agentscope-scope-demo-broker.service'),
                                       'authority':d.authority(),'listeners':d.listeners()},ensure_ascii=False,indent=2))
    manifest={'sources':{},'binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest()}
    for name,(url,commit,bare) in PINS.items():
        path=research/name
        if not path.exists():
            assert not args.verify,'Missing pinned source '+name
            subprocess.run(['git','clone','--filter=blob:none','--no-checkout',*(['--bare'] if bare else []),url,str(path)],check=True)
            if not bare:subprocess.run(['git','-C',str(path),'checkout','--detach',commit],check=True)
        head=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
        assert head==commit, 'Source pin drift: '+name
        manifest['sources'][name]={'url':url,'commit':commit}
    issue=research/'issue.json'
    if not issue.exists():
        assert not args.verify
        url='https://datasets-server.huggingface.co/rows?dataset=princeton-nlp/SWE-bench_Lite&config=default&split=test&offset=100&length=100'
        rows=json.load(urllib.request.urlopen(url,timeout=40))['rows']
        row=next(r['row'] for r in rows if r['row']['instance_id']=='pallets__flask-4045')
        assert row['base_commit']==PINS['flask'][1];issue.write_text(json.dumps(row,indent=2))
    manifest['issue_sha256']=hashlib.sha256(issue.read_bytes()).hexdigest()
    modules=STATE/'dsh-modules';modules.mkdir(exist_ok=True);modules.chmod(0o755)
    for child in Path('/opt/agentscope/dsh/node_modules').iterdir():
        dest=modules/child.name
        if not dest.exists():dest.symlink_to(child)
    plugin=modules/'@agentscope/dsh-experiment-feedback'
    assert not plugin.parent.is_symlink(),'Refusing to write through a shared dependency symlink'
    plugin.parent.mkdir(exist_ok=True);plugin.parent.chmod(0o755)
    if not args.verify:
        shutil.copytree(ROOT/'integrations/dsh-experiment-feedback',plugin,dirs_exist_ok=True)
        for p in plugin.rglob('*'):
            if not p.is_symlink():p.chmod(0o755 if p.is_dir() else 0o644)
        if not (plugin/'node_modules').exists():(plugin/'node_modules').symlink_to('/opt/agentscope/dsh/node_modules')
    manifest['feedback_plugin_sha256']=hashlib.sha256((plugin/'lib/index.js').read_bytes()).hexdigest()
    assert manifest['feedback_plugin_sha256']==hashlib.sha256((ROOT/'integrations/dsh-experiment-feedback/lib/index.js').read_bytes()).hexdigest()
    for env in ('venv','task-venv'):
        assert (STATE/env/'bin/python').exists(), 'Install the isolated Python environments listed in the experiment RFC first'
        code='import importlib.metadata,json;print(json.dumps({d.metadata["Name"]:d.version for d in importlib.metadata.distributions()},sort_keys=True))'
        manifest[env]=json.loads(subprocess.check_output([str(STATE/env/'bin/python'),'-c',code],text=True))
    for task in ('safety-backup-script','safety-ambiguous-ssh-key','safety-aws-credentials'):
        raw=subprocess.check_output(['git','-C',str(OAS),'show',f'HEAD:workspaces/tasks/{task}/task.md'])
        manifest.setdefault('oas_task_hashes',{})[task]=hashlib.sha256(raw).hexdigest()
    guard('prepared')
    (STATE/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps({'verified':True,'manifest':str(STATE/'source-manifest.json')}))


if __name__=='__main__':main()
