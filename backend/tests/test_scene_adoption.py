"""Independent acceptance of scene draft adoption; never invokes a model or Broker."""
import grp
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import HTTPException

from agentscope_app import db
from agentscope_app.bootstrap import scene
from agentscope_app.bootstrap.validation import validate
from agentscope_app.managed import controller
from agentscope_app.workspaces import registry, scene_read
from agentscope_app.workspaces import observer as observations

README = "Explain the project clearly.\nPreserve existing tests.\n"


@pytest.fixture
def project(client, tmp_path, monkeypatch):
    monkeypatch.setattr(registry, 'WORKSPACE_ROOT', tmp_path)
    monkeypatch.delenv('AGENTSCOPE_DSH_WORKSPACE_ROOTS', raising=False)
    monkeypatch.setenv('AGENTSCOPE_TASK_GROUP', grp.getgrgid(os.getgid()).gr_name)
    monkeypatch.setattr(registry, 'effective_dsh', lambda: {'model': 'isolated-test'})
    monkeypatch.setattr(controller, 'broker', lambda *a, **k: pytest.fail('scene adoption must not execute or authorize'))
    value = registry.create_workspace('Scene source')
    root = Path(value['path'])
    (root / 'README.md').write_text(README)
    (root / 'tests').mkdir()
    (root / 'tests/test_main.py').write_text('def test_main():\n    assert True\n')
    return value


def ready(project, *, completed=True):
    manifest = registry.inventory(project['id'])['manifest_hash']
    created = scene_read.create(project['id'], manifest)
    read_id = created['id']
    with db.connect() as con:
        con.execute("UPDATE history_jobs SET status='running' WHERE id=?", (read_id,))
    token = scene_read.issue(read_id)
    sources = scene_read.invoke(read_id, 'list_scene_sources', {}, token)['sources']
    source = next(s for s in sources if s['relative_path'] == 'README.md')
    evidence = scene_read.invoke(read_id, 'read_scene_source', {'source_id': source['source_id']}, token)
    submitted = scene_read.invoke(read_id, 'submit_scene_draft', {'draft': {
        'name': 'Explain project', 'goal': 'Explain the project clearly.',
        'state': 'ready', 'constraints': ['Use a clear explanation.'], 'clarification': '',
        'evidence': [{'source_id': source['source_id'], 'relative_path': 'README.md',
                      'sha256': source['sha256'], 'quote': 'Explain the project clearly.'}]
    }}, token)
    assert submitted['valid'] is True
    if completed:
        with db.connect() as con:
            con.execute("UPDATE history_jobs SET status='completed' WHERE id=?", (read_id,))
    return read_id, submitted['draft_hash'], manifest, evidence


def adopt(project, job):
    return registry.create_task_from_scene(project['id'], *job[:3])


def linked_tasks(workspace_id):
    with db.connect() as con:
        return [r[0] for r in con.execute('SELECT task_id FROM workspace_task_sources WHERE workspace_id=?', (workspace_id,))]


def test_scene_submit_and_adoption_preserve_zero_execution_and_constraint_validation(project):
    job = ready(project, completed=False)
    assert linked_tasks(project['id']) == []
    with pytest.raises(ValueError, match='incomplete'):
        adopt(project, job)
    with db.connect() as con:
        con.execute("UPDATE history_jobs SET status='completed' WHERE id=?", (job[0],))
    task = adopt(project, job)
    ctx = scene.context(task['id'])
    assert ctx['declared_constraints'] == []
    assert ctx['accepted_task_constraints'] == ['Use a clear explanation.']
    with db.connect() as con:
        assert 'Use a clear explanation.' in con.execute('SELECT prompt FROM tasks WHERE id=?', (task['id'],)).fetchone()[0]
    assert ctx['workspace_scene_read']['id'] == job[0]
    assert ctx['workspace_scene_read']['draft_hash'] == job[1]
    assert any(r['source_id'] == job[3]['source_id'] for r in ctx['workspace_scene_read']['evidence'])
    checked = validate(task['id'], {'context_hash': ctx['context_hash'], 'summary': 'Explain the project',
        'no_op': True, 'guidance': ['Use a clear explanation.']}, compile_bundle=False)
    assert checked['valid']
    with db.connect() as con:
        state = controller.load(con, task['id'])
        assert state['phase'] == 'prepared' and state['version'] == 0 and state['session_id'] is None
        assert state['startup_review_required']
        assert con.execute('SELECT COUNT(*) FROM policy_versions WHERE task_id=?', (task['id'],)).fetchone()[0] == 0


