"""Collect immutable source evidence and frozen-artifact checks, never run agents.

Requires pre-fetched public repositories and paper hashes in --source-root.
Does not call models, modify application state, load BPF or read private chats.
"""
import argparse,ast,hashlib,json,re,subprocess
from collections import Counter
from pathlib import Path
import yaml

REPOS={
 'actplane-master':('eunomia-bpf/ActPlane','404542899a2153af0952cbf0dc52aeab0b7c5034','MIT; BPF per-file GPL-2.0 OR BSD-3-Clause'),
 'actplane-artifact':('eunomia-bpf/ActPlane','63db86945c9b8618a46aa68c8de214bc4b8343d9','MIT; benchmark assets retain their own provenance'),
 'progent':('sunblaze-ucb/progent','5be7b63fa96f70bc19b72fbcee81f1c0bcc1a565','MIT'),
 'fides':('microsoft/fides','669c046c4adbc56ee49c9672fdd30c54937ea062','MIT'),
 'camel':('google-research/camel-prompt-injection','f083b6b396399d3b3c7f2ddaf613a5945eaf32d8','Apache-2.0'),
}
FILES={
 'actplane-master':['LICENSE','docs/rule-language.md','test/e2e_cases.yaml','script/e2e_examples.sh','docs/design/arch_plan.md','crates/actplane-runtime/src/config.rs','crates/actplane-runtime/src/runtime.rs','crates/actplane-runtime/src/mcp.rs','crates/actplane-runtime/src/feedback.rs','crates/actplane-ifc-compiler/src/dsl/lower.rs','bpf/capability.bpf.h','bpf/taint_engine.bpf.h','bpf/src/capability.rs','bpf/src/lib.rs'],
 'actplane-artifact':['docs/ARTIFACT.md','docs/artifact/verify_results.py','docs/artifact/rq4_octobench_ledger.json','docs/artifact/rq4_octobench_summary.json','docs/artifact/rq5_openagentsafety_ledger.json','docs/artifact/rq5_openagentsafety_summary.json','docs/OpenAgentSafety/scripts/generate_remaining_description_policies.py','docs/OpenAgentSafety/data/remaining_attempt0_description_manifest.json','docs/OpenAgentSafety/README.md','docs/OctoBench/README.md','docs/OctoBench/run_cases.py','docs/OctoBench/data/selected_cases_21.jsonl','docs/OctoBench/data/policy_manifest.jsonl','docs/rq1-expressiveness/README.md','docs/corpus-test/sample_manifest.json'],
 'progent':['LICENSE','secagent/tool.py','secagent/policy_analysis.py','secagent/policy_type_check.py','secagent/progent_proxy.py'],
 'fides':['LICENSE','README.md','Tutorial.ipynb'],
 'camel':['LICENSE','README.md','src/camel/security_policy.py','src/camel/quarantined_llm.py','src/camel/pipeline_elements/privileged_llm.py','src/camel/interpreter/interpreter.py'],
}
LOCAL=['UPSTREAM.md','backend/agentscope_app/history/agent_context.py','backend/agentscope_app/history/agent_scene.py','backend/agentscope_app/history/intent.py','backend/agentscope_app/instances/dsl_policy.py','backend/agentscope_app/instances/dsl_api.py','backend/agentscope_app/instances/approval_views.py','backend/agentscope_app/instances/sessions.py','backend/broker/instance_runtime.py','backend/agentscope_app/managed/controller.py','backend/agentscope_app/managed/worker.py','frontend/src/PolicyApprovals.jsx','docs/acceptance/20261011-policy-source-semantics-dsh/acceptance.json']
def sha(data):return hashlib.sha256(data).hexdigest()
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
def write(out,name,value):
    (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def file_record(base,repo,path,commit,url):
    raw=(base/path).read_bytes();text=raw.decode('utf-8');record=dict(repo=repo,path=path,commit=commit,sha256=sha(raw),lines=len(text.splitlines()),url=url)
    if path.endswith('.py'):
        tree=ast.parse(text);record['symbols']=[dict(name=n.name,line=n.lineno,end=n.end_lineno) for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
    else:
        record['symbols']=[dict(name=line.strip()[:130],line=i) for i,line in enumerate(text.splitlines(),1) if re.match(r'(?:pub )?(?:async )?fn |\s*(?:pub )?fn |### E\d|static.*cap_|\s*fn ',line)]
    return record
def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,required=True);args=p.parse_args();root=args.source_root.resolve();out=Path(__file__).resolve().parent;local=out.parents[2]
    repos=[];records=[]
    for name,(remote,commit,license_text) in REPOS.items():
        base=root/name;assert git(base,'rev-parse','HEAD')==commit
        assert not git(base,'status','--porcelain','--untracked-files=no'),name+' tracked source changed'
        repos.append(dict(id=name,repository='https://github.com/'+remote,commit=commit,license=license_text))
        for path in FILES[name]:
            records.append(file_record(base,name,path,commit,f'https://github.com/{remote}/blob/{commit}/{path}'))
    audited='fc4e9d5368fecc713830738a7ad5896dcfd00fd8'
    for path in LOCAL:
        blob=subprocess.check_output(['git','-C',str(local),'show',audited+':'+path]);assert blob==(local/path).read_bytes(),'Audited source drift '+path
        record=file_record(local,'agentscope',path,audited,None)
        record['availability']='local_git_only_not_remote_publication'
        records.append(record)
    papers=json.loads((root/'papers.json').read_text())
    for row in papers:assert sha((root/(row['name']+'.html')).read_bytes())==row['sha256']
    write(out,'source-lock.json',dict(date='2026-10-12',repositories=repos,papers=papers,agentscope_commit=audited,agentscope_commit_published=False,agentscope_vendored_base='4c36aa54da2daf2b64de8782a38f77d5b76ec75a',raw_backup_commit='cceaee6be878eeff4b42caf9a069d535699ecf69'))
    write(out,'source-evidence.json',records)
    master=root/'actplane-master';artifact=root/'actplane-artifact'
    doc=(master/'docs/rule-language.md').read_text();examples=re.findall(r'^### (E\d+) — (.+)$',doc,re.M)
    tests=yaml.safe_load((master/'test/e2e_cases.yaml').read_text())['cases'];assert len(examples)==13 and len(tests)==12
    write(out,'example-source-index.json',dict(document_examples=[dict(id=i,title=t) for i,t in examples],test_cases=[dict(name=t['name'],expect=t['expect'],policy_sha256=sha(t['policy'].encode()),trigger_sha256=sha(t['trigger'].encode())) for t in tests],runtime_executed=False))
    rq4=json.loads((artifact/'docs/artifact/rq4_octobench_ledger.json').read_text());rq5=json.loads((artifact/'docs/artifact/rq5_openagentsafety_ledger.json').read_text());manifest=json.loads((artifact/'docs/OpenAgentSafety/data/remaining_attempt0_description_manifest.json').read_text())
    ast_tree=ast.parse((artifact/'docs/OpenAgentSafety/scripts/generate_remaining_description_policies.py').read_text())
    imports=[n.module for n in ast.walk(ast_tree) if isinstance(n,ast.ImportFrom)]+[a.name for n in ast.walk(ast_tree) if isinstance(n,ast.Import) for a in n.names]
    raw_ref='cceaee6be878eeff4b42caf9a069d535699ecf69';raw_paths=git(master,'ls-tree','-r','--name-only',raw_ref,'docs/OpenAgentSafety/scripts','docs/OctoBench').splitlines()
    raw_code=[x for x in raw_paths if x.endswith('.py')]
    write(out,'generation-provenance.json',dict(
      rq4=dict(task_count=len(rq4['rows']),rule_count=rq4['actplane_feedback_rule_count'],per_task_reward_available=sum(bool(x['per_task_reward_available']) for x in rq4['rows']),case_ids=[x['case_id'] for x in rq4['rows']],claim_runtime_deltas=110,delta_trace_reproduced=False),
      rq5=dict(task_count=len(rq5['rows']),policy_groups=dict(Counter(x['policy_group'] for x in rq5['rows'])),description_manifest_rows=len(manifest['cases']),description_manifest_method=manifest['method'],noops=sum(bool(x['is_noop']) for x in rq5['rows']),per_task_outcome_available=sum(bool(x['per_task_outcome_available']) for x in rq5['rows']),generator_imports=imports,generator_kind='deterministic_keyword_and_path_rules',llm_generation_reproduced=False),
      raw_backup=dict(commit=raw_ref,searched_code_paths=raw_code,full_raw_trajectories_read=False),status='paper_to_generator_provenance_gap_not_resolved'))
    result=subprocess.run(['/opt/agentscope/.venv/bin/python','docs/artifact/verify_results.py','all'],cwd=artifact,text=True,capture_output=True)
    (out/'upstream-artifact-check.txt').write_text(result.stdout+result.stderr);assert result.returncode==0
    # Record static checks separately from any native/model/kernel acceptance.
    write(out,'artifact-check.json',dict(command='python docs/artifact/verify_results.py all',repository='actplane-artifact',returncode=result.returncode,stdout_sha256=sha(result.stdout.encode()),kind='frozen_summary_and_inventory_validation',agents_run=False,bpf_loaded=False,models_called=False))
    print(json.dumps(dict(source_files=len(records),repositories=len(repos),papers=len(papers),document_examples=len(examples),test_cases=len(tests),artifact_check_passed=True)))
if __name__=='__main__':main()
