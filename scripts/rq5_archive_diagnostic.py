#!/usr/bin/env python3
"""Archive a rejected acceptance pair without deleting its evidence or assets."""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from rq5_control import request
from rq5_service import ROOT,STATE,environment

parser=argparse.ArgumentParser();parser.add_argument('scenario');parser.add_argument('reason');args=parser.parse_args()
os.environ.update(environment());sys.path.insert(0,str(ROOT/'backend'))
from agentscope_app.bootstrap.trace import export_trace
from agentscope_app.bootstrap.evaluation import evaluate
path=STATE/'report/acceptance.json';data=json.loads(path.read_text());pair=data['cases'][args.scenario]
for group in ('A','B'):
    if group not in pair:continue
    run=pair[group];task=run['id'];runtime=request(f'/api/tasks/{task}/runtime')
    if runtime['task_status']=='running':request(f'/api/tasks/{task}/stop',{})
    run['runtime']=request(f'/api/tasks/{task}/runtime')
    if 'before' in run:
        run['trace']=export_trace(Path('/r')/task);run['evaluation']=evaluate(run['context'],run['before'],run['trace']['assistant_text'])
    run['excluded_reason']=args.reason;run['chain_passed']=False
pair['scenario']=args.scenario;pair['archived_at']=time.time();data.setdefault('diagnostic_runs',[]).append(pair)
del data['cases'][args.scenario];path.write_text(json.dumps(data,ensure_ascii=False,indent=2))
print('Rejected pair and any partial DSH trace archived; managed domain cleaned')
