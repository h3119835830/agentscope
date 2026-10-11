#!/usr/bin/env python3
"""Public evidence for the isolated 18005 instance; never approves or starts DSH."""
import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path
from because_service import STATE, environment

REPORT = STATE / 'report/feedback-skill-tasks.json'


def prepare():
    if REPORT.exists():raise RuntimeError('Acceptance tasks already exist; inspect their report')
    env=environment()
    os.environ.update(env)
    if os.geteuid()==0:
        import pwd
        user=pwd.getpwnam('agentscope-api')
        os.initgroups(user.pw_name,user.pw_gid);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from agentscope_app.bootstrap.scene import create_scene
    tasks=[]
    for case in ('safety-impossible-tests','safety-delete-config'):
        task=create_scene(case,workspace_leaf='r',compact_paths=True)
        request=urllib.request.Request(env['AGENTSCOPE_PUBLIC_URL']+'/api/tasks/'+task['id']+'/bootstrap',
            data=b'{}',headers={'Content-Type':'application/json','Authorization':'Bearer '+env['AGENTSCOPE_ADMIN_TOKEN']})
        with urllib.request.urlopen(request,timeout=15) as response:job=json.load(response)
        tasks.append({'case':case,'task_id':task['id'],'job_id':job['id']})
    REPORT.write_text(json.dumps(tasks,ensure_ascii=False,indent=2))
    print(json.dumps(tasks))


def verify():
    result=[]
    with sqlite3.connect(STATE/'acceptance.sqlite3') as con:
        con.row_factory=sqlite3.Row
        for item in json.loads(REPORT.read_text()):
            job=con.execute('SELECT * FROM history_jobs WHERE id=?',(item['job_id'],)).fetchone()
            if job['status']!='completed':
                print(json.dumps({**item,'status':job['status'],'error':job['error']}));continue
            runtime=json.loads(job['result_json'])['runtime']
            proof=runtime['lifecycle']['skill']
            assert proof['context_verified'] and proof['discovery_verified']
            proposal=con.execute('SELECT * FROM bootstrap_proposals WHERE job_id=?',(item['job_id'],)).fetchone()
            data=json.loads(proposal['proposal_json'])
            assert proposal['state']=='validated' and data['draft']['atoms']
            for atom,rule in zip(data['draft']['atoms'],data['policy_ir']['rules'],strict=True):
                assert atom['feedback'] and rule['reason'].startswith(atom['feedback'])
            task=con.execute('SELECT * FROM tasks WHERE id=?',(item['task_id'],)).fetchone()
            assert task['active_version']==0
            assert not con.execute('SELECT 1 FROM policy_versions WHERE task_id=?',(item['task_id'],)).fetchone()
            assert not con.execute('SELECT 1 FROM managed_tasks WHERE task_id=?',(item['task_id'],)).fetchone()
            result.append({**item,'status':job['status'],'proposal_state':proposal['state'],
                'proposal_hash':proposal['content_hash'],'skill':runtime['feedback_skill'],'native_context':proof,
                'tool_calls':json.loads(job['result_json'])['tool_calls'],'active_version':0,'loaded':False,
                'feedback':[a['feedback'] for a in data['draft']['atoms']],
                'compiled_reasons':[r['reason'] for r in data['policy_ir']['rules']]})
    if len(result)==2:
        target=STATE/'report/feedback-skill-acceptance.json'
        target.write_text(json.dumps({'passed':True,'tasks':result},ensure_ascii=False,indent=2))
        print(json.dumps({'passed':True,'tasks':len(result),'loaded':False,'report':str(target)}))


if __name__=='__main__':
    {'prepare':prepare,'verify':verify}[sys.argv[1]]()
