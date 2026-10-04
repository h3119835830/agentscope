#!/usr/bin/env python3
"""Repeat probes only after all managed DSH domains are clean."""
import json
import os
import sqlite3
import sys
from rq5_service import ROOT, STATE, environment
from rq5_acceptance import probes

os.environ.update(environment());sys.path.insert(0,str(ROOT/'backend'))
path=STATE/'report/acceptance.json';data=json.loads(path.read_text())
with sqlite3.connect(STATE/'acceptance.sqlite3') as con:
    if con.execute("SELECT 1 FROM tasks WHERE status IN ('starting','running','bootstrapping')").fetchone():raise SystemExit('Finish the managed domain before independent probes')
for case,pair in data['cases'].items():
    if case=='safety-abusive-apology':continue
    run=pair['B'];result=probes(run['id'],run['context'],run['version'])
    run.setdefault('prior_probe_reports',[]).append(run.get('probes'))
    run['probes']=result
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    print(json.dumps({'scenario':case,'checks':result['checks'],'violations':sum(r['illegal'] for r in result['operations']['records'])}))
    if not all(result['checks'].values()):raise RuntimeError('probe acceptance failed')
