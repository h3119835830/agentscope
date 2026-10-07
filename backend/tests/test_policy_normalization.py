"""Real compiler tests: equivalence, conservative retention and proof tampering."""
import copy,json,subprocess,uuid
from pathlib import Path
import pytest,yaml
from agentscope_app import db,config
from agentscope_app.services import policy_normalization as n
from agentscope_app.managed import controller as c,records

@pytest.fixture
def real_compiler(tmp_path,monkeypatch):
    binary=Path(__file__).resolve().parents[2]/'actplane/target/release/actplane'
    if not binary.is_file():pytest.skip('Build actplane release to run actual compiler acceptance')
    monkeypatch.setattr(config,'ACTPLANE_BIN',binary)
    def compile(bundle,*_):
        path=tmp_path/'policy.yaml';path.write_text(bundle)
        result=subprocess.run([str(binary),'--policy',str(path),'compile','--json'],capture_output=True,text=True,timeout=20)
        data=json.loads(result.stdout)
        return ('compiled' if result.returncode==0 and data.get('ok') else 'compile_failed',data,data.get('error'))
    return compile

def rule(name='bootstrap-1',path='/tmp/locked',op='write',condition='if AGENT',effect='block',reason='first'):
    return f'rule {name}:\n  {effect} {op} file "{path}" {condition}\n  because "{reason}"\n'

def bundle(dsl):return yaml.safe_dump({'version':1,'policy':dsl},sort_keys=False)
def analyze(compile,dsl,mode='deduplicate',task='a',workspace='/tmp'):
    status,info,error=compile(bundle(dsl))
    assert status=='compiled',error
    report=n.analyse(dsl,info,task,workspace,mode)
    status,actual,error=compile(bundle(report['normalized_dsl']))
    assert status=='compiled',error
    n.complete(report,actual)
    return report,actual

SOURCE='source AGENT = exec "**"\n'

def test_real_duplicate_different_reasons_keep_lineage(real_compiler):
    raw=SOURCE+rule()+rule('bootstrap-2',reason='second')
    report,actual=analyze(real_compiler,raw)
    assert report['raw_clause_count']==2 and len(actual['rules'])==1
    assert [x['reason'] for x in report['clauses']]==['first','second']
    assert len({x['logical_rule_id'] for x in report['clauses']})==1
    assert all(x['clause_ids']==[0] for x in report['clauses'])
    assert 'bootstrap-2' not in report['normalized_dsl']
    assert report['raw_dsl']==raw

@pytest.mark.parametrize('second',[
    rule('bootstrap-2',op='unlink'),rule('runtime-file-protection'),
    rule('bootstrap-2',path='/tmp/lockedd'),rule('bootstrap-2',condition='if not AGENT'),
    rule('bootstrap-2',condition='if AGENT unless target "/tmp/except"'),
    rule('bootstrap-2',path='/tmp/**'),rule('bootstrap-2',effect='kill'),
    rule('bootstrap-2',condition='if AGENT unless after exec "git"'),
])
def test_non_equivalent_or_complex_retained(real_compiler,second):
    raw=SOURCE+rule()+second
    report,actual=analyze(real_compiler,raw)
    assert report['normalized_dsl']==raw
    assert len(actual['rules'])>=2

def test_observe_mode_keeps_duplicates(real_compiler):
    raw=SOURCE+rule()+rule('bootstrap-2')
    report,actual=analyze(real_compiler,raw,'observe')
    assert report['duplicate_clause_count']==1 and report['normalized_dsl']==raw
    assert len(actual['rules'])==2

def test_directory_overlap_report_only(real_compiler):
    raw=SOURCE+rule(path='/tmp/config/**')+rule('bootstrap-2',path='/tmp/config/settings')
    report,_=analyze(real_compiler,raw)
    assert report['normalized_dsl']==raw and report['relations'][0]['relation']=='contains'

