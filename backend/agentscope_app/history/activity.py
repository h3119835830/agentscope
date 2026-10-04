"""Paginated public projections of persisted jobs and history audit events."""
from .. import db

PUBLIC_KEYS=set('repo_url ref additional_paths document_ids document_id statement_version_id statement_version_ids artifact_id attempt_ids task_id job_id strategy_id old_id new_id proposal_id dataset_identity artifact_commit repository commit file_count documents coverage llm_runs provider model response_model prompt_version input_hash output_hash usage prompt_tokens completion_tokens total_tokens duration_ms input_count unique_count inserted_count reused_count verified_count unverified_count repositories compile_state decision revision fields reason id'.split())

def public(value):
    if isinstance(value,dict):return {key:public(item) for key,item in value.items() if key in PUBLIC_KEYS}
    if isinstance(value,list):return [public(item) for item in value]
    return value

def page(section='jobs',kind='',status='',q='',limit=20,offset=0):
    if section not in ('jobs','events'):raise ValueError('审计记录类型无效')
    table='history_jobs' if section=='jobs' else 'audit_log'
    filters=[];params=[]
    if section=='events':filters.append("(action GLOB 'history_*' OR action GLOB 'strategy_*' OR action='rq1_corpus_import')")
    if kind:
        filters.append(('kind' if section=='jobs' else 'action')+'=?');params.append(kind)
    if status and section=='jobs':filters.append('status=?');params.append(status)
    if q:
        columns=('id','input_json') if section=='jobs' else ('id','actor','details_json')
        filters.append('('+' OR '.join(column+' LIKE ?' for column in columns)+')');params.extend(['%'+q+'%']*len(columns))
    where=' WHERE '+' AND '.join(filters) if filters else ''
    with db.connect() as con:
        total=con.execute('SELECT count(*) FROM '+table+where,params).fetchone()[0]
        rows=[db.row_dict(row) for row in con.execute('SELECT * FROM '+table+where+' ORDER BY created_at DESC,rowid DESC LIMIT ? OFFSET ?',[*params,limit,offset])]
    for row in rows:
        for field in ('input','result','details'):
            if field in row:row[field]=public(row[field])
    return {'items':rows,'total':total,'limit':limit,'offset':offset}
