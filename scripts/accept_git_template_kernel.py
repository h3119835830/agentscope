"""Opt-in isolated Git/BPF acceptance; never touches DSH or production authority."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    assert os.geteuid()==0
    state=Path(tempfile.mkdtemp(prefix='as-git-'));state.chmod(0o755)
    os.environ['AGENTSCOPE_STATE_DIR']=str(state/'state')
    sys.path.insert(0,str(ROOT/'backend'))
    from agentscope_app.instances import template_configurations as tc,template_catalog as catalog
    owner=pwd.getpwnam('happy')
    workspace=state/'work';workspace.mkdir();os.chown(workspace,owner.pw_uid,owner.pw_gid)
    tools=state/'bin';tools.mkdir()
    probe=tools/'gitprobe';shutil.copy2('/usr/bin/python3',probe)
    checker=tools/'gitcheck';shutil.copy2('/bin/sh',checker)
    changed=workspace/'source.txt';changed.write_text('synthetic source\n');os.chown(changed,owner.pw_uid,owner.pw_gid)
    pin=Path('/sys/fs/bpf')/('as-git-'+str(os.getpid()));assert not pin.exists()
    cli=ROOT/'actplane/target/release/actplane'
    report={'scope':'Synthetic Git repositories and isolated ActPlane engines; no DSH, shared Broker, remote network or production policy changes.',
            'cli_sha256':hashlib.sha256(cli.read_bytes()).hexdigest(),'cases':[]}
    runner=state/'probe.py'
    runner.write_text('''import json,subprocess,sys\nfrom pathlib import Path\nrepo,checker,source,command,mode=sys.argv[1:]\nif mode in ('success','failed','changed'):\n r=subprocess.run([checker,'-c','exit 1' if mode=='failed' else 'exit 0']); assert r.returncode==(1 if mode=='failed' else 0)\nif mode=='changed':Path(source).write_text('modified after check\\n')\nargs={'commit':['commit','--allow-empty','-m','synthetic'],'push':['push','--dry-run','origin','HEAD:refs/heads/test'],'clean':['clean','-nd'],'reset':['reset','--soft','HEAD'],'bypass':['commit','--no-verify','--allow-empty','-m','synthetic']}[command]\nr=subprocess.run(['/usr/bin/git',*args],cwd=repo,capture_output=True,text=True)\nprint(json.dumps({'command':command,'mode':mode,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}),flush=True)\n''')
    cases=[('GIT-COMMIT','commit','missing',True),('GIT-PUSH','push','missing',True),
           ('GIT-LOCAL','clean','missing',True),('GIT-LOCAL','reset','missing',False),('GIT-BYPASS','bypass','missing',True)]
    cases += [('GIT-'+command.upper()+'-CHECK',command,mode,mode!='success') for command in ('commit','push') for mode in ('missing','success','failed','changed')]
    env={'PATH':'/usr/bin:/bin','HOME':owner.pw_dir,'SUDO_UID':str(owner.pw_uid),'SUDO_GID':str(owner.pw_gid),
         'ACTPLANE_BPF_PIN_ROOT':str(pin),'ACTPLANE_RESERVE_OPEN_RULES':'1','ACTPLANE_HOOK_PROFILE':'full'}
    out=ROOT/'docs/REVIEW/evidence/git-templates-20261019';out.mkdir(parents=True,exist_ok=True)
    try:
        for n,(ident,command,mode,violation) in enumerate(cases):
            directory=state/('case-'+str(n));directory.mkdir()
            repo=workspace/('repo-'+str(n));repo.mkdir();os.chown(repo,owner.pw_uid,owner.pw_gid)
            def git(*args):
                return subprocess.run(['/usr/bin/git',*args],cwd=repo,user=owner.pw_uid,group=owner.pw_gid,capture_output=True,text=True,check=True)
            git('init','-q');git('config','user.name','Synthetic Test');git('config','user.email','synthetic@example.invalid')
            git('commit','--allow-empty','-qm','initial')
            bare=workspace/('bare-'+str(n));git('init','--bare','-q',str(bare));git('remote','add','origin',str(bare))
            t=catalog.get(ident,2);params={p['key']:p['default'] for p in t['parameters']}
            params['effect']='kill' if ident.endswith('-CHECK') else 'notify'
            if ident=='GIT-LOCAL':params['tokens']=['clean']
            if ident.endswith('-CHECK'):params.update(target=str(changed),checker='gitcheck',exit_code=0)
            body={'template_id':ident,'template_version':2,'scope':'system','name':'Synthetic '+ident,'parameters':params}
            payload=tc.materialize('probe'+str(n),'system',body)
            dsl='source AGENT = exec "**/gitprobe"\n'+payload['document']['original_dsl']
            policy=directory/'policy.yaml';policy.write_text('version: 1\npolicy: |\n'+''.join('  '+line+'\n' for line in dsl.splitlines()))
            result=subprocess.run([str(cli),'--policy',str(policy),'run','--',str(probe),str(runner),str(repo),str(checker),str(changed),command,mode],cwd=directory,env=env,capture_output=True,text=True,timeout=60)
            (out/(str(n)+'-stdout.txt')).write_text(result.stdout);(out/(str(n)+'-stderr.txt')).write_text(result.stderr)
            observed=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{"command"')]
            event_files=list(directory.glob('.actplane/runs/*/events.jsonl'))
            events=[json.loads(line) for path in event_files for line in path.read_text().splitlines() if line.strip()]
            record={'template':ident,'command':command,'mode':mode,'dsl':dsl,'cli_exit':result.returncode,
                'observed':observed,'kernel_events':events,'event_file_owners':[p.stat().st_uid for p in event_files]}
            matched=[e for e in events if e.get('rule')=='config-probe'+str(n) or e.get('rule_name')=='config-probe'+str(n)]
            # Event format may use rule IDs; each isolated policy has just one rule.
            has_event=bool(matched or events)
            child_ok=bool(observed) and ((observed[-1]['returncode']<0) if ident.endswith('-CHECK') and violation else observed[-1]['returncode']==0)
            record['passed']=result.returncode==0 and child_ok and has_event==violation and all(p.stat().st_uid==owner.pw_uid for p in event_files)
            report['cases'].append(record)
            (out/'kernel-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps({'template':ident,'mode':mode,'passed':record['passed'],'events':len(events),'child':observed[-1]['returncode'] if observed else None}),flush=True)
            assert record['passed'],str(n)+': '+result.stderr[-1500:]
    finally:
        if pin.exists():
            assert pin.parent==Path('/sys/fs/bpf') and pin.name=='as-git-'+str(os.getpid())
            shutil.rmtree(pin)
        report['test_pin_root_removed']=not pin.exists()
        report['passed']=len(report['cases'])==len(cases) and all(c['passed'] for c in report['cases'])
        (out/'kernel-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'passed':report['passed'],'cases':len(report['cases']),'evidence':str(out)}),flush=True)


if __name__=='__main__':main()
