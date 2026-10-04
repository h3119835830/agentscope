import json
import hashlib
import tempfile
from pathlib import Path
import pytest
from agentscope_app import db, main
from agentscope_app.history import sources, pipeline, generations, registry, inputs, catalog
from agentscope_app.history.models import Statement, MarkdownDocument, Origin
from agentscope_app.policy_ir import PolicyIR, Rule, Clause, Gate, Source, LabelExpression, render

AUTH={"Authorization":"Bearer test-admin-token-not-for-production"}
SHA="a"*40


def clause(text, line=1, **kwargs):
    return Statement(source_quote=text,line_start=line,line_end=line,text_original=text,text_zh=text,
        content_type="policy",policy_kind="constraint",topics=[],enforcement_level="per_event",
        context_requirement="task",**kwargs)


class Provider:
    def __init__(self): self.calls=[]
    def generate(self,system,payload,version):
        self.calls.append((version,payload))
        if version=="history-policy-ir-v1":
            ctx=payload["VERIFIED_CONTEXT"]
            path=ctx.get("verified_targets",[{}])[0].get("absolute_path") if ctx.get("verified_targets") else None
            return {"version":"PolicyIR/v1","required_context":[] if path else ["protected_path"],
                "rules":[{"name":"protect","reason":"Protect tests","clauses":[{"operation":op,"pattern":path or "${protected_path}"} for op in ("write","unlink")]}]}, {"model":"fixture","prompt_version":version}
        if payload.get("first_pass") and len(payload["first_pass"])==1:
            statements=payload["first_pass"]
        else:
            statements=[]
            for entry in payload["lines"]:
                text=entry["text"]
                if not text.strip() or text.startswith("#"):continue
                s=clause(text,entry["line"])
                if "polite" in text:s=s.model_copy(update={"enforcement_level":"semantic_only","context_requirement":"self_contained"})
                statements.append(s.model_dump())
        if version=="history-completeness-v2":
            statements=[{**s,"completeness":"complete","review_issues":[]} for s in statements]
        return {"statements":statements},{"model":"fixture","prompt_version":version}


@pytest.fixture
def isolated(client,tmp_path,monkeypatch):
    monkeypatch.setattr(db,"DB_PATH",tmp_path/"generation.sqlite3")
    monkeypatch.setattr(sources,"ROOT",tmp_path/"snapshots")
    db.init_db()
    text="Never write or delete tests.\nBe polite.\n"
    doc=MarkdownDocument(text=text,origin=Origin(document_id="fixture-document",repository="example/repo",commit=SHA,path="AGENTS.md",content_hash=hashlib.sha256(text.encode()).hexdigest()))
    doc=inputs.snapshot(doc)
    def collect(*args,**kwargs):return {"repository":"example/repo","commit":SHA,"document_ids":[doc.origin.document_id],"file_count":1}
    monkeypatch.setattr(sources,"collect_documents",collect)
    monkeypatch.setattr(main,"compile_policy",lambda *args:("compiled",{"compiler_version":"fixture"},None))
    return client,doc


def create_run():return generations.create({"repo_url":"https://github.com/example/repo","ref":SHA,"additional_paths":[]})["id"]


def review_item(row):return {"statement_version_id":row["statement_version_id"],"expected_statement_hash":row["statement_hash"],"artifact_id":row["artifact_id"],"expected_artifact_hash":row["artifact_hash"]}


def test_merged_pipeline_pending_review_and_hash_invalidation(isolated):
    run=create_run();p=Provider();result=generations.execute(run,p)
    assert result["status"]=="completed"
    rows=generations.results(run)["items"]
    assert len(rows)==2 and all(r["review_status"]=="pending_review" for r in rows)
    execution=next(r for r in rows if r["adaptation"]["state"]=="required")
    semantic=next(r for r in rows if r["adaptation"]["state"]=="not_required")
    assert execution["artifact"]["actplane_dsl"] is None
    assert 'policy_ir {' in execution['artifact']['pseudo_code'] and 'protected_path' in execution['artifact']['pseudo_code']
    assert semantic["artifact"]["policy_ir"]["guidance"]==["Be polite."]
    item=review_item(execution);bad={**item,"expected_statement_hash":"wrong"}
    with pytest.raises(ValueError,match="hash"):generations.final_review(run,[bad],"approve","tester")
    generations.final_review(run,[item,review_item(semantic)],"approve","tester")
    assert not any(r["eligible"] for r in generations.results(run)["items"])
    assert generations.create({"repo_url":"https://github.com/example/repo","ref":SHA,"additional_paths":[]})["id"]==run
    assert [v for v,_ in p.calls]==["history-extract-v2","history-completeness-v2","history-policy-ir-v1"]


