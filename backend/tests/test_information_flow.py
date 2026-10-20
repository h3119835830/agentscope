import copy
import json
import pytest
from agentscope_app import db
from agentscope_app.instances import information_flow as flow,sessions,dsl_policy
from test_dsl_configuration import world
from test_dsl_configuration import ADMIN


@pytest.fixture
def evidence(world,monkeypatch):
    ident=world.a['id'];gen='flow-generation'
    row={**world.a,'generation':gen}
    receipt={'generation':gen,'bundle_hash':'approved-hash','artifact':{
        'binding':{'domain_id':41},'documents':[{'id':'config-a','name':'敏感外发','effective_dsl':'source doc_SECRET = file "/w/0/secret.txt"','label_sources':[]}]}}
    monkeypatch.setattr(sessions,'session_context',lambda *_:(row,{'id':'s1'},gen,True))
    monkeypatch.setattr(sessions,'collect_kernel',lambda *_:{'available':True})
    monkeypatch.setattr(dsl_policy,'receipt',lambda *_:receipt)
    def proc(pid,start):return {'kind':'process','pid':pid,'start_boottime_ns':str(start)}
    def file(ino):return {'kind':'file','device':1,'inode':str(ino),'inode_generation':2}
    secret=file(11);derived=file(12);a=proc(100,10);b=proc(101,11);endpoint={'kind':'endpoint','address':'127.0.0.1'}
    events=[]
    for index,(subject,obj,op) in enumerate([(secret,a,'source_introduced'),(a,derived,'process_to_file'),(derived,b,'file_to_process'),(b,endpoint,'rule_match')],1):
        events.append({'event':'label_transition','schema_version':1,'event_id':f'boot:map:9:{index}','stream_id':'boot:map:9',
                       'predecessor_event_id':f'boot:map:9:{index-1}' if index>1 else None,
                       'monotonic_ns':str(index*100),'domain_id':41,'process_domain_id':41,'generation':gen,
                       'policy_hash':'approved-hash','label_mask':'0x2','label_names':['doc_SECRET'],'subject':subject,'object':obj,
                       'operation':op,'root_source':index==1,'identity_complete':True,'lost_total':'0',
                       'tool_call_tag':'0','target':'/w/0/secret.txt' if index==1 else '/w/0/derived.txt' if index<4 else '127.0.0.1',
                       'outcome':'block' if index==4 else 'propagated','hook':'lsm/socket_connect' if index==4 else 'lsm/file_permission'})
    def insert(event,offset=None):
        with db.connect() as con:
            con.execute('INSERT INTO instance_kernel_events(instance_id,generation,source_key,bundle_hash,domain_id,event_json,created_at) VALUES(?,?,?,?,?,?,?)',
                        (ident,gen,str(offset or event['event_id']),'approved-hash',41,json.dumps(event),db.now()))
    return ident,events,insert


def test_real_edge_only_chain_and_shared_scope(evidence):
    ident,events,insert=evidence
    for e in events:insert(e)
    data=flow.query(ident,'s1',view='shared_domain')
    assert data['integrity']['state']=='complete' and len(data['edges'])==4 and len(data['nodes'])==5
    assert all(e['evidence_ref'] for e in data['edges'])
    assert not flow.query(ident,'s1')['edges']
    assert data['available_labels']==['SECRET']
    assert data['anchors'][0]['configuration_names']==[]  # source is not the hit rule


def test_hit_name_requires_exact_compiled_rule_evidence():
    saved={'artifact':{'compile':{'rules':[{'rule_id':7,'name':'rule-a','source_ref':'src'}]},
                       'documents':[{'name':'实际命中配置','rules':[{'compiled_name':'rule-a','source_ref':'src'}]}]}}
    assert flow.matched_names(saved,{'rule_id':7})==['实际命中配置']
    assert flow.matched_names(saved,{'rule_id':8})==[]
    assert flow.matched_names(saved,{})==[]


def test_desired_state_mismatch_does_not_turn_current_evidence_into_history(evidence,monkeypatch):
    ident,_,_=evidence
    monkeypatch.setattr(sessions,'session_context',lambda *_:({'generation':'flow-generation'},{'id':'s1'},'flow-generation',False))
    assert flow.query(ident,'s1')['historical'] is False
    monkeypatch.setattr(sessions,'session_context',lambda *_:({'generation':'next-run'},{'id':'s1'},'flow-generation',False))
    assert flow.query(ident,'s1')['historical'] is True


