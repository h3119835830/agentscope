"""DSL contracts use ActPlane's real parser/compiler; only privileged IO is faked."""
import hashlib
import json
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import pytest
from agentscope_app import db
from agentscope_app.instances import controller as c,store,dsl_policy as dsl,sessions,system_policy as system
from agentscope_app.instances.policy import default_policy,digest
from dsl_documents import prepare,fingerprint,canonical_documents,adapter_binary

ADMIN={'Authorization':'Bearer test-admin-token-not-for-production'}
TEXT='source AGENT = exec "**"\nrule protect:\n block read file "/w/0/block.txt" if AGENT\n notify read file "/w/0/notify.txt" if AGENT\n kill read file "/w/0/kill.txt" if AGENT\n because "Isolation acceptance"\n'
def document(text=TEXT,ident='doc',metadata=None):
    return dict(id=ident,name='Security.dsl',original_dsl=text,metadata=metadata or {})

@pytest.fixture
def world(client,tmp_path,monkeypatch):
    def clear():
        with db.connect() as con:
            for table in ('policy_application_requests','policy_approval_decisions','policy_draft_creations','policy_draft_versions','policy_drafts','system_policy_library_proposals','system_policy_library_versions','system_policy_library','instance_dsl_scopes','instance_dsl_proposals','instance_policy_receipts','instance_session_cache','instance_kernel_cursors','instance_kernel_events','instance_session_task_bindings','instance_leases','instance_events','instance_proposals','instance_proposal_locals','system_security_proposals','instance_local_policies','agent_instances'):
                con.execute('DELETE FROM '+table)
            con.execute("UPDATE system_security_policy SET policy_json=?,policy_hash=?,revision=0,phase='ready'",(json.dumps(default_policy()),digest(default_policy())))
    clear()
    if not Path(adapter_binary()).exists():pytest.fail('Build backend/dsl-adapter before DSL acceptance')
    roots=[tmp_path/'a',tmp_path/'b']
    for p in roots:p.mkdir()
    a=store.create('Same name','dsh',[str(roots[0])]);b=store.create('Same name','hermes',[str(roots[1])])
    live={};calls=[];fail={'start':False,'stop':False};artifacts={}
    # Use the real compiled clauses, not a regex-based replacement compiler.
    def compile_message(message,timeout=60):
        assert message['action']=='agent-instance-dsl-compile'
        parsed=prepare(message['dsl_documents'],message['resources'],{'dsh':'**/node','hermes':'**/python'}.get(message.get('agent_type')))
        from broker.instance_runtime import policy_dsl,validate_runtime_capabilities
        validate_runtime_capabilities(parsed)
        text=policy_dsl(message['resources'],message['policy'])+'\n'+'\n'.join(d['effective_dsl'] for d in parsed)
        path=tmp_path/'compile.yaml';path.write_text('version: 1\npolicy: |\n'+''.join('  '+l+'\n' for l in text.splitlines()))
        engine=Path(__file__).resolve().parents[2]/'actplane/target/release/actplane'
        result=subprocess.run([str(engine),'--policy',str(path),'compile','--json'],capture_output=True,text=True,timeout=15)
        if result.returncode:raise ValueError(result.stderr)
        compiled=json.loads(result.stdout)
        if not all(x['supported'] for x in compiled['backend_support']['clauses']):raise ValueError('Unsupported clause')
        artifact=dict(documents=parsed,effective_dsl=text,compile=compiled,bundle_hash=hashlib.sha256(text.encode()).hexdigest(),dsl_hash=fingerprint(message['dsl_documents'],message['resources']),loaded=False)
        artifacts[message['instance_id']]=artifact
        return artifact
    monkeypatch.setattr(dsl,'broker',compile_message)
    class Adapter:
        def stop(self,row):
            calls.append(('stop',row['id']))
            if fail['stop']:raise RuntimeError('stop failed')
            live.pop(row['id'],None)
        def start(self,row,token,generation):
            calls.append(('start',row['id']))
            if fail['start']:raise RuntimeError('load failed')
            spec=dsl.launch_spec(row)
            artifact=compile_message(dict(action='agent-instance-dsl-compile',instance_id=row['id'],agent_type=row['agent_type'],resources=row['resources'],policy=row['policy'],dsl_documents=spec['dsl_documents']))
            runtime=dict(connected=True,verified=True,generation=generation,pid=1234,domain_id=900,dsl_hash=spec['dsl_hash'],policy_artifact={**artifact,'loaded':True})
            live[row['id']]={**runtime,'id':row['id']};return runtime
    monkeypatch.setattr(c,'adapter',lambda row:Adapter())
    monkeypatch.setattr(c.observer,'snapshot',lambda:list(live.values()))
    monkeypatch.setattr(c.observer,'collect',lambda:None)
    monkeypatch.setattr(c.discovery,'windows_snapshot',lambda:[])
    monkeypatch.setattr(sessions,'collect_kernel',lambda row:{'available':False})
    def running(row):
        gen=uuid.uuid4().hex;store.update(row['id'],gate='open',generation=gen,runtime={'verified':True})
        live[row['id']]={'id':row['id'],'connected':True,'verified':True,'generation':gen,'domain_id':900,'pid':1234}
    yield SimpleNamespace(a=a,b=b,live=live,calls=calls,fail=fail,run=running,client=client,compile=compile_message)
    clear()

