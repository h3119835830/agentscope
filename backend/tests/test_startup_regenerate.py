"""Returning startup candidates preserves evidence and queues factual feedback atomically."""
import grp
import hashlib
import json
import os
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import HTTPException

from agentscope_app import db
from agentscope_app.bootstrap import api as bootstrap_api, runner, scene, validation
from agentscope_app.history import jobs
from agentscope_app.managed import controller as c
from agentscope_app.workspaces import registry

AUTH = {'Authorization': 'Bearer test-admin-token-not-for-production'}
RUNTIME = {'model': 'isolated-regeneration'}
REASON = 'The candidate applies the cited cleanup condition outside cleanup; reassess its applicability.'


@pytest.fixture
def reviewed(client, monkeypatch):
    with tempfile.TemporaryDirectory(prefix='', dir='/tmp/a') as directory:
        monkeypatch.setattr(registry, 'WORKSPACE_ROOT', Path(directory))
        monkeypatch.setenv('AGENTSCOPE_TASK_GROUP', grp.getgrgid(os.getgid()).gr_name)
        monkeypatch.setattr(registry, 'effective_dsh', lambda: RUNTIME.copy())
        monkeypatch.setattr(scene, 'effective_dsh', lambda: RUNTIME.copy())
        monkeypatch.setattr(c, 'broker', lambda *a, **k: pytest.fail('review return cannot call Broker'))
        monkeypatch.setattr(runner, 'run', lambda *a, **k: pytest.fail('review return cannot run a model'))
        workspace = registry.create_workspace('Review source')
        (Path(workspace['path']) / 'main.py').write_text('print("source")\n')
        task = registry.create_task(workspace['id'], 'Review task', 'Explain main.py; preserve its source.',
                                    registry.inventory(workspace['id'])['manifest_hash'])
        task_id = task['id']; ctx = scene.context(task_id)
        with db.connect() as con:
            task_source = con.execute("SELECT id FROM bootstrap_sources WHERE task_id=? AND role='task'", (task_id,)).fetchone()[0]
            asset_source = con.execute("SELECT id,path FROM bootstrap_sources WHERE task_id=? AND role='asset'", (task_id,)).fetchone()
        import agentscope_app.main as main
        monkeypatch.setattr(main, 'compile_policy', lambda *a, **k: ('compiled', {'ok': True}, ''))
        checked = validation.validate(task_id, {'context_hash': ctx['context_hash'], 'summary': 'Preserve source',
            'no_op': False, 'atoms': [{'decision': 'new_candidate', 'statement': 'Preserve source identity',
                'evidence_ids': [task_source, asset_source['id']], 'operations': ['unlink'],
                'paths': [asset_source['path']], 'reason': 'Task requests preserving existing source.'}]})
        assert checked['valid'] and checked['compile_state'] == 'compiled'
        monkeypatch.setattr(main, 'compile_policy', lambda *a, **k: pytest.fail('return must not compile or load policy'))
        job_id, proposal_id = uuid.uuid4().hex, uuid.uuid4().hex
        with db.connect() as con:
            con.execute('INSERT INTO history_jobs(id,kind,status,input_json,created_at,error) VALUES(?,?,?,?,?,?)',
                        (job_id, 'task_bootstrap', 'completed', json.dumps({'task_id': task_id}), db.now(), 'Prior synthetic diagnostic'))
            con.execute('INSERT INTO bootstrap_proposals VALUES(?,?,?,?,?,?,?,?,?)',
                        (proposal_id, task_id, job_id, ctx['context_hash'], checked['proposal_hash'],
                         json.dumps(checked['proposal']), json.dumps({k:v for k,v in checked.items() if k!='proposal'}), 'validated', db.now()))
            state = c.load(con, task_id)
            state.update(phase='policy_review', gate='waiting_confirmation', startup_job=job_id,
                         startup_proposal=proposal_id, startup_review_required=True)
            c.save(con, task_id, state)
            con.execute("UPDATE tasks SET status='policy_review' WHERE id=?", (task_id,))
        yield {'task_id': task_id, 'job_id': job_id, 'proposal_id': proposal_id,
               'checked': checked, 'asset_source_id': asset_source['id'],
               'body': {'expected_context_hash': ctx['context_hash'], 'expected_proposal_hash': checked['proposal_hash'], 'reason': REASON}}


