"""Session inheritance and applied additions; no desired-state or name fallback."""
import json
import re
from pathlib import PurePosixPath
from .. import db
from ..managed import controller as managed, records as views
from .session_loaded_policies import snapshot


def action(effects):
    values=set(filter(None,effects))
    return next(iter(values)) if len(values)==1 else 'mixed' if values else None


def target_name(pattern):
    recursive=pattern.endswith('/**')
    path=pattern[:-3] if recursive else pattern
    mount=re.fullmatch(r'/w/(\d+)(?:/(.*))?',path)
    if mount:
        # These are frozen execution paths. Historical receipts do not retain
        # resource aliases; never substitute a present-day resource name.
        path='资源目录 '+str(int(mount[1])+1)+((' / '+mount[2]) if mount[2] else '')
    else:path=str(PurePosixPath(path))
    return path+' 下的所有文件（含子目录）' if recursive else path


def startup_name(record):
    if record.get('source_kind')!='startup' or record.get('scope')=='system':return record['name']
    clauses=record['clauses']
    targets=list(dict.fromkeys(target_name(c['target']) for c in clauses if c.get('target')))
    verbs={'write':'修改','unlink':'删除','read':'读取'}
    operations=list(dict.fromkeys(c.get('operation') for c in clauses))
    title='禁止'+'和'.join(verbs[op] for op in operations) if operations and all(op in verbs for op in operations) and all(c.get('effect')=='block' for c in clauses) else record['name'].split('（')[0]
    return title+' · '+'、'.join(targets[:2])+(' 等' if len(targets)>2 else '') if targets else record['name']


def build(row, session, generation, receipt, current):
    records=[]
    if session.get('historical') and session.get('recorded_generation')!=generation:
        return {'schema':'SessionPolicyRecords/1','records':[],'instance_id':row['id'],'session_id':session['id'],
                'generation':generation,'loading_status':current['loading_status']}
    if receipt and row.get('mode')=='controlled':
        saved=snapshot(row,generation,receipt)
        for record in saved['records']:
            records.append({**record,'name':startup_name(record),'stage':'startup',
                'default_action':action(c.get('effect') for c in record['clauses']),
                'status':'loaded' if current['loading_status']['state']=='loaded' and not session.get('historical') and generation==row.get('generation') else 'historical_loaded',
                'source_label':'运行前 · '+('系统继承' if record['scope']=='system' else 'Agent 继承')})
    with db.connect() as con:
        con.execute('PRAGMA query_only=ON')
        binding=con.execute('SELECT * FROM instance_session_task_bindings WHERE instance_id=? AND generation=? AND session_id=?',
                            (row['id'],generation,session['id'])).fetchone()
        if binding:
            saved=con.execute('SELECT state_json FROM managed_tasks WHERE task_id=?',(binding['task_id'],)).fetchone()
            state=json.loads(saved['state_json']) if saved else {}
            domain=(receipt or {}).get('artifact',{}).get('binding',{}).get('domain_id')
            if domain is None and generation==row.get('generation'):domain=row.get('domain_id')
            if domain is not None and state.get('session_id')==binding['managed_session_id'] and state.get('binding',{}).get('domain_id')==domain:
                task=managed.task_row(con,binding['task_id'])
                for job in con.execute("SELECT * FROM managed_jobs WHERE task_id=? AND status='completed' AND proposal_json IS NOT NULL ORDER BY rowid DESC",(task['id'],)):
                    for record in views.runtime_statement_records(con,task,state,job):
                        if record['effect']!='restrict' or record['policy_type']=='semantic_only' or not record.get('targets') or not record['loading'].get('loaded'):continue
                        records.append({**record,'name':record.get('name') or record['statement'],'scope':'agent','clauses':[],
                                        'status':'historical_loaded' if state.get('phase')=='ended' else 'applied',
                                        'source_label':'运行时 · '+{'native_user':'用户消息','administrator':'管理员消息','persistent_memory':'跨会话记忆'}.get(record.get('trigger',{}).get('actor'),'来源未记录')})
    return {'schema':'SessionPolicyRecords/1','records':records,'instance_id':row['id'],'session_id':session['id'],
            'generation':generation,'loading_status':current['loading_status']}
