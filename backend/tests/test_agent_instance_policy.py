import hashlib, json, time, uuid
import pytest
from agentscope_app import db
from agentscope_app.instances import controller as c, store
from agentscope_app.instances.policy import canonical, default_policy, digest, restrictive, records

ADMIN={'Authorization':'Bearer test-admin-token-not-for-production'}

@pytest.fixture
def instance(client,tmp_path,monkeypatch):
    with db.connect() as con:
        for table in ('instance_leases','instance_events','instance_proposals','agent_instances'): con.execute('DELETE FROM '+table)
    monkeypatch.setattr(c,'clean_resources',lambda paths:paths)
    monkeypatch.setattr(c.observer,'collect',lambda:None)
    monkeypatch.setattr(c.observer,'snapshot',lambda:[])
    row=store.create('test','dsh',[str(tmp_path)])
    return row

def proposal(row,policy,key=None):
    return {'policy':policy,'generation':row['generation'],'base_hash':row['policy_hash'],'request_key':key or uuid.uuid4().hex}

def test_typed_paths_do_not_admit_control_tree_or_unknown_fields(tmp_path):
    with pytest.raises(ValueError): canonical({'rules':[{'action':'write','target':'/etc','effect':'allow','text':''}]},[str(tmp_path)])
    with pytest.raises(ValueError): canonical({'rules':[],'delta_text':'block write'},[str(tmp_path)])
    with pytest.raises(ValueError): canonical({'rules':[{'action':'network','effect':'allow','target':'1.2.3.4'}]},[str(tmp_path)])

def test_subset_check_requires_confirmation_to_remove_denies(tmp_path):
    old=canonical({'rules':[{'action':'write','target':str(tmp_path),'effect':'deny','text':''}]},[str(tmp_path)])
    assert not restrictive(old,default_policy())
    assert restrictive(default_policy(),old)
    assert not restrictive({'rules':[],'network':'disabled'},default_policy())
    assert records({'rules':[{'action':'behavior','target':'','effect':'deny','text':'保留测试'}],'network':'model_only'},[],True)[-1]['result']=='不作强制执行声明'

def test_expansion_requires_exact_hash_and_stale_confirmation_rejected(instance,monkeypatch):
    row=instance; policy={'rules':[{'action':'write','target':row['resources'][0],'effect':'allow','text':''}],'network':'model_only'}
    p=c.proposals(row['id'],proposal(row,policy))
    assert p['state']=='pending' and store.get(row['id'])['policy']==default_policy()
    with pytest.raises(ValueError): c.apply(row['id'],p['id'],'0'*64)
    store.update(row['id'],generation='a'*32)
    with pytest.raises(ValueError,match='过期'): c.apply(row['id'],p['id'],p['proposal_hash'])
    assert store.get(row['id'])['policy']==default_policy()

def test_idempotency_key_is_bound_to_candidate(instance):
    row=instance; policy={'rules':[{'action':'write','target':row['resources'][0],'effect':'allow','text':''}],'network':'model_only'}
    key=uuid.uuid4().hex; first=c.proposals(row['id'],proposal(row,policy,key))
    assert c.proposals(row['id'],proposal(row,policy,key))['id']==first['id']
    with pytest.raises(ValueError,match='幂等'): c.proposals(row['id'],proposal(row,default_policy(),key))

def test_automatic_restriction_is_instance_local_and_has_quiescence(instance,monkeypatch,tmp_path):
    first=instance; other=store.create('other','dsh',[str(tmp_path)])
    calls=[]
    class Adapter:
        def stop(self,row): calls.append((row['id'],store.get(row['id'])['gate'])); return {'status':'stopped'}
    monkeypatch.setattr(c,'adapter',lambda row:Adapter())
    result=c.proposals(first['id'],proposal(first,{'rules':[],'network':'disabled'}),'agent')
    assert result['state']=='applied'
    assert calls==[(first['id'],'updating')]
    assert store.get(first['id'])['policy']['network']=='disabled'
    assert store.get(other['id'])['policy']['network']=='model_only'

def test_failed_quiescence_never_opens_gate_or_accepts_proposal(instance,monkeypatch):
    class Adapter:
        def stop(self,row): raise RuntimeError('cannot quiesce')
    monkeypatch.setattr(c,'adapter',lambda row:Adapter())
    with pytest.raises(RuntimeError): c.proposals(instance['id'],proposal(instance,{'rules':[],'network':'disabled'}))
    row=store.get(instance['id'])
    assert row['gate']=='paused' and row['policy']==default_policy()
    assert store.events(row['id'])[0]['kind']=='policy_apply_failed'