def immutable(value):
    task_id, job_id = value['task_id'], value['job_id']
    with db.connect() as con:
        rows={table:[tuple(r) for r in con.execute(sql,(ident,))] for table,sql,ident in (
            ('context','SELECT * FROM bootstrap_contexts WHERE task_id=?',task_id),
            ('sources','SELECT * FROM bootstrap_sources WHERE task_id=? ORDER BY id',task_id),
            ('proposal','SELECT * FROM bootstrap_proposals WHERE task_id=? ORDER BY id',task_id),
            ('job','SELECT * FROM history_jobs WHERE id=?',job_id),
            ('root','SELECT * FROM snapshot_roots WHERE task_id=?',task_id),
            ('source','SELECT * FROM workspace_task_sources WHERE task_id=?',task_id))}
    rows['assets']={a['mapped_path']:hashlib.sha256(Path(a['mapped_path']).read_bytes()).hexdigest()
                    for a in scene.context(task_id)['assets']}
    return rows


def assert_unbound(task_id):
    with db.connect() as con:
        state=c.load(con,task_id)
        assert state['version']==0 and not state['session_id'] and not state['binding']
        assert not state.get('startup_confirmation') and state['startup_review_required']
        assert not con.execute('SELECT 1 FROM policy_versions WHERE task_id=?',(task_id,)).fetchone()
        assert not con.execute('SELECT 1 FROM task_credentials WHERE task_id=?',(task_id,)).fetchone()


def regenerate(value, **overrides):
    body={**value['body'],**overrides}
    return c.regenerate_startup(value['task_id'],body['expected_context_hash'],body['expected_proposal_hash'],body['reason'])


def test_http_return_regenerates_same_task_and_preserves_all_immutable_evidence(reviewed,client):
    before=immutable(reviewed)
    response=client.post('/api/managed/tasks/'+reviewed['task_id']+'/startup/regenerate',json=reviewed['body'],headers=AUTH)
    assert response.status_code==200
    result=response.json(); assert result['decision']=='return_for_revision' and result['job_id']!=reviewed['job_id']
    assert immutable(reviewed)==before
    with db.connect() as con:
        state=c.load(con,reviewed['task_id'])
        assert state['phase']=='generating' and state['gate']=='waiting_policy'
        assert state['startup_job']==result['job_id'] and 'startup_proposal' not in state
        job=con.execute('SELECT * FROM history_jobs WHERE id=?',(result['job_id'],)).fetchone()
        payload=json.loads(job['input_json']); feedback=payload['review_feedback']
        assert job['retry_of']==reviewed['job_id']
        assert feedback=={'proposal_id':reviewed['proposal_id'],'proposal_hash':reviewed['body']['expected_proposal_hash'],
                          'context_hash':reviewed['body']['expected_context_hash'],'reason':REASON,'authority':'control_plane_factual_review'}
        for kind in ('startup_reviewed','startup_generation'):
            event=con.execute('SELECT payload_json FROM managed_events WHERE task_id=? AND kind=?',(reviewed['task_id'],kind)).fetchone()
            data=json.loads(event[0]); assert data['decision']=='return_for_revision' and data['previous_job_id']==reviewed['job_id'] and data['reason']==REASON
    assert_unbound(reviewed['task_id'])


def test_feedback_is_committed_and_visible_before_worker_wakes(reviewed,monkeypatch):
    observed=[]
    class Wake:
        def set(self):
            with db.connect() as con:
                row=con.execute("SELECT input_json,retry_of FROM history_jobs WHERE kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=? AND status='queued'",(reviewed['task_id'],)).fetchone()
                payload=json.loads(row['input_json'])
                assert payload['review_feedback']['proposal_id']==reviewed['proposal_id']
                assert payload['review_feedback']['reason']==REASON and row['retry_of']==reviewed['job_id']
                observed.append(payload['job_id'])
    monkeypatch.setattr(jobs.worker,'wake',Wake())
    result=regenerate(reviewed)
    assert observed==[result['job_id']]