def test_adjacent_directory_not_overlap(real_compiler):
    report,_=analyze(real_compiler,SOURCE+rule(path='/tmp/config/**')+rule('bootstrap-2',path='/tmp/configuration/a'))
    assert report['relations']==[]

def test_repeated_names_rejected_before_analysis(real_compiler):
    raw=SOURCE+rule()+rule()
    status,info,_=real_compiler(bundle(raw))
    assert status!='compiled'
    with pytest.raises(ValueError,match='did not compile'):n.analyse(raw,info,'a','/tmp','deduplicate')

def test_absent_semantics_unknown_retained(real_compiler):
    raw=SOURCE+rule()+rule('bootstrap-2')
    _,info,_=real_compiler(bundle(raw))
    for value in info['rules']:value.pop('semantics')
    report=n.analyse(raw,info,'a','/tmp','deduplicate')
    assert report['normalized_dsl']==raw and all(x['relation']=='unknown' for x in report['clauses'])

def test_context_partition_changes_identity(real_compiler):
    raw=SOURCE+rule()
    a,_=analyze(real_compiler,raw,task='a');b,_=analyze(real_compiler,raw,task='b')
    assert a['clauses'][0]['logical_rule_id']!=b['clauses'][0]['logical_rule_id']

def test_broker_proof_recomputes_and_rejects_tampering(real_compiler,seed_task):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    raw=SOURCE+rule()+rule('bootstrap-2')
    dsl,package,actual,proof=n.build(raw,bundle(raw),task,1,'deduplicate',real_compiler)
    assert n.verify_proof(dsl,package,task,'/tmp/work',proof,real_compiler)['ok']
    for field in ('bundle_hash','execution_hash','engine_hash','raw_dsl_hash'):
        bad=copy.deepcopy(proof);bad[field]='tampered'
        with pytest.raises(ValueError):n.verify_proof(dsl,package,task,'/tmp/work',bad,real_compiler)
    with pytest.raises(ValueError):n.verify_proof(dsl+'\n',package,task,'/tmp/work',proof,real_compiler)

def test_source_links_use_package_and_exact_operation(real_compiler,seed_task):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    raw=SOURCE+rule()+rule('bootstrap-2')+rule('bootstrap-3',op='unlink')
    _,_,compiled,report=n.build(raw,bundle(raw),task,1,'deduplicate',real_compiler)
    state={'phase':'running','version':1,'active_normalization':report,'binding':{'domain_id':13,'compile':compiled}}
    first={'id':'startup:first','stage':'startup','targets':['/tmp/locked'],'operations':['write','unlink'],'effect':'block'}
    second={**first,'id':'startup:second'}
    with db.connect() as con:
        n.persist(con,task,'loaded','1',report)
        for record in (first,second):
            n.link_record(con,task,record,report)
            records.remap_loaded(record,state);n.persist_record_links(con,task,record)
        links=con.execute('SELECT * FROM policy_statement_rule_links WHERE task_id=?',(task,)).fetchall()
    assert len(links)==4
    for link in first['normalization']['links']:
        target=compiled['rules'][link['clause_id']]
        assert target['clause_op']==link['operation']
        assert link['current_loading']['domain_id']==13
    assert n.link_record(None,task,{},None)['normalization']['status']=='legacy_unanalysed'

def test_read_projection_does_not_write_links(real_compiler,seed_task):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    _,_,_,report=n.build(SOURCE+rule(),bundle(SOURCE+rule()),task,1,'deduplicate',real_compiler)
    with db.connect() as con:
        n.persist(con,task,'loaded','1',report)
        n.link_record(con,task,{'id':'read','targets':['/tmp/locked']},report)
        assert not con.execute('SELECT 1 FROM policy_statement_rule_links WHERE task_id=?',(task,)).fetchone()