def test_atomic_lease_and_generation_guard(instance):
    ident=instance['id']; gen='a'*32
    store.update(ident,generation=gen,gate='open')
    body={'generation':gen,'session_id':'s1','call_id':'c1','tool':'read'}
    assert c.lease(ident,body)['allowed']
    store.update(ident,gate='updating')
    assert not c.lease(ident,{**body,'call_id':'c2'})['allowed']
    c.result(ident,{**body,'succeeded':True})
    with db.connect() as con: assert con.execute('SELECT COUNT(*) FROM instance_leases').fetchone()[0]==0
    store.update(ident,gate='open',generation='b'*32)
    assert not c.lease(ident,body)['allowed']

def test_agent_credentials_cannot_call_control_or_other_instance(instance,client):
    token='secret-'+uuid.uuid4().hex;gen='a'*32
    store.update(instance['id'],generation=gen,gate='open',token_hash=hashlib.sha256(token.encode()).hexdigest())
    agent={'Authorization':'Bearer '+token}
    r=client.post('/api/agent-instances/'+instance['id']+'/stop',headers=agent,json={})
    assert r.status_code==401
    body={'generation':gen,'session_id':'s','call_id':'c','tool':'read'}
    assert client.post('/api/agent/instances/'+instance['id']+'/lease',headers=agent,json=body).status_code==200
    assert client.post('/api/agent/instances/instance-0000000000000000/lease',headers=agent,json=body).status_code==401
    body['generation']='b'*32
    assert client.post('/api/agent/instances/'+instance['id']+'/lease',headers=agent,json=body).status_code==401

def test_observation_expires_and_history_cannot_restore_active(instance,monkeypatch):
    gen='a'*32;store.update(instance['id'],generation=gen,gate='open')
    observer=c.Observer()
    observer.rows={instance['id']:{'id':instance['id'],'generation':gen,'connected':True,'verified':True,'_observed':time.monotonic()-9}}
    assert not observer.snapshot()[0]['verified']
    monkeypatch.setattr(c,'observer',observer)
    assert not c.detail(instance['id'])['active']

def test_successful_proposal_retry_remains_idempotent_after_policy_changes(instance,monkeypatch):
    class Adapter:
        def stop(self,row):return {'status':'stopped'}
    monkeypatch.setattr(c,'adapter',lambda row:Adapter())
    body=proposal(instance,{'rules':[],'network':'disabled'})
    first=c.proposals(instance['id'],body)
    assert c.proposals(instance['id'],body)['id']==first['id']
    assert len([e for e in store.events(instance['id']) if e['kind']=='policy_applied'])==1

def test_two_sessions_read_one_tool_policy_and_other_instance_is_unaffected(instance,monkeypatch,tmp_path):
    class Adapter:
        def stop(self,row):return {'status':'stopped'}
    monkeypatch.setattr(c,'adapter',lambda row:Adapter())
    other=store.create('independent','hermes',[str(tmp_path)])
    deny={'rules':[{'action':'tool','target':'bash','effect':'deny','text':''}],'network':'model_only'}
    c.proposals(instance['id'],proposal(instance,deny))
    for row in (instance,other):store.update(row['id'],gate='open',generation='a'*32)
    for sid in ('session-a','session-b'):
        b={'generation':'a'*32,'session_id':sid,'call_id':sid,'tool':'bash'}
        assert not c.lease(instance['id'],b)['allowed']
        assert c.lease(other['id'],b)['allowed']

