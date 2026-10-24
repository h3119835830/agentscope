"""Runtime binding tests independent of a privileged kernel."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from broker import instance_runtime as r
from agentscope_app.instances.mapping import translate

def test_controlled_instance_execution_requires_an_explicit_deployment_profile(monkeypatch):
    monkeypatch.setattr(r,'B',SimpleNamespace(RUNTIME=Path('/run/agentscope-preview')))
    monkeypatch.delenv('AGENTSCOPE_CONTROLLED_INSTANCE_PROFILE',raising=False)
    assert not r.controlled_instance_execution_enabled()
    for profile in ('isolated-acceptance','production'):
        assert r.controlled_instance_execution_enabled(profile=profile)
    assert not r.controlled_instance_execution_enabled(profile='preview')
    assert r.controlled_instance_execution_enabled(runtime_name='agentscope-scope-demo',profile='')

def test_dsh_and_generic_agents_use_the_configured_agent_identity(monkeypatch):
    agent=SimpleNamespace(pw_name='agentscope-agent',pw_uid=994,pw_gid=985)
    monkeypatch.setattr(r,'B',SimpleNamespace(AGENT=agent,TASK_GID=987))
    assert r.execution_user('dsh') is agent
    assert r.execution_user('other') is agent
    assert r.execution_gid()==987

def test_instance_state_uses_the_dedicated_runtime_root(monkeypatch,tmp_path):
    dedicated=tmp_path/'controlled-instances'
    monkeypatch.setattr(r,'B',SimpleNamespace(TASK_ROOT=tmp_path/'api-private',INSTANCE_ROOT=dedicated))
    value='instance-0000000000000001'
    assert r.root(value)==dedicated/value

def test_long_source_paths_compile_to_distinct_exact_aliases(tmp_path):
    base=tmp_path/('a'*70);base.mkdir();source=base/'source';source.mkdir();protected=base/'config';protected.mkdir()
    policy={'rules':[{'action':'write','effect':'allow','target':str(source)},{'action':'write','effect':'deny','target':str(protected)}]}
    dsl=r.policy_dsl([str(base)],policy)
    assert 'file "/w/0/**"' in dsl and 'unless target "/w/0/source/**"' in dsl
    assert 'file "/w/0/config/**"' in dsl and str(base) not in dsl
    assert translate('/w/0/config/settings.json',[str(base)],reverse=True)==str(protected/'settings.json')

def test_native_namespace_pid_is_resolved_only_inside_registered_cgroup(tmp_path,monkeypatch):
    proc=tmp_path/'proc';group=tmp_path/'group';group.mkdir();(group/'cgroup.procs').write_text('101\n102\n')
    for pid,ns in ((101,2),(102,3)):
        p=proc/str(pid);p.mkdir(parents=True);(p/'status').write_text('NSpid:\t'+str(pid)+'\t'+str(ns)+'\n');(p/'cmdline').write_bytes(b'node\0/trusted/dsh.js\0')
    real=Path
    monkeypatch.setattr(r,'Path',lambda value:proc if value=='/proc' else real(value))
    monkeypatch.setattr(r,'B',SimpleNamespace(task_cgroup=lambda _:group,DSH_WEB=real('/trusted/dsh.js')))
    assert r.native_pid({'agent_type':'dsh'},2)==101
    (proc/'102/status').write_text('NSpid:\t102\t2\n')
    with pytest.raises(ValueError,match='ambiguous'):r.native_pid({'agent_type':'dsh'},2)

@pytest.mark.parametrize('failure',['wrong_domain','pid_reuse'])
def test_lost_binding_freezes_scope_and_cannot_claim_active(tmp_path,monkeypatch,failure):
    group=tmp_path/'group';group.mkdir();(group/'cgroup.procs').write_text('101\n');(group/'cgroup.freeze').write_text('0')
    rec={'instance_id':'instance-0000000000000001','generation':'a'*32,'ready':True,'watch':SimpleNamespace(poll=lambda:None),'agent_pid':101,'runner_pid':99,'domain_id':10,'verification':{'passed':True}}
    monkeypatch.setattr(r,'RUNS',{rec['instance_id']:rec})
    monkeypatch.setattr(r,'native',lambda *_:{'pid':2})
    monkeypatch.setattr(r,'native_pid',lambda *_:101)
    identities=iter([{'pid':101,'start_ticks':'100'},{'pid':101,'start_ticks':'101' if failure=='pid_reuse' else '100'}])
    monkeypatch.setattr(r,'identity',lambda _:next(identities))
    monkeypatch.setattr(r,'B',SimpleNamespace(domain_members=lambda _:[101] if failure=='pid_reuse' else [],task_cgroup=lambda _:group))
    got=r.observe(rec['instance_id'])
    assert not got['verified'] and not got['connected'] and rec['paused']
    assert (group/'cgroup.freeze').read_text()=='1'

def test_recovery_refuses_forged_manifest_before_any_process_is_signalled(tmp_path,monkeypatch):
    import json
    value='instance-0000000000000001'
    base=tmp_path/'instances'/value;base.mkdir(parents=True)
    p=base/'manifest.json'
    p.write_text(json.dumps({'instance_id':value,'task_id':'not-derived'}));p.chmod(0o600)
    monkeypatch.setattr(r,'B',SimpleNamespace(RUNTIME=tmp_path))
    with pytest.raises(RuntimeError):r.recover()