def test_real_worker_passes_only_task_and_job_to_runner_and_retains_feedback(reviewed,monkeypatch):
    result=regenerate(reviewed); observed=[]
    with db.connect() as con:
        # Schedule only this isolated test job first, without draining other jobs.
        con.execute("UPDATE history_jobs SET created_at='0001' WHERE id=?",(result['job_id'],))
    def run(task_id,job_id):
        assert task_id==reviewed['task_id'] and job_id==result['job_id']
        with db.connect() as con:
            payload=json.loads(con.execute('SELECT input_json FROM history_jobs WHERE id=?',(job_id,)).fetchone()[0])
        assert payload['review_feedback']['reason']==REASON
        observed.append((task_id,job_id))
        return {'status':'synthetic-unit-result'}
    monkeypatch.setattr(runner,'run',run)
    assert jobs.Worker().run_one() is True
    assert observed==[(reviewed['task_id'],result['job_id'])]


@pytest.mark.parametrize('field',['expected_context_hash','expected_proposal_hash'])
def test_stale_hashes_never_enqueue_or_change_candidate(reviewed,field,monkeypatch):
    before=immutable(reviewed)
    monkeypatch.setattr(jobs,'enqueue',lambda *a,**k:pytest.fail('stale review cannot enqueue'))
    with pytest.raises(ValueError):regenerate(reviewed,**{field:'0'*64})
    assert immutable(reviewed)==before


@pytest.mark.parametrize('change',['job_other_task','job_other_kind','job_failed','job_running','job_missing',
                                   'proposal_other_job','proposal_context','proposal_hash','summary_valid','summary_compile',
                                   'summary_hash','summary_embedded','body_shape','draft_context','source_missing','source_corrupt'])
def test_candidate_job_validation_and_source_bindings_are_required(reviewed,change,monkeypatch):
    task_id=reviewed['task_id']
    with db.connect() as con:
        row=con.execute('SELECT * FROM bootstrap_proposals WHERE id=?',(reviewed['proposal_id'],)).fetchone()
        if change=='job_other_task':con.execute('UPDATE history_jobs SET input_json=? WHERE id=?',(json.dumps({'task_id':'other-task'}),reviewed['job_id']))
        elif change=='job_other_kind':con.execute("UPDATE history_jobs SET kind='compile' WHERE id=?",(reviewed['job_id'],))
        elif change in ('job_failed','job_running'):con.execute('UPDATE history_jobs SET status=? WHERE id=?',(change.removeprefix('job_'),reviewed['job_id']))
        elif change=='job_missing':
            state=c.load(con,task_id);state['startup_job']=uuid.uuid4().hex;c.save(con,task_id,state)
        elif change=='proposal_other_job':con.execute('UPDATE bootstrap_proposals SET job_id=? WHERE id=?',(uuid.uuid4().hex,reviewed['proposal_id']))
        elif change=='proposal_context':con.execute('UPDATE bootstrap_proposals SET context_hash=? WHERE id=?',('0'*64,reviewed['proposal_id']))
        elif change=='proposal_hash':con.execute('UPDATE bootstrap_proposals SET content_hash=? WHERE id=?',('0'*64,reviewed['proposal_id']))
        elif change.startswith('summary_'):
            data=json.loads(row['validation_json'])
            key={'summary_valid':'valid','summary_compile':'compile_state','summary_hash':'proposal_hash','summary_embedded':'proposal'}[change]
            data[key]={'valid':False,'compile_state':'compile_failed','proposal_hash':'0'*64,'proposal':{'different':'body'}}[key]
            con.execute('UPDATE bootstrap_proposals SET validation_json=? WHERE id=?',(json.dumps(data),reviewed['proposal_id']))
        elif change in ('body_shape','draft_context'):
            data=[] if change=='body_shape' else json.loads(row['proposal_json'])
            if change=='draft_context':data['draft']['context_hash']='0'*64
            # Rebind the test's forged body so source/draft validation is tested,
            # rather than stopping at the earlier content hash check.
            hashed=scene.digest(data);summary=json.loads(row['validation_json']);summary['proposal_hash']=hashed
            con.execute('UPDATE bootstrap_proposals SET proposal_json=?,content_hash=?,validation_json=? WHERE id=?',(json.dumps(data),hashed,json.dumps(summary),reviewed['proposal_id']))
            reviewed['body']['expected_proposal_hash']=hashed
        elif change=='source_missing':con.execute('DELETE FROM bootstrap_sources WHERE id=?',(reviewed['asset_source_id'],))
        elif change=='source_corrupt':con.execute("UPDATE bootstrap_sources SET text='changed evidence' WHERE id=?",(reviewed['asset_source_id'],))
    monkeypatch.setattr(jobs,'enqueue',lambda *a,**k:pytest.fail('invalid candidate cannot enqueue'))
    with pytest.raises(ValueError):regenerate(reviewed)


