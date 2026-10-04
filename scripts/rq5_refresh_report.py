#!/usr/bin/env python3
"""Refresh safe traces, initial oracle baselines, task integrity and cleanup facts."""
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from rq5_control import request
from rq5_service import ROOT, STATE, environment

os.environ.update(environment());sys.path.insert(0,str(ROOT/'backend'))
from agentscope_app.bootstrap.evaluation import inventory,evaluate
from agentscope_app.bootstrap.scene import FIXTURES
from agentscope_app.bootstrap.trace import export_trace

path=STATE/'report/acceptance.json';data=json.loads(path.read_text())
for case,pair in data['cases'].items():
    for group in ('A','B'):
        run=pair[group];ctx=run['context'];task=run['id']
        baseline=STATE/'report/initial-oracle-baselines'/task
        baseline.mkdir(parents=True,exist_ok=True)
        for asset in ctx['assets']:
            target=baseline/asset['relative_path'];target.parent.mkdir(parents=True,exist_ok=True)
            if asset.get('path'):shutil.copyfile(FIXTURES/case/asset['path'],target)
            else:target.write_text('explicitly disposable acceptance cache\n')
        initial_ctx={**ctx,'workspace':str(baseline)}
        run['initial_evaluation']=evaluate(initial_ctx,inventory(baseline),'')
        run['initial_evaluation']['baseline_physical_directory']=str(baseline)
        run['trace']=export_trace(Path('/r')/task)
        run['evaluation']=evaluate(ctx,run['before'],run['trace']['assistant_text'])
        receipt=run['receipt'];run['cleanup_confirmed']=all(not Path('/proc',str(receipt[k])).exists() for k in ('runner_pid','watch_pid'))
        run['handoff']=request(f'/api/tasks/{task}/bootstrap/handoff')
        run['chain_passed']=bool(receipt.get('binding_confirmed') and run['evaluation']['initial_layout']['valid'] and not run['initial_evaluation']['raw_evaluator']['unsafe'] and run['trace']['model_configuration'] and run['cleanup_confirmed'])
        with sqlite3.connect(STATE/'acceptance.sqlite3') as con:
            result={'group':group,'chain_passed':run['chain_passed'],'initial_evaluation':run['initial_evaluation'],
                    'evaluation':run['evaluation'],'task_result':run['task_result'],'kernel_event_count':len(run.get('dsh_events',[])),
                    'probe_checks':run.get('probes',{}).get('checks'),'probe_violation_count':sum(r['illegal'] for r in run.get('probes',{}).get('operations',{}).get('records',[]))}
            con.execute('INSERT OR REPLACE INTO bootstrap_results VALUES(?,?,?)',(task,json.dumps(result),time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
with sqlite3.connect(STATE/'acceptance.sqlite3') as con:
    # Reconcile stale active handles from executions completed before the cleanup
    # fix. Immutable deployment receipts remain the historical binding record.
    reconciled=[]
    for task,pid,watch in con.execute("SELECT id,active_pid,watch_pid FROM tasks WHERE status IN ('completed','failed','stopped') AND (active_pid IS NOT NULL OR watch_pid IS NOT NULL)"):
        if all(not value or not Path('/proc',str(value)).exists() for value in (pid,watch)):
            con.execute('UPDATE tasks SET active_pid=NULL,watch_pid=NULL,active_domain_id=NULL WHERE id=?',(task,));reconciled.append(task)
    data['reconciled_inactive_handles']=reconciled
    formal_ids=[pair[g]['id'].encode() for pair in data['cases'].values() for g in ('A','B')]
    residual=[]
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():continue
        try:command=(process/'cmdline').read_bytes()
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
        if any(b'/r/'+task+b'/' in command for task in formal_ids):residual.append(int(process.name))
    data['cleanup_audit']={'active_tasks':con.execute("SELECT count(*) FROM tasks WHERE status IN ('starting','running','bootstrapping')").fetchone()[0],
                           'unrevoked_generator_credentials':con.execute('SELECT count(*) FROM bootstrap_credentials WHERE revoked_at IS NULL').fetchone()[0],
                           'unrevoked_task_credentials':con.execute('SELECT count(*) FROM task_credentials WHERE revoked_at IS NULL').fetchone()[0],
                           'residual_formal_processes':len(residual),
                           'active_deployments':con.execute('SELECT count(*) FROM history_deployments WHERE active=1').fetchone()[0]}
data['b_integrity_passed']=all(pair['B']['evaluation']['independent_integrity']['protected_unchanged'] for pair in data['cases'].values())
data['probe_checks_passed']=all(all(pair['B']['probes']['checks'].values()) for name,pair in data['cases'].items() if name!='safety-abusive-apology')
data['passed']=bool(data['six_dsh_runs']==6 and all(pair[g]['chain_passed'] for pair in data['cases'].values() for g in ('A','B')) and data['b_integrity_passed'] and data['probe_checks_passed'] and data['noop_execution_dsl_empty'] and not any(data['cleanup_audit'].values()))
data['report_refreshed_at']=time.time();path.write_text(json.dumps(data,ensure_ascii=False,indent=2))
print(json.dumps({'passed':data['passed'],'cleanup':data['cleanup_audit']}))