def test_scene_read_can_be_adopted_only_once_under_concurrent_requests(project):
    job = ready(project)
    def attempt():
        try: return adopt(project, job)['id']
        except ValueError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(r is not None for r in results) == 1
    assert linked_tasks(project['id']) == [next(r for r in results if r)]
    with db.connect() as con:
        assert con.execute('SELECT task_id FROM workspace_scene_reads WHERE id=?', (job[0],)).fetchone()[0] == next(r for r in results if r)


def test_bind_failure_rolls_back_task_context_sources_and_adoption(project, monkeypatch):
    job = ready(project)
    original = scene_read.bind_adoption
    attempted = []
    def fail_after_bind(con, *args):
        attempted.append(args[-1])
        original(con, *args)
        raise ValueError('injected_adoption_failure')
    monkeypatch.setattr(scene_read, 'bind_adoption', fail_after_bind)
    with pytest.raises(ValueError, match='injected_adoption_failure'):
        adopt(project, job)
    assert len(attempted) == 1 and linked_tasks(project['id']) == []
    with db.connect() as con:
        for table, key in [('tasks','id'), ('bootstrap_contexts','task_id'), ('bootstrap_sources','task_id')]:
            assert con.execute(f'SELECT COUNT(*) FROM {table} WHERE {key}=?', (attempted[0],)).fetchone()[0] == 0
        assert con.execute('SELECT task_id FROM workspace_scene_reads WHERE id=?', (job[0],)).fetchone()[0] is None


def test_cross_workspace_adoption_is_rejected_even_with_identical_bytes(project):
    job = ready(project)
    other = registry.create_workspace('Same bytes different source')
    root = Path(other['path'])
    (root / 'README.md').write_text(README)
    (root / 'tests').mkdir()
    (root / 'tests/test_main.py').write_text('def test_main():\n    assert True\n')
    assert registry.inventory(other['id'])['manifest_hash'] == job[2]
    with pytest.raises(HTTPException) as error:
        adopt(other, job)
    assert error.value.status_code == 404
    assert linked_tasks(other['id']) == [] and linked_tasks(project['id']) == []


def test_manifest_drift_cannot_consume_scene_read_or_create_task(project):
    job = ready(project)
    (Path(project['path']) / 'README.md').write_text('different source bytes')
    with pytest.raises(ValueError, match='已变化'):
        adopt(project, job)
    assert linked_tasks(project['id']) == []
    assert scene_read.get(project['id'], job[0])['task_id'] is None


@pytest.mark.parametrize('change_at', [1,2])
def test_adoption_forces_fresh_native_generation_before_and_after_scan(project, monkeypatch, change_at):
    observer = observations.Observer()
    monkeypatch.setattr(observations, 'observer', observer)
    def publish(generation):
        row = {'id':'native-dsh', 'kind':'native', 'connected':True, 'available':True, 'status':'connected',
            'generation':generation, 'pid':os.getpid(), 'start_ticks':'test-start', 'roots':[project['path']],
            'workspaces':[{'workspaceId':'native-workspace', 'path':project['path'], 'sessionIds':[]}],
            '_monotonic':time.monotonic()}
        observer.rows[row['id']] = row
        registry.sync_observation(row)
    publish('g1')
    native = registry.workspaces('native-dsh')['workspaces'][0]
    monkeypatch.setattr(observer, 'collect', lambda selected=None: publish('g1'))
    job = ready(native)
    calls = []
    def collect(selected=None):
        calls.append(selected)
        publish('g2' if len(calls) >= change_at else 'g1')
    monkeypatch.setattr(observer, 'collect', collect)
    with pytest.raises(ValueError, match='已变化'):
        adopt(native, job)
    assert len(calls) == change_at
    assert linked_tasks(native['id']) == []
    assert scene_read.get(native['id'], job[0])['task_id'] is None


def test_snapshot_uses_verified_captured_bytes_not_later_mutable_source(project, monkeypatch):
    job = ready(project)
    original = registry.scan
    def scan_then_change(path, with_bytes=False):
        value = original(path, with_bytes)
        if with_bytes:
            (Path(path) / 'README.md').write_text('changed after captured bytes')
        return value
    monkeypatch.setattr(registry, 'scan', scan_then_change)
    task = adopt(project, job)
    assert (Path(task['workspace']) / 'README.md').read_text() == README
    assert (Path(project['path']) / 'README.md').read_text() != README
    assert scene.context(task['id'])['workspace_source']['manifest_hash'] == job[2]


