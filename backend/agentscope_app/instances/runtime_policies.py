"""Read-only runtime policy records, scoped by saved instance/session bindings."""
from fastapi import APIRouter,HTTPException,Query
from .. import db
from ..managed import controller as managed,records as views
from . import store

router=APIRouter()

def bound_tasks(ident,generation):
    try:row=store.get(ident)
    except ValueError:raise HTTPException(404,'Agent 不存在')
    if row['mode']!='controlled' or not generation or generation!=row.get('generation'):
        raise HTTPException(409,'Agent 运行身份已变化，请重新选择')
    domain=(row.get('runtime') or {}).get('domain_id');result=[]
    with db.connect() as con:
        con.execute('PRAGMA query_only=ON')
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='instance_session_task_bindings'").fetchone():return []
        for binding in con.execute('SELECT * FROM instance_session_task_bindings WHERE instance_id=? AND generation=?',(ident,generation)):
            saved=con.execute('SELECT state_json FROM managed_tasks WHERE task_id=?',(binding['task_id'],)).fetchone()
            if not saved:continue
            state=views.decode(saved,'state_json')
            if domain is not None and state.get('session_id')==binding['managed_session_id'] and state.get('binding',{}).get('domain_id')==domain:
                result.append(binding['task_id'])
    return sorted(set(result))

def compact(record,task):
    return {k:v for k,v in record.items() if k not in ('evidence','explanation','compilation','loading','delta','identified_statements')}|{'task_id':task['id'],'workspace':task['workspace'],'compile_status':record['compilation']['status']}

def page(tasks,before=None):
    if not tasks:return {'records':[],'next_cursor':None}
    boundary=None;offset=-1
    if before:
        parts=before.split(':')
        if len(parts)!=2 or not all(part.isdigit() for part in parts):raise HTTPException(422,'无效的记录位置')
        boundary,offset=map(int,parts)
    result=[];cursors=[];first=True
    with db.connect() as con:
        con.execute('PRAGMA query_only=ON')
        while len(result)<13:
            predicate='task_id IN ('+','.join('?' for _ in tasks)+") AND status='completed' AND proposal_json IS NOT NULL";args=list(tasks)
            if boundary is not None:predicate+=' AND rowid<=?';args.append(boundary)
            rows=con.execute('SELECT rowid AS cursor,* FROM managed_jobs WHERE '+predicate+' ORDER BY rowid DESC LIMIT 32',args).fetchall()
            if not rows:break
            for row in rows:
                task=managed.task_row(con,row['task_id']);state=managed.load(con,row['task_id'])
                try:children=[item for item in views.runtime_statement_records(con,task,state,row) if item['effect']=='restrict' and item['policy_type']!='semantic_only' and item.get('targets')]
                except (ValueError,KeyError,TypeError):raise HTTPException(409,'历史策略材料无法读取')
                for index,item in enumerate(children):
                    if first and row['cursor']==boundary and index<=offset:continue
                    result.append(compact(item,task));cursors.append(str(row['cursor'])+':'+str(index))
                    if len(result)==13:break
                if len(result)==13:break
            if len(result)==13:break
            boundary=rows[-1]['cursor']-1;first=False
    return {'records':result[:12],'next_cursor':cursors[11] if len(result)>12 else None}

def detail(tasks,record_id):
    if not record_id.startswith('runtime:'):raise HTTPException(404,'策略记录不属于当前范围')
    job=record_id[8:].split(':statement:')[0]
    with db.connect() as con:
        row=con.execute('SELECT task_id FROM managed_jobs WHERE id=?',(job,)).fetchone()
    if not row or row['task_id'] not in tasks:raise HTTPException(404,'策略记录不属于当前范围')
    try:return views.detail(row['task_id'],record_id)
    except ValueError:raise HTTPException(404,'策略记录不属于当前范围')

@router.get('/api/agent-instances/{ident}/runtime-policies')
def instance_records(ident:str,generation:str=Query(min_length=1,max_length=100),before:str|None=None):
    return page(bound_tasks(ident,generation),before)

@router.get('/api/agent-instances/{ident}/runtime-policies/{record_id}')
def instance_record(ident:str,record_id:str,generation:str=Query(min_length=1,max_length=100)):
    return detail(bound_tasks(ident,generation),record_id)

@router.get('/api/runtime-tasks/{task_id}/policies')
def task_records(task_id:str,before:str|None=None):
    with db.connect() as con:
        row=con.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not row:raise HTTPException(404,'任务不存在')
        task=dict(row)
        saved=con.execute('SELECT state_json FROM managed_tasks WHERE task_id=?',(task_id,)).fetchone()
        state=views.decode(saved,'state_json') if saved else {'phase':'ended'}
    return {**page([task_id],before),'task_id':task_id,'name':task['name'],'workspace':task['workspace'],'historical':state['phase'] in ('ended','completed','failed')}

@router.get('/api/runtime-tasks/{task_id}/policies/{record_id}')
def task_record(task_id:str,record_id:str):return detail([task_id],record_id)