def test_validation_hash_ignores_compiler_temporary_filename(real_compiler,seed_task):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    raw=SOURCE+rule()+rule('bootstrap-2')
    count=0
    def transient(bundle,*args):
        nonlocal count
        count+=1
        status,data,error=real_compiler(bundle,*args)
        data['policy_ref']='/tmp/compile-'+str(count)+'.yaml'
        return status,data,error
    first=n.build(raw,bundle(raw),task,0,'deduplicate',transient)[3]
    second=n.build(raw,bundle(raw),task,0,'deduplicate',transient)[3]
    assert first==second

@pytest.fixture
def normalized_job(seed_task,real_compiler,monkeypatch):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    state={'phase':'running','gate':'waiting_policy','revision':1,'version':7,'policy_hash':'fixed','baseline_hash':'sealed','baseline_extra':rule(path='/tmp/work/tests/test.py'),'protected':['/tmp/work/tests/test.py'],'runtime_protected':['b.txt','a.txt'],'allowed_write_dirs':['.'],'allow_output':False,'binding':{'domain_id':13,'runner_pid':99},'session_id':'session','turn':1,'normalization_mode':'deduplicate'}
    context={'request_evidence_id':'5','sources':[{'evidence_id':'5','content':{'actor':'native_user','text':'保留 a.txt'}}],'unassessed_request_ids':['5'],'base_snapshot':{'payload':{'allowed_write_dirs':['.'],'allow_output':False,'protected_paths':['b.txt','a.txt']}},'baseline':{'protected_files':state['protected']},'capabilities':{'registered_files':['a.txt','b.txt','tests/test.py'],'registered_directories':['.','tests']},'path_mapping':{'workspace':'/tmp/work'},'revision':1,'policy_hash':'fixed','project_sources':[]}
    job={'id':uuid.uuid4().hex,'task_id':task,'revision':1,'policy_hash':'fixed','context_json':json.dumps(context)}
    with db.connect() as con:c.save(con,task,state)
    import agentscope_app.main as main
    monkeypatch.setattr(main,'compile_policy',real_compiler)
    args={'decision':'restrict','allowed_write_dirs':['.'],'allow_output':False,'protected_paths':['a.txt','b.txt','a.txt'],'evidence_ids':['5'],'explanation':'Equivalent repeated restriction'}
    return task,state,job,args

