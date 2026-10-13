"""Read-only customer history; raw jobs, prompts and compiler diagnostics stay in operations APIs."""
import json
from .. import db
from . import generations


def source_label(run):
    repository=(run.get('source') or {}).get('repository','')
    return '策略需求' if not repository or repository.startswith('manual/') else repository


def summary(run):
    return {key:run.get(key) for key in ('id','status','created_at','finished_at')} | {
        'source_label':source_label(run), 'candidate_count':sum(run.get('statistics',{}).values())}


def page(q='',status='',limit=20,offset=0):
    data=generations.page_runs(q,status,limit,offset,console=True)
    return {**data,'items':[summary(run) for run in data['items']]}


def detail(ident,limit=20,offset=0):
    from ..instances import store
    from ..console import hidden
    run=generations.get(ident)
    # History describes saved candidates. Live eligibility/approval checks belong
    # to the control flow, and must not make archived records depend on a Broker.
    joined=" FROM history_generation_results r JOIN strategy_statement_versions v ON v.id=r.statement_version_id LEFT JOIN history_artifacts a ON a.id=r.artifact_id WHERE r.run_id=? AND COALESCE(json_extract(v.record_json,'$.statement.content_type'),'policy')!='description'"
    with db.connect() as con:
        total=con.execute('SELECT COUNT(*)'+joined,(ident,)).fetchone()[0]
        rows=con.execute('SELECT v.record_json,a.artifact_json,a.compile_state'+joined+' ORDER BY v.created_at,r.statement_version_id LIMIT ? OFFSET ?',(ident,limit,offset)).fetchall()
    names={row['id']:row['name'] for row in store.rows() if row['id'] not in hidden('agent')}
    items=[]
    for row in rows:
        record=json.loads(row['record_json']); statement=record['statement']; context=record.get('resolved_context',{})
        artifact=json.loads(row['artifact_json'] or '{}')
        target=context.get('policy_target') or {}
        if target.get('scope'):
            from ..instances.policy_targets import label
            scope_label=label(target,context)
        else:
            scope_label='历史记录：未冻结范围' if context.get('kind')=='agent' else '未指定应用范围'
        clauses=[c for rule in artifact.get('policy_ir',{}).get('rules',[]) for c in rule.get('clauses',[])]
        ready=bool(artifact.get('actplane_dsl')) and row['compile_state']=='compiled'
        items.append({'text':statement.get('text_zh') or statement.get('text_original') or '策略候选',
            'target_name':names.get(context.get('instance_id'),'历史 Agent（当前不可用）') if context.get('kind')=='agent' else '通用候选（未绑定 Agent）',
            'scope_label':scope_label,
            'targets':list(dict.fromkeys(c['pattern'] for c in clauses if c.get('pattern'))),
            'operations':list(dict.fromkeys(c['operation'] for c in clauses if c.get('operation'))),
            'effects':list(dict.fromkeys(c['effect'] for c in clauses if c.get('effect'))),
            'status':'ready' if ready else 'incomplete',
            'has_conditions':any(c.get('unless') or (c.get('when') or {}).get('kind')!='label' for c in clauses),
            'dsl':artifact.get('actplane_dsl') if ready else None})
    return {**summary(run),'candidate_count':total,'total':total,'limit':limit,'offset':offset,'items':items}