def candidate(scope='system',docs=None,key=None):
    base=dsl.current(scope)
    return dsl.propose(scope,dict(documents=[document()] if docs is None else docs,base_hash=base['document_hash'],base_revision=base['revision'],request_key=key or uuid.uuid4().hex))
def apply(scope='system',docs=None):
    p=candidate(scope,docs);assert p['state']=='pending',p['result']['error']
    return dsl.apply(scope,p['id'],p['proposal_hash'])

def test_real_ast_multi_action_original_document_and_clause_mapping(world):
    p=candidate(world.a['id'])
    assert p['state']=='pending' and not world.calls
    assert dsl.current(world.a['id'])['documents']==[]
    artifact=p['result']['compilations'][0]
    record=dsl.policy_records(artifact)[0]
    assert record['effects']==['block','notify','kill'] and record['event_types']==['per_event']
    assert record['original_document']==TEXT and record['statement_origin']=='dsl_summary'
    assert len(record['compiled_refs'])==3 and not record['loaded'] and not record['active']
    assert all(r['source_ref']==record['source_ref'] and r['clause_hash'] for r in record['compiled_refs'])

def test_static_supported_but_pinned_matcher_unavailable_cannot_apply(world):
    text=TEXT.replace('/w/0/block.txt','**/block.txt')
    p=candidate(world.a['id'],[document(text)])
    assert p['state']=='invalid' and '文件路径后缀匹配' in p['result']['error']
    assert dsl.current(world.a['id'])['documents']==[] and not world.calls
    with pytest.raises(ValueError):dsl.apply(world.a['id'],p['id'],p['proposal_hash'])

def test_real_gate_taint_lineage_and_transforms_preserved(world):
    text='''source AGENT = exec "**"
source SECRET = file "/w/0/.env"
declassify SECRET by exec "sanitizer"
rule gate:
 kill exec "git" "commit" if AGENT unless after exec "pytest" exits 0 since write "/w/0/src/**" or write "/w/0/tests/**"
 because "Tests required"
rule flow:
 notify connect endpoint "10.0.0.1" if SECRET
 because "Secret flow"
rule lineage:
 kill exec "curl" if AGENT unless lineage-includes exec "approved"
 because "Lineage required"
'''
    p=candidate(world.a['id'],[document(text)])
    assert p['state']=='pending',p['result']['error']
    records=dsl.policy_records(p['result']['compilations'][0])
    assert len(records)==3 and all(r['event_types']==['cross_event'] for r in records)
    assert 'since write "/w/0/src/**" or write "/w/0/tests/**"' in p['result']['compilations'][0]['effective_dsl']
    assert all(r['original_document']==text for r in records)

