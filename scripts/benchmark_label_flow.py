"""Bounded synthetic audit overhead sample, not a production capacity claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def workload(folder,count):
    folder=Path(folder)
    data=(folder/'secret.txt').read_bytes()
    start=time.perf_counter()
    for index in range(count):
        path=folder/f'derived-{index}'
        path.write_bytes(data)
        path.read_bytes()
    print(json.dumps({'workload_seconds':time.perf_counter()-start,'files':count}),flush=True)
    time.sleep(.4)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',required=True,type=Path)
    parser.add_argument('--count',type=int,default=2000)
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    assert os.geteuid()==0 and 1<=args.count<=10000 and 1<=args.repeats<=5
    folder=Path(tempfile.mkdtemp(prefix='lfperf-',dir='/var/tmp'))
    engines={'baseline':args.baseline.resolve(),'transitions':ROOT/'actplane/target/release/actplane'}
    report={'kind':'bounded-synthetic-not-production-benchmark','files_per_sample':args.count,
            'binaries':{k:{'path':str(v),'sha256':hashlib.sha256(v.read_bytes()).hexdigest()} for k,v in engines.items()},
            'samples':[],'evidence_directory':str(folder)}
    for repeat in range(args.repeats):
        for name in ('native','baseline','transitions'):
            directory=folder/f'{repeat}-{name}';directory.mkdir()
            (directory/'secret.txt').write_bytes(b'SYNTHETIC_BENCHMARK_DATA'*6)
            command=[sys.executable,__file__,'worker',str(directory),str(args.count)]
            pin=Path('/sys/fs/bpf')/(folder.name+'-'+str(repeat)+'-'+name)
            env={**os.environ,'ACTPLANE_BPF_PIN_ROOT':str(pin),'ACTPLANE_RESERVE_FILE_FLOW':'1'}
            if name!='native':
                policy=f'source AGENT = exec "**/python3"\nsource SECRET = file "{directory}/secret.txt"\nrule protect:\n block connect endpoint "127.0.0.1" if AGENT and SECRET\n'
                command=[str(engines[name]),'--rule',policy,'run','--run-as-root']+command
            result=subprocess.run(command,cwd=directory,env=env,capture_output=True,text=True,timeout=120)
            (directory/'collector.log').write_text(result.stderr)
            assert result.returncode==0,result.stderr[-1200:]
            metric=next(json.loads(line) for line in result.stdout.splitlines() if line.startswith('{"workload_seconds"'))
            events=[json.loads(line) for path in directory.rglob('events.jsonl') for line in path.read_text().splitlines() if line]
            transitions=[e for e in events if e.get('event')=='label_transition']
            writes=[e for e in transitions if e.get('operation')=='process_to_file' and 'SECRET' in e.get('label_names',[])
                    and e.get('target','').startswith(str(directory/'derived-'))]
            lost=max((int(e['lost_total']) for e in transitions),default=0)
            sample={'mode':name,'repeat':repeat,**metric,'transitions':len(transitions),'secret_file_witnesses':len(writes),
                    'reported_lost':lost,'audit_bytes':sum(p.stat().st_size for p in directory.rglob('events.jsonl'))}
            if name=='transitions':
                assert len(writes)==args.count and lost==0,sample
            report['samples'].append(sample)
            (folder/'acceptance.json').write_text(json.dumps(report,indent=2))
            # This root was generated for exactly this exited child and never
            # aliases a deployed pin directory. No recursive broad deletion.
            if pin.exists():
                assert pin.parent==Path('/sys/fs/bpf') and pin.name.startswith(folder.name+'-') and not pin.is_symlink()
                for path in sorted(pin.rglob('*'),key=lambda p:len(p.parts),reverse=True):
                    if path.is_dir() and not path.is_symlink():path.rmdir()
                    else:path.unlink()
                pin.rmdir()
    report['median_seconds']={name:statistics.median(s['workload_seconds'] for s in report['samples'] if s['mode']==name) for name in ('native','baseline','transitions')}
    report['transition_vs_baseline_ratio']=report['median_seconds']['transitions']/report['median_seconds']['baseline']
    report['passed']=True
    (folder/'acceptance.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='worker':workload(sys.argv[2],int(sys.argv[3]))
    else:main()
