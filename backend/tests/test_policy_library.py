"""Persisted draft/version/application boundaries, using the real DSL adapter."""
import json,uuid
import pytest
from agentscope_app import db
from agentscope_app.instances import policy_library as lib,dsl_policy as dsl,store,approval_views
from dsl_documents import prepare
from test_dsl_configuration import world,ADMIN,TEXT,document

def config(template='env',**extra):
    row=next(t for t in lib.CATALOG if t['id']==template)
    return {**{k:row[k] for k in ('name','mode','values','ops','effect','reason')},'template_id':template,**extra}
def save(**extra):return lib.save({'kind':'structured','config':config(**extra),'base_revision':0})
def proposal(items,removals=None):
    base=dsl.current('system')
    return lib.propose(dict(selections=[{'id':i['id'],'revision':i['revision']} for i in items],removals=removals or [],base_revision=base['revision'],base_hash=base['document_hash'],request_key=uuid.uuid4().hex))

@pytest.fixture
def capable(world,monkeypatch):
    from broker import instance_runtime
    monkeypatch.setattr(instance_runtime,'execution_capabilities',lambda:{'verified':True,'file_suffix':True,'max_suffix_bytes':63})
    return world

def test_save_is_persistent_unselected_and_versioned_without_runtime_changes(world):
    item=save()
    assert item['revision']==1 and dsl.current('system')['documents']==[] and not world.calls
    data=world.client.get('/api/security/system/policy-library',headers=ADMIN).json()
    assert len(data['catalog'])==12 and len(data['items'])==1
    assert data['items'][0]['id']==item['id'] and not data['items'][0]['applied']
    edited=lib.save(dict(kind='structured',config=config(effect='notify'),base_revision=1),item['id'])
    assert edited['revision']==2 and lib.get(item['id'])['config']['effect']=='notify'
    with pytest.raises(ValueError,match='修改'):lib.save(dict(kind='structured',config=config(),base_revision=1),item['id'])
    assert not world.calls and dsl.current('system')['revision']==0

def test_twelve_presets_all_three_effects_compile_with_trusted_identity(capable):
    for preset in lib.CATALOG:
        for effect in ('block','notify','kill'):
            params=config(preset['id'],effect=effect)
            if not params['values']:params['values']='/real-policy-store'
            item=lib.save(dict(kind='structured',config=params,base_revision=0))
            p=proposal([item]);assert p['state']=='pending',p['result']
            assert len(p['result']['compilations'])==2
            for art in p['result']['compilations']:
                doc=art['documents'][0]
                assert doc['identity_binding']['pattern'] in ('**/node','**/python')
                assert doc['original_dsl']==item['document']['original_dsl']
                assert doc['rules'][0]['source_start_line']>=1
                assert all(c['effect']==effect for c in doc['rules'][0]['clauses'])
    assert not capable.calls and dsl.current('system')['revision']==0

def test_edit_active_keeps_old_version_selected_merge_and_explicit_remove(capable):
    a=save();p=proposal([a]);dsl.apply('system',p['id'],p['proposal_hash'])
    current=dsl.current('system');assert current['documents'][0]==a['document']
    edited=lib.save(dict(kind='structured',config=config(effect='notify'),base_revision=1),a['id'])
    assert dsl.current('system')==current
    b=lib.save(dict(kind='structured',config=config('network-audit'),base_revision=0))
    p=proposal([b]);assert len(p['documents'])==2
    assert next(d for d in p['documents'] if d['id']==a['id'])==a['document']
    dsl.apply('system',p['id'],p['proposal_hash'])
    data=lib.directory();first=next(i for i in data['items'] if i['id']==a['id'])
    assert first['has_changes'] and first['applied_revision']==1 and first['revision']==2
    with pytest.raises(ValueError,match='停用'):lib.archive(a['id'],2)
    p=proposal([], [a['id']]);assert [d['id'] for d in p['documents']]==[b['id']]
    dsl.apply('system',p['id'],p['proposal_hash']);lib.archive(a['id'],2)
    assert lib.get(a['id'])['archived']

def test_library_revision_change_stales_existing_approval(capable):
    a=save();p=proposal([a])
    lib.save(dict(kind='structured',config=config(effect='notify'),base_revision=1),a['id'])
    assert approval_views.detail(p['id'])['status']=='stale'
    with pytest.raises(ValueError,match='配置库'):dsl.apply('system',p['id'],p['proposal_hash'])
    assert not capable.calls

def test_raw_multi_rule_document_and_dependencies_round_trip_atomically(capable):
    source=TEXT+'\nrule second:\n notify exec "git" if AGENT unless after read "/w/0/approved"\n because "Full dependency"\n'
    item=lib.save(dict(kind='dsl',document=document(source),base_revision=0))
    assert len(item['rules'])==2 and lib.get(item['id'])['document']['original_dsl']==source
    p=proposal([item]);assert p['state']=='pending',p['result']
    assert len(p['documents'])==1 and len(dsl.policy_records(p['result']['compilations'][0]))==2
    dsl.apply('system',p['id'],p['proposal_hash'])
    assert dsl.current('system')['documents'][0]['original_dsl']==source
    assert proposal([], [item['id']])['documents']==[]

