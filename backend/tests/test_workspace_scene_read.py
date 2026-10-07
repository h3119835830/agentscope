"""Read-only scene recognition: frozen evidence and independent bounded capabilities."""
import json
import threading
import uuid
from pathlib import Path
import pytest
from fastapi import HTTPException
from agentscope_app import db, pi_rpc
from agentscope_app.bootstrap.scene import digest
from agentscope_app.history import jobs
from agentscope_app.workspaces import registry, scene_read as scene
from agentscope_app.workspaces.observer import observer


@pytest.fixture
def workspace(tmp_path,monkeypatch):
    db.init_db();registry.init();scene.init()
    root=tmp_path/'sources';root.mkdir()
    project=root/'project';project.mkdir()
    (project/'README.md').write_text('A sample library.\nExplicit task: add a focused regression test.\nDo not edit protected files.\n')
    monkeypatch.setattr(registry,'WORKSPACE_ROOT',root)
    monkeypatch.setattr(observer,'rows',{})
    return registry.register(str(project),'scene-test')


def create(workspace,supplement=''):
    manifest,_=registry.scan(workspace['path'])
    return scene.create(workspace['id'],manifest['manifest_hash'],supplement)


def running(workspace,supplement=''):
    read=create(workspace,supplement)
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='running' WHERE id=?",(read['id'],))
    return read,scene.issue(read['id'])


def sources(read,token):return scene.invoke(read['id'],'list_scene_sources',{},token)['sources']
def read_source(read,token,source,**args):return scene.invoke(read['id'],'read_scene_source',{'source_id':source['source_id'],**args},token)
def draft(source,quote='Explicit task: add a focused regression test.',**changes):
    return {'name':'Regression test','goal':'Add a focused regression test.','state':'ready','constraints':['Do not edit protected files.'],'clarification':'','evidence':[{k:source[k] for k in ('source_id','relative_path','sha256')}|{'quote':quote}],**changes}
def submit(read,token,value):return scene.invoke(read['id'],'submit_scene_draft',{'draft':value},token)
def complete(read):
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='completed' WHERE id=?",(read['id'],))


def test_create_frozen_manifest_has_no_execution_side_effects(workspace):
    with db.connect() as con:before=[con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('tasks','managed_tasks','policy_versions','task_credentials')]
    read=create(workspace)
    assert read['status']=='queued' and read['read_only'] and read['task_id'] is None and read['draft'] is None
    with db.connect() as con:
        assert before==[con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('tasks','managed_tasks','policy_versions','task_credentials')]
        row=con.execute('SELECT kind,input_json FROM history_jobs WHERE id=?',(read['id'],)).fetchone()
    assert row['kind']=='workspace_scene_read' and json.loads(row['input_json'])=={'read_id':read['id']}


def test_source_set_excludes_secrets_private_sessions_and_evaluator_not_tests(workspace):
    root=Path(workspace['path'])
    for path in ('.env','.env.local','.dsh/session.sqlite','utils/evaluator.py','oracle_policy.dsl','.agentscope-private/native.json','tests/test_goal.py'):
        target=root/path;target.parent.mkdir(exist_ok=True);target.write_text('do not expose reserved material')
    read,token=running(workspace)
    paths={s['relative_path'] for s in sources(read,token)}
    assert paths=={'README.md','tests/test_goal.py'}
    with db.connect() as con:manifest=json.loads(con.execute('SELECT manifest_json FROM workspace_scene_reads WHERE id=?',(read['id'],)).fetchone()[0])
    assert {x['relative_path'] for x in manifest['files']}==paths


def test_tools_use_snapshot_even_after_project_changed(workspace):
    read,token=running(workspace)
    (Path(workspace['path'])/'README.md').write_text('malicious replacement')
    (Path(workspace['path'])/'later.txt').write_text('new file')
    listed=sources(read,token)
    assert len(listed)==1
    result=read_source(read,token,listed[0])
    assert 'Explicit task:' in result['content'] and 'replacement' not in result['content']
    assert submit(read,token,draft(listed[0]))['valid']
    public=scene.get(workspace['id'],read['id'])
    assert public['draft_hash']==digest(public['draft'])
    assert public['evidence'][0]['byte_count']==len(result['content'].encode())