def test_system_isolation_future_connection_and_stopped_connections(world):
    world.run(world.a);store.update(world.b['id'],gate='paused')
    receipt=apply()
    assert receipt['affected_count']==2 and receipt['resumed_count']==1
    assert [x[1] for x in world.calls if x[0]=='start']==[world.a['id']]
    assert store.get(world.b['id'])['gate']=='closed'
    assert all(len(dsl.launch_spec(store.get(row['id']))['dsl_documents'])==1 for row in (world.a,world.b))
    future=store.create('Future','dsh',world.a['resources'])
    assert dsl.launch_spec(future)['dsl_documents'][0]['scope_id']=='system'
    apply(world.a['id'],[document(TEXT,'own')])
    assert len(dsl.documents_for(world.a['id']))==2 and len(dsl.documents_for(world.b['id']))==1
    apply(world.a['id'],[])
    assert dsl.documents_for(world.a['id'])[0]['scope_id']=='system'

def test_invalid_context_syntax_and_foreign_labels_save_non_applicable_drafts(world):
    for doc in (document('invalid'),document(TEXT.replace('if AGENT','if FOREIGN')),document(metadata={'protect':{'context_requirement':'project'}}),document('source A = exec "**"\nrule p:\n block exec "git" "commit" if A\n because "Unsupported pre-exec argv"')):
        p=candidate(world.a['id'],[doc]);assert p['state']=='invalid' and p['result']['error']
        with pytest.raises(ValueError):dsl.apply(world.a['id'],p['id'],p['proposal_hash'])
    assert dsl.current(world.a['id'])['revision']==0 and not world.calls

def test_namespaces_cannot_declassify_parent_or_platform(world):
    apply('system',[document(TEXT,'shared')])
    text='source AGENT = exec "**"\ndeclassify AGENT by exec "anything"\nrule protect:\n notify exec "git" if AGENT\n because "Own labels only"\n'
    p=candidate(world.a['id'],[document(text,'shared')]);assert p['state']=='pending'
    art=p['result']['compilations'][0];a,b=art['documents']
    assert a['namespace']!=b['namespace']
    assert 'declassify '+b['namespace']+'_AGENT' in art['effective_dsl']
    assert 'declassify '+a['namespace']+'_AGENT' not in art['effective_dsl']
    assert 'rule immutable-no-publish:' in art['effective_dsl']

def test_stale_generation_system_change_concurrent_edit_and_exact_idempotency(world):
    p=candidate(world.a['id']);store.update(world.a['id'],generation='new')
    with pytest.raises(ValueError,match='变化'):dsl.apply(world.a['id'],p['id'],p['proposal_hash'])
    p=candidate(world.a['id']);apply('system')
    with pytest.raises(ValueError,match='变化'):dsl.apply(world.a['id'],p['id'],p['proposal_hash'])
    candidates=[candidate(world.a['id']),candidate(world.a['id'],[])]
    def confirm(p):
        try:return dsl.apply(world.a['id'],p['id'],p['proposal_hash'])['state']
        except ValueError:return 'stale'
    with ThreadPoolExecutor(2) as pool:assert sorted(pool.map(confirm,candidates))==['applied','stale']
    key=uuid.uuid4().hex;p=candidate(world.b['id'],key=key)
    assert candidate(world.b['id'],key=key)['id']==p['id']
    with pytest.raises(ValueError,match='幂等'):candidate(world.b['id'],[],key=key)

@pytest.mark.parametrize('failure',['stop','start'])
def test_failed_load_blocks_leases_and_recovery_never_restarts_stopped_agent(world,failure):
    world.run(world.a);world.run(world.b);p=candidate(world.a['id']);world.fail[failure]=True
    with pytest.raises(RuntimeError):dsl.apply(world.a['id'],p['id'],p['proposal_hash'])
    assert dsl.current(world.a['id'])['phase']=='blocked' and not c.detail(world.a['id'])['active']
    assert not c.lease(world.a['id'],dict(generation=store.get(world.a['id'])['generation'],session_id='s',call_id='x',tool='read'))['allowed']
    assert c.lease(world.b['id'],dict(generation=store.get(world.b['id'])['generation'],session_id='other',call_id='unaffected',tool='read'))['allowed']
    world.fail[failure]=False;apply(world.a['id'])
    assert dsl.current(world.a['id'])['phase']=='ready' and store.get(world.a['id'])['gate']=='closed'