def test_cancel_after_one_model_call_then_retry_checkpoints(isolated):
    run=create_run()
    class CancelProvider(Provider):
        def generate(self,*args):
            result=super().generate(*args);generations.cancel(run);return result
    p=CancelProvider();assert generations.execute(run,p)["status"]=="cancelled" and len(p.calls)==1
    assert generations.get(run)["steps"][0]["status"]=="completed"
    generations.retry(run);p=Provider();assert generations.execute(run,p)["status"]=="completed"
    before=generations.get(run)
    with pytest.raises(ValueError):generations.retry(run)
    assert before["status"]=="completed"


def test_partial_failure_retries_only_failed_candidates(isolated):
    run=create_run()
    class FailProvider(Provider):
        def generate(self,system,payload,version):
            if version=="history-policy-ir-v1":raise TimeoutError("provider unavailable")
            return super().generate(system,payload,version)
    assert generations.execute(run,FailProvider())["status"]=="partial"
    assert len(generations.results(run)["items"])==2
    generations.retry(run);p=Provider();generations.execute(run,p)
    assert [v for v,_ in p.calls]==["history-policy-ir-v1"]


def test_full_paragraph_is_not_cut_at_line_65():
    text="# Rules\n"+"\n".join("continuation "+str(i) for i in range(100))+"\n"
    assert pipeline.semantic_chunks(text)==[(0,101)]


@pytest.mark.parametrize("text",["Never delete tests unless explicitly authorized.","Only after tests pass may changes be committed.","Do not expose credentials."])
def test_second_review_reads_full_context_and_conditions(text):
    doc=MarkdownDocument(text="# Constraints\nShared precondition:\n\n"+text,origin=Origin(document_id="x",repository="x/y",commit=SHA,path="AGENTS.md",content_hash="x"))
    p=Provider();pipeline.extract_strategy_statements(doc,provider=p)
    review=p.calls[1][1]
    assert review["lines"][-1]["text"]==text
    assert any(x["text"]=="Shared precondition:" for x in review["lines"])


def test_multispan_exact_evidence_and_missing_context():
    text="Only production builds:\n\nNever delete tests.\n"
    doc=MarkdownDocument(text=text,origin=Origin(document_id="x",repository="x/y",commit=SHA,path="AGENTS.md",content_hash="x"))
    s=clause("Never delete tests.",3,evidence_spans=[{"source_quote":"Only production builds:","line_start":1,"line_end":1}])
    assert pipeline.verify_evidence(doc,s).evidence_state=="verified"
    bad=s.model_copy(update={"evidence_spans":[{"source_quote":"No builds","line_start":1,"line_end":1}]})
    assert pipeline.verify_evidence(doc,bad).evidence_state=="evidence_unresolved"


def test_unreviewed_is_not_implicitly_complete(isolated):
    run=create_run()
    class MissingReview(Provider):
        def generate(self,*args):
            result,meta=super().generate(*args)
            for s in result.get("statements",[]):s.pop("completeness",None)
            return result,meta
    generations.execute(run,MissingReview())
    rows=generations.results(run)["items"]
    assert all(r["status"]=="needs_clarification" and not r["artifact"] for r in rows)
    with pytest.raises(ValueError):generations.final_review(run,[review_item(rows[0])],"approve","tester")


def test_api_auth_fixed_source_and_final_review_contract(isolated):
    client,_=isolated
    assert client.post('/api/history/generations',json={}).status_code==401
    r=client.post('/api/history/generations',headers=AUTH,json={"repo_url":"https://github.com/example/repo","ref":SHA})
    assert r.status_code==200
    run=r.json()['id'];generations.execute(run,Provider())
    rows=client.get('/api/history/generations/'+run+'/results?adaptation=required',headers=AUTH).json()
    assert rows['total']==1 and rows['items'][0]['adaptation']['state']=='required'
    assert client.post('/api/history/generations/'+run+'/review',headers=AUTH,json={'decision':'approve','items':[{'statement_version_id':'unknown','expected_statement_hash':'bad'}]}).status_code==409