def test_quote_must_be_from_actual_successful_byte_slice(workspace):
    read,token=running(workspace);source=sources(read,token)[0]
    assert not submit(read,token,draft(source))['valid']
    read_source(read,token,source,limit=17)
    result=submit(read,token,draft(source))
    assert result['diagnostic']=='scene_quote_not_in_actual_read'
    read_source(read,token,source,offset=18)
    assert submit(read,token,draft(source))['valid']
    assert not submit(read,token,draft(source))['valid']


@pytest.mark.parametrize('field,value',[('relative_path','other.md'),('sha256','f'*64),('source_id','foreign')])
def test_forged_evidence_rejected(workspace,field,value):
    read,token=running(workspace);source=sources(read,token)[0];read_source(read,token,source)
    proposal=draft(source);proposal['evidence'][0][field]=value
    assert submit(read,token,proposal)['diagnostic']=='scene_evidence_source_mismatch'


def test_cross_job_and_workspace_isolation(workspace):
    first,token=running(workspace);second,token2=running(workspace)
    source=sources(first,token)[0]
    with pytest.raises(HTTPException) as error:scene.invoke(second['id'],'list_scene_sources',{},token)
    assert error.value.status_code==401
    assert read_source(second,token2,source)['diagnostic']=='scene_source_not_readable'
    with pytest.raises(HTTPException) as error:scene.get('foreign-workspace',first['id'])
    assert error.value.status_code==404


def test_clarification_requires_read_and_quote_when_text_exists(workspace):
    (Path(workspace['path'])/'README.md').write_text('Sample library installation instructions only.')
    read,token=running(workspace);source=sources(read,token)[0]
    value=draft(source,goal='',state='needs_clarification',clarification='What concrete change should be made?',evidence=[])
    assert submit(read,token,value)['diagnostic']=='scene_clarification_requires_read_evidence'
    value['evidence']=draft(source,quote='Sample library installation instructions only.')['evidence']
    assert submit(read,token,value)['diagnostic']=='scene_quote_not_in_actual_read'
    read_source(read,token,source)
    assert submit(read,token,value)['valid']
    complete(read)
    with pytest.raises(ValueError,match='scene_requires_clarification'):scene.adoption_preview(workspace['id'],read['id'],scene.get(workspace['id'],read['id'])['draft_hash'],read['manifest_hash'])


def test_binary_only_can_request_explicit_metadata_based_clarification(workspace):
    root=Path(workspace['path']);(root/'README.md').unlink();(root/'photo.bin').write_bytes(b'\x00\x80')
    read,token=running(workspace);source=sources(read,token)[0]
    assert not source['readable']
    value=draft(source,goal='',state='needs_clarification',clarification='Only unreadable binary content is available; what is the task?',evidence=[])
    assert submit(read,token,value)['valid']


def test_supplement_is_own_source_and_new_job(workspace):
    first,token=running(workspace,'Please add a regression test for parsing.')
    second=create(workspace,'Please document the parser instead.')
    assert first['id']!=second['id'] and first['manifest_hash']==second['manifest_hash']
    source=next(s for s in sources(first,token) if s['kind']=='user')
    assert read_source(first,token,source)['content']=='Please add a regression test for parsing.'
    assert submit(first,token,draft(source,quote='Please add a regression test for parsing.'))['valid']


def test_manifest_mismatch_and_generation_race_create_nothing(workspace,monkeypatch):
    with pytest.raises(ValueError,match='scene_manifest_changed'):scene.create(workspace['id'],'wrong')
    original=registry.get_workspace;calls=[]
    def changing(ident):
        row=original(ident);row['instance_generation']='before' if not calls else 'after';calls.append(ident);return row
    monkeypatch.setattr(registry,'get_workspace',changing)
    with pytest.raises(ValueError,match='scene_source_generation_changed'):create(workspace)
    with db.connect() as con:assert not con.execute('SELECT 1 FROM workspace_scene_reads WHERE workspace_id=?',(workspace['id'],)).fetchone()


def test_create_actively_observes_native_generation_before_and_after(workspace,monkeypatch):
    source=workspace|{'agent_id':'native-dsh','instance_generation':'g1'}
    monkeypatch.setattr(registry,'get_workspace',lambda ident:dict(source))
    seen=[];monkeypatch.setattr(observer,'collect',lambda agent:seen.append(agent))
    create(workspace)
    assert seen==['native-dsh','native-dsh']


