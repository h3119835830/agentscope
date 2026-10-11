"""Read-only executable observation, PID reuse and exact target source isolation."""
import copy
import os
from pathlib import Path
import pytest
from agentscope_app import console
from agentscope_app.instances import policy_sources as ps, controller, dsl_policy


def row(ident='agent-a', product='dsh'):
    identity=dict(generation='gen-a',pid=55,start_ticks='100',domain_id=99,host_id='host',boot_id='boot')
    return dict(id=ident,name='Test Agent',mode='controlled',connected=True,agent_type=product,
                **identity,runtime={**identity,'verified':True,'executable':'/opt/launcher/bin.js'})


def test_actual_process_executable_is_read_without_command_or_environment():
    pid=os.getpid();stat=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert ps.process_executable(pid,stat,boot)==os.readlink(f'/proc/{pid}/exe')
    with pytest.raises(ValueError):ps.process_executable(pid,'wrong-start',boot)
    with pytest.raises(ValueError):ps.process_executable(pid,stat,'wrong-boot')


def test_sources_follow_observed_executor_not_product_names(monkeypatch):
    monkeypatch.setattr(ps,'process_executable',lambda *args:'/opt/custom/python3.12')
    fact=ps.source_for(row(product='dsh'))
    assert fact['pattern']=='**/python3.12'
    assert fact['entry']=='/opt/launcher/bin.js'
    assert fact['basis']=='verified-process-executable'
    assert not {'argv','environment','token'} & fact.keys()


@pytest.mark.parametrize('mutate',[
    lambda r:r.update(connected=False),lambda r:r.update(mode='observed'),
    lambda r:r['runtime'].update(verified=False),lambda r:r.update(pid=99),
    lambda r:r['runtime'].update(generation='other'),lambda r:r['runtime'].pop('boot_id'),
])
def test_missing_or_stale_identity_never_reads_or_guesses_executor(monkeypatch,mutate):
    r=row();mutate(r)
    monkeypatch.setattr(ps,'process_executable',lambda *args:pytest.fail('Must not observe unverified PID'))
    fact=ps.source_status(r)
    assert not fact['ready'] and 'pattern' not in fact


def test_failed_read_does_not_substitute_dsh_or_hermes(monkeypatch):
    def fail(*args):raise ValueError('进程已退出')
    monkeypatch.setattr(ps,'process_executable',fail)
    for product in ['dsh','hermes']:
        assert ps.source_status(row(product=product))==dict(ready=False,instance_id='agent-a',message='进程已退出')


def test_exec_change_during_observation_is_rejected(monkeypatch):
    calls=iter(['/opt/bin/node','/opt/bin/python'])
    monkeypatch.setattr(os,'readlink',lambda *args:next(calls))
    pid=os.getpid();stat=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    with pytest.raises(ValueError,match='已变化'):ps.process_executable(pid,stat,boot)


def test_product_sources_and_dsl_context_are_read_only_and_hide_retained_agents(client,monkeypatch):
    rows=[row(),row('agent-b','hermes'),row('hidden')];rows[1]['connected']=False
    monkeypatch.setattr(controller,'listing',lambda:{'instances':copy.deepcopy(rows)})
    monkeypatch.setattr(ps,'process_executable',lambda *args:'/opt/bin/node')
    monkeypatch.setattr(dsl_policy,'detail',lambda scope:dict(scope_id=scope,records=[],targets=[],documents=[]))
    monkeypatch.setattr(console,'hidden',lambda kind:{'hidden'} if kind=='agent' else set())
    admin={'Authorization':'Bearer test-admin-token-not-for-production'}
    assert client.get('/api/console/security/system/dsl').status_code==401
    data=client.get('/api/console/security/system/dsl',headers=admin).json()['source_context']
    assert not data['ready'] and len(data['sources'])==len(data['unavailable'])==1
    assert data['sources'][0]['id']=='agent-a' and data['sources'][0]['pattern']=='**/node'
    assert data['unavailable'][0]['id']=='agent-b'
    own=client.get('/api/console/agents/agent-a/dsl',headers=admin).json()['source_context']
    assert own['ready'] and len(own['sources'])==1
    with pytest.raises(ValueError):ps.source_for(rows[1])


@pytest.mark.parametrize('patch',[
    {'observed_monotonic':90}, {'observed_monotonic':101}, {'boot_id':'other'},
    {'sources':{}}, {'sources':{'agent-a':{'pid':999}}},
])
def test_expired_cross_boot_or_foreign_cached_fact_cannot_be_used(patch):
    r=row();snapshot={'observed_monotonic':99,'boot_id':'boot','sources':{'agent-a':{**r['runtime'],'executable':'/opt/bin/node'}}}
    assert ps.cached_fact(snapshot,r,100)=='/opt/bin/node'
    snapshot.update(patch)
    with pytest.raises(ValueError):ps.cached_fact(snapshot,r,100)


def test_cache_can_bridge_only_permission_isolation_not_pid_drift(monkeypatch):
    r=row()
    def denied(*args):raise PermissionError('Separate API account')
    monkeypatch.setattr(ps,'process_executable',denied)
    monkeypatch.setattr(ps,'cached_executable',lambda current:'/opt/bin/node' if current['id']=='agent-a' else pytest.fail('Wrong Agent'))
    assert ps.source_for(r)['pattern']=='**/node'
    def changed(*args):raise ValueError('Process changed')
    monkeypatch.setattr(ps,'process_executable',changed)
    with pytest.raises(ValueError):ps.source_for(r)



def test_source_sampler_only_reads_admitted_open_identities_and_never_exports_runtime_secrets(tmp_path,monkeypatch):
    import importlib.util,json,sqlite3
    script=Path(__file__).resolve().parents[2]/'scripts/observe_agent_policy_sources.py'
    spec=importlib.util.spec_from_file_location('source_sampler_test',script);sampler=importlib.util.module_from_spec(spec);spec.loader.exec_module(sampler)
    dbfile=tmp_path/'source.sqlite3';boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    runtime={**row()['runtime'],'boot_id':boot,'private_test_field':'never-export'}
    with sqlite3.connect(dbfile) as con:
        con.execute('CREATE TABLE agent_instances(id,mode,gate,generation,runtime_json)')
        for ident,mode,gate,gen in [('admitted','controlled','open','gen-a'),('stopped','controlled','closed','gen-a'),('observed','observed','open','gen-a'),('stale','controlled','open','old')]:
            con.execute('INSERT INTO agent_instances VALUES(?,?,?,?,?)',(ident,mode,gate,gen,json.dumps(runtime)))
    before=dbfile.read_bytes();calls=[]
    monkeypatch.setattr(sampler,'process_executable',lambda *args:calls.append(args) or '/opt/bin/node')
    snapshot=sampler.collect(dbfile)
    assert list(snapshot['sources'])==['admitted'] and len(calls)==1
    assert 'never-export' not in json.dumps(snapshot) and 'entry' not in snapshot['sources']['admitted']
    assert dbfile.read_bytes()==before


def test_api_rejects_untrusted_or_writable_snapshot_files(tmp_path,monkeypatch):
    cache=tmp_path/'facts.json';cache.write_text('{}');cache.chmod(0o666)
    monkeypatch.setattr(ps,'CACHE',cache)
    with pytest.raises(ValueError,match='尚未核验'):ps.cached_executable(row())
