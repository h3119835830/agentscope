import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import pytest
from agentscope_app import db
from agentscope_app.instances import controller as c, store, system_policy as system
from agentscope_app.instances.policy import canonical, default_policy, digest

ADMIN={'Authorization':'Bearer test-admin-token-not-for-production'}

def rule(action='tool',target='bash',effect='deny',text=''):
    return dict(action=action,target=target,effect=effect,text=text)
def policy(*rules,network='model_only'):
    return dict(rules=list(rules),network=network)
def reset():
    with db.connect() as con:
        for table in ('instance_leases','instance_events','instance_proposals','instance_proposal_locals','system_security_proposals','instance_local_policies','agent_instances'):
            con.execute('DELETE FROM '+table)
        con.execute("UPDATE system_security_policy SET policy_json=?,policy_hash=?,revision=0,phase='ready'",(json.dumps(default_policy()),digest(default_policy())))

@pytest.fixture
def world(client,tmp_path,monkeypatch):
    reset()
    roots=[tmp_path/'a',tmp_path/'b']
    for p in roots:p.mkdir()
    dsh=store.create('DSH','dsh',[str(roots[0])])
    hermes=store.create('Hermes','hermes',[str(roots[1])])
    observed=store.create('Observed','other',[],mode='observed')
    live={};calls=[];fail={'stop':False,'start':False,'verified':True}
    class Adapter:
        def observe(self,row):return live.get(row['id'],{})
        def stop(self,row):
            calls.append(('stop',row['id'],system.current()['phase'],[r['gate'] for r in store.rows() if r['mode']=='controlled']))
            if fail['stop']:raise RuntimeError('cannot stop executor')
            live.pop(row['id'],None)
            return {'status':'stopped'}
        def start(self,row,token,generation):
            calls.append(('start',row['id'],system.current()['phase']))
            if fail['start']:raise RuntimeError('cannot start executor')
            runtime={'verified':fail['verified'],'generation':generation,'connected':True}
            live[row['id']]={'id':row['id'],**runtime}
            return runtime
    monkeypatch.setattr(c,'adapter',lambda row:Adapter())
    monkeypatch.setattr(c.observer,'snapshot',lambda:list(live.values()))
    monkeypatch.setattr(c.observer,'collect',lambda:None)
    monkeypatch.setattr(c.discovery,'windows_snapshot',lambda:[])
    def running(row):
        gen=uuid.uuid4().hex
        store.update(row['id'],gate='open',generation=gen,runtime={'verified':True})
        live[row['id']]={'id':row['id'],'connected':True,'verified':True,'generation':gen}
    yield SimpleNamespace(client=client,dsh=dsh,hermes=hermes,observed=observed,roots=roots,live=live,calls=calls,fail=fail,running=running)
    reset()

def propose(candidate,key=None):
    shared=system.current()
    return system.propose({'policy':candidate,'base_hash':shared['policy_hash'],'revision':shared['revision'],'request_key':key or uuid.uuid4().hex})
def apply(candidate):
    p=propose(candidate)
    return system.apply(p['id'],p['proposal_hash'])
def local(row,candidate):
    row=store.get(row['id'])
    return c.proposals(row['id'],dict(policy=candidate,base_hash=row['policy_hash'],generation=row['generation'],request_key=uuid.uuid4().hex))

def test_global_rule_is_pending_until_exact_confirmation(world):
    p=propose(policy(rule()))
    assert p['state']=='pending' and system.current()['policy']==default_policy()
    assert not world.calls
    with pytest.raises(ValueError,match='确认'):system.apply(p['id'],'0'*64)
    assert store.get(world.dsh['id'])['policy']==default_policy()
    receipt=system.apply(p['id'],p['proposal_hash'])
    assert receipt['state']=='applied' and receipt['affected_count']==2
    assert system.apply(p['id'],p['proposal_hash'])['idempotent']
    assert system.current()['revision']==1

def test_global_tool_denial_inherited_by_all_sessions_and_future_agents(world):
    apply(policy(rule()))
    for row in (world.dsh,world.hermes):
        assert store.get(row['id'])['local_policy']==default_policy()
        world.running(row)
        for sid in ('one','two'):
            body={'generation':store.get(row['id'])['generation'],'session_id':sid,'call_id':sid,'tool':'bash'}
            assert not c.lease(row['id'],body)['allowed']
    assert store.get(world.observed['id'])['policy']==default_policy()
    future=store.create('future','dsh',[str(world.roots[0])])
    assert future['policy']==policy(rule()) and future['local_policy']==default_policy()