def test_read_receipt_from_old_document_is_never_new_policy_active(world):
    world.run(world.a);apply(world.a['id'])
    first=dsl.detail(world.a['id']);assert first['records'][0]['active']
    with db.connect() as con:con.execute("UPDATE instance_dsl_scopes SET documents_json=?,document_hash=? WHERE scope_id=?",(json.dumps([document(TEXT.replace('Isolation acceptance','Changed'))]),digest([document(TEXT.replace('Isolation acceptance','Changed'))]),world.a['id']))
    assert not c.detail(world.a['id'])['active']
    assert not [r for r in dsl.detail(world.a['id'])['records'] if r.get('active')]

def test_admin_api_and_native_agent_token_rejected(world):
    token=uuid.uuid4().hex;store.update(world.a['id'],token_hash=hashlib.sha256(token.encode()).hexdigest())
    agent={'Authorization':'Bearer '+token}
    for path in ('/api/security/system/dsl','/api/agent-instances/'+world.a['id']+'/dsl','/api/sessions'):
        assert world.client.get(path,headers=agent).status_code==401
        assert world.client.get(path,headers=ADMIN).status_code==200
    base=dsl.current('system');body=dict(documents=[document()],base_hash=base['document_hash'],base_revision=0,request_key=uuid.uuid4().hex)
    assert world.client.post('/api/security/system/dsl/proposals',headers=agent,json=body).status_code==401
    p=world.client.post('/api/security/system/dsl/proposals',headers=ADMIN,json=body);assert p.status_code==200 and p.json()['state']=='pending'
    assert world.client.post('/api/security/system/dsl/proposals',headers=ADMIN,json={**body,'command':'x'}).status_code==422

def test_directory_same_native_id_two_connections_workspace_optional_and_cache(world,monkeypatch):
    world.run(world.a);world.run(world.b)
    def native(message,**kw):
        if message['instance_id']==world.a['id']:return {'sessions':[{'id':'same','name':'Same name','resource':world.a['resources'][0],'mapping':'native_registry','process_ids':[1234],'status':'idle'}],'executor_shared':True}
        return {'sessions':[{'id':'same','name':'Same name','mapping':'native_gateway','process_ids':[5678],'status':'idle'}],'executor_shared':True}
    monkeypatch.setattr(sessions,'broker',native)
    rows=sessions.directory()['records'];assert len(rows)==2 and {r['instance_id'] for r in rows}=={world.a['id'],world.b['id']}
    assert all(r['agent_pid']==1234 for r in rows)
    assert all(r['pid']==1234 for r in sessions.directory()['connections'])
    path=world.a['resources'][0]
    filtered=sessions.directory(workspace=path,limit=1)
    assert [s['instance_id'] for s in filtered['records']]==[world.a['id']]
    assert filtered['workspaces']==[path] and filtered['total']==1
    assert sessions.directory(workspace=path+'/not-native')['records']==[]
    response=world.client.get('/api/sessions',headers=ADMIN,params={'workspace':path,'limit':1})
    assert response.status_code==200 and response.json()['total']==1
    assert sessions.directory('hermes')['workspace_available'] is False
    world.live.clear();stored=sessions.directory()['records'];assert all(s['historical'] and not s['process_ids'] for s in stored)
    assert all(s['agent_pid'] is None for s in stored)
    assert all(s['pid'] is None for s in sessions.directory()['connections'])
    assert len(sessions.directory(q='Same name')['records'])==2

