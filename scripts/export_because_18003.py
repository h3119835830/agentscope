#!/usr/bin/env python3
"""Publish allowlisted evidence from the shared real DSH acceptance only."""
import json
import time
from pathlib import Path
import accept_because_18003 as main
import deploy_system_policy as deploy
from deploy_because_18003 import scope_summary

a=main.a
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/because-feedback/main18003-evidence'


def export():
    release=Path(deploy.service('api')['WorkingDirectory'])
    assert deploy.service('broker')['WorkingDirectory']==str(release)
    deployment=json.loads((OUT/'deployment.json').read_text())
    assert str(release)==deployment['release']
    assert scope_summary(deploy.scopes())==deployment['policy_scopes']
    assert deploy.other_ports()==deployment['other_ports']
    proof=dict(schema='SharedBecauseFeedbackAcceptance/1',api=a.URL,release=str(release),
               controlled_fault='Agent-executed non-mutating O_WRONLY open; further work autonomous',
               natural_attack_rate_experiment=False,extra_solution_prompt=False,cases=[])
    for t in a.tasks():
        ident=t['task_id'];v=json.loads(a.report_path(ident).read_text());records=a.rows(ident)
        assert v['safety_recovery_passed']
        item={k:v[k] for k in ('case','task_id','workspace','context_hash','scenario_commit','asset_layout_mapping_hash',
              'policy_hash','version','domain_id','process_epoch','session_id','engine','recovery_bundle_hash',
              'protected_count','safety_recovery_passed','functional','kernel_event_ids','feedback_admission_ids',
              'subsequent_tool_ids','kernel_pi_jobs','policy_and_domain_unchanged','changed_assets')}
        item['skill']=json.loads((a.REPORT/('skill-'+ident+'.json')).read_text())
        item['admission_control']=json.loads((a.REPORT/('admission-control-'+ident+'.json')).read_text())
        item['protected_assets']=[dict(path=p,before_sha256=h,after_sha256=a.sha(p),unchanged=a.sha(p)==h) for p,h in v['baseline'].items()]
        item['feedback_chain']=[]
        for r in records:
            if r['kind']!='kernel' or r['id'] not in v['kernel_event_ids']:continue
            payload=r['payload'];event=payload['event'];feedback=payload['feedback']
            assert feedback['because'] in item['skill']['compiled_reasons'], 'Actual feedback must use this Pi Skill candidate reason'
            row=dict(kernel_event_id=r['id'],tool_call_id=payload.get('tool_call_id'),feedback=feedback,
                kernel={k:event.get(k) for k in ('op','target','pid','blocked','killed','effect','process_domain_id','session_root','kernel_call_tag','rule')})
            for kind in ('feedback_offer','feedback_context_admitted','feedback_persisted'):
                row[kind]=[x['id'] for x in records if x['kind']==kind and r['id'] in x['payload'].get('event_ids',[])]
            assert row['feedback_context_admitted']
            item['feedback_chain'].append(row)
        item['native_storage']=json.loads((a.REPORT/('storage-'+ident+'.json')).read_text())
        assert item['native_storage']['canonical_contexts_persisted']
        item['persistence_authority']='independent canonical native-session disk verification; immediate post-hook has no background persistence ACK'
        item['original_oracle']=json.loads((a.REPORT/('oracle-'+ident+'.json')).read_text())
        operations=json.loads((a.REPORT/('operations-'+ident+'.json')).read_text())
        item['independent_operations']=[dict(target=r['target'],operation=r['operation'],classification=r['classification'],
             domain_id=r['domain_id'],pid=r['probe']['pid'],kernel_event_count=len(r['kernel_events'])) for r in operations]
        log=Path(t['workspace'])/'.actplane/events.jsonl';st=log.lstat()
        item['kernel_log_trust']=dict(root_owned=st.st_uid==0,group_or_other_writable=bool(st.st_mode&0o022),
                                      symlink=log.is_symlink(),sha256=a.sha(log))
        assert st.st_uid==0 and not st.st_mode&0o022 and not log.is_symlink()
        proof['cases'].append(item)
        functional=a.REPORT/('functional-'+ident+'.txt')
        if functional.exists():(OUT/functional.name).write_text(functional.read_text())
    runtime=[]
    for name in ('backend/agentscope_app/pi_feedback.py','backend/agentscope_app/pi_rpc.py',
                 'backend/agentscope_app/bootstrap/runner.py','backend/agentscope_app/bootstrap/validation.py',
                 'backend/agentscope_app/scope/pi.py','backend/agentscope_app/managed/feedback.py',
                 'backend/agentscope_app/managed/recovery.py','backend/broker/main.py',
                 'backend/agentscope_app/instances/approval_locations.py','backend/agentscope_app/instances/approval_views.py',
                 'backend/agentscope_app/instances/system_policy_catalog.json',
                 'integrations/pi-policy-tools/skills/policy-feedback/SKILL.md',
                 'integrations/dsh-managed-web/lib/index.js','integrations/dsh-managed-web/lib/feedback-guard.js'):
        assert a.sha(ROOT/name)==a.sha(release/name),name+' release drift'
        runtime.append(dict(path=name,source_sha256=a.sha(ROOT/name),release_sha256=a.sha(release/name)))
    proof.update(runtime_source_hashes=runtime,shared_policies_unchanged=True,other_ports_unchanged=True,
                 private_content_exported=False,generated_at=time.time())
    (OUT/'live-acceptance.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
    print(json.dumps(dict(cases=len(proof['cases']),operations=sum(len(c['independent_operations']) for c in proof['cases']),
                         source_release_matches=len(runtime),shared_policies_unchanged=True)))


if __name__=='__main__':export()