@pytest.mark.parametrize('binding',['session_id','binding','startup_confirmation','active_version','active_pid',
                                    'active_domain_id','watch_pid','ended_at','credential','policy_version'])
def test_any_execution_authority_blocks_return(reviewed,binding,monkeypatch):
    task_id=reviewed['task_id']
    with db.connect() as con:
        if binding in ('session_id','binding','startup_confirmation'):
            state=c.load(con,task_id);state[binding]='bound' if binding=='session_id' else {'bound':True};c.save(con,task_id,state)
        elif binding=='credential':con.execute('INSERT INTO task_credentials(id,task_id,token_sha256,created_at) VALUES(?,?,?,?)',(uuid.uuid4().hex,task_id,uuid.uuid4().hex,db.now()))
        elif binding=='policy_version':con.execute('INSERT INTO policy_versions(id,task_id,version,layer,dsl_text,policy_yaml,compile_state,status,change_summary,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,task_id,1,'task_bootstrap','','','compiled','draft','existing',db.now()))
        else:con.execute('UPDATE tasks SET '+binding+'=? WHERE id=?',(db.now() if binding=='ended_at' else 1,task_id))
    monkeypatch.setattr(jobs,'enqueue',lambda *a,**k:pytest.fail('bound task cannot enqueue'))
    with pytest.raises(ValueError):regenerate(reviewed)


@pytest.mark.parametrize('change',['context_hash','prompt','settings','asset','runtime','root','output','manifest'])
def test_frozen_task_snapshot_and_source_manifest_must_match(reviewed,change,monkeypatch):
    task_id=reviewed['task_id'];ctx=scene.context(task_id)
    with db.connect() as con:
        if change=='context_hash':con.execute("UPDATE bootstrap_contexts SET context_hash=? WHERE task_id=?",('0'*64,task_id))
        elif change=='prompt':con.execute("UPDATE tasks SET prompt='different goal' WHERE id=?",(task_id,))
        elif change=='settings':con.execute("UPDATE tasks SET settings_json='{}' WHERE id=?",(task_id,))
        elif change=='output':con.execute('UPDATE tasks SET output_dir=? WHERE id=?',(str(Path(ctx['workspace']).parent/'tmp'),task_id))
        elif change=='manifest':con.execute('UPDATE workspace_task_sources SET manifest_hash=? WHERE task_id=?',('0'*64,task_id))
    if change=='asset':Path(ctx['assets'][0]['mapped_path']).write_text('changed source')
    elif change=='runtime':monkeypatch.setattr(scene,'effective_dsh',lambda:{'model':'changed'})
    elif change=='root':
        root=Path(ctx['workspace']).parent;root.rename(root.with_name(root.name+'-retained'))
        (root/'r').mkdir(parents=True);(root/'output').mkdir()
    monkeypatch.setattr(jobs,'enqueue',lambda *a,**k:pytest.fail('changed snapshot cannot enqueue'))
    with pytest.raises((ValueError,FileNotFoundError)):regenerate(reviewed)


@pytest.mark.parametrize('status',['queued','running'])
def test_any_active_generation_blocks_return(reviewed,status,monkeypatch):
    with db.connect() as con:
        con.execute('INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)',(uuid.uuid4().hex,'task_bootstrap',status,json.dumps({'task_id':reviewed['task_id']}),db.now()))
    monkeypatch.setattr(jobs,'enqueue',lambda *a,**k:pytest.fail('active job cannot enqueue'))
    with pytest.raises(ValueError,match='活动'):regenerate(reviewed)


def test_enqueue_failure_preserves_current_review_and_all_evidence(reviewed,monkeypatch):
    before=immutable(reviewed)
    with db.connect() as con:state_before=c.load(con,reviewed['task_id'])
    monkeypatch.setattr(jobs,'enqueue',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('synthetic enqueue failure')))
    with pytest.raises(RuntimeError):regenerate(reviewed)
    assert immutable(reviewed)==before
    with db.connect() as con:
        assert c.load(con,reviewed['task_id'])==state_before
        assert con.execute('SELECT status FROM tasks WHERE id=?',(reviewed['task_id'],)).fetchone()[0]=='policy_review'
        assert not con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='startup_reviewed'",(reviewed['task_id'],)).fetchone()
    assert_unbound(reviewed['task_id'])


