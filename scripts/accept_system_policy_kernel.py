#!/usr/bin/env python3
"""Synthetic, isolated kernel acceptance. Creates its own processes and pins."""
import hashlib,json,os,platform,shutil,subprocess,tempfile,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    if os.getuid()!=0:raise SystemExit('Isolated kernel acceptance requires root')
    root=Path(tempfile.mkdtemp(prefix='asp-kernel-'));root.chmod(0o755)
    binary=ROOT/'actplane/target/release/actplane';pin=Path('/sys/fs/bpf')/('asp-kernel-'+uuid.uuid4().hex)
    env={**os.environ,'ACTPLANE_BPF_PIN_ROOT':str(pin),'ACTPLANE_RESERVE_PATH_SUFFIX':'1','ACTPLANE_RESERVE_OPEN_RULES':'1','ACTPLANE_RESERVE_FILE_FLOW':'1','SUDO_UID':'65534','SUDO_GID':'65534'}
    deep=root
    for i in range(10):deep=deep/('level-'+str(i)+'-'+'a'*35)
    deep.mkdir(parents=True)
    names=['.env','production.env','.env.local','production.ENV','public.txt','key.'+'a'*62]
    paths=[]
    for directory in (root,deep):
        for name in names:
            p=directory/name;p.write_text('synthetic-canary\n');paths.append(p)
    (deep/'alias.txt').symlink_to(deep/'production.env')
    (deep/'alias.env').symlink_to(deep/'public.txt')
    paths.extend([deep/'alias.txt',deep/'alias.env'])
    report={'schema':'agentscope.execution-capabilities.v1','binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'kernel_release':platform.release(),'root':str(root),'cases':[]}
    def run(name,clauses,code,sources=''):
        home=root/('case-'+name);home.mkdir();home.chmod(0o755)
        dsl='source AGENT = exec "**/python3"\n'+sources+'\nrule '+name+':\n'+clauses+'\n because "Synthetic kernel acceptance"\n'
        policy=home/'policy.yaml';policy.write_text('version: 1\npolicy: |\n'+''.join('  '+l+'\n' for l in dsl.splitlines()))
        result=subprocess.run([str(binary),'--policy',str(policy),'run','/usr/bin/python3','-c',code],cwd=home,env=env,capture_output=True,text=True,timeout=100)
        (home/'stdout').write_text(result.stdout);(home/'stderr').write_text(result.stderr)
        events=[]
        for file in home.glob('.actplane/**/events.jsonl'):
            for line in file.read_text().splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
        # Runs may write the same event stream at two feedback locations.
        events=list({json.dumps(e,sort_keys=True):e for e in events}.values())
        case={'name':name,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'events':events,'dsl':dsl}
        report['cases'].append(case)
        return case
    def reader(files):
        return 'import os,json\nresults=[]\nfor p in '+repr([str(p) for p in files])+':\n try:\n  fd=os.open(p,os.O_RDONLY);os.close(fd);results.append([p,True])\n except PermissionError:\n  results.append([p,False])\nprint("RESULT="+json.dumps({"pid":os.getpid(),"reads":results}),flush=True)\n'
    def result(case):
        return json.loads(next(line[7:] for line in case['stdout'].splitlines() if line.startswith('RESULT=')))
    def events(case,effect,pid):
        found=[e for e in case['events'] if e.get('pid')==pid and e.get('effect')==effect]
        assert found,(case['name'],case['returncode'],case['stderr'][-1600:],case['events'])
        return found
    try:
        for effect in ('block','notify'):
            case=run('suffix-'+effect,' '+effect+' open file "**/*.env" if AGENT',reader(paths));value=result(case)
            assert case['returncode']==0
            for path,allowed in value['reads']:
                expected=not str(Path(path).resolve()).endswith('.env') if effect=='block' else True
                assert allowed==expected,(effect,path,allowed)
            found=events(case,effect,value['pid'])
            assert all(e.get('blocked') is (effect=='block') and not e.get('killed') for e in found)
        case=run('suffix-kill',' kill open file "**/*.env" if AGENT','import os,json\nprint("RESULT="+json.dumps({"pid":os.getpid()}),flush=True)\nopen('+repr(str(deep/'production.env'))+').read()\nprint("UNEXPECTED_COMPLETION")')
        assert case['returncode'] in (137,-9),case
        assert 'UNEXPECTED_COMPLETION' not in case['stdout']
        assert any(e.get('killed') for e in events(case,'kill',result(case)['pid']))
        case=run('filename',' block open file "**/.env" if AGENT',reader([root/'.env',root/'production.env',deep/'.env',deep/'production.env']))
        assert [v for p,v in result(case)['reads']]==[False,True,False,True]
        suffix='.'+'a'*62
        case=run('long-suffix',' block open file "**/*'+suffix+'" if AGENT',reader([deep/('key'+suffix),deep/'public.txt']))
        assert [v for p,v in result(case)['reads']]==[False,True]
        mutations=deep/'mutations';mutations.mkdir();os.chown(mutations,65534,65534)
        for name in ('production.env','production.env.local'):
            path=mutations/name;path.write_text('synthetic');os.chown(path,65534,65534)
        code='import os,json\nr=[]\nfor p in '+repr([str(mutations/'production.env'),str(mutations/'production.env.local')])+':\n for op in ("write","unlink"):\n  try:\n   if op=="write":\n    fd=os.open(p,os.O_WRONLY);os.write(fd,b"safe");os.close(fd)\n   else:os.unlink(p)\n   r.append([op,True])\n  except PermissionError:r.append([op,False])\nprint("RESULT="+json.dumps({"pid":os.getpid(),"mutations":r}),flush=True)'
        case=run('suffix-mutations',' block write file "**/*.env" if AGENT\n block unlink file "**/*.env" if AGENT',code)
        assert [v for op,v in result(case)['mutations']]==[False,False,True,True]
        assert all(e.get('blocked') for e in events(case,'block',result(case)['pid']))
        directory=root/'directory';directory.mkdir();(directory/'plain').write_text('synthetic')
        case=run('directory',' block open file '+json.dumps(str(directory))+' if AGENT\n block open file '+json.dumps(str(directory)+'/**')+' if AGENT',reader([directory,directory/'plain',root/'public.txt']))
        assert [v for p,v in result(case)['reads']]==[False,False,True]
        case=run('target-exception',' block open file '+json.dumps(str(root)+'/**')+' if AGENT unless target "**/*.env"',reader([root/'.env',deep/'production.env',deep/'.env.local']))
        assert [v for p,v in result(case)['reads']]==[True,True,False]
        code='import os,json,subprocess\nopen('+repr(str(deep/'production.env'))+').read()\ntry:\n subprocess.run(["/usr/bin/true"],check=True);print("UNEXPECTED_EXEC")\nexcept PermissionError:\n print("FLOW_BLOCKED",flush=True)'
        executable=Path('/usr/bin/true').resolve().name
        case=run('source-propagation',' block exec '+json.dumps(executable)+' if AGENT and SECRET',code,'source SECRET = file "**/*.env"')
        assert case['returncode']==0 and 'FLOW_BLOCKED' in case['stdout'] and any(e.get('blocked') for e in case['events']),case
        features=subprocess.run(['/usr/sbin/bpftool','-j','map','lookup','pinned',str(pin/'maps/engine_features'),'key','hex','00','00','00','00'],capture_output=True,text=True,check=True)
        report.update(file_suffix=True,max_suffix_bytes=63,runtime_verified=True,loaded_features=json.loads(features.stdout))
        (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'passed':True,'cases':len(report['cases']),'report':str(root/'report.json'),'binary_sha256':report['binary_sha256']}))
    except Exception:
        report['runtime_verified']=False
        (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'passed':False,'report':str(root/'report.json')}))
        raise
    finally:
        if pin.parent==Path('/sys/fs/bpf') and pin.name.startswith('asp-kernel-') and pin.exists():shutil.rmtree(pin)

if __name__=='__main__':main()