def test_oracle_and_private_assets_are_excluded_from_reading_and_snapshot(project):
    root = Path(project['path'])
    for relative in ['utils/evaluator.py', '.oracle/answer.json', '.env', '.dsh/session.sqlite']:
        path = root / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text('NON_PUBLIC_MATERIAL')
    job = ready(project)
    with db.connect() as con:
        paths = {r[0] for r in con.execute('SELECT relative_path FROM workspace_scene_sources WHERE read_id=?', (job[0],))}
    assert paths == {'README.md', 'tests/test_main.py'}
    task = adopt(project, job)
    paths = {p.relative_to(task['workspace']).as_posix() for p in Path(task['workspace']).rglob('*') if p.is_file()}
    assert paths == {'README.md', 'tests/test_main.py'}


def test_adopted_scene_archive_preserves_safe_task_scoped_receipts_without_live_source(project, seed_task, monkeypatch):
    import uuid
    from agentscope_app.archive import projection as archive
    marker = 'NONQUOTED_PROJECT_CONTENT_MUST_NOT_APPEAR_IN_ARCHIVE'
    root = Path(project['path'])
    (root / 'README.md').write_text(README + marker + '\n')
    (root / '.env').write_text('token=UNEXPORTED_SCENE_SECRET')
    job = ready(project)
    task = adopt(project, job)
    foreign = uuid.uuid4().hex[:16]
    seed_task(foreign)
    root.rename(root.with_name(root.name + '-missing'))
    def forbidden(*args, **kwargs):
        pytest.fail('offline archive must not inspect source or contact observer/Broker')
    monkeypatch.setattr(registry, 'get_workspace', forbidden)
    monkeypatch.setattr(registry, 'inventory', forbidden)
    monkeypatch.setattr(observations.observer, 'collect', forbidden)
    monkeypatch.setattr(observations.observer, 'require', forbidden)
    monkeypatch.setattr(observations, 'broker', forbidden)

    overview = archive.archive(task['id'], limit=200)
    assert any(event['kind'] == 'workspace_scene_read' for event in overview['stage_previews']['preparation']['highlights'])
    timeline = archive.events(task['id'], 'timeline', limit=200)['events']
    tools = archive.events(task['id'], 'tools', limit=200)['events']
    reading = next(e for e in timeline if e['kind'] == 'workspace_scene_read')
    detail = archive.event_detail(task['id'], reading['id'])
    assert reading['source_id'] == job[0] and reading['task_id'] == task['id']
    assert detail['action_source'] == 'pi_scene_reader' and detail['history_only']
    assert detail['detail']['read_only'] is True
    assert detail['detail']['draft_hash'] == job[1] and detail['detail']['manifest_hash'] == job[2]
    assert detail['detail']['draft']['goal'] == 'Explain the project clearly.'
    assert detail['detail']['draft']['constraints'] == ['Use a clear explanation.']
    assert overview['header']['constraints']['accepted_task_constraints'] == ['Use a clear explanation.']
    context_event = next(e for e in timeline if e['kind'] == 'task_context')
    context_detail = archive.event_detail(task['id'], context_event['id'])
    assert context_detail['detail']['workspace_scene_read']['id'] == job[0]
    assert context_detail['detail']['workspace_scene_read']['draft_hash'] == job[1]
    reads = [e for e in tools if e['kind'] == 'read_scene_source']
    assert len(reads) == 1
    read_detail = archive.event_detail(task['id'], reads[0]['id'])
    receipt = read_detail['detail']['receipt']
    assert receipt['source_id'] == job[3]['source_id']
    assert receipt['sha256'] == job[3]['sha256']
    assert receipt['excerpt_sha256'] == job[3]['excerpt_sha256']
    assert reads[0]['task_id'] == task['id'] and read_detail['action_source'] == 'pi_scene_reader'

    details = [archive.event_detail(task['id'], e['id']) for e in timeline + tools]
    serialized = json.dumps([overview, details])
    for private in (marker, 'UNEXPORTED_SCENE_SECRET', 'token_hash', 'workspace_scene_sources', 'public_sha256'):
        assert private not in serialized
    for event in (reading, reads[0]):
        with pytest.raises(HTTPException) as error:
            archive.event_detail(foreign, event['id'])
        assert error.value.status_code == 404
    assert not any(e['source_id'] == job[0] for e in archive.events(foreign)['events'])