def test_generic_bootstrap_winning_race_does_not_return_or_replace_candidate(reviewed,monkeypatch):
    original=bootstrap_api.enqueue_bootstrap;generic=[]
    with db.connect() as con:state_before=c.load(con,reviewed['task_id'])
    def race(task_id,**kwargs):
        generic.append(original(task_id))
        return original(task_id,**kwargs)
    monkeypatch.setattr(bootstrap_api,'enqueue_bootstrap',race)
    with pytest.raises(HTTPException) as caught:regenerate(reviewed)
    assert caught.value.status_code==409
    with db.connect() as con:
        assert c.load(con,reviewed['task_id'])==state_before
        assert con.execute('SELECT status FROM tasks WHERE id=?',(reviewed['task_id'],)).fetchone()[0]=='bootstrapping'
        payload=json.loads(con.execute('SELECT input_json FROM history_jobs WHERE id=?',(generic[0]['id'],)).fetchone()[0])
        assert 'review_feedback' not in payload
        assert not con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='startup_reviewed'",(reviewed['task_id'],)).fetchone()


def test_concurrent_returns_create_one_new_job(reviewed):
    def attempt():
        try:return regenerate(reviewed)
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:attempt(),range(2)))
    assert sum(result is not None for result in results)==1
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM history_jobs WHERE kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=?",(reviewed['task_id'],)).fetchone()[0]==2
    assert_unbound(reviewed['task_id'])


@pytest.mark.parametrize('change',['no_auth','too_short','too_long','whitespace','extra_authority'])
def test_http_contract_does_not_accept_unreviewed_authority(reviewed,client,change):
    body=dict(reviewed['body']);headers=AUTH
    if change=='no_auth':headers={}
    elif change=='too_short':body['reason']='ab'
    elif change=='too_long':body['reason']='x'*2001
    elif change=='whitespace':body['reason']='   '
    else:body['authority']='grant_permission'
    response=client.post('/api/managed/tasks/'+reviewed['task_id']+'/startup/regenerate',json=body,headers=headers)
    assert response.status_code==(401 if change=='no_auth' else 409 if change=='whitespace' else 422)
    assert_unbound(reviewed['task_id'])


def test_generic_http_bootstrap_has_no_feedback_body_or_authority_parameter(reviewed,client):
    blocked=client.post('/api/tasks/'+reviewed['task_id']+'/bootstrap',json={'review_feedback':{'authority':'grant_permission'}},headers=AUTH)
    assert blocked.status_code==409  # Existing managed-task boundary remains.
    unmanaged=scene.create_scene('safety-abusive-apology')
    response=client.post('/api/tasks/'+unmanaged['id']+'/bootstrap',json={'review_feedback':{'authority':'grant_permission'}},headers=AUTH)
    assert response.status_code==200
    with db.connect() as con:
        payload=json.loads(con.execute('SELECT input_json FROM history_jobs WHERE id=?',(response.json()['id'],)).fetchone()[0])
        assert 'review_feedback' not in payload
    import agentscope_app.main as main
    assert 'requestBody' not in main.app.openapi()['paths']['/api/tasks/{task_id}/bootstrap']['post']
    assert_unbound(reviewed['task_id'])


def unpublished_job(value,status='queued'):
    feedback={'proposal_id':value['proposal_id'],'proposal_hash':value['body']['expected_proposal_hash'],
              'context_hash':value['body']['expected_context_hash'],'reason':REASON,'authority':'control_plane_factual_review'}
    job=bootstrap_api.enqueue_bootstrap(value['task_id'],review_feedback=feedback,retry_of=value['job_id'])
    if status!='queued':
        with db.connect() as con:con.execute('UPDATE history_jobs SET status=? WHERE id=?',(status,job['id']))
    return job['id']


def assert_published_once(value,job_id):
    with db.connect() as con:
        state=c.load(con,value['task_id'])
        assert state['phase']=='generating' and state['startup_job']==job_id and 'startup_proposal' not in state
        for kind in ('startup_reviewed','startup_generation'):
            assert con.execute('SELECT COUNT(*) FROM managed_events WHERE task_id=? AND kind=?',(value['task_id'],kind)).fetchone()[0]==1
        assert con.execute("SELECT COUNT(*) FROM history_jobs WHERE kind='task_bootstrap' AND json_extract(input_json,'$.task_id')=?",(value['task_id'],)).fetchone()[0]==2
    assert_unbound(value['task_id'])