def test_adapted_version_and_environment_drift(isolated,seed_task):
    seed_task('adapted');work=Path(tempfile.mkdtemp(prefix='hp-'));(work/'tests').mkdir()
    with db.connect() as con:con.execute("UPDATE tasks SET workspace=?,status='prepared' WHERE id='adapted'",(str(work),))
    inp=inputs.create_input({'text':'Never write or delete tests.','task_id':'adapted','enforcement_level':'per_event','context_requirement':'task'},'tester')
    revised=registry.revise_statement(inp['id'],{'resolved_context':{'task_id':'adapted','target_paths':['tests']}})
    run=generations.create({'statement_version_id':revised})['id'];generations.execute(run,Provider())
    row=generations.results(run)['items'][0]
    assert row['artifact']['actplane_dsl'] and row['compile_state']=='compiled'
    generations.final_review(run,[review_item(row)],'approve','tester')
    target=main.require_task('adapted');assert registry.selected_artifacts(target,[row['artifact_id']])
    assert catalog.page(adaptation='complete',loadable='yes')['total']==1
    with db.connect() as con:con.execute("UPDATE tasks SET dsh_profile='different' WHERE id='adapted'")
    with pytest.raises(ValueError,match='环境'):registry.selected_artifacts(main.require_task('adapted'),[row['artifact_id']])
    assert catalog.page(loadable='yes')['total']==0
    with pytest.raises(ValueError):registry.revise_statement(inp['id'],{'adaptation':'complete'})


def test_structured_renderer_supports_gates_network_exec_boolean_and_limits():
    ir=PolicyIR(sources=[Source(name='other',kind='exec',pattern='/usr/bin/git')],rules=[Rule(name='test',reason='reason',clauses=[
        Clause(operation='connect',pattern='127.0.0.1:8080',when=LabelExpression(kind='any',operands=[LabelExpression(),LabelExpression(label='other')]),unless=Gate(kind='lineage',pattern='/usr/bin/git')),
        Clause(operation='exec',pattern='/usr/bin/git',argument='push',effect='kill',unless=Gate(kind='after',pattern='/usr/bin/test',exits_zero=True,since=[{'operation':'write','pattern':'/tmp/repo/**'}])),
        Clause(operation='read',pattern='/tmp/repo/**',unless=Gate(kind='target',pattern='/tmp/repo/public/**'))])])
    dsl=render(ir,'h_test_')
    assert dsl.count('connect endpoint')==2 and 'since write' in dsl and 'kill exec' in dsl
    pipeline.validate_fragment(dsl,'h_test_')
    with pytest.raises(ValueError):render(PolicyIR(rules=[Rule(name='x',reason='x',clauses=[Clause(operation='write',pattern='/'+('x'*64))])]),'h_')
    with pytest.raises(ValueError):render(PolicyIR(rules=[Rule(name='x',reason='x',clauses=[Clause(operation='exec',pattern='/bin/x',argument='push')])]),'h_')


@pytest.mark.parametrize('compiler_state,attempts',[('compile_failed',2),('partial',2),('compile_timeout',1),('backend_missing',1)])
def test_compiler_failures_remain_unapproved_and_retry_checkpoint(isolated,seed_task,monkeypatch,compiler_state,attempts):
    seed_task('compiler');work=Path(tempfile.mkdtemp(prefix='mc-'));(work/'tests').mkdir()
    with db.connect() as con:con.execute("UPDATE tasks SET workspace=?,status='prepared' WHERE id='compiler'",(str(work),))
    inp=inputs.create_input({'text':'Never write or delete tests.','task_id':'compiler','enforcement_level':'per_event','context_requirement':'task'},'tester')
    revised=registry.revise_statement(inp['id'],{'resolved_context':{'task_id':'compiler','target_paths':['tests']}})
    calls=[]
    def unavailable(*args):
        calls.append(args)
        return compiler_state,{'diagnostic':'unsupported or unavailable'},'compiler diagnostic'
    monkeypatch.setattr(main,'compile_policy',unavailable)
    run=generations.create({'statement_version_id':revised})['id']
    assert generations.execute(run,Provider())['status']=='failed'
    row=generations.results(run)['items'][0]
    assert len(calls)==attempts and row['status']=='failed'
    assert row['error']=='compiler diagnostic' and row['compilation']['diagnostic']=='compiler diagnostic'
    assert row['review_blockers'] and not row['eligible']
    with pytest.raises(ValueError,match='校验未完成'):generations.final_review(run,[review_item(row)],'approve','tester')
    generations.retry(run)
    monkeypatch.setattr(main,'compile_policy',lambda *args:('compiled',{'compiler_version':'fixture'},None))
    provider=Provider();assert generations.execute(run,provider)['status']=='completed'
    assert [version for version,_ in provider.calls]==['history-policy-ir-v1']
    assert generations.results(run)['items'][0]['statement_version_id']==row['statement_version_id']