def test_kernel_requires_exact_generation_domain_hash_clause_and_trusted_tool_tag(world):
    world.run(world.a);apply(world.a['id']);row=store.get(world.a['id']);saved=dsl.receipt(row['id'],row['generation']);ref=saved['artifact']['compile']['rules'][-1]
    event=dict(event='taint_violation',process_domain_id=900,domain_id=900,rule_id=77,pid=999,effect=ref['effect'],action='notify',blocked=False,killed=False,op='file_read',target='/w/0/notify.txt',tool_call_tag=91,rule=ref)
    raw=dict(id=1,generation=row['generation'],bundle_hash=saved['bundle_hash'],domain_id=900,event_json=json.dumps(event),created_at=db.now())
    value=sessions.project_kernel(row,saved,raw)
    assert value['source_refs'] and value['attribution']=='shared_executor_unattributed' and value['feedback_delivered'] is None
    for field,value in (('bundle_hash','wrong'),('generation','wrong'),('domain_id',901)):
        assert not sessions.project_kernel(row,saved,{**raw,field:value})['source_refs']
    store.event(row['id'],'tool_start',{'kernel_call_tag':91,'domain_id':900},row['generation'],'same','call1','read')
    linked=sessions.project_kernel(row,saved,raw);assert linked['session_id']=='same' and linked['call_id']=='call1'
    with db.connect() as con:
        con.execute('INSERT INTO instance_kernel_events(instance_id,generation,source_key,bundle_hash,domain_id,event_json,created_at) VALUES(?,?,?,?,?,?,?)',
                    (row['id'],row['generation'],'test-hit',saved['bundle_hash'],900,json.dumps(event),db.now()))
    records=dsl.policy_records(saved['artifact'])
    sessions.attach_hits(records,row,row['generation'],session_id='other-session')
    assert all(not r['hits'] for r in records)
    sessions.attach_hits(records,row,row['generation'],session_id='same')
    assert any(r['hits'] for r in records)
    wrong={**event,'process_domain_id':901};assert sessions.project_kernel(row,saved,{**raw,'event_json':json.dumps(wrong)})['session_id'] is None

def test_tool_admission_denial_does_not_fabricate_kernel_event(world,monkeypatch):
    world.run(world.a);row=store.get(world.a['id'])
    monkeypatch.setattr(sessions,'native_sessions',lambda row:{'sessions':[{'id':'same','name':'Sample','process_ids':[1234]}]})
    store.event(row['id'],'tool_denied',{'reason':'Blocked by tool admission'},row['generation'],'same','denied','bash')
    result=sessions.traces(row['id'],'same')['records'][0]
    assert result['result']=='tool_denied' and result['kernel_events']==[] and result['feedback_delivered'] is None
    assert sessions.kernel_page(row['id'],'same')['records']==[]


@pytest.mark.parametrize('template_index',range(6))
def test_curated_rq1_templates_compile_as_unapplied_agent_candidates(world,template_index):
    # Reuse the frontend materializer and the real AST/runtime compiler in an isolated DB.
    frontend=Path(__file__).resolve().parents[2]/'frontend'
    program="""import fs from 'node:fs';
import {materializeTemplate} from './src/agentPolicyHandoff.mjs';
const t=JSON.parse(fs.readFileSync('./src/rq1-agent-templates.json','utf8')).templates[Number(process.argv[1])];
console.log(JSON.stringify(materializeTemplate(t,Object.fromEntries(t.parameters.map(p=>[p.key,p.value])),'isolated acceptance','rq1-candidate',[{pattern:'**/node'}])));"""
    result=subprocess.run(['node','--input-type=module','-e',program,str(template_index)],cwd=frontend,capture_output=True,text=True,check=True)
    doc=json.loads(result.stdout)
    proposal=candidate(world.a['id'],[doc])
    assert dsl.current(world.a['id'])['documents']==[] and not world.calls
    # Unsupported runtime semantics must stay invalid, never become applicable based on RQ1 history.
    if template_index==3:
        assert proposal['state']=='invalid' and proposal['result']['error']
    else:
        assert proposal['state']=='pending',proposal['result']['error']