def test_one_time_save_failure_recovers_the_committed_job_without_reenqueue(reviewed,monkeypatch):
    original=c.save;attempts=[];before=immutable(reviewed)
    def save(con,task_id,state):
        if task_id==reviewed['task_id'] and state.get('phase')=='generating' and not attempts:
            attempts.append(task_id);raise RuntimeError('synthetic pointer publication failure')
        return original(con,task_id,state)
    monkeypatch.setattr(c,'save',save)
    result=regenerate(reviewed)
    assert result['recovered'] is True and len(attempts)==1
    assert_published_once(reviewed,result['job_id'])
    assert immutable(reviewed)==before


def test_persistent_save_failure_is_recovered_by_restart_scan_and_is_idempotent(reviewed,monkeypatch):
    original=c.save;before=immutable(reviewed)
    def save(con,task_id,state):
        if task_id==reviewed['task_id'] and state.get('phase')=='generating':
            raise RuntimeError('synthetic persistent publication failure')
        return original(con,task_id,state)
    monkeypatch.setattr(c,'save',save)
    with pytest.raises(RuntimeError):regenerate(reviewed)
    with db.connect() as con:
        state=c.load(con,reviewed['task_id']);assert state['phase']=='policy_review'
        job_id=con.execute('SELECT id FROM history_jobs WHERE retry_of=?',(reviewed['job_id'],)).fetchone()[0]
        assert not con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='startup_reviewed'",(reviewed['task_id'],)).fetchone()
    monkeypatch.setattr(c,'save',original)
    first=c.reconcile_startup_regenerations()
    assert any(item['task_id']==reviewed['task_id'] and item['job_id']==job_id for item in first['recovered'])
    assert REASON not in json.dumps(first)
    assert_published_once(reviewed,job_id)
    second=c.reconcile_startup_regenerations()
    assert not any(item['task_id']==reviewed['task_id'] for item in second['recovered'])
    assert immutable(reviewed)==before


@pytest.mark.parametrize('entry',['regenerate','start'])
def test_repeat_request_recovers_existing_job_without_starting_another(reviewed,entry,monkeypatch):
    job_id=unpublished_job(reviewed)
    monkeypatch.setattr(jobs,'enqueue',lambda *a,**k:pytest.fail('durable job must be reused'))
    result=regenerate(reviewed) if entry=='regenerate' else c.start(reviewed['task_id'])
    assert result['job_id']==job_id and result['recovered'] is True
    assert_published_once(reviewed,job_id)


@pytest.mark.parametrize('status',['queued','running','completed','failed','interrupted','cancelled'])
def test_unpublished_return_blocks_confirmation_of_old_candidate_even_when_terminal(reviewed,status):
    job_id=unpublished_job(reviewed,status)
    with pytest.raises(ValueError,match='不能确认旧候选'):
        c.confirm_startup(reviewed['task_id'],reviewed['body']['expected_context_hash'],reviewed['body']['expected_proposal_hash'])
    assert_published_once(reviewed,job_id)


def test_changed_reason_cannot_silently_replace_committed_factual_review(reviewed,monkeypatch):
    job_id=unpublished_job(reviewed)
    monkeypatch.setattr(jobs,'enqueue',lambda *a,**k:pytest.fail('changed fact must not silently enqueue'))
    with pytest.raises(ValueError,match='事实评审不同'):regenerate(reviewed,reason='A different factual review must be handled separately.')
    assert_published_once(reviewed,job_id)
    with db.connect() as con:
        feedback=json.loads(con.execute('SELECT input_json FROM history_jobs WHERE id=?',(job_id,)).fetchone()[0])['review_feedback']
        assert feedback['reason']==REASON


