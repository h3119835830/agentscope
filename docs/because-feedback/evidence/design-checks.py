"""Read-only source checks and isolated design validation; never loads policy."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
DOCS = ROOT.parents[2]
PYTHON = sys.executable

LINUX_CHECKS = r'''
import ast, hashlib, importlib.util, json, os, pathlib, re, shutil, subprocess, sys, tempfile
root=pathlib.Path('/opt/agentscope-system-policy-20261011-161846')
fixtures=root/'backend/agentscope_app/bootstrap/fixtures/rq5'
payload=json.load(sys.stdin)
report={'scope':'source_reproduction_and_offline_design_only','live_enforcement_executed':False,'agent_recovery_executed':False,'runtime_root':str(root)}
sources=['backend/agentscope_app/managed/feedback.py','backend/agentscope_app/managed/controller.py','backend/agentscope_app/managed/worker.py','backend/agentscope_app/bootstrap/scene.py','backend/agentscope_app/bootstrap/evaluation.py','integrations/dsh-managed-web/lib/index.js','integrations/dsh-managed-web/lib/public-session.js']
report['source_files']={f:{'sha256':hashlib.sha256((root/f).read_bytes()).hexdigest(),'lines':len((root/f).read_text().splitlines())} for f in sources}
manifest=json.loads((fixtures/'manifest.json').read_text())
checked=[]
for case,entries in manifest['cases'].items():
 for item in entries:
  digest=hashlib.sha256((fixtures/case/item['path']).read_bytes()).hexdigest()
  assert digest==item['sha256'],(case,item['path'])
  checked.append((case,item['path']))
report['fixture_manifest']={'commit':manifest['commit'],'files_verified':len(checked),'passed':True,'oracle_not_used_as_agent_input':True}
spec=importlib.util.spec_from_file_location('isolated_feedback',root/'backend/agentscope_app/managed/feedback.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
raw={'op':'write','target':'/tmp/as-because/repo/transaction-verification-service/tests/test_rate_limiter.py','blocked':True,'rule':{'name':'rq5-preserve-tests','reason':'BECAUSE_GUIDANCE_MARKER: fix implementation and preserve tests'}}
formatted=module.operation_feedback(1,raw,{'workspace':'/tmp/as-because/repo','output_dir':'/tmp/as-because/output'})
assert 'BECAUSE_GUIDANCE_MARKER' not in json.dumps(formatted)
report['current_feedback_reproduction']={'because_marker_preserved':False,'observed_reason':formatted['reason'],'observed_alternative':formatted['alternative'],'finding':'existing formatter loses rule-specific because; remediation pending','input_is_synthetic':True}
scene_tree=ast.parse((root/'backend/agentscope_app/bootstrap/scene.py').read_text())
selected=[n for n in scene_tree.body if isinstance(n,ast.FunctionDef) and n.name in ('digest','mapped_asset','declared_constraints')]
namespace={'Path':pathlib.Path,'hashlib':hashlib,'json':json,'CASES':('safety-delete-config','safety-impossible-tests','safety-abusive-apology')}
exec(compile(ast.Module(body=selected,type_ignores=[]),'<extracted-pure-scene-functions>','exec'),namespace)
sample_root='/tmp/as-because/repo'
assets=[]
case='safety-impossible-tests'
for item in manifest['cases'][case]:
 if item['role']=='workspace':
  mapped=namespace['mapped_asset'](case,item['path'].removeprefix('workspace/'))
  assets.append({**item,'relative_path':mapped,'mapped_path':sample_root+'/'+mapped})
constraints=namespace['declared_constraints'](case,pathlib.Path(sample_root),(fixtures/case/'task.md').read_text(),assets)
protected=constraints[0]['targets']
expected=set(protected)
policy=payload['policies']['rq5-tests.dsl']
actual=set(re.findall(r'block (?:write|unlink) file "([^"]+)"',policy))
runner=sample_root+'/transaction-verification-service/run_tests.py'
assert expected.issubset(actual)
assert actual-expected=={runner}
assert sample_root+'/test_validator.py' in expected and sample_root+'/tests_rate_limiter.py' in expected
report['protected_registry']={'targets':sorted(expected),'complete_in_example':True,'separate_platform_candidate':[runner],'directory_permission_not_inferred':True}
with tempfile.TemporaryDirectory(prefix='agentscope-because-design-') as temporary:
 temp=pathlib.Path(temporary)
 temp.chmod(0o755)
 workspace=temp/'mapped-workspace';workspace.mkdir()
 for item in assets:
  dest=workspace/item['relative_path'];dest.parent.mkdir(parents=True,exist_ok=True)
  shutil.copyfile(fixtures/case/item['path'],dest)
 before={a['relative_path']:hashlib.sha256((workspace/a['relative_path']).read_bytes()).hexdigest() for a in assets}
 env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(temp),'PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8'}
 baselines=[]
 task_runtime=pathlib.Path('/var/lib/agentscope-rq5-v1/task-python')
 for label,interpreter in [('system_preflight',sys.executable),('recorded_task_runtime',str(task_runtime/'bin/python'))]:
  baseline=subprocess.run(['/usr/sbin/runuser','-u','agentscope-agent','--',interpreter,'-B','run_tests.py'],cwd=workspace/'transaction-verification-service',env=env,capture_output=True,text=True,timeout=30)
  output=baseline.stdout+'\n'+baseline.stderr
  count=re.findall(r'Ran (\d+) tests?',output)
  final=re.findall(r'^(?:FAILED[^\n]*|OK)$',output,re.M)
  headings=re.findall(r'^(?:ERROR|FAIL):[^\n]*',output,re.M)
  startup=re.findall(r'^(?:ModuleNotFoundError|ImportError|SyntaxError):[^\n]*',output,re.M)
  loaders_only=bool(headings) and all('unittest.loader._FailedTest' in h for h in headings)
  baselines.append({'label':label,'interpreter':interpreter,'execution_user':'agentscope-agent','exit_code':baseline.returncode,'runner_reported_count':int(count[-1]) if count else None,'actual_tests_executed':0 if loaders_only else int(count[-1]) if count else None,'summary':final[-1] if final else 'inspect environment/test startup','failure_headings':headings,'startup_errors':startup,'classification':'environment_precondition_failed' if startup or not count else 'baseline_failure_not_recovery_acceptance' if baseline.returncode else 'baseline_pass_not_recovery_acceptance'})
 after={a['relative_path']:hashlib.sha256((workspace/a['relative_path']).read_bytes()).hexdigest() for a in assets}
 report['environment_preflight']=baselines[0]
 report['mapped_scenario_baseline']={**baselines[-1],'runtime_facts_sha256':hashlib.sha256((task_runtime/'runtime-facts.json').read_bytes()).hexdigest(),'workspace_original_asset_bytes_unchanged':before==after,'source_fixture_unchanged':True}
 compiler=pathlib.Path('/home/happy/.cargo/bin/actplane')
 version=subprocess.run([str(compiler),'--version'],capture_output=True,text=True,timeout=10)
 report['compiler']={'path':str(compiler),'resolved_path':str(compiler.resolve()),'sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'version':version.stdout.strip(),'policy_load_performed':False}
 compiled={}
 for name,text in payload['policies'].items():
  binary=temp/(name+'.bin')
  result=subprocess.run([str(compiler),'--rule',text,'compile','--out',str(binary)],capture_output=True,text=True,timeout=30)
  if result.returncode:raise RuntimeError(name+': '+result.stderr)
  data=binary.read_bytes();compiled[name]=data
  report.setdefault('dsl_compile',{})[name]={'exit_code':result.returncode,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
 alternate=re.sub(r'because "[^"\n]*"','because "Different guidance, unchanged constraints."',payload['policies']['rq5-tests.dsl'])
 binary=temp/'alternate.bin'
 result=subprocess.run([str(compiler),'--rule',alternate,'compile','--out',str(binary)],capture_output=True,text=True,timeout=30)
 assert result.returncode==0,result.stderr
 assert binary.read_bytes()==compiled['rq5-tests.dsl']
 report['because_semantics']={'only_reason_changed':True,'kernel_bytes_identical':True,'passed':True}
report['checks_passed']=True
print(json.dumps(report,ensure_ascii=False))
'''


def main():
    policies = {p.name: p.read_text(encoding='utf-8') for p in ROOT.glob('*.dsl')}
    assert {'rq5-tests.dsl', 'rq5-config.dsl'} <= policies.keys()
    specs = json.loads((ROOT / 'recovery-specs.json').read_text(encoding='utf-8'))
    reasons = {}
    for policy in policies.values():
        for block in re.split(r'(?m)(?=^rule )', policy):
            name = re.search(r'^rule ([^:]+):', block)
            reason = re.search(r'(?m)^\s+because ("[^"\n]*")$', block)
            if name and reason:
                reasons[name.group(1)] = json.loads(reason.group(1))
    for spec in specs['specs']:
        assert any('rule ' + spec['rule_ref'] + ':' in p for p in policies.values())
        assert spec['explanation'] == reasons[spec['rule_ref']]
        assert spec['escalation']['permission_change'] == 'separate_human_approval_required'
        assert spec['allowed_targets'] and spec['steps'] and spec['resume_conditions']
        assert all(p.startswith(specs['workspace_root'] + '/') for p in spec['allowed_targets'])
    result = subprocess.run(
        ['wsl', '-d', 'Ubuntu', '-u', 'root', '--exec', 'python3', '-c', LINUX_CHECKS],
        input=json.dumps({'policies': policies}, ensure_ascii=False).encode('utf-8'),
        capture_output=True, timeout=90,
    )
    if result.returncode:
        raise RuntimeError(result.stdout.decode('utf-8', errors='replace') + result.stderr.decode('utf-8', errors='replace'))
    report = json.loads(result.stdout.decode('utf-8'))
    report['client_date'] = '2026-10-11'
    report['recovery_specs_validated'] = len(specs['specs'])
    output = ROOT / 'design-checks.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    docs = [DOCS / folder / (folder + '-20261011-AgentScope-because-feedback.md') for folder in ('RFC', 'ADR', 'REVIEW', 'BUG')]
    links = 0
    for doc in docs:
        text = doc.read_text(encoding='utf-8')
        assert text.count('```') % 2 == 0, doc.name
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
            if target.startswith(('https://', 'http://', '#')):
                continue
            resolved = (doc.parent / target.split('#')[0]).resolve()
            assert resolved.exists(), (doc.name, target)
            links += 1
    rfc = docs[0].read_text(encoding='utf-8')
    assert set(re.findall(r'\| (T\d\d) \|', rfc)) == {'T' + str(i).zfill(2) for i in range(1, 20)}
    report['document_checks'] = {'files': len(docs), 'local_links_verified': links, 'acceptance_cases': 19, 'passed': True}
    report['design_file_sha256'] = {str(p.relative_to(DOCS)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [*docs, *ROOT.glob('*.dsl'), ROOT / 'recovery-specs.json']}
    report['pending_live_acceptance'] = ['kernel_allow_block', 'native_context_admission', 'agent_compliant_recovery', 'fault_injection', 'abc_comparison']
    report['checks_passed'] = True
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'design_checks_passed': True,
        'fixture_files': report['fixture_manifest']['files_verified'],
        'protected_test_files': len(report['protected_registry']['targets']),
        'policies_compiled': list(report['dsl_compile']),
        'because_only_change_same_kernel_bytes': report['because_semantics']['passed'],
        'baseline': report['mapped_scenario_baseline'],
        'documents': report['document_checks'],
        'live_acceptance': 'not_executed; design_only',
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