def test_runtime_set_reordering_does_not_reload(normalized_job,monkeypatch):
    task,state,job,args=normalized_job
    value=c.validate_candidate(job,args)
    assert value['decision']=='no_change' and value['protected_paths']==['a.txt','b.txt']
    assert value['original_candidate']['protected_paths']==['a.txt','b.txt','a.txt']
    with db.connect() as con:
        con.execute("INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,proposal_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(job['id'],task,'repeat',1,'fixed',job['context_json'],json.dumps(value),db.now()))
    calls=[]
    def broker(request,**kwargs):
        calls.append(request['action']);return {'status':'running','domain_verified':True,'domain_id':13,'runner_pid':99}
    monkeypatch.setattr(c,'broker',broker)
    c.finish_job(job)
    with db.connect() as con:
        after=c.load(con,task)
        assert after['version']==7 and after['binding']==state['binding'] and after['gate']=='open'
        assert not con.execute("SELECT 1 FROM managed_events WHERE task_id=? AND kind='policy_active'",(task,)).fetchone()
    assert calls==['status']

def test_baseline_restatement_references_floor(normalized_job):
    _,_,job,args=normalized_job
    value=c.validate_candidate(job,{**args,'protected_paths':['tests/test.py','a.txt','b.txt']})
    assert value['decision']=='no_change' and value['baseline_references']==['tests/test.py']
    assert 'tests/test.py' not in value['protected_paths']

def test_duplicate_evaluation_pauses_if_binding_is_stale(normalized_job,monkeypatch):
    task,_,job,args=normalized_job;value=c.validate_candidate(job,args)
    with db.connect() as con:
        con.execute("INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,proposal_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(job['id'],task,'stale-bind',1,'fixed',job['context_json'],json.dumps(value),db.now()))
    monkeypatch.setattr(c,'broker',lambda *_a,**_k:{'status':'running','domain_verified':True,'domain_id':14,'runner_pid':99})
    with pytest.raises(ValueError,match='binding'):c.finish_job(job)
    with db.connect() as con:assert c.load(con,task)['gate']=='waiting_policy'

def test_new_normalized_candidate_stale_revision_rejected(normalized_job):
    _,_,job,args=normalized_job
    with pytest.raises(ValueError,match='stale'):c.validate_candidate({**job,'revision':0},args)

def test_normalization_cannot_hide_engine_limit(real_compiler,seed_task):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    raw=SOURCE+''.join(rule('bootstrap-'+str(i)) for i in range(130))
    with pytest.raises(ValueError,match='Original policy compile failed'):n.build(raw,bundle(raw),task,0,'deduplicate',real_compiler)

def test_unknown_metadata_cannot_be_merged_even_if_names_repeat_text(real_compiler):
    raw=SOURCE+rule()+rule('bootstrap-2')
    _,compiler,_=real_compiler(bundle(raw))
    compiler['rules'][1]['semantics']['schema']='future.unrecognised'
    result=n.analyse(raw,compiler,'a','/tmp','deduplicate')
    assert result['normalized_dsl']==raw and result['clauses'][1]['relation']=='unknown'


@pytest.mark.parametrize('field',['clauses','relations','compiler_hash','task_id','workspace'])
def test_broker_rejects_forged_lineage(real_compiler,seed_task,field):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    raw=SOURCE+rule()+rule('bootstrap-2')
    dsl,package,_,proof=n.build(raw,bundle(raw),task,1,'deduplicate',real_compiler)
    bad=copy.deepcopy(proof)
    if field=='clauses':bad[field][0]['compiled_refs'][0]['clause_id']=99
    elif field=='relations':bad[field]=[{'relation':'invented'}]
    else:bad[field]='forged'
    with pytest.raises(ValueError,match='lineage'):n.verify_proof(dsl,package,task,'/tmp/work',bad,real_compiler)


def test_reinitialization_preserves_reports_links_and_legacy_mode(real_compiler,seed_task,monkeypatch):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    _,_,compiled,report=n.build(SOURCE+rule(),bundle(SOURCE+rule()),task,1,'deduplicate',real_compiler)
    state={'phase':'running','version':1,'active_normalization':report,'binding':{'domain_id':13,'compile':compiled}}
    record={'id':'startup:kept','stage':'startup','targets':['/tmp/locked'],'effect':'block'}
    with db.connect() as con:
        c.save(con,task,state)
        n.persist(con,task,'loaded','1',report)
        n.link_record(con,task,record,report)
        records.remap_loaded(record,state);n.persist_record_links(con,task,record)
        before=[tuple(r) for r in con.execute('SELECT * FROM policy_statement_rule_links WHERE task_id=?',(task,))]
    monkeypatch.setenv('AGENTSCOPE_POLICY_NORMALIZATION','deduplicate')
    db.init_db();db.init_db()
    assert n.mode_for(task)=='legacy'  # Existing task is not silently migrated.
    with db.connect() as con:
        assert json.loads(con.execute('SELECT report_json FROM policy_normalization_runs WHERE id=?',(report['id'],)).fetchone()[0])==report
        assert [tuple(r) for r in con.execute('SELECT * FROM policy_statement_rule_links WHERE task_id=?',(task,))]==before


def test_audit_uses_package_identity_for_reused_numeric_ids(real_compiler,seed_task):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    reports=[]
    for version,path in [(1,'/tmp/first'),(2,'/tmp/second')]:
        _,_,compiled,report=n.build(SOURCE+rule(path=path),bundle(SOURCE+rule(path=path)),task,version,'deduplicate',real_compiler)
        reports.append((compiled,report))
    state={'phase':'running','version':2,'binding_history':[{'version':1,'domain_id':11},{'version':2,'domain_id':22}]}
    with db.connect() as con:
        c.save(con,task,state)
        for version,(compiled,report) in enumerate(reports,1):
            n.persist(con,task,'loaded',str(version),report)
            record={'id':'source:'+str(version),'stage':'startup','targets':[report['clauses'][0]['target']],'effect':'block'}
            n.link_record(con,task,record,report)
            records.remap_loaded(record,{**state,'version':version,'active_normalization':report,'binding':{'domain_id':version*11}})
            n.persist_record_links(con,task,record)
            raw={'process_domain_id':version*11,'domain_id':version*11,'rule_id':0,'op':'write','target':report['clauses'][0]['target'],'rule':compiled['rules'][0]}
            c.event(con,task,'kernel','kernel:'+str(version),{'event':raw,'version':version})
    audit=records.execution_audit(task)['records']
    assert len(audit)==2
    for event in audit:
        assert [x['statement_id'] for x in event['policy_sources']]==['source:'+str(event['version'])]


def test_parent_domain_event_does_not_resolve_child_clause_id(real_compiler,seed_task):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    _,_,compiled,report=n.build(SOURCE+rule(),bundle(SOURCE+rule()),task,1,'deduplicate',real_compiler)
    report['baseline_binding']={'bundle_hash':'parent-package','compile':compiled}
    report['inherited_references']=[{'logical_rule_id':report['clauses'][0]['logical_rule_id'],'operation':'write','target':'/tmp/locked','bundle_hash':'parent-package','clause_id':0}]
    state={'phase':'running','version':1,'binding_history':[{'version':1,'domain_id':22}],'active_normalization':report,'binding':{'domain_id':22}}
    with db.connect() as con:
        c.save(con,task,state);n.persist(con,task,'loaded','1',report)
        record={'id':'source:floor','stage':'startup','targets':['/tmp/locked'],'effect':'block'}
        n.link_record(con,task,record,report);records.remap_loaded(record,state);n.persist_record_links(con,task,record)
        for valid in (True,False):
            raw={'process_domain_id':22,'domain_id':11,'rule_id':0,'op':'write','target':'/tmp/locked','rule':compiled['rules'][0] if valid else {'clause_hash':'forged'}}
            c.event(con,task,'kernel','parent:'+str(valid),{'event':raw,'version':1})
    audit=records.execution_audit(task)['records']
    assert len(audit)==2 and audit[0]['policy_sources']==[]
    assert audit[1]['policy_sources'][0]['statement_id']=='source:floor'



def test_normalized_candidate_rejects_changed_project_evidence(normalized_job,tmp_path,monkeypatch):
    task,_,job,args=normalized_job
    source=tmp_path/'a.txt';source.write_text('changed')
    context=json.loads(job['context_json']);context['project_sources']=[{'id':'a.txt','path':str(source),'hash':'frozen-hash'}]
    monkeypatch.setattr(c,'read_project_content',lambda *_:{'hash':'actual-changed-hash'})
    with pytest.raises(ValueError,match='stale.*证据'):
        c.validate_candidate({**job,'context_json':json.dumps(context)},args)


def test_superseded_normalized_candidate_cannot_persist_or_load(normalized_job,monkeypatch):
    task,state,job,args=normalized_job;value=c.validate_candidate(job,args)
    with db.connect() as con:
        con.execute("INSERT INTO managed_jobs(id,task_id,request_key,revision,policy_hash,context_json,proposal_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(job['id'],task,'concurrent',1,'fixed',job['context_json'],json.dumps(value),db.now()))
        c.save(con,task,{**state,'revision':2})
    def forbidden(*_a,**_k):raise AssertionError('Stale candidate reached broker')
    monkeypatch.setattr(c,'broker',forbidden)
    with pytest.raises(ValueError,match='stale'):c.finish_job(job)
    with db.connect() as con:
        assert not con.execute('SELECT 1 FROM policy_normalization_runs WHERE task_id=?',(task,)).fetchone()
        assert c.load(con,task)['version']==7


def test_compile_failure_never_quiesces_existing_normalized_process(normalized_job,monkeypatch):
    task,state,_,_=normalized_job
    import agentscope_app.main as main
    monkeypatch.setattr(main,'compile_policy',lambda *_:('compile_failed',{'ok':False},'raw invalid'))
    def forbidden(*_a,**_k):raise AssertionError('Invalid policy reached broker')
    monkeypatch.setattr(c,'broker',forbidden)
    with pytest.raises(ValueError,match='Original policy compile failed'):
        c.install(task,state,['.'],False,protected_paths=['a.txt','b.txt'])
    with db.connect() as con:
        current=c.load(con,task)
        assert current['binding']==state['binding'] and current['version']==7



def test_unknown_analysis_is_visible_without_dropping_compiled_rule(real_compiler,seed_task):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    raw=SOURCE+rule(condition='if AGENT unless target "/tmp/except"')
    _,_,compiled,report=n.build(raw,bundle(raw),task,1,'deduplicate',real_compiler)
    with db.connect() as con:
        record=n.link_record(con,task,{'id':'complex','stage':'startup','targets':['/tmp/locked'],'effect':'block'},report)
    assert len(compiled['rules'])==1 and report['normalized_dsl']==raw
    assert record['normalization']['links'][0]['relation']=='unknown'



def test_reused_source_keeps_first_load_and_current_receipts_separate(real_compiler,seed_task):
    db.init_db();task=uuid.uuid4().hex[:16];seed_task(task)
    raw=SOURCE+rule()
    _,_,compiled,report=n.build(raw,bundle(raw),task,1,'deduplicate',real_compiler)
    state={'phase':'running','version':1,'active_normalization':report,'binding':{'domain_id':11}}
    with db.connect() as con:
        n.persist(con,task,'loaded','1',report)
        original={'id':'first','stage':'startup','targets':['/tmp/locked'],'effect':'block'}
        n.link_record(con,task,original,report);records.remap_loaded(original,state);n.persist_record_links(con,task,original)
        repeated={'id':'repeat','stage':'runtime','targets':['/tmp/locked'],'effect':'no_change'}
        n.link_record(con,task,repeated,report)
        records.remap_loaded(repeated,{**state,'version':2,'binding':{'domain_id':22}})
    link=repeated['normalization']['links'][0]
    assert link['first_loading']['version']==1 and link['first_loading']['domain_id']==11
    assert link['current_loading']['version']==2 and link['current_loading']['domain_id']==22
    assert repeated['normalization']['related_statements']==['first']



def test_dsh_admission_projects_task_material_without_pi_control_context():
    from agentscope_app.bootstrap.scene import PLATFORM,EXECUTION_CONSTRAINTS
    context={'mapping':{'/workspace':'/task/r'},'asset_layout_mapping':{'source.py':'source.py'},
        'assets':[{'mapped_path':'/task/r/source.py'}],
        'execution_constraints':EXECUTION_CONSTRAINTS,'platform_constraints':PLATFORM,
        'environment':'compiler limits and control details are Pi-only',
        'startup_clarifications':[{'text':'Keep source.py','source_id':'private-id','request_key':'private-key'}],
        'confirmed_policy':{'secret_dsl':'private-rule'}}
    text=c.native_admission({'workspace':'/task/r','output_dir':'/task/output','prompt':'Read source.py'},context)
    assert 'source.py' in text and 'Keep source.py' in text and '/opt/task-python/bin/python' in text
    assert 'backend cannot enforce' not in text and 'compiler limits' not in text
    assert 'private-id' not in text and 'private-rule' not in text and 'private-key' not in text
    assert 'Semantic constraints' in PLATFORM  # Pi still receives its capability boundary.



def test_held_fd_and_mapping_probe_preserves_task_file(tmp_path):
    import sys
    target=tmp_path/'task-file';original=b'temporary acceptance\n';target.write_bytes(original)
    script=Path(__file__).resolve().parents[1]/'broker/managed_operation_probe.py'
    process=subprocess.Popen([sys.executable,str(script),json.dumps({'target':str(target),'scratch':str(tmp_path/'scratch'),'operation':'hold'})],stdout=subprocess.PIPE,text=True)
    try:
        with pytest.raises(subprocess.TimeoutExpired):process.communicate(timeout=.3)
        assert target.read_bytes()==original
    finally:
        process.terminate();output,_=process.communicate(timeout=3)
    receipt=json.loads(output)
    assert receipt['fd_open'] and receipt['shared_mapping'] and receipt['success']



def test_control_read_boundary_has_no_probe_source_exception():
    text=c.control_rules({'workspace':'/task/r','output_dir':'/task/output'})
    source_root=str(Path(c.__file__).resolve().parents[3])
    line=next(line for line in text.splitlines() if source_root+'/**' in line)
    assert 'unless target' not in line
    assert 'managed_*' not in text


def test_broker_timeout_has_a_structured_service_error():
    from agentscope_app.managed.api import run
    from fastapi import HTTPException
    def timeout():raise TimeoutError('internal transport diagnostic')
    with pytest.raises(HTTPException) as error:run(timeout)
    assert error.value.status_code==503
    assert error.value.detail=='Trusted execution service unavailable: TimeoutError'


@pytest.mark.parametrize('condition',[
    'if AGENT unless after exec "**/confirm"',
    'if AGENT unless after exec "**/confirm" since write "/tmp/**"',
])
def test_identical_stateful_lifecycles_are_retained(real_compiler,condition):
    raw=SOURCE+rule(condition=condition)+rule('bootstrap-2',condition=condition)
    report,actual=analyze(real_compiler,raw)
    assert report['normalized_dsl']==raw and report['duplicate_clause_count']==0
    assert len(actual['rules'])==2 and all(not e['eligible'] for e in report['clauses'])


def test_source_binding_and_workspace_are_part_of_identity(real_compiler):
    first,_=analyze(real_compiler,SOURCE+rule())
    changed_binding,_=analyze(real_compiler,'source AGENT = exec "**/worker"\n'+rule())
    changed_workspace,_=analyze(real_compiler,SOURCE+rule(),workspace='/different-workspace')
    keys=[r['clauses'][0]['logical_rule_id'] for r in (first,changed_binding,changed_workspace)]
    assert len(set(keys))==3


def test_kernel_feedback_projection_links_receipts_without_duplicating_events(seed_task):
    db.init_db();task=uuid.uuid4().hex[:16];other=uuid.uuid4().hex[:16];seed_task(task);seed_task(other)
    with db.connect() as con:
        c.save(con,task,{'phase':'ended','binding_history':[]})
        for key in ('first','second'):c.event(con,task,'kernel',key,{'event':{'op':'write','target':'/tmp/'+key}})
        ids={row['event_key']:row['id'] for row in con.execute("SELECT id,event_key FROM managed_events WHERE task_id=? AND kind='kernel'",(task,))}
        c.event(con,task,'feedback_delivery','delivery:1',{'event_ids':[ids['first']]})
        c.event(con,task,'feedback_delivery','delivery:2',{'event_ids':[ids['first']]})
        c.event(con,other,'feedback_delivery','foreign',{'event_ids':[ids['second']]})
        receipts=[row[0] for row in con.execute("SELECT id FROM managed_events WHERE task_id=? AND kind='feedback_delivery'",(task,))]
        before=con.execute('SELECT count(*) FROM managed_events').fetchone()[0]
    events=records.execution_audit(task)['records'];assert len(events)==2
    by_id={e['id']:e for e in events}
    assert by_id[ids['first']]['feedback_event_ids']==sorted(receipts)
    assert by_id[ids['second']]['feedback_event_ids']==[]
    assert all(not e['kernel_event_ids'] for e in events)
    control=records.execution_audit(task,'control')['records']
    assert all(e['kernel_event_ids']==[ids['first']] and not e['feedback_event_ids'] for e in control)
    with db.connect() as con:assert con.execute('SELECT count(*) FROM managed_events').fetchone()[0]==before
