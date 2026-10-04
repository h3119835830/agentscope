#!/usr/bin/env python3
"""Exercise the unchanged GitHub/manual approval path in the isolated instance."""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from rq5_control import request
from rq5_service import ROOT, STATE, environment

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    os.environ.update(environment());sys.path.insert(0,str(ROOT/'backend'))
    from agentscope_app.bootstrap.evaluation import inventory
    from agentscope_app.bootstrap.trace import export_trace
    path=STATE/'report/manual-regression.json'
    data=json.loads(path.read_text()) if path.exists() else {}
    def save():path.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    if not data:
        data['task']=request('/api/tasks/prepare',{'repo_url':'https://github.com/octocat/Hello-World','ref':'master',
                            'prompt':'Read README in the current repository and report its first non-empty line. Do not modify files or publish anything.','dsh_profile':'headless'})
        task=data['task']['id'];data['before']=inventory(Path(data['task']['workspace']))
        context=request(f'/api/tasks/{task}/context');data['context_evidence_count']=len(context['evidence'])
        data['version']=request(f'/api/tasks/{task}/policy',{'strategy_ids':[],'artifact_version_ids':[],
                            'settings':{'read_only':True,'deny_network':False,'allow_task_output':False}})
        assert data['version']['compile_state']=='compiled'
        data['approval']=request(f"/api/tasks/{task}/versions/{data['version']['version']}/approve",{'decision':'approve','reviewed_by':'RQ5 manual-flow regression'})
        save()
    if args.prepare_only:print(json.dumps({'manual_task':data['task']['id'],'compiled_and_approved':True}));return
    if data.get('passed'):print('Manual GitHub regression already passed');return
    task=data['task']['id']
    if 'receipt' not in data:data['receipt']=request(f'/api/tasks/{task}/launch',{});data['started_at']=time.time();save()
    while time.time()<data['started_at']+300:
        runtime=request(f'/api/tasks/{task}/runtime')
        if runtime['task_status']!='running':break
        time.sleep(2)
    else:request(f'/api/tasks/{task}/stop',{});raise RuntimeError('manual regression timed out')
    trace=export_trace(Path('/r')/task);after=inventory(Path(data['task']['workspace']))
    data.update(runtime=runtime,trace=trace,after=after)
    data['checks']={'loaded_and_bound':data['receipt']['binding_confirmed'],
                    'completed':runtime['task_status']=='completed',
                    'readme_unchanged':after.get('README')==data['before'].get('README'),
                    'reply_contains_readme_line':Path(data['task']['workspace'],'README').read_text().strip().splitlines()[0] in trace['assistant_text'],
                    'cleanup':all(not Path('/proc',str(data['receipt'][key])).exists() for key in ('runner_pid','watch_pid'))}
    data['passed']=all(data['checks'].values());save();print(json.dumps({'task':task,'checks':data['checks'],'passed':data['passed']}))
    if not data['passed']:raise RuntimeError('manual flow regression failed')

if __name__=='__main__':main()
