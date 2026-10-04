#!/usr/bin/env python3
"""Export public acceptance evidence; never copy session stores or credential files."""
import json
import hashlib
import shutil
import subprocess
from pathlib import Path
from history_acceptance import STATE,ROOT,request

destination=Path('/mnt/c/Users/happy/Desktop/归纳梳理/技术文档/REVIEW/AgentScope-history-v1-20261004')
destination.mkdir(parents=True,exist_ok=True)
for name in ('first-layer.json','first-layer-environment-self-invalidation.json','rq5-regression.json'):
    shutil.copyfile(STATE/'report'/name,destination/name)
run='0baaa2e715014785b0482b5dd50bdb02'
generation=request('/api/history/generations/'+run)
results=request('/api/history/generations/'+run+'/results?limit=100')
(destination/'github-unified.json').write_text(json.dumps({'generation':generation,'results':results},ensure_ascii=False,indent=2))
isolation={'worktree':str(ROOT),'branch':subprocess.check_output(['runuser','-u','happy','--','git','-C',str(ROOT),'branch','--show-current'],text=True).strip(),
    'head':subprocess.check_output(['runuser','-u','happy','--','git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
    'base':'0456086db8263c98fa4fd3c760cf3136c797afde','url':'http://127.0.0.1:18002',
    'database':str(STATE/'acceptance.sqlite3'),'task_root':'/h','broker_socket':'/run/agentscope-history-v1/broker.sock',
    'original_read_only_observation':request('/api/dashboard',base='http://127.0.0.1:18000')['stats'],
    'bulk_rq1_import_enabled':False,'push_performed':False}
(destination/'isolation.json').write_text(json.dumps(isolation,ensure_ascii=False,indent=2))
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.iterdir() if p.is_file() and p.name!='manifest.json'}
(destination/'manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'destination':str(destination),'evidence_files':list(manifest),'first_layer_passed':json.loads((destination/'first-layer.json').read_text())['passed']},ensure_ascii=False))