@pytest.mark.parametrize('tamper',["UPDATE workspace_scene_sources SET text='modified' WHERE read_id=?","UPDATE workspace_scene_sources SET sha256='modified' WHERE read_id=?","UPDATE workspace_scene_reads SET manifest_hash='modified' WHERE id=?"])
def test_frozen_integrity_failures_detected(workspace,tamper):
    read=create(workspace)
    with db.connect() as con:con.execute(tamper,(read['id'],))
    with pytest.raises(ValueError,match='integrity_failed'):scene.get(workspace['id'],read['id'])


def test_independent_budget_expiry_and_revocation(workspace,monkeypatch):
    read,token=running(workspace)
    with db.connect() as con:con.execute('UPDATE scene_read_credentials SET calls=? WHERE read_id=?',(scene.BUDGET-1,read['id']))
    assert sources(read,token)
    with pytest.raises(HTTPException) as error:sources(read,token)
    assert error.value.status_code==429
    with db.connect() as con:con.execute('UPDATE scene_read_credentials SET expires_at=0 WHERE read_id=?',(read['id'],))
    with pytest.raises(HTTPException) as error:sources(read,token)
    assert error.value.status_code==401
    scene.revoke(read['id'])
    with db.connect() as con:assert con.execute('SELECT revoked_at FROM scene_read_credentials WHERE read_id=?',(read['id'],)).fetchone()[0]


def test_public_sources_draft_errors_runtime_and_traces_do_not_leak(workspace):
    secret='SENSITIVE_UNIQUE_VALUE'
    (Path(workspace['path'])/'README.md').write_text('Task: add tests.\napi_key='+secret+'\n<think>PRIVATE_UNIQUE_REASONING</think>\n')
    read,token=running(workspace);source=sources(read,token)[0]
    result=read_source(read,token,source)
    assert secret not in result['content'] and 'PRIVATE_UNIQUE_REASONING' not in result['content']
    value=draft(source,quote='Task: add tests.',goal='Add tests. password='+secret)
    assert submit(read,token,value)['valid']
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='failed',error=?,input_json=? WHERE id=?",('provider dump '+secret,json.dumps({'runtime':{'model':secret,'private_reasoning':secret,'allowed_tools':['shell'],'lifecycle':{'protocol':secret}}}),read['id']))
    public=json.dumps(scene.get(workspace['id'],read['id']))
    assert secret not in public and 'PRIVATE_UNIQUE_REASONING' not in public and token not in public and 'shell' not in public


def test_preview_and_binding_are_atomic_and_do_not_consume_early(workspace,seed_task):
    read,token=running(workspace);source=sources(read,token)[0];read_source(read,token,source);submit(read,token,draft(source));complete(read)
    public=scene.get(workspace['id'],read['id']);preview=scene.adoption_preview(workspace['id'],read['id'],public['draft_hash'],read['manifest_hash'])
    assert preview['id']==preview['read_id']==read['id'] and preview['evidence']
    task=uuid.uuid4().hex;seed_task(task)
    with pytest.raises(RuntimeError):
        with db.connect() as con:
            scene.bind_adoption(con,read['id'],workspace['id'],public['draft_hash'],read['manifest_hash'],None,task)
            raise RuntimeError('transaction rollback')
    assert scene.get(workspace['id'],read['id'])['task_id'] is None
    with db.connect() as con:scene.bind_adoption(con,read['id'],workspace['id'],public['draft_hash'],read['manifest_hash'],None,task)
    assert scene.get(workspace['id'],read['id'])['task_id']==task
    with db.connect() as con:
        with pytest.raises(ValueError):scene.bind_adoption(con,read['id'],workspace['id'],public['draft_hash'],read['manifest_hash'],None,task)
    with pytest.raises(ValueError,match='already_adopted'):scene.adoption_preview(workspace['id'],read['id'],public['draft_hash'],read['manifest_hash'])


@pytest.mark.parametrize('field,value',[('draft_hash','wrong'),('manifest_hash','wrong'),('source_generation','wrong')])
def test_binding_stale_identity_rejected_without_consuming(workspace,seed_task,field,value):
    read,token=running(workspace);source=sources(read,token)[0];read_source(read,token,source);submit(read,token,draft(source));complete(read)
    public=scene.get(workspace['id'],read['id']);task=uuid.uuid4().hex;seed_task(task)
    args={'read_id':read['id'],'workspace_id':workspace['id'],'draft_hash':public['draft_hash'],'expected_manifest_hash':read['manifest_hash'],'source_generation':None,'task_id':task}
    args['expected_manifest_hash' if field=='manifest_hash' else field]=value
    with db.connect() as con:
        with pytest.raises(ValueError):scene.bind_adoption(con,**args)
    assert scene.get(workspace['id'],read['id'])['task_id'] is None


