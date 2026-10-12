"""Isolated reproductions of current behavior, not desired-behavior acceptance."""
import json
from test_dsl_configuration import world, apply
from agentscope_app import db, console
from agentscope_app.instances import store, sessions, dsl_policy as dsl

def setup(world, monkeypatch, tag):
    world.run(world.a)
    apply(world.a['id'])
    row=store.get(world.a['id'])
    saved=dsl.receipt(row['id'],row['generation'])
    ref=saved['artifact']['compile']['rules'][-1]
    monkeypatch.setattr(sessions,'native_sessions',lambda row:{'sessions':[{'id':'A'},{'id':'B'}]})
    event=dict(event='taint_violation',process_domain_id=900,domain_id=900,rule_id=77,pid=999,
               effect=ref['effect'],action='notify',blocked=False,killed=False,op='file_read',
               target='/w/0/notify.txt',tool_call_tag=tag,rule=ref)
    with db.connect() as con:
        con.execute('INSERT INTO instance_kernel_events(instance_id,generation,source_key,bundle_hash,domain_id,event_json,created_at) VALUES(?,?,?,?,?,?,?)',
                    (row['id'],row['generation'],'synthetic-audit-reproduction',saved['bundle_hash'],900,json.dumps(event),db.now()))
    return row

def test_reproduce_unattributed_event_is_included_by_default_session_endpoint(world,monkeypatch):
    row=setup(world,monkeypatch,0)
    records=sessions.kernel_page(row['id'],'A')['records']
    assert len(records)==1 and records[0]['session_id'] is None
    assert records[0]['attribution']=='shared_executor_unattributed'
    assert sessions.kernel_page(row['id'],'A',session_only=True)['records']==[]
    assert console.session_read(row['id'],'A','kernel-events',before=None,limit=30)['records']==[]

def test_reproduce_policy_detail_hits_can_include_another_sessions_event(world,monkeypatch):
    row=setup(world,monkeypatch,91)
    store.event(row['id'],'tool_start',{'kernel_call_tag':91,'domain_id':900},row['generation'],'B','call-B','read')
    hits=[hit for record in sessions.policies(row['id'],'A')['records'] for hit in record.get('hits',[])]
    assert hits and any(hit['session_id']=='B' for hit in hits)
    assert sessions.kernel_page(row['id'],'A',session_only=True)['records']==[]
    product=console.session_read(row['id'],'A','policies',limit=30)
    assert not any(hit['session_id']=='B' for record in product['records'] for hit in record.get('hits',[]))
