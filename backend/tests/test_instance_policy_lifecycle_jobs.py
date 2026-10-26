"""Lifecycle jobs bind exact immutable evidence; reviews never mutate it."""
import json
import uuid
import pytest
from agentscope_app import db
from agentscope_app.instances import policy_lifecycle as life,store,template_tools
from agentscope_app.instances.policy import digest
from test_policy_workspace_references import reference
from test_dsl_configuration import world,ADMIN

@pytest.fixture
def scene(reference):
    world,root,body=reference
    with db.connect() as con:
        for t in ('instance_policy_jobs','instance_lifecycle_configs','instance_audit_reviews'):con.execute('DELETE FROM '+t)
    configuration=life.configure(world.a['id'],{'enabled':True,'requirements':'不得修改说明文件，允许完成正常统计。','workspace_id':body['workspace_id'],'integrity_paths':['README.md']})
    world.run(world.a);return world,root,configuration

def test_configuration_uses_actual_reader_and_resource_binding(scene):
    world,root,configuration=scene
    assert configuration['baseline']['README.md'] and configuration['resource_hash']==digest(world.a['resources'])
    row=store.get(world.a['id']);key=life.enqueue(row,'session','postrun','unique')
    assert life.enqueue(row,'session','postrun','unique')==key
    with db.connect() as con:job=dict(con.execute('SELECT * FROM instance_policy_jobs WHERE id=?',(key,)).fetchone())
    snapshot=json.loads(job['input_json'])
    assert digest(snapshot)==job['input_hash'] and snapshot['integrity'][0]['unchanged']
    (root/'README.md').write_text('changed')
    changed=life.enqueue(row,'session','postrun','second')
    with db.connect() as con:snapshot=json.loads(con.execute('SELECT input_json FROM instance_policy_jobs WHERE id=?',(changed,)).fetchone()[0])
    assert not snapshot['integrity'][0]['unchanged']
    store.update(row['id'],resources=[str(root/'other')])
    with pytest.raises(ValueError,match='资源'):life.enqueue(store.get(row['id']),'session','postrun','third')

def test_native_audit_cannot_cite_unread_or_unknown_evidence():
    agent=life.AuditAgent({'records':[{'id':'kernel:1','kind':'kernel','value':{'blocked':True}}]})
    value={'summary':'一次已阻止的修改尝试，不表示损害','findings':[{'evidence_ids':['kernel:1'],'category':'integrity','severity':'medium','explanation':'修改被阻止'}]}
    with pytest.raises(ValueError,match='实际'):agent.validate_final(value)
    with pytest.raises(ValueError):agent.execute({'tool':'shell','arguments':{}})
    agent.execute({'tool':'read_evidence','arguments':{'evidence_id':'kernel:1'}})
    agent.validate_final(value)
    value['findings'][0]['evidence_ids']=['kernel:999']
    with pytest.raises(ValueError):agent.validate_final(value)

def test_postrun_reader_failure_preserves_unknown_integrity_evidence(scene,monkeypatch):
    world,_,_=scene
    def unavailable(*args):raise life.refs.ReaderUnavailable()
    monkeypatch.setattr(life.refs,'snapshot',unavailable)
    key=life.enqueue(store.get(world.a['id']),'failed-read','postrun','unavailable-reader')
    with db.connect() as con:snapshot=json.loads(con.execute('SELECT input_json FROM instance_policy_jobs WHERE id=?',(key,)).fetchone()[0])
    assert snapshot['integrity'][0]['unchanged'] is None
    assert snapshot['integrity'][0]['after_sha256'] is None
    assert any(r['id']=='integrity:README.md' for r in snapshot['records'])
    assert not snapshot['integrity_coverage']['continuous_monitoring']

def test_review_requires_same_instance_input_and_append_only(scene):
    world,_,_=scene;row=store.get(world.a['id']);key=life.enqueue(row,'s','postrun',uuid.uuid4().hex)
    result={'summary':'审计完成','findings':[{'id':'0','evidence_ids':['kernel:1']}]}
    with db.connect() as con:con.execute("UPDATE instance_policy_jobs SET state='completed',result_json=? WHERE id=?",(json.dumps(result),key))
    job=life.jobs(row['id'],'s')['records'][0];body={'input_hash':job['input_hash'],'finding_id':'0','disposition':'needs_investigation','note':'核对业务意图'}
    with pytest.raises(ValueError):life.review(world.b['id'],key,body)
    with pytest.raises(ValueError):life.review(row['id'],key,{**body,'input_hash':'f'*64})
    assert life.review(row['id'],key,body)['original_evidence_changed'] is False
    assert life.jobs(row['id'],'s')['records'][0]['result']==result
    assert len(life.jobs(row['id'],'s')['reviews'])==1

def test_template_tools_publish_schema_and_materialize_without_apply(reference):
    world,_,_=reference
    tools=template_tools.definitions();tool=next(t for t in tools if t['template_id']=='FILE-CHANGE')
    assert tool['input_schema']['additionalProperties'] is False and tool['applicable_when']['stages']==['preflight','runtime']
    draft=template_tools.instantiate(world.a['id'],tool['name'],{'name':'说明文件保护','parameters':{'target':'/w/0/README.md','operations':'write,unlink'}})
    assert draft['validated'] and not draft['applied'] and not world.calls
    with pytest.raises(ValueError):template_tools.instantiate(world.a['id'],tool['name'],{'name':'越界','parameters':{'target':'/etc/passwd'}})
    with pytest.raises(ValueError):template_tools.instantiate(world.a['id'],tool['name'],{'name':'扩权','parameters':{'target':'/w/0/a'},'apply':True})

def test_lifecycle_endpoints_are_authenticated(scene):
    world,_,_=scene
    path='/api/policy-lifecycle/'+world.a['id']
    assert world.client.get(path).status_code==401
    assert world.client.get(path,headers=ADMIN).status_code==200
    assert world.client.post(path+'/jobs/foreign/review',headers=ADMIN,json={'input_hash':'a'*64,'finding_id':'0','disposition':'confirmed_risk','note':'check','apply':True}).status_code==422

def test_lifecycle_requirements_do_not_persist_credentials(scene):
    world,_,configuration=scene
    value=life.configure(world.a['id'],{'enabled':False,'requirements':'场景要求 password=fixture-redaction-only',
        'workspace_id':configuration['workspace_id'],'integrity_paths':['README.md']})
    assert 'fixture-redaction-only' not in value['requirements']
    assert '[REDACTED]' in life.config(world.a['id'])['requirements']
