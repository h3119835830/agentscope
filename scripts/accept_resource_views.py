#!/usr/bin/env python3
"""Synthetic native kernel acceptance, never the product's RQ5 UI workflow.

Unique temporary data and BPF pins only. No service/API/DB access or restart.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import uuid

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'backend'))
from agentscope_app.instances import resource_views as views
from agentscope_app.instances.policy import canonical
from broker.instance_runtime import policy_dsl
from broker.resource_view_mounts import mount_arguments


def probe(root):
    config=json.loads((root/'fixture.json').read_text())
    args,fds=mount_arguments(config['resources'],config['plan'],probe=True)
    code='''import json,os
result=[]
for item in json.loads(os.environ['PROBES']):
 try:
  fd=os.open(item['path'],os.O_WRONLY|os.O_APPEND);os.write(fd,b'probe\\n');os.close(fd)
  allowed=True;number=None
 except OSError as e:allowed=False;number=e.errno
 result.append({**item,'allowed':allowed,'errno':number})
print('RESULT='+json.dumps({'pid':os.getpid(),'uid':os.getuid(),'results':result}),flush=True)
'''
    try:
        result=subprocess.run(['/usr/bin/bwrap','--unshare-user','--unshare-pid','--die-with-parent','--cap-drop','ALL',
            '--ro-bind','/usr','/usr','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev',
            *args,'--','/usr/bin/python3','-c',code],pass_fds=tuple(fds),capture_output=True,text=True,timeout=20,
            env={'PROBES':json.dumps(config['probes'])})
    finally:
        for fd in fds:os.close(fd)
    print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr)
    return result.returncode


def main():
    if len(sys.argv)==3 and sys.argv[1]=='--probe':return probe(Path(sys.argv[2]))
    if os.geteuid()!=0:raise SystemExit('Explicit root invocation required for isolated BPF acceptance')
    owner=pwd.getpwnam('happy');root=Path(tempfile.mkdtemp(prefix='as-resource-views-',dir='/var/tmp'));root.chmod(0o755)
    resource=root/'resource';project=resource/('scene-'+'x'*65)/'workspace/project'
    source=project/'src';output=project/'acceptance-artifacts';tests=project/'tests'
    for p in (source,output,tests):p.mkdir(parents=True)
    files={name:p/'probe.txt' for name,p in [('root',resource),('parent',project),('source',source),('output',output),('test',tests)]}
    for p in files.values():p.write_text('synthetic\n')
    for p in [root,*root.rglob('*')]:os.chown(p,owner.pw_uid,owner.pw_gid)
    resources=[str(resource)];plan=views.freeze(resources,[str(project),str(source),str(output)])
    rule=lambda p,e:{'action':'write','target':str(p),'effect':e,'text':''}
    policy=canonical({'network':'disabled','rules':[rule(source,'allow'),rule(output,'allow'),rule(tests,'deny')],
                      'resource_views':plan},resources)
    probes=[{'name':name,'path':views.translate(str(p),resources,plan),'expected':name in ('source','output')} for name,p in files.items()]
    for name in ('source','output','test'):
        probes.append({'name':'original-'+name,'path':'/w/0/'+str(files[name].relative_to(resource)),'expected':name in ('source','output')})
    (root/'fixture.json').write_text(json.dumps({'resources':resources,'plan':plan,'probes':probes}))
    document=policy_dsl(resources,policy)
    (root/'policy.yaml').write_text('version: 1\npolicy: |\n'+''.join('  '+line+'\n' for line in document.splitlines()))
    binary=REPO/'actplane/target/release/actplane'
    pin=Path('/sys/fs/bpf')/('as-resource-views-'+uuid.uuid4().hex)
    assert not pin.exists() and pin.parent==Path('/sys/fs/bpf')
    environment={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':owner.pw_dir,'SUDO_UID':str(owner.pw_uid),'SUDO_GID':str(owner.pw_gid),
                 'ACTPLANE_BPF_PIN_ROOT':str(pin),'ACTPLANE_RESERVE_OPEN_RULES':'1','ACTPLANE_RESERVE_FILE_FLOW':'1','ACTPLANE_HOOK_PROFILE':'full'}
    baseline=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--probe',str(root)],user=owner.pw_uid,group=owner.pw_gid,
                            capture_output=True,text=True,timeout=25)
    value=lambda text:json.loads(next(line[7:] for line in text.splitlines() if line.startswith('RESULT=')))
    assert baseline.returncode==0,baseline.stderr
    assert all(r['allowed'] for r in value(baseline.stdout)['results']),baseline.stdout
    for p in files.values():p.write_text('synthetic\n')
    before={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in files.items()}
    report={'scope':'isolated native kernel; not product RQ5 acceptance','root':str(root),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
            'baseline':value(baseline.stdout),'policy':policy,'passed':False}
    try:
        result=subprocess.run([str(binary),'--policy',str(root/'policy.yaml'),'run','/usr/bin/python3',str(Path(__file__).resolve()),'--probe',str(root)],
                              cwd=root,env=environment,capture_output=True,text=True,timeout=100)
        report.update(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
        assert result.returncode==0,result.stderr
        outcome=value(result.stdout);report['outcome']=outcome
        assert all(r['allowed']==r['expected'] for r in outcome['results']),outcome
        events=[]
        for file in root.glob('.actplane/**/events.jsonl'):
            for line in file.read_text().splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
        blocked=[e for e in events if e.get('blocked') and e.get('op')=='write']
        report['blocked_events']=blocked
        for name in ('root','parent','test'):
            target=views.translate(str(files[name]),resources,plan)
            assert any(e.get('target')==target for e in blocked),(name,blocked)
            assert hashlib.sha256(files[name].read_bytes()).hexdigest()==before[name]
        report['protected_integrity']={name:{'before':before[name],'after':hashlib.sha256(files[name].read_bytes()).hexdigest()}
                                       for name in ('root','parent','test')}
        report['passed']=True
    finally:
        (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        # Only these uniquely-created pins; never shared engines or user data.
        if pin.parent==Path('/sys/fs/bpf') and pin.name.startswith('as-resource-views-') and pin.exists():shutil.rmtree(pin)
        print(json.dumps({'passed':report['passed'],'report':str(root/'report.json')}))
    return 0


if __name__=='__main__':raise SystemExit(main())