@pytest.mark.parametrize('template_index',range(3))
def test_system_configuration_records_compile_without_applying(world,template_index):
    frontend=Path(__file__).resolve().parents[2]/'frontend'
    program="""import fs from 'node:fs';
import {createSystemHandoff} from './src/agentPolicyHandoff.mjs';
const t=JSON.parse(fs.readFileSync('./src/system-policy-configurations.json','utf8'))[Number(process.argv[1])];
console.log(JSON.stringify(createSystemHandoff(t,Object.fromEntries(t.parameters.map(p=>[p.key,p.value])),'isolated acceptance','system-candidate',[{pattern:'**/node'},{pattern:'**/python'}]).document));"""
    result=subprocess.run(['node','--input-type=module','-e',program,str(template_index)],cwd=frontend,capture_output=True,text=True,check=True)
    proposal=candidate('system',[json.loads(result.stdout)])
    assert proposal['state']=='pending',proposal['result']['error']
    assert dsl.current('system')['documents']==[] and not world.calls


def test_generated_candidate_context_is_rechecked_before_confirm_and_no_process_is_stopped(world,monkeypatch):
    from agentscope_app.history import agent_context
    doc=document(TEXT,'generated')
    doc['generation_binding']={'artifact_id':'a'*32,'context_hash':'b'*64}
    checks=[]
    def selected(scope,artifact):
        checks.append((scope,artifact))
        return {'document':doc,'scopeType':'agent'}
    monkeypatch.setattr(agent_context,'selected_candidate',selected)
    p=candidate(world.a['id'],[doc])
    assert p['state']=='pending' and len(checks)==1 and not world.calls
    def stale(*args):raise ValueError('Agent 或会话环境已变化')
    monkeypatch.setattr(agent_context,'selected_candidate',stale)
    with pytest.raises(ValueError,match='环境已变化'):dsl.apply(world.a['id'],p['id'],p['proposal_hash'])
    assert not world.calls and dsl.current(world.a['id'])['revision']==0


# Same executor/product/name/resource does not define an instance security scope.
def test_node_agent_candidate_and_application_never_select_other_dsh_or_hermes(world):
    other=store.create(world.a['name'],'dsh',world.a['resources'])
    for row in (world.a,other,world.b):world.run(row)
    foreign_before={r['id']:store.get(r['id']) for r in (other,world.b)}
    source=TEXT.replace('exec "**"','exec "**/node"')
    p=candidate(world.a['id'],[document(source)])
    assert p['state']=='pending',p['result']['error']
    assert [t['id'] for t in p['targets']]==[world.a['id']]
    assert [r['instance_id'] for r in p['result']['compilations']]==[world.a['id']]
    assert not world.calls
    assert all(d['scope_id']==world.a['id'] for d in p['result']['compilations'][0]['documents'])
    # This apply executes only the existing fixture Adapter against the test DB.
    result=dsl.apply(world.a['id'],p['id'],p['proposal_hash'])
    assert result['affected_count']==result['resumed_count']==1
    assert world.calls==[('stop',world.a['id']),('stop',world.a['id']),('start',world.a['id'])]
    for ident,before in foreign_before.items():
        assert store.get(ident)==before
        assert dsl.current(ident)['documents']==[]
        assert dsl.launch_spec(store.get(ident))['dsl_documents']==[]
        assert ident in world.live


def test_node_candidate_cannot_be_confirmed_through_a_different_agent(world):
    source=TEXT.replace('exec "**"','exec "**/node"')
    p=candidate(world.a['id'],[document(source)])
    assert p['state']=='pending'
    before={r['id']:store.get(r['id']) for r in (world.a,world.b)}
    with pytest.raises(ValueError,match='确认内容不一致'):
        dsl.apply(world.b['id'],p['id'],p['proposal_hash'])
    assert not world.calls
    assert all(store.get(ident)==r for ident,r in before.items())
    assert dsl.current(world.a['id'])['documents']==[]
    assert dsl.current(world.b['id'])['documents']==[]


def test_system_node_scope_and_agent_node_scope_are_explicitly_different(world):
    source=TEXT.replace('exec "**"','exec "**/node"')
    agent=candidate(world.a['id'],[document(source)])
    shared=candidate('system',[document(source)])
    assert [t['id'] for t in agent['targets']]==[world.a['id']]
    assert {t['id'] for t in shared['targets']}=={world.a['id'],world.b['id']}
    assert not world.calls
    assert dsl.current('system')['documents']==[]