def test_concurrent_candidates_cannot_apply_against_a_changed_base(instance,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    class Adapter:
        def stop(self,row):return {'status':'stopped'}
    monkeypatch.setattr(c,'adapter',lambda row:Adapter())
    bodies=[proposal(instance,{'rules':[],'network':'disabled'}) for _ in range(2)]
    def run(body):
        try:return c.proposals(instance['id'],body)['state']
        except ValueError:return 'stale'
    with ThreadPoolExecutor(2) as pool:assert sorted(pool.map(run,bodies))==['applied','stale']

def test_manual_connection_rejects_shell_and_only_opens_registered_local_url(instance,client):
    body={'name':'Other','agent_type':'other','mode':'observed','environment':'windows','resources':[],'open_url':'http://127.0.0.1:19000/'}
    bad={**body,'command':'cmd /c whoami'}
    assert client.post('/api/agent-instances',headers=ADMIN,json=bad).status_code==422
    assert client.post('/api/agent-instances',headers=ADMIN,json={**body,'open_url':'http://attacker.example/'}).status_code==409
    row=client.post('/api/agent-instances',headers=ADMIN,json=body).json()
    assert client.post('/api/agent-instances/'+row['id']+'/open',headers=ADMIN,json={}).json()=={'url':body['open_url']}
    assert client.post('/api/agent-instances/'+row['id']+'/start',headers=ADMIN,json={}).status_code==409

def test_windows_discovery_is_path_checked_expires_and_never_claims_enforcement(monkeypatch):
    from agentscope_app.instances import discovery as d
    base={'name':'candidate','agent_type':'codex','pid':100,'started_at':'20261008090000000','executable':r'C:\Users\happy\AppData\Local\OpenAI\Codex\bin\979a96ce184041d1\codex.exe'}
    d.windows_report([base])
    row=d.windows_snapshot()[0]
    assert not row['active'] and not row['connected'] and row['status']=='discovered'
    old=row['id'];d.windows_report([{**base,'started_at':'20261008090100000'}])
    assert d.windows_snapshot()[0]['id']!=old
    future=time.monotonic()+20
    monkeypatch.setattr(d.time,'monotonic',lambda:future)
    assert d.windows_snapshot()[0]['status']=='stale'
    with pytest.raises(ValueError):d.windows_report([{**base,'executable':r'C:\\Python\\python.exe'}])
    d.windows_report([])


def test_listing_distinguishes_controlled_web_native_web_and_cli_installation(instance,monkeypatch):
    store.create('Hermes','hermes',instance['resources'])
    monkeypatch.setattr(c.observer,'snapshot',lambda:[
        {'id':'native-dsh','agent_type':'dsh','entry_kind':'web','status':'unknown','connected':False},
        {'id':'installed-wsl-hermes','agent_type':'hermes','entry_kind':'cli_install','status':'installed','connected':False},
    ])
    monkeypatch.setattr(c.discovery,'windows_snapshot',lambda:[])
    rows=c.listing()['instances']
    assert len(rows)==4
    assert [r['entry']['kind'] for r in rows]==['web','web','web','cli_install']
    installed=rows[-1]
    assert installed['entry']['label']=='CLI 安装入口'
    assert installed['entry']['command']=='wsl -d Ubuntu -u happy -- /home/happy/.local/bin/hermes'
    assert not installed['connected'] and not installed['can_open']
    assert '直接运行 CLI 尚未接入实例策略' in installed['entry']['instructions']


def test_unclassified_os_process_cannot_advertise_a_cli_or_web_entry():
    from agentscope_app.instances.adapters import entry_details
    row={'agent_type':'codex','executable':'codex.exe','status':'discovered'}
    assert entry_details(row)['kind']=='process'
    assert 'command' not in entry_details(row)


def test_deleting_protected_rule_waits_for_exact_confirmation_and_keeps_other_permissions(instance,monkeypatch):
    from pathlib import Path
    base=instance['resources'][0]
    protected=Path(base)/'tests';protected.mkdir()
    grant={'action':'write','target':base,'effect':'allow','text':'修复源码'}
    deny={'action':'write','target':str(protected),'effect':'deny','text':'保留测试'}
    original=canonical({'rules':[grant,deny],'network':'model_only'},[base])
    store.update(instance['id'],policy=original,policy_hash=digest(original))
    row=store.get(instance['id'])
    candidate={**original,'rules':[grant]}
    p=c.proposals(row['id'],proposal(row,candidate))
    assert p['state']=='pending' and p['classification']=='expand'
    assert store.get(row['id'])['policy']==original
    with pytest.raises(ValueError): c.apply(row['id'],p['id'],'wrong-confirmation')
    assert store.get(row['id'])['policy']==original
    class Adapter:
        def stop(self,row):return {'status':'stopped'}
    monkeypatch.setattr(c,'adapter',lambda _:Adapter())
    assert c.apply(row['id'],p['id'],p['proposal_hash'])['state']=='applied'
    assert store.get(row['id'])['policy']==candidate
