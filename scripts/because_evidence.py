#!/usr/bin/env python3
"""Export allowlisted acceptance evidence; never export native private streams."""
import json
import subprocess
import time
from pathlib import Path
import because_acceptance as a


def export():
    repo=Path(__file__).resolve().parents[1]
    out=repo/'docs/because-feedback/evidence';out.mkdir(parents=True,exist_ok=True)
    proof={'schema':'BecauseFeedbackAcceptance/1',
           'source_head_at_export':subprocess.check_output(['git','-c','safe.directory='+str(repo),'rev-parse','HEAD'],cwd=repo,text=True).strip(),
           'branch':subprocess.check_output(['git','-c','safe.directory='+str(repo),'branch','--show-current'],cwd=repo,text=True).strip(),
           'release':'/opt/agentscope-because-feedback-20261011','api':a.URL,'task_root':'/b',
           'controlled_fault':{'source':'actual Agent tool requests non-mutating O_WRONLY open; subsequent actions autonomous',
                               'natural_attack_rate_experiment':False,'extra_safe_solution_prompt':False},'cases':[]}
    for t in a.tasks():
        v=json.loads(a.report_path(t['task_id']).read_text());records=a.rows(t['task_id'])
        item={k:v[k] for k in ['case','task_id','workspace','context_hash','scenario_commit','asset_layout_mapping_hash',
                              'policy_hash','version','domain_id','process_epoch','session_id','engine','recovery_bundle_hash',
                              'protected_count','safety_recovery_passed','functional','kernel_event_ids','feedback_admission_ids',
                              'subsequent_tool_ids','kernel_pi_jobs','policy_and_domain_unchanged','changed_assets']}
        item['protected_assets']=[{'path':p,'before_sha256':h,'after_sha256':a.sha(p),'unchanged':a.sha(p)==h} for p,h in v['baseline'].items()]
        item['feedback_chain']=[]
        for r in records:
            if r['kind']!='kernel' or r['payload'].get('verification_probe'):continue
            p=r['payload'];e=p['event'];f=p['feedback']
            offers=[{'id':x['id'],'channel':x['payload']['channel']} for x in records if x['kind']=='feedback_offer' and r['id'] in x['payload']['event_ids']]
            admissions=[x['id'] for x in records if x['kind']=='feedback_context_admitted' and r['id'] in x['payload']['event_ids']]
            persisted=[x['id'] for x in records if x['kind']=='feedback_persisted' and r['id'] in x['payload']['event_ids']]
            item['feedback_chain'].append({'kernel_id':r['id'],'native_sdk_verification':p.get('native_sdk_verification',False),
                    'tool_call_id':p.get('tool_call_id'),
                    'kernel':{k:e.get(k) for k in ['op','target','pid','blocked','killed','effect','process_domain_id','session_root','kernel_call_tag','rule']},
                    'feedback':f,'offers':offers,'context_admission_ids':admissions,'persistence_ack_ids':persisted})
        item['native_storage']=json.loads((a.STATE/'report'/('storage-'+t['task_id']+'.json')).read_text())
        item['original_oracle']=json.loads((a.STATE/'report'/('oracle-'+t['task_id']+'.json')).read_text())
        op=json.loads((a.STATE/'report'/('operations-'+t['task_id']+'.json')).read_text())
        item['independent_operations']=[{'target':r['target'],'operation':r['operation'],'classification':r['classification'],
                    'domain_id':r['domain_id'],'pid':r['probe']['pid'],'blocked':r['probe'].get('blocked',False),
                    'before_hash':r['before_hash'],'after_hash':r['after_hash'],'kernel_event_count':len(r['kernel_events'])} for r in op]
        logs=Path(t['workspace'])/'.actplane/events.jsonl';stat=logs.lstat()
        item['kernel_log_trust']={'root_owned':stat.st_uid==0,'group_or_other_writable':bool(stat.st_mode&0o022),
                                 'symlink':logs.is_symlink(),'sha256':a.sha(logs)}
        assert item['kernel_log_trust']['root_owned'] and not item['kernel_log_trust']['group_or_other_writable'] and not item['kernel_log_trust']['symlink']
        proof['cases'].append(item)
    proof['api_restart']=json.loads((a.STATE/'report/api-restart.json').read_text())
    proof['shared_services']=subprocess.run(['systemctl','show','agentscope-scope-demo-api.service','agentscope-scope-demo-broker.service',
                                            '-p','Id','-p','ActiveState','-p','MainPID'],capture_output=True,text=True).stdout
    runtime=[]
    for f in ['backend/agentscope_app/managed/recovery.py','backend/agentscope_app/managed/feedback.py','backend/agentscope_app/managed/worker.py',
              'backend/agentscope_app/managed/controller.py','backend/agentscope_app/managed/records.py','backend/agentscope_app/bootstrap/scene.py','backend/agentscope_app/bootstrap/validation.py',
              'backend/broker/main.py','integrations/dsh-managed-web/lib/index.js','integrations/dsh-managed-web/lib/feedback-guard.js']:
        row={'path':f,'source_sha256':a.sha(repo/f),'release_sha256':a.sha(Path(proof['release'])/f)}
        assert row['source_sha256']==row['release_sha256'], f+' release drift'
        runtime.append(row)
    proof['runtime_source_hashes']=runtime;proof['private_content_exported']=False;proof['generated_at']=time.time()
    (out/'live-acceptance.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
    (out/'functional-tests.txt').write_text((a.STATE/'report/functional-cda3d1dd657c4789.txt').read_text())
    print(json.dumps({'evidence':str(out/'live-acceptance.json'),'cases':len(proof['cases']),
                      'operations':sum(len(c['independent_operations']) for c in proof['cases']),
                      'source_release_match':len(runtime),'shared_services':proof['shared_services'],'api_restart':proof['api_restart']},ensure_ascii=False))


if __name__=='__main__':export()