def test_existing_system_dsl_migration_preserves_original_and_applied_link(world):
    doc=document()
    with db.connect() as con:
        con.execute('INSERT INTO instance_dsl_scopes VALUES(?,?,?,?,?,?)',('system',5,json.dumps([doc]),dsl.digest([doc]),'ready',db.now()))
        lib.init(con)
    item=lib.directory()['items'][0]
    assert item['document']==doc and item['applied'] and item['applied_revision']==1
    with db.connect() as con:lib.init(con)
    assert len(lib.directory()['items'])==1


def test_legacy_dsl_confirmed_after_startup_is_visible_without_replacing_drafts(world):
    from test_dsl_configuration import apply
    apply('system',[document()])
    first=lib.directory()['items'][0]
    assert first['document']['original_dsl']==TEXT and first['applied']
    edited=lib.save(dict(kind='dsl',document=document(TEXT.replace('Isolation acceptance','Edited draft')),base_revision=1),'doc')
    refreshed=lib.directory()['items'][0]
    assert refreshed['document']==edited['document'] and refreshed['has_changes']

def test_native_credentials_cannot_read_save_propose_archive_or_confirm(world):
    token='native-not-admin';headers={'Authorization':'Bearer '+token}
    for path,body in [('/api/security/system/policy-library',dict(kind='structured',config=config(),base_revision=0)),('/api/security/system/policy-library/x/versions',dict(kind='dsl',document=document(),base_revision=1)),('/api/security/system/policy-library/x/archive',dict(revision=1)),('/api/security/system/policy-library/proposals',{}),('/api/security/system/dsl/proposals/x/confirm',{'proposal_hash':'0'*64})]:
        assert world.client.post(path,headers=headers,json=body).status_code==401
    for path in ('/api/security/system/policy-library','/api/security/system/execution-capabilities'):
        assert world.client.get(path,headers=headers).status_code==401

def test_suffix_size_literal_semantics_and_reserved_binding(world):
    doc,_=lib.structured('long',config(values='.'+'a'*62))
    assert prepare([{**doc,'scope_id':'system'}],[],'**/node')
    for values in ('.'+'a'*63,'.环境'*16,'*.env','env'):
        with pytest.raises(ValueError):lib.structured('bad',config(values=values))
    with pytest.raises(ValueError,match='可信'):prepare([{**doc,'scope_id':'system'}],[])
    with pytest.raises(ValueError,match='覆盖'):prepare([{**doc,'scope_id':'system','original_dsl':'source AGENT = exec "**"\n'+doc['original_dsl']}],[],'**/node')

def test_malformed_configuration_is_rejected_without_server_error(world):
    for extra in ({'name':[]},{'mode':{}},{'effect':[]},{'ops':[{}]}):
        response=world.client.post('/api/security/system/policy-library',headers=ADMIN,json=dict(kind='structured',config=config(**extra),base_revision=0))
        assert response.status_code==409,response.text

def test_capability_change_after_preview_blocks_before_stopping(capable,monkeypatch):
    p=proposal([save()]);original=dsl.broker
    def changed(*a,**k):return {**original(*a,**k),'execution_capabilities':{'binary_sha256':'different'}}
    monkeypatch.setattr(dsl,'broker',changed)
    with pytest.raises(ValueError,match='执行能力'):dsl.apply('system',p['id'],p['proposal_hash'])
    assert not capable.calls


def test_partial_system_load_failure_persists_target_results_and_pauses_all(capable,monkeypatch):
    from agentscope_app.instances import controller as c
    capable.run(capable.a);capable.run(capable.b)
    p=proposal([save()]);original=c.start
    def start(ident):
        if ident==capable.b['id']:raise RuntimeError('isolated load failure')
        return original(ident)
    monkeypatch.setattr(c,'start',start)
    with pytest.raises(RuntimeError):dsl.apply('system',p['id'],p['proposal_hash'])
    detail=dsl.detail('system');result=detail['proposals'][0]['result']['application']
    assert result['failed_target']==capable.b['id'] and result['failed_operation']=='load'
    assert {t['status'] for t in result['targets']}=={'failed','paused'}
    assert detail['phase']=='blocked' and not any(t['active'] for t in detail['targets'])


def test_system_preview_includes_retained_controlled_targets(capable,monkeypatch):
    from agentscope_app import console
    monkeypatch.setattr(console,'hidden',lambda kind:{capable.b['id']})
    p=proposal([save()]);view=approval_views.detail(p['id'])
    assert len(p['targets'])==2
    assert {t['id'] for t in view['targets']}=={capable.a['id'],capable.b['id']}
