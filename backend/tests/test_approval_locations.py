"""Approval source links use immutable generation evidence and exact session keys."""
import copy
import json
from agentscope_app import db
from agentscope_app.history import agent_context
from agentscope_app.instances import controller, sessions
from agentscope_app.instances.approval_locations import Locations
from test_agent_policy_context import world as context_world, generated


def location_fixture(world):
    _, results=generated(world)
    doc=agent_context.selected_candidate('agent-a',results[0]['artifact_id'])['document']
    world.monkeypatch.setattr(controller,'listing',lambda:dict(instances=[copy.deepcopy(world.row)]))
    with db.connect() as con:
        sessions.init(con)
        for ident,name in [('agent-a','Native task'),('agent-b','Wrong Agent, same session ID')]:
            con.execute('INSERT INTO instance_session_cache VALUES(?,?,?,?,?)',
                        (ident,'session-a',json.dumps(dict(name=name)), 'gen-a',db.now()))
    return doc


def test_generated_location_survives_pid_drift_and_stays_exact(context_world):
    w=context_world;doc=location_fixture(w)
    w.row.update(pid=77,generation='gen-b')
    locations=Locations()
    row=locations.project(dict(scope_id='agent-a',documents=[doc]),[dict(id='agent-a',name='RQ5 DSH 受控实例',agent_type='dsh',pid=55,active=True)])
    assert row['agents'][0]['pid']==77 and row['agents'][0]['submitted_pid']==55
    assert row['agents'][0]['name']=='DeepSeek Harness'
    assert row['origin_sessions']==[dict(instance_id='agent-a',session_id='session-a',name='Native task',available=True,generation_pid=55)]
    assert row['origin_state']=='linked'
    assert locations.origin('agent-b',doc['generation_binding']) is None
    changed={**doc['generation_binding'],'context_hash':'0'*64}
    assert locations.origin('agent-a',changed) is None


def test_missing_session_retains_identity_but_does_not_invent_a_link(context_world):
    w=context_world;doc=location_fixture(w)
    with db.connect() as con:con.execute("DELETE FROM instance_session_cache WHERE instance_id='agent-a'")
    origin=Locations().origin('agent-a',doc['generation_binding'])
    assert origin['session_id']=='session-a' and not origin['available']
    assert origin['name']=='会话记录暂不可用'
    row=Locations().project(dict(scope_id='agent-a',documents=[{**doc,'generation_binding':{'artifact_id':'missing','context_hash':'x'}}]),[])
    assert row['origin_state']=='unavailable' and row['origin_sessions']==[]


def test_tampered_generation_evidence_cannot_assert_session_ownership(context_world):
    w=context_world;doc=location_fixture(w)
    with db.connect() as con:
        con.execute("UPDATE strategy_statement_versions SET content_sha256=?",('0'*64,))
    assert Locations().origin('agent-a',doc['generation_binding']) is None