def test_agent_local_edit_cannot_remove_shared_denial_or_network_limit(world):
    apply(policy(rule(),network='disabled'))
    result=local(world.dsh,policy(rule('tool','read')))
    assert result['state']=='applied'
    row=store.get(world.dsh['id'])
    assert row['local_policy']==policy(rule('tool','read'))
    assert row['policy']==canonical(policy(rule(),rule('tool','read'),network='disabled'),row['resources'])
    assert store.get(world.hermes['id'])['local_policy']==default_policy()
    value=system.local_candidate(row,row['policy'],'agent')
    assert value['rules']==row['local_policy']['rules']
    assert rule() in system.compose(default_policy(),row['resources'])['rules']

def test_file_rules_match_registered_resource_and_allow_never_masks_deny(world):
    target=world.roots[0]/'secret';target.write_text('fixture')
    grant=rule('write',str(target),'allow')
    original=canonical(policy(grant),world.dsh['resources'])
    store.update(world.dsh['id'],policy=original,policy_hash=digest(original))
    deny=rule('write',str(target))
    apply(policy(deny))
    assert store.get(world.dsh['id'])['local_policy']==original
    assert deny in store.get(world.dsh['id'])['policy']['rules']
    from broker import instance_runtime
    dsl=instance_runtime.policy_dsl(world.dsh['resources'],store.get(world.dsh['id'])['policy'])
    assert 'block write file "/w/0/secret" if AGENT' in dsl
    assert 'block unlink file "/w/0/secret" if AGENT' in dsl
    assert not store.get(world.hermes['id'])['policy']['rules']
    assert c.detail(world.dsh['id'])['local_policy_records'][-1]['result']=='受系统禁止约束'
    assert system.detail()['policy_records'][0]['result']=='已核验 0 / 1 个连接'

@pytest.mark.parametrize('candidate',[{'rules':[None]}, {'rules':'bad'},policy(rule(effect='allow')),policy(rule('write','/etc/passwd')),policy(rule('write','/w/0/secret'))])
def test_invalid_shared_rules_rejected_without_pending_mutation(world,candidate):
    with pytest.raises((ValueError,OSError)):propose(candidate)
    assert system.current()['revision']==0
    with db.connect() as con:assert con.execute('SELECT COUNT(*) FROM system_security_proposals').fetchone()[0]==0

def test_every_gate_closes_and_every_old_executor_stops_before_restart(world):
    world.running(world.dsh);world.running(world.hermes)
    apply(policy(rule()))
    stops=[i for i,item in enumerate(world.calls) if item[0]=='stop']
    starts=[i for i,item in enumerate(world.calls) if item[0]=='start']
    # c.start also performs an idempotent stop before its own new executor.
    first_start=min(starts)
    assert {item[1] for item in world.calls[:first_start] if item[0]=='stop'}=={world.dsh['id'],world.hermes['id']}
    assert world.calls[0][2]=='updating' and world.calls[0][3]==['updating','updating']
    assert len(starts)==2 and all(c.detail(r['id'])['active'] for r in (world.dsh,world.hermes))
    assert system.current()['phase']=='ready'

def test_stopped_agent_is_not_started_by_global_configuration(world):
    world.running(world.dsh)
    store.update(world.hermes['id'],gate='paused')
    apply(policy(rule()))
    assert [x[1] for x in world.calls if x[0]=='start']==[world.dsh['id']]
    assert store.get(world.hermes['id'])['gate']=='closed'
    assert system.detail()['network_result']=='已核验 1 / 2 个连接'

@pytest.mark.parametrize('failure',['stop','start','verified'])
def test_failure_blocks_admission_and_never_claims_active(world,failure):
    world.running(world.dsh)
    world.fail[failure]=False if failure=='verified' else True
    p=propose(policy(rule()))
    with pytest.raises((RuntimeError,ValueError)):system.apply(p['id'],p['proposal_hash'])
    assert system.current()['phase']=='blocked'
    assert all(not c.detail(r['id'])['active'] for r in (world.dsh,world.hermes))
    body=dict(generation=store.get(world.dsh['id'])['generation'],session_id='s',call_id='c',tool='read')
    assert not c.lease(world.dsh['id'],body)['allowed']
    with pytest.raises(ValueError,match='系统规则'):c.start(world.dsh['id'])
    world.fail.update(stop=False,start=False,verified=True)
    assert apply(system.current()['policy'])['state']=='applied'
    assert system.current()['phase']=='ready'
    if failure=='stop':assert not [x for x in world.calls if x[0]=='start']
    assert all(store.get(r['id'])['gate']=='closed' for r in (world.dsh,world.hermes))