def test_worker_restart_revokes_scene_credentials_and_marks_interrupted(workspace,monkeypatch):
    read,token=running(workspace)
    worker=jobs.Worker();monkeypatch.setenv('AGENTSCOPE_HISTORY_WORKER','1')
    monkeypatch.setattr(threading.Thread,'start',lambda self:None)
    worker.start()
    assert scene.get(workspace['id'],read['id'])['status']=='interrupted'
    with db.connect() as con:assert con.execute('SELECT revoked_at FROM scene_read_credentials WHERE read_id=?',(read['id'],)).fetchone()[0]
    with pytest.raises(HTTPException):sources(read,token)


def fake_runtime(tmp_path,monkeypatch):
    integration=tmp_path/'integration';package=integration/'node_modules/@earendil-works/pi-coding-agent';package.mkdir(parents=True)
    (package/'package.json').write_text('{"version":"1.0.1"}')
    for name in ('scene-read-extension.ts','scene-read-system.md','package-lock.json'):(integration/name).write_text('fixture')
    state=tmp_path/'state';state.mkdir()
    monkeypatch.setattr(scene,'INTEGRATION',integration);monkeypatch.setattr(scene,'STATE_DIR',state);monkeypatch.setenv('AGENTSCOPE_HISTORY_LLM_KEY','TEST_PROVIDER_SECRET')
    return integration


def test_runner_sandbox_fixed_tools_trace_allowlist_and_job_routing(workspace,tmp_path,monkeypatch):
    integration=fake_runtime(tmp_path,monkeypatch)
    read=create(workspace);commands=[]
    def drive(command,environment,prompt,status,trace):
        commands.append(command)
        assert status()['remaining_tool_calls']==40 and not status()['submitted']
        token=environment['AGENTSCOPE_SCENE_READ_TOKEN'];source=sources(read,token)[0];read_source(read,token,source)
        trace({'kind':'tool_start','tool':'read_scene_source','args':{'secret':'UNIQUE_TRACE_SECRET','private_reasoning':'UNIQUE_PRIVATE_REASONING'},'diagnostic':'UNIQUE_DIAGNOSTIC'})
        assert submit(read,token,draft(source))['valid'] and status()['submitted']
        return {'continuations':0,'protocol':'Pi RPC agent_settled; server submission verified','raw_stream':'UNIQUE_RAW_STREAM'}
    monkeypatch.setattr(pi_rpc,'drive',drive)
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='running' WHERE id=?",(read['id'],))
    result=jobs.execute('workspace_scene_read',{'read_id':read['id'],'task_id':'forbidden'})
    assert result['read_only']
    command=commands[0]
    assert command[0]=='/usr/bin/bwrap' and '--no-builtin-tools' in command
    assert command[command.index('--tools')+1]==','.join(scene.TOOLS)
    assert workspace['path'] not in command and str(db.DB_PATH) not in command and '--no-context-files' in command
    with db.connect() as con:
        assert con.execute('SELECT revoked_at FROM scene_read_credentials WHERE read_id=?',(read['id'],)).fetchone()[0]
        serialized=' '.join(r[0] for r in con.execute('SELECT metadata_json FROM scene_read_events WHERE read_id=?',(read['id'],)))
    serialized+=json.dumps(scene.get(workspace['id'],read['id']))
    for secret in ('UNIQUE_TRACE_SECRET','UNIQUE_PRIVATE_REASONING','UNIQUE_DIAGNOSTIC','UNIQUE_RAW_STREAM','TEST_PROVIDER_SECRET'):assert secret not in serialized


def test_runner_failure_is_fixed_code_and_revokes_capability(workspace,tmp_path,monkeypatch):
    fake_runtime(tmp_path,monkeypatch);read=create(workspace)
    with db.connect() as con:con.execute("UPDATE history_jobs SET status='running' WHERE id=?",(read['id'],))
    monkeypatch.setattr(pi_rpc,'drive',lambda *args:(_ for _ in ()).throw(RuntimeError('UNIQUE_PROVIDER_SECRET')))
    with pytest.raises(ValueError,match='^scene_read_failed$'):scene.run(read['id'])
    with db.connect() as con:assert con.execute('SELECT revoked_at FROM scene_read_credentials WHERE read_id=?',(read['id'],)).fetchone()[0]
