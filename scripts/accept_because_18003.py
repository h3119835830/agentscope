#!/usr/bin/env python3
"""Fresh, owned RQ5 fixtures on the integrated shared console; no global policy edits."""
import json
import sqlite3
import sys
from pathlib import Path
import because_acceptance as a
from deploy_system_policy import api

ROOT = Path(__file__).resolve().parents[1]
a.DB = Path('/var/lib/agentscope-scope-demo/demo.sqlite3')
a.REPORT = Path('/var/lib/agentscope-scope-demo/report/because-20261011-2201')
a.URL = 'http://127.0.0.1:18003'
a.api = api


def create():
    a.REPORT.mkdir(mode=0o750, exist_ok=True)
    marker = a.REPORT / 'live-tasks.json'
    assert not marker.exists(), 'Do not replace another acceptance run'
    tasks = []
    marker.write_text('[]')
    for case in ('safety-impossible-tests', 'safety-delete-config'):
        task = api('/api/managed/scenarios/' + case + '/tasks', {})
        tasks.append(dict(case=case,task_id=task['id'],workspace=task['workspace']))
        marker.write_text(json.dumps(tasks,indent=2))
        api('/api/managed/tasks/' + task['id'] + '/start', {})
    print(json.dumps(tasks))


def skill_proof(t):
    with sqlite3.connect(a.DB) as con:
        con.row_factory=sqlite3.Row
        job=con.execute("SELECT * FROM history_jobs WHERE kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=? ORDER BY created_at DESC LIMIT 1",(t['task_id'],)).fetchone()
        assert job['status']=='completed', 'Pi startup not completed'
        result=json.loads(job['result_json']);runtime=result['runtime'];proof=runtime['lifecycle']['skill']
        assert proof['context_verified'] and proof['discovery_verified']
        proposal=con.execute('SELECT * FROM bootstrap_proposals WHERE job_id=?',(job['id'],)).fetchone()
        assert proposal['state']=='validated'
        data=json.loads(proposal['proposal_json'])
        for atom,rule in zip(data['draft']['atoms'],data['policy_ir']['rules'],strict=True):
            assert atom['feedback'] and rule['reason'].startswith(atom['feedback'])
        value=dict(task_id=t['task_id'],job_id=job['id'],proposal_hash=proposal['content_hash'],
                   skill=runtime['feedback_skill'],native_context=proof,tool_calls=result['tool_calls'],
                   feedback=[atom['feedback'] for atom in data['draft']['atoms']],
                   compiled_reasons=[rule['reason'] for rule in data['policy_ir']['rules']])
    (a.REPORT/('skill-'+t['task_id']+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2))
    print(json.dumps(dict(task_id=t['task_id'],pi_skill_verified=True,tool_calls=value['tool_calls'])))


if __name__=='__main__':
    command=sys.argv[1]
    if command=='create':create()
    else:
        for t in a.tasks():
            if len(sys.argv)>2 and sys.argv[2]!=t['case']:continue
            if command=='status':print(json.dumps(a.status(t),ensure_ascii=False),flush=True)
            elif command=='skill':skill_proof(t)
            elif command=='close':print(json.dumps(api('/api/managed/tasks/'+t['task_id']+'/close',{})))
            else:getattr(a,command)(t)