def test_unattributed_modern_events_are_not_misreported_as_legacy(evidence):
    ident,events,insert=evidence
    events[-1]['target']=''
    for e in events:insert(e)
    insert({'event':'taint_violation','event_id':'legacy-coexisting'})
    assert flow.query(ident,'s1')['integrity']['state']=='empty'
    data=flow.query(ident,'s1',view='shared_domain')
    assert data['anchors'][0]['target']=='127.0.0.1'


@pytest.mark.parametrize('collection,legacy,expected',[
    ({'available':True},False,'empty'),
    ({'available':True},True,'legacy'),
    ({'available':True,'transitions_supported':False},False,'unsupported'),
    ({'available':False,'error':'isolated test outage'},False,'collection_failed'),
])
def test_absence_and_collection_failures_remain_distinct(evidence,monkeypatch,collection,legacy,expected):
    ident,events,insert=evidence
    monkeypatch.setattr(sessions,'collect_kernel',lambda _:collection)
    if legacy:insert({'event':'taint_violation','event_id':'old-receipt'})
    data=flow.query(ident,'s1',view='shared_domain')
    assert data['integrity']['state']==expected and data['edges']==[]


@pytest.mark.parametrize('mutation,reason',[
    ('pid_reuse','predecessor_identity_mismatch'),('file_replace','predecessor_identity_mismatch'),
    ('generation','unverified_receipt'),('missing','missing_predecessor'),('duplicate','conflicting_duplicate'),
    ('lost','collector_loss'),('identity','identity_or_predecessor_missing'),('label','predecessor_identity_mismatch')])
def test_gaps_never_create_false_complete_paths(evidence,mutation,reason):
    ident,events,insert=evidence
    if mutation=='pid_reuse':events[3]['subject']={**events[3]['subject'],'start_boottime_ns':'999'}
    if mutation=='file_replace':events[2]['subject']={**events[2]['subject'],'inode':'88'}
    if mutation=='generation':events[1]['generation']='old'
    if mutation=='lost':events[2]['lost_total']='1'
    if mutation=='identity':events[1]['identity_complete']=False
    if mutation=='label':events[1]['label_mask']='0x4'
    for index,e in enumerate(events):
        if mutation=='missing' and index==1:continue
        insert(e)
    if mutation=='duplicate':insert({**events[1],'target':'/different'},'duplicate')
    data=flow.query(ident,'s1',view='shared_domain')
    assert data['integrity']['state']=='incomplete'
    assert reason in data['integrity']['reasons']


def test_out_of_order_duplicate_delivery_rename_and_pagination(evidence):
    ident,events,insert=evidence
    events[2]['target']='/w/0/renamed.txt'
    for e in reversed(events):insert(e)
    insert(events[1],'reconnected-delivery')
    first=flow.query(ident,'s1',view='shared_domain',limit=2)
    assert first['integrity']['state']=='paged' and len(first['edges'])==2
    second=flow.query(ident,'s1',view='shared_domain',anchor=first['anchor'],cursor=first['next_cursor'],limit=2)
    assert second['integrity']['state']=='complete' and len(second['edges'])==2
    assert flow.query(ident,'s1',view='shared_domain')['integrity']['state']=='complete'
    with pytest.raises(ValueError):flow.query(ident,'s1',view='shared_domain',anchor=first['anchor'],cursor='other')


def test_conflict_after_many_identical_deliveries_is_not_hidden(evidence):
    ident,events,insert=evidence
    for e in events:insert(e)
    for n in range(5):insert(events[1],'delivery-'+str(n))
    insert({**events[1],'target':'/conflicting'},'bad-delivery')
    data=flow.query(ident,'s1',view='shared_domain')
    assert data['integrity']['state']=='incomplete'
    assert 'conflicting_duplicate' in data['integrity']['reasons']


def test_product_console_read_projection_exposes_same_explicit_scope(evidence,world):
    ident,events,insert=evidence
    for e in events:insert(e)
    route='/api/console/agents/'+ident+'/sessions/s1/information-flow'
    data=world.client.get(route+'?view=shared_domain&label=SECRET',headers=ADMIN).json()
    assert data['integrity']['state']=='complete' and len(data['edges'])==4
    data=world.client.get(route,headers=ADMIN).json()
    assert data['view']=='session' and data['edges']==[]
    assert world.client.get(route+'?view=untrusted',headers=ADMIN).status_code==422