def test_single_review_has_one_candidate_contract_and_bound_context(isolated,seed_task):
    seed_task('single')
    with db.connect() as con:con.execute("UPDATE tasks SET status='prepared' WHERE id='single'")
    inp=inputs.create_input({'text':'Never write or delete tests.','task_id':'single','enforcement_level':'per_event','context_requirement':'task'},'tester')
    revised=registry.revise_statement(inp['id'],{'resolved_context':{'task_id':'single'}})
    provider=Provider()
    result=generations.review_single(registry.load_statement(revised),provider)
    assert len(result['statement_version_ids'])==1
    payload=provider.calls[0][1]
    assert payload['VERIFIED_CONTEXT']['task_id']=='single'
    assert 'cover every substantive line' not in pipeline.SINGLE_COMPLETENESS_PROMPT
    assert 'exactly one' in pipeline.SINGLE_COMPLETENESS_PROMPT


def test_compiled_pending_adaptation_and_changed_label_never_load(isolated,seed_task):
    seed_task('blocked')
    run=create_run();generations.execute(run,Provider())
    row=next(r for r in generations.results(run)['items'] if r['adaptation']['state']=='required')
    generations.final_review(run,[review_item(row)],'approve','tester')
    data=row['artifact'];data['actplane_dsl']='rule h_'+row['statement_version_id'][:16]+'_fake:\n  block write file "/tmp/**" if AGENT\n  because "fake"'
    def forge():
        with db.connect() as con:
            con.execute("UPDATE history_artifacts SET artifact_json=?,compile_state='compiled',content_sha256=?,reviewed_hash=? WHERE id=?",(json.dumps(data),pipeline.digest(data),pipeline.digest(data),row['artifact_id']))
    forge()
    with pytest.raises(ValueError):registry.selected_artifacts(main.require_task('blocked'),[row['artifact_id']])
    data['policy_record']['metadata']['adaptation']={'state':'complete','required_parameters':[]}
    forge()
    with pytest.raises(ValueError):registry.selected_artifacts(main.require_task('blocked'),[row['artifact_id']])
    assert generations.results(run,loadable='yes')['total']==0


def test_ir_bound_object_and_nested_instruction_scope(isolated):
    from agentscope_app.history.models import StrategyStatementVersion
    statement=StrategyStatementVersion(id='v',strategy_id='s',version=1,origin=isolated[1].origin,
        statement=clause('Never delete tests.'),scope_path='sub',resolved_context={'workspace':'/tmp/repo','verified_targets':[{'absolute_path':'/tmp/repo/sub/tests'}]})
    def ir(path):return PolicyIR(rules=[Rule(name='x',reason='x',clauses=[Clause(operation='unlink',pattern=path)])])
    pipeline.validate_ir_scope(ir('/tmp/repo/sub/tests/**'),statement)
    for path in ('/tmp/repo/tests/**','/tmp/repo/sub/other/**','/etc/**'):
        with pytest.raises(ValueError):pipeline.validate_ir_scope(ir(path),statement)


def test_over_budget_block_is_retained_as_clarification():
    text='Never change '+('a'*90000)+'.'
    document=MarkdownDocument(text=text,origin=Origin(document_id='huge',repository='x/y',commit=SHA,path='AGENTS.md',content_hash='x'))
    provider=Provider();result=pipeline.extract_strategy_statements(document,provider=provider)
    assert not provider.calls
    assert result.statements[0].completeness=='needs_clarification'
    assert result.statements[0].source_quote==text
    assert result.statements[0].evidence_state=='verified'


def test_dangling_candidate_cannot_be_complete_despite_attached_command():
    doc=MarkdownDocument(text='Run tests with:\npython tests.py\n',origin=Origin(document_id='x',repository='x/y',commit=SHA,path='AGENTS.md',content_hash='x'))
    candidate=clause('Run tests with:',completeness='complete',evidence_spans=[{'source_quote':'python tests.py','line_start':2,'line_end':2}])
    checked=pipeline.verify_evidence(doc,candidate)
    assert checked.evidence_state=='verified' and checked.completeness=='needs_clarification'
    corrected=candidate.model_copy(update={'text_original':'Run tests with python tests.py.'})
    assert pipeline.verify_evidence(doc,corrected).completeness=='complete'


def test_incomplete_coverage_checkpoint_is_retried_without_source_fetch(isolated):
    run=create_run()
    class MissingLine(Provider):
        def generate(self,system,payload,version):
            result,meta=super().generate(system,payload,version)
            if version=='history-extract-v2':result['statements']=result['statements'][:1]
            return result,meta
    assert generations.execute(run,MissingLine())['status']=='partial'
    generations.retry(run);provider=Provider()
    assert generations.execute(run,provider)['status']=='completed'
    assert provider.calls[0][0]=='history-extract-v2'
    assert generations.get(run)['steps'][0]['step_key']=='source'