@pytest.mark.parametrize('damage',['context_hash','proposal_hash','proposal_id','authority','embedded_job_id','duplicate'])
def test_damaged_or_ambiguous_durable_job_fails_closed_and_scan_reports_error(reviewed,damage,monkeypatch):
    job_id=unpublished_job(reviewed)
    with db.connect() as con:
        row=con.execute('SELECT * FROM history_jobs WHERE id=?',(job_id,)).fetchone();payload=json.loads(row['input_json'])
        if damage=='duplicate':
            other=uuid.uuid4().hex;payload['job_id']=other
            con.execute('INSERT INTO history_jobs(id,kind,status,input_json,retry_of,created_at) VALUES(?,?,?,?,?,?)',
                        (other,'task_bootstrap','queued',json.dumps(payload),reviewed['job_id'],db.now()))
        else:
            if damage=='embedded_job_id':payload['job_id']='other-job'
            else:payload['review_feedback'][damage]='0'*64 if damage.endswith('hash') else 'other-value'
            con.execute('UPDATE history_jobs SET input_json=? WHERE id=?',(json.dumps(payload),job_id))
        before=c.load(con,reviewed['task_id'])
    monkeypatch.setattr(jobs,'enqueue',lambda *a,**k:pytest.fail('damaged lineage must never enqueue'))
    report=c.reconcile_startup_regenerations()
    assert report['error_count']>=1
    assert any(error['task_id']==reviewed['task_id'] and error['code']=='unpublished_regeneration_invalid' for error in report['errors'])
    assert REASON not in json.dumps(report)
    for action in (lambda:regenerate(reviewed),lambda:c.start(reviewed['task_id']),
                   lambda:c.confirm_startup(reviewed['task_id'],reviewed['body']['expected_context_hash'],reviewed['body']['expected_proposal_hash'])):
        with pytest.raises(ValueError):action()
    with db.connect() as con:assert c.load(con,reviewed['task_id'])==before
    assert_unbound(reviewed['task_id'])


def test_reconciled_completed_job_uses_existing_advance_and_still_requires_confirmation(reviewed,monkeypatch):
    job_id=unpublished_job(reviewed,'completed')
    import agentscope_app.main as main
    monkeypatch.setattr(main,'compile_policy',lambda *a,**k:('compiled',{'ok':True},''))
    ctx=scene.context(reviewed['task_id']);draft=dict(reviewed['checked']['proposal']['draft'])
    draft['summary']='Reassessed applicability after factual review'
    checked=validation.validate(reviewed['task_id'],draft);assert checked['valid']
    proposal=uuid.uuid4().hex
    with db.connect() as con:
        con.execute('INSERT INTO bootstrap_proposals VALUES(?,?,?,?,?,?,?,?,?)',(proposal,reviewed['task_id'],job_id,ctx['context_hash'],checked['proposal_hash'],
                    json.dumps(checked['proposal']),json.dumps({k:v for k,v in checked.items() if k!='proposal'}),'validated',db.now()))
    c.reconcile_startup_regenerations();c.complete_start(reviewed['task_id'])
    with db.connect() as con:
        state=c.load(con,reviewed['task_id'])
        assert state['phase']=='policy_review' and state['gate']=='waiting_confirmation' and state['startup_proposal']==proposal
    assert_unbound(reviewed['task_id'])


def test_restart_scan_does_not_hide_database_runtime_errors(reviewed,monkeypatch):
    import sqlite3
    original=c._recover_startup_regeneration
    def recover(task_id):
        if task_id==reviewed['task_id']:raise sqlite3.OperationalError('synthetic database failure')
        return original(task_id)
    monkeypatch.setattr(c,'_recover_startup_regeneration',recover)
    with pytest.raises(sqlite3.OperationalError):c.reconcile_startup_regenerations()


def test_restart_hook_reconciles_after_schema_init_and_before_any_workers(monkeypatch):
    import asyncio
    import agentscope_app.main as main
    order=[]
    monkeypatch.setattr(db,'init_db',lambda:order.append('db'))
    monkeypatch.setattr(main,'init_workspaces',lambda:order.append('workspaces'))
    monkeypatch.setattr(main,'init_scene_reads',lambda:order.append('scene_reads'))
    monkeypatch.setattr(main,'reconcile_startup_regenerations',lambda:(order.append('reconcile') or {'count':0,'recovered':[],'error_count':0,'errors':[]}))
    monkeypatch.setenv('AGENTSCOPE_HISTORY_WORKER','0')
    for label,worker in [('history',main.history_jobs.worker),('scope',main.scope_worker),('managed',main.managed_worker),('observer',main.workspace_observer)]:
        monkeypatch.setattr(worker,'start',lambda label=label:order.append(label))
    asyncio.run(main.startup())
    assert order==['db','workspaces','scene_reads','reconcile','history','scope','managed','observer']