def test_lease_rejected_for_updating_and_blocked_even_if_instance_gate_open(world):
    world.running(world.dsh)
    for phase in ('updating','blocked'):
        with db.connect() as con:con.execute('UPDATE system_security_policy SET phase=?',(phase,))
        body=dict(generation=store.get(world.dsh['id'])['generation'],session_id='s',call_id=phase,tool='read')
        assert not c.lease(world.dsh['id'],body)['allowed']

def test_frozen_target_or_base_change_rejects_stale_confirmation(world):
    p=propose(policy(rule()))
    store.update(world.dsh['id'],generation='a'*32)
    with pytest.raises(ValueError,match='变化'):system.apply(p['id'],p['proposal_hash'])
    assert system.current()['revision']==0
    q=propose(policy(rule()))
    apply(policy(network='disabled'))
    with pytest.raises(ValueError,match='过期'):system.apply(q['id'],q['proposal_hash'])

def test_idempotency_key_bound_to_exact_candidate_and_retries_do_not_roll_out_again(world):
    key=uuid.uuid4().hex;p=propose(policy(rule()),key)
    assert propose(policy(rule()),key)['id']==p['id']
    shared=system.current()
    with pytest.raises(ValueError,match='幂等'):
        system.propose(dict(policy=policy(network='disabled'),base_hash=shared['policy_hash'],revision=shared['revision'],request_key=key))
    system.apply(p['id'],p['proposal_hash'])
    count=len(world.calls)
    assert system.propose(dict(policy=p['policy'],base_hash=p['base_hash'],revision=p['revision'],request_key=key))['state']=='applied'
    assert len(world.calls)==count

def test_concurrent_confirmations_apply_one_revision(world):
    candidates=[propose(policy(rule())),propose(policy(network='disabled'))]
    def confirm(p):
        try:return system.apply(p['id'],p['proposal_hash'])['state']
        except ValueError:return 'stale'
    with ThreadPoolExecutor(2) as pool:assert sorted(pool.map(confirm,candidates))==['applied','stale']
    assert system.current()['revision']==1

def test_global_update_supersedes_pending_agent_expansion_and_preview_remains_local(world):
    apply(policy(rule()))
    p=local(world.dsh,policy(rule('tool','read','allow')))
    assert p['state']=='pending'
    local_preview=c.detail(world.dsh['id'])['proposals'][0]['policy']
    assert local_preview==policy(rule('tool','read','allow'))
    apply(policy(rule(),network='disabled'))
    with pytest.raises(ValueError,match='过期'):c.apply(world.dsh['id'],p['id'],p['proposal_hash'])
    assert store.get(world.dsh['id'])['local_policy']==default_policy()

def test_default_migration_preserves_local_hash_and_incomplete_rollout_blocks(world):
    original=canonical(policy(rule()),world.dsh['resources'])
    store.update(world.dsh['id'],policy=original,policy_hash=digest(original))
    with db.connect() as con:
        con.execute('DELETE FROM instance_local_policies')
        con.execute("UPDATE system_security_policy SET phase='updating'")
        system.init(con)
    row=store.get(world.dsh['id'])
    assert row['policy']==original and row['local_policy']==original and row['policy_hash']==digest(original)
    assert system.current()['phase']=='blocked'

def test_api_admin_contract_and_agent_credentials_cannot_change_system_rules(world):
    client=world.client;shared=system.current()
    token='agent-'+uuid.uuid4().hex
    store.update(world.dsh['id'],token_hash=hashlib.sha256(token.encode()).hexdigest(),generation='a'*32,gate='open')
    body=dict(policy=policy(rule()),base_hash=shared['policy_hash'],revision=shared['revision'],request_key='api')
    agent={'Authorization':'Bearer '+token}
    for headers in ({},agent):
        assert client.get('/api/security/system',headers=headers).status_code==401
        assert client.post('/api/security/system/proposals',headers=headers,json=body).status_code==401
    assert client.post('/api/security/system/proposals',headers=ADMIN,json={**body,'extra':'command'}).status_code==422
    assert client.post('/api/security/system/proposals',headers=ADMIN,json={**body,'policy':{'rules':[None]}}).status_code==409
    p=client.post('/api/security/system/proposals',headers=ADMIN,json=body)
    assert p.status_code==200 and p.json()['state']=='pending'
    assert client.post('/api/security/system/proposals/'+p.json()['id']+'/confirm',headers=agent,json={'proposal_hash':p.json()['proposal_hash']}).status_code==401
    result=client.post('/api/security/system/proposals/'+p.json()['id']+'/confirm',headers=ADMIN,json={'proposal_hash':p.json()['proposal_hash']})
    assert result.status_code==200 and result.json()['state']=='applied'
    info=client.get('/api/security/system',headers=ADMIN).json()
    assert info['policy']==policy(rule()) and info['connection_count']==2
