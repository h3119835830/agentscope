#!/usr/bin/env python3
"""Read-only live-instance isolation audit. Never exports authentication data."""
import json
import os
import shlex
import sqlite3
import urllib.request
from pathlib import Path
from rq5_service import STATE

if os.getuid()!=0:raise SystemExit('Requires root to read the existing protected service configuration')
live_env={}
for line in Path('/etc/agentscope/agentscope.env').read_text().splitlines():
    if not line.strip() or line.lstrip().startswith('#'):continue
    key,value=line.split('=',1);parsed=shlex.split(value);live_env[key]=parsed[0] if len(parsed)==1 else value
database=Path(live_env.get('AGENTSCOPE_DB',str(Path(live_env.get('AGENTSCOPE_STATE_DIR','/var/lib/agentscope'))/'agentscope.sqlite3')))
with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as con:
    pending=con.execute("SELECT count(*) FROM strategies WHERE status='pending_review' AND is_archived=0").fetchone()[0]
    rq5=con.execute("SELECT count(*) FROM tasks WHERE name IN ('safety-delete-config','safety-impossible-tests','safety-abusive-apology') AND repo='Open-Agent-Safety/OpenAgentSafety'").fetchone()[0]
    tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    contexts=con.execute('SELECT count(*) FROM bootstrap_contexts').fetchone()[0] if 'bootstrap_contexts' in tables else 0
request=urllib.request.Request('http://127.0.0.1:18000/api/dashboard',headers={'Authorization':'Bearer '+live_env['AGENTSCOPE_ADMIN_TOKEN']})
with urllib.request.urlopen(request,timeout=10) as response:dashboard=json.load(response)
result={'original_url':'http://127.0.0.1:18000','original_database':str(database),'pending_review_nonarchived':pending,
        'original_rq5_tasks':rq5,'original_bootstrap_contexts':contexts,'original_active_tasks':dashboard['stats']['active_tasks'],
        'original_service_available':True,'isolated_database':str(STATE/'acceptance.sqlite3')}
result['checks']={'721_pending_preserved':pending==721,'no_test_task_injection':rq5==0 and contexts==0,
                  'original_no_active_domain':not dashboard['stats']['active_tasks'] and not dashboard['active'],
                  'distinct_database':database.resolve()!=(STATE/'acceptance.sqlite3').resolve()}
(STATE/'report/isolation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result))
if not all(result['checks'].values()):raise SystemExit('Isolation audit failed')
