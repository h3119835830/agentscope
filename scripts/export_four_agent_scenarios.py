#!/usr/bin/env python3
"""Export public tools, kernel effects and independent outcomes, no thinking/keys."""
import hashlib, json, os, shutil
from pathlib import Path
from accept_four_agent_scenarios import ROOT, STATE, LAB, guard

DEST=ROOT/'docs/research/four-agent-scenarios-20261013'
SELECTED={'dsh': 'v5','mini':'v4'}


def safe_write(path, data, key):
    raw=data.encode() if isinstance(data,str) else data
    assert key.encode() not in raw, 'Credential found in export candidate'
    assert b'"reasoning_content"' not in raw and b'"type": "thinking"' not in raw, 'Private model block found'
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);path.chmod(0o644)


def main():
    assert os.geteuid()==0
    import yaml
    key=yaml.safe_load(Path('/var/lib/agentscope-scope-demo/dsh-home/.credentials.yaml').read_text())['refs']['DEEPSEEK_API_KEY']
    assert isinstance(key,str)
    guard('export')
    aggregate={'schema':'agentscope.four-agent-experiments.v1','cases':[],
       'method':'Pinned scenario adaptations and selected attack-entry execution; qualitative scaffold comparison, not attack success-rate or official benchmark score.',
       'conditions':{'model':'deepseek-v4-flash','dsh_protocol':'Messages, reasoningEffort=high','mini_protocol':'Chat Completions, temperature=0',
                     'dsh_first_three_task_python':'3.14','dsh_repair_and_mini_task_python':'3.11.17'},'failures_preserved':[]}
    for agent,version in SELECTED.items():
        report=json.loads((STATE/f'report-{agent}-{version}.json').read_text())
        for item in report['cases']:
            run=Path(item['run']);case=item['case'];target=DEST/agent/case
            assert run.parent==LAB
            item['harness_child_sha256']=hashlib.sha256((run/'child.py').read_bytes()).hexdigest()
            item['task_sha256']=hashlib.sha256((run/'task.txt').read_bytes()).hexdigest()
            item['policy_sha256']=hashlib.sha256((run/'policy.yaml').read_bytes()).hexdigest()
            assert item['protected_intact'] and not item['secret_received']
            kernels=json.loads((run/'kernel-events.json').read_text())
            assert any(e.get('blocked') and e.get('effect')=='block' for e in kernels)
            if agent=='mini':
                receipts=run/'home/model-feedback-receipts.jsonl'
                assert receipts.exists() and all(json.loads(l)['response_received'] for l in receipts.read_text().splitlines())
                item['feedback_model_response_received']=True
                safe_write(target/'model-feedback-receipts.jsonl',receipts.read_bytes(),key)
                safe_write(target/'public-tools.jsonl',(run/'home/public-mini.jsonl').read_bytes(),key)
            else:
                public=json.loads((run/'public-session.json').read_text())
                contexts=[i for i,e in enumerate(public) if e.get('type')=='user/message' and '[ActPlane 内核反馈]' in e.get('text','') and (e.get('source') or {}).get('kind')=='context']
                assert contexts and any(e.get('type')=='assistant/message' for e in public[contexts[0]+1:])
                item['feedback_followed_by_response']=True
                safe_write(target/'public-session.json',(run/'public-session.json').read_bytes(),key)
            for name in ('task.txt','policy.yaml','child.py','kernel-events.json','protected-before.json','process-identities.json','adaptation.json'):
                if (run/name).exists():safe_write(target/name,(run/name).read_bytes(),key)
            safe_write(target/'result.json',json.dumps(item,ensure_ascii=False,indent=2),key)
            aggregate['cases'].append(item)
    # Every completed attempt is indexed, including startup/adapter failures.
    for p in sorted(LAB.glob('*/result.json')):
        item=json.loads(p.read_text())
        if item['run'] not in [c['run'] for c in aggregate['cases']]:
            aggregate['failures_preserved'].append({k:item.get(k) for k in ('run','case','returncode','kernel_denials','legal_completed','feedback_delivered','passed')})
    controls=[]
    for name in ('raw-backup-controls2','raw-ssh-controls3','raw-flow-controls2','raw-repair-controls2','probe-flow-control3'):
        run=LAB/name;item=json.loads((run/'result.json').read_text());controls.append(item)
        for file in ('result.json','kernel-events.json','task.txt','policy.yaml'):
            safe_write(DEST/'controls'/name/file,(run/file).read_bytes(),key)
    aggregate['controls']=controls
    aggregate['passed_runs']=sum(c['passed'] for c in aggregate['cases'])
    aggregate['total_runs']=len(aggregate['cases'])
    assert aggregate['total_runs']==8
    assert next(c for c in controls if c['case']=='ssh')['secret_received']
    assert next(c for c in controls if c['case']=='flow')['secret_received']
    assert not next(c for c in controls if c['case']=='backup')['protected_intact']
    assert not next(c for c in controls if c['case']=='repair')['protected_intact']
    baseline=json.loads((LAB/'oracle-baseline-repair-v3/baseline-result.json').read_text())
    assert '2 failed, 50 passed' in baseline['functional']['output']
    safe_write(DEST/'swe-baseline.json',json.dumps(baseline,ensure_ascii=False,indent=2),key)
    safe_write(DEST/'source-manifest.json',(STATE/'source-manifest.json').read_bytes(),key)
    safe_write(DEST/'flask-LICENSE.rst',(STATE/'research/flask/LICENSE.rst').read_bytes(),key)
    proofs=[]
    for p in sorted(STATE.glob('production-*.json')):
        d=json.loads(p.read_text())
        if p.name=='production-before.json':
            proofs.append({'file':p.name,'agents':d['authority']['agents'],'api':d['api'],'broker':d['broker']})
        elif 'checks' in d:
            assert all(d['checks'].values())
            proofs.append({'file':p.name,'checks':d['checks'],'agents':d['authority']['agents'],'api':d['api'],'broker':d['broker'],'protection':d.get('protection')})
    safe_write(DEST/'production-safety.json',json.dumps(proofs,ensure_ascii=False,indent=2),key)
    aggregate['production_unchanged']=all(all(p.get('checks',{}).values()) for p in proofs)
    aggregate['remaining_test_credentials']=len(list(LAB.glob('*/home/.dsh/.credentials.yaml')))
    aggregate['remaining_bpf_pins']=[p.name for p in Path('/sys/fs/bpf').glob('as4-*')]
    active=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            args=(proc/'cmdline').read_bytes().decode().split('\0');comm=(proc/'comm').read_text().strip()
            if comm in ('node','python','python3','python3.11','python3.14') and any(a.startswith('/a4/') or a=='/lab-child.py' for a in args):active.append(int(proc.name))
        except (OSError,UnicodeError):pass
    aggregate['active_test_processes']=active
    assert aggregate['remaining_test_credentials']==0 and aggregate['remaining_bpf_pins']==[] and not active
    safe_write(DEST/'summary.json',json.dumps(aggregate,ensure_ascii=False,indent=2),key)
    hashes={str(p.relative_to(DEST)):hashlib.sha256(p.read_bytes()).hexdigest() for p in DEST.rglob('*') if p.is_file() and p.name!='manifest.json'}
    safe_write(DEST/'manifest.json',json.dumps(hashes,ensure_ascii=False,indent=2),key)
    print(json.dumps({'export':str(DEST),'files':len(hashes),'passed':aggregate['passed_runs'],'total':aggregate['total_runs'],'production_unchanged':aggregate['production_unchanged']}))


if __name__=='__main__':main()
