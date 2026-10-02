import hashlib
import json
import uuid
import urllib.error
from pathlib import Path
import pytest
from agentscope_app import db, main
from agentscope_app.history import sources, pipeline, registry, jobs
from agentscope_app.history.models import Statement, StrategyStatementVersion, ExtractionResult
from agentscope_app.history.llm import DeepSeekProvider, LLMError
from agentscope_app.history.provider import ActPlaneProvider

SHA = "a"*40
AUTH = {"Authorization":"Bearer test-admin-token-not-for-production"}

@pytest.fixture
def corpus(client, tmp_path, monkeypatch):
    monkeypatch.setattr(db,"DB_PATH",tmp_path/"isolated.sqlite3")
    db.init_db()
    monkeypatch.setattr(sources,"ROOT",tmp_path/"snapshots")
    docs={"AGENTS.md":b'# Instructions\n- Do not modify unrelated modules.\n- This project uses Rust.\n',
          "nested/AGENTS.md":b'- Never access private files.\n', "SECURITY.md":b'Security description.\n'}
    def reader(url):
        if "/commits/" in url: return json.dumps({"sha":SHA}).encode()
        if "/git/trees/" in url: return json.dumps({"tree":[{"type":"blob","path":p,"mode":"100644"} for p in docs]}).encode()
        return docs[url.split(SHA+"/")[1]]
    result=sources.collect_documents("https://github.com/example/repo",SHA,["SECURITY.md"],reader=reader)
    return result, reader, docs

def statement(document, line=2, **changes):
    s=Statement(source_quote=document.text.splitlines()[line-1],line_start=line,line_end=line,
        text_original=document.text.splitlines()[line-1],text_zh="不要修改无关模块",language="en",
        content_type="policy",policy_kind="constraint",topics=["scope"],
        enforcement_level="per_event",context_requirement="task")
    return pipeline.verify_evidence(document,s.model_copy(update=changes))

def saved(corpus):
    result,_,_=corpus
    doc=next(sources.read_document(i) for i in result["document_ids"] if sources.read_document(i).origin.path=="AGENTS.md")
    s=statement(doc)
    ident=registry.save_extraction(doc,ExtractionResult(statements=[s],coverage={},llm_runs=[]))[0]
    return doc,ident

def task(seed_task,tmp_path,ident=None):
    ident=ident or uuid.uuid4().hex
    seed_task(ident)
    (tmp_path/"nested").mkdir(exist_ok=True)
    with db.connect() as con:
        con.execute("UPDATE tasks SET status='prepared',workspace=? WHERE id=?",(str(tmp_path),ident))
    return main.require_task(ident)

class Stub:
    def __init__(self,values): self.values=iter(values);self.calls=[]
    def generate(self,system,payload,version):
        self.calls.append((system,payload,version))
        return next(self.values),{"model":"fixture","prompt_version":version}

def translation(version, *, dsl=True, required=None):
    prefix="h_"+version.id[:16]+"_"
    return {"candidate_rule":{"source":"AGENT","target":"repository","effect":"block","reason":"scope"},
        "actplane_dsl": f'rule {prefix}scope:\n  block write file "/tmp/repo/**" if AGENT unless target "/tmp/repo/allowed/**"\n  because "scope"' if dsl else None,
        "required_context":required or [],"unresolved":[],"required_hooks":["file_permission"]}

def artifact(ident):
    version=registry.load_statement(ident)
    version=version.model_copy(update={"resolved_context":{"task_id":"fixture"}})
    return pipeline.generate_policy_artifact(version,provider=Stub([translation(version)]))

def test_recursive_snapshot_hash_and_idempotence(corpus):
    result,reader,docs=corpus
    again=sources.collect_documents("https://github.com/example/repo",SHA,["SECURITY.md"],reader=reader)
    assert result==again and result["file_count"]==3
    with db.connect() as con:
        rows=con.execute("SELECT * FROM history_documents WHERE id IN (?,?,?)",result["document_ids"]).fetchall()
    assert {r["relative_path"]:r["scope_path"] for r in rows}=={"AGENTS.md":"","nested/AGENTS.md":"nested","SECURITY.md":""}
    for row in rows:
        assert row["content_sha256"]==hashlib.sha256(docs[row["relative_path"]]).hexdigest()
        assert sources.read_document(row["id"]).text.encode()==docs[row["relative_path"]]

@pytest.mark.parametrize("path",["../AGENTS.md","/etc/passwd","a/../AGENTS.md","a\\b","./x","a//b"])
def test_collection_rejects_noncanonical_paths(path):
    with pytest.raises(ValueError): sources.relative_path(path)

def test_truncated_tree_walk_and_symlink_rejection(client,tmp_path,monkeypatch):
    monkeypatch.setattr(sources,"ROOT",tmp_path)
    def reader(url):
        if "/commits/" in url:return json.dumps({"sha":SHA}).encode()
        if "recursive=1" in url:return b'{"truncated":true}'
        if url.endswith(SHA):return b'{"tree":[{"type":"tree","path":"sub","sha":"child"}]}'
        return b'{"tree":[{"type":"blob","path":"AGENTS.md","mode":"120000"}]}'
    with pytest.raises(ValueError,match="符号链接"):
        sources.collect_documents("https://github.com/example/repo",reader=reader)

def test_rate_limit_uses_readonly_git_fallback(client,tmp_path,monkeypatch):
    monkeypatch.setattr(sources,"ROOT",tmp_path)
    def limited(url):raise urllib.error.HTTPError(url,403,"rate limited",{},None)
    monkeypatch.setattr(sources,"git_snapshot",lambda repo,ref:(SHA,{"AGENTS.md":{"mode":"100644"}},lambda _:b"- rule\n"))
    assert sources.collect_documents("https://github.com/example/repo",reader=limited)["commit"]==SHA

def test_exact_evidence_does_not_repair_wrong_line_span(corpus):
    doc,_=saved(corpus)
    assert statement(doc).evidence_state=="verified"
    assert statement(doc,line_start=1,line_end=2).evidence_state=="evidence_unresolved"
    assert statement(doc,source_quote="Do not modify UNRELATED modules.").evidence_state=="evidence_unresolved"

def test_extraction_two_passes_and_coverage_are_program_verified(corpus):
    doc,_=saved(corpus)
    first={"statements":[statement(doc).model_dump(exclude={"evidence_state","char_start","char_end"})]}
    desc=statement(doc,line=3,content_type="description",policy_kind="none",
        enforcement_level="not_applicable",context_requirement="not_applicable")
    second={"statements":first["statements"]+[desc.model_dump(exclude={"evidence_state","char_start","char_end"})]}
    stub=Stub([first,second]);result=pipeline.extract_strategy_statements(doc,provider=stub)
    assert len(stub.calls)==2 and result.coverage["complete"]
    assert result.statements[1].content_type=="description"

def test_missing_json_contract_is_failure(corpus):
    doc,_=saved(corpus)
    with pytest.raises(ValueError,match="statements"):pipeline.extract_strategy_statements(doc,provider=Stub([{}]))

def test_versions_idempotent_new_labels_and_approval_hash(corpus):
    doc,ident=saved(corpus)
    s=statement(doc);result=ExtractionResult(statements=[s],coverage={},llm_runs=[])
    assert registry.save_extraction(doc,result)==[ident]
    changed=registry.save_extraction(doc,result.model_copy(update={"statements":[s.model_copy(update={"topics":["changed"]})]}))[0]
    assert changed!=ident and registry.load_statement(changed).version==2
    registry.review_statement(ident,"approve","tester")
    revised=registry.revise_statement(ident,{"statement":{"text_zh":"修订翻译"}})
    assert registry.load_statement(revised).review_status=="pending_review"
    assert registry.load_statement(ident).statement.text_zh!="修订翻译"
    with db.connect() as con:
        r=con.execute("SELECT * FROM strategy_statement_versions WHERE id=?",(ident,)).fetchone()
    assert r["reviewed_hash"]==r["content_sha256"]

def test_unverified_evidence_cannot_be_approved(corpus):
    doc,ident=saved(corpus)
    bad=registry.revise_statement(ident,{"statement":{"line_start":1}})
    with pytest.raises(ValueError,match="原文"):registry.review_statement(bad,"approve","tester")

def test_binding_verifies_repo_commit_scope_and_task(corpus,seed_task,tmp_path):
    doc,ident=saved(corpus);target=task(seed_task,tmp_path)
    revised=registry.revise_statement(ident,{"resolved_context":{"task_id":target["id"],"allowed_paths":["nested"]}})
    assert registry.load_statement(revised).resolved_context["allowed_paths"]==[str(tmp_path/"nested")]
    with pytest.raises(ValueError):registry.revise_statement(ident,{"resolved_context":{"task_id":target["id"],"allowed_paths":["../outside"]}})
    with db.connect() as con:con.execute("UPDATE tasks SET status='running' WHERE id=?",(target["id"],))
    with pytest.raises(ValueError,match="尚未启动"):registry.revise_statement(ident,{"resolved_context":{"task_id":target["id"]}})

def test_context_absent_never_emits_executable_dsl(corpus):
    _,ident=saved(corpus);registry.review_statement(ident,"approve","tester")
    version=registry.load_statement(ident)
    output=pipeline.generate_policy_artifact(version,provider=Stub([translation(version)]))
    assert output.state=="requires_context" and output.actplane_dsl is None
    assert "policy_record" in output.pseudo_code and "governance" in output.pseudo_code

def test_semantic_and_descriptive_candidates_keep_pseudocode_without_llm(corpus):
    _,ident=saved(corpus);registry.review_statement(ident,"approve","tester")
    version=registry.load_statement(ident)
    version=version.model_copy(update={"statement":version.statement.model_copy(update={"enforcement_level":"content"})})
    stub=Stub([]);out=pipeline.generate_policy_artifact(version,provider=stub)
    assert out.state=="unsupported" and out.actplane_dsl is None and not stub.calls

@pytest.mark.parametrize("dsl",['source AGENT = exec "**"','rule other:\n  block write file "/tmp/**" if AGENT','# metadata','declassify AGENT'])
def test_fragments_cannot_override_labels_or_inject_governance(dsl):
    with pytest.raises(ValueError):pipeline.validate_fragment(dsl,"h_fixture_")

def test_selection_is_all_or_nothing_reviewed_and_task_bound(corpus,seed_task,tmp_path):
    _,ident=saved(corpus);registry.review_statement(ident,"approve","tester")
    target=task(seed_task,tmp_path);bound=registry.revise_statement(ident,{"resolved_context":{"task_id":target["id"],"allowed_paths":["nested"]}})
    registry.review_statement(bound,"approve","tester");v=registry.load_statement(bound)
    out=pipeline.generate_policy_artifact(v,provider=Stub([translation(v)]))
    aid=registry.save_artifact(out,"compiled",{})
    with pytest.raises(ValueError,match="未批准"):registry.selected_artifacts(target,[aid])
    registry.review_artifact(aid,"approve","tester")
    assert len(registry.selected_artifacts(target,[aid]))==1
    with pytest.raises(ValueError):registry.selected_artifacts(target,[aid,"missing"])
    other=task(seed_task,tmp_path)
    with pytest.raises(ValueError,match="其他任务"):registry.selected_artifacts(other,[aid])
    with db.connect() as con:con.execute("UPDATE history_artifacts SET artifact_json='{}' WHERE id=?",(aid,))
    with pytest.raises(ValueError,match="hash"):registry.selected_artifacts(target,[aid])

def test_full_task_bundle_includes_selected_dsl_and_baseline(corpus,seed_task,tmp_path,monkeypatch):
    _,ident=saved(corpus);registry.review_statement(ident,"approve","tester")
    target=task(seed_task,tmp_path);bound=registry.revise_statement(ident,{"resolved_context":{"task_id":target["id"],"allowed_paths":["nested"]}})
    registry.review_statement(bound,"approve","tester");v=registry.load_statement(bound)
    out=pipeline.generate_policy_artifact(v,provider=Stub([translation(v)]));aid=registry.save_artifact(out,"compiled",{})
    registry.review_artifact(aid,"approve","tester")
    captured=[]
    monkeypatch.setattr(main,"compile_policy",lambda yaml,*_:(captured.append(yaml) or "compiled",{}, ""))
    bundle=main.create_policy_version(target,1,"static",{},[],"fixture",artifact_ids=[aid])
    assert out.actplane_dsl in bundle["dsl_text"] and "AGENT" in captured[0]
    with db.connect() as con:
        link=con.execute("SELECT artifact_hash FROM history_policy_artifacts WHERE policy_version_id=?",(bundle["id"],)).fetchone()
    assert link[0]==pipeline.digest(out.model_dump())

def test_job_fifo_failure_does_not_promote_success(client,monkeypatch):
    with db.connect() as con:con.execute("DELETE FROM history_jobs")
    first=jobs.enqueue("collect",{"name":"first"});second=jobs.enqueue("collect",{"name":"second"})
    seen=[]
    def execute(kind,payload):
        seen.append(payload["name"])
        if payload["name"]=="first":raise TimeoutError("fixture timeout")
        return {"fixture":True}
    monkeypatch.setattr(jobs,"execute",execute);w=jobs.Worker();assert w.run_one() and w.run_one()
    with db.connect() as con:rows=con.execute("SELECT status FROM history_jobs ORDER BY created_at,rowid").fetchall()
    assert seen==["first","second"] and [r[0] for r in rows]==["failed","completed"]
    retried=client.post("/api/history/jobs/"+first["id"]+"/retry",json={},headers=AUTH)
    assert retried.status_code==200
    assert client.post("/api/history/jobs/"+second["id"]+"/retry",json={},headers=AUTH).status_code==409

@pytest.mark.parametrize("mode",["success","unavailable","missing","wrong_binding"])
def test_loader_records_actual_binding_or_failure(client,seed_task,tmp_path,monkeypatch,mode):
    target=task(seed_task,tmp_path)
    monkeypatch.setattr(main,"compile_policy",lambda *args:("compiled",{}, ""))
    bundle=main.create_policy_version(target,1,"static",{},[],"fixture")
    with db.connect() as con:
        con.execute("UPDATE policy_versions SET status='approved' WHERE id=?",(bundle["id"],))
        con.execute("UPDATE tasks SET status='approved',active_version=1 WHERE id=?",(target["id"],))
    revoked=[];calls=[]
    def broker(body,**kw):
        calls.append(body["action"])
        if body["action"]=="launch":
            if mode=="unavailable":raise RuntimeError("Broker unavailable")
            return {} if mode=="missing" else {"domain_id":44,"runner_pid":101,"watch_pid":102}
        if body["action"]=="status":
            return {"child":{"child_id":45 if mode=="wrong_binding" else 44},"runner_pid":101,"agent_status":"running"}
        return {}
    p=ActPlaneProvider(broker,lambda *_:"prompt",lambda _:("token","credential"),revoked.append,lambda *_:None,"http://localhost")
    if mode=="success":assert p.load_task_policy(target["id"],bundle["id"])["binding_confirmed"]
    else:
        with pytest.raises(RuntimeError):p.load_task_policy(target["id"],bundle["id"])
        assert revoked==["credential"]
    with db.connect() as con:r=con.execute("SELECT * FROM history_deployments WHERE task_id=?",(target["id"],)).fetchone()
    assert r["status"]==("loaded" if mode=="success" else "load_failed")
    assert r["active"]==int(mode=="success")
    if mode=="success":
        with pytest.raises(ValueError):p.load_task_policy(target["id"],bundle["id"])

def test_llm_retains_final_json_not_credentials_or_reasoning(monkeypatch):
    import io
    response={"choices":[{"finish_reason":"stop","message":{"content":'{"statements":[]}',"reasoning_content":"PRIVATE_REASONING"}}],"model":"deepseek-flash"}
    monkeypatch.setattr("urllib.request.urlopen",lambda *_,**kw:io.BytesIO(json.dumps(response).encode()))
    output,meta=DeepSeekProvider(api_key="PRIVATE_CREDENTIAL").generate("system",{},"fixture")
    assert output=={"statements":[]}
    assert "PRIVATE" not in json.dumps([output,meta])
    response["choices"][0]["message"]["content"]="invalid JSON"
    with pytest.raises(LLMError,match="JSON"):DeepSeekProvider(api_key="key").generate("system",{},"fixture")

def test_additive_schema_keeps_legacy_records(client):
    with db.connect() as con:
        ident=uuid.uuid4().hex
        con.execute("INSERT INTO strategies(id,text,category,category_confidence,context_scope,execution_layer,status,source_kind,sentence_sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (ident,"legacy fixture","semantic",0.7,"task","semantic","approved","rq1",ident,db.now()))
    db.init_db()
    with db.connect() as con:assert con.execute("SELECT text FROM strategies WHERE id=?",(ident,)).fetchone()[0]=="legacy fixture"


def test_invalid_fragment_retained_but_cannot_be_compiled_or_approved(corpus):
    _,ident=saved(corpus);registry.review_statement(ident,"approve","tester")
    v=registry.load_statement(ident).model_copy(update={"resolved_context":{"task_id":"fixture"}})
    raw=translation(v);raw["actplane_dsl"]='source AGENT = exec "**"\nrule other:\n  block write file "/tmp/**" if AGENT'
    out=pipeline.generate_policy_artifact(v,provider=Stub([raw]))
    assert out.state=="invalid_candidate" and out.policy_record["compile_check"]["diagnostics"]
    aid=registry.save_artifact(out,"invalid_candidate",{})
    with pytest.raises(ValueError):registry.review_artifact(aid,"approve","tester")
    with pytest.raises(ValueError):jobs.execute("compile",{"artifact_id":aid})

def test_translation_null_gate_and_note_variants_are_canonical():
    from agentscope_app.history.models import Translation
    raw={"candidate_rule":{"source":"AGENT","target":"file","effect":"block","reason":"fixture","gate":None},"actplane_dsl":None,"semantic_notes":["a","b"]}
    assert Translation.model_validate(raw).candidate_rule.gate=="none"
    raw["semantic_notes"]="one";assert Translation.model_validate(raw).semantic_notes==["one"]

def test_prepare_dangling_symlink_does_not_chown_target(client,tmp_path,monkeypatch):
    from types import SimpleNamespace
    from agentscope_app.services import github
    monkeypatch.setattr(github,"WORKSPACE_ROOT",tmp_path)
    monkeypatch.setattr(github.grp,"getgrnam",lambda _:SimpleNamespace(gr_gid=0))
    actual_chown=github.os.chown;seen=[]
    def ownership(path,uid,gid,**kw):
        seen.append((Path(path).name,kw.get("follow_symlinks",True)))
        return actual_chown(path,uid,gid,**kw)
    monkeypatch.setattr(github.os,"chown",ownership)
    def git(args,cwd=None):
        if args[0]=="checkout":(Path(cwd)/"AGENTS.md").symlink_to(tmp_path/"missing-external")
        return SHA if args[0]=="rev-parse" else ""
    monkeypatch.setattr(github,"run_git",git)
    result=github.prepare({"repo_url":"https://github.com/example/repo","prompt":"fixture"})
    assert result["evidence_count"]==0 and ("AGENTS.md",False) in seen
    assert not (tmp_path/"missing-external").exists()

def test_runtime_restart_inherits_history_and_closes_previous_domain(corpus,seed_task,tmp_path,monkeypatch):
    _,ident=saved(corpus);registry.review_statement(ident,"approve","tester")
    target=task(seed_task,tmp_path);bound=registry.revise_statement(ident,{"resolved_context":{"task_id":target["id"],"allowed_paths":["nested"]}})
    registry.review_statement(bound,"approve","tester");v=registry.load_statement(bound)
    out=pipeline.generate_policy_artifact(v,provider=Stub([translation(v)]));aid=registry.save_artifact(out,"compiled",{})
    registry.review_artifact(aid,"approve","tester")
    monkeypatch.setattr(main,"compile_policy",lambda *args:("compiled",{}, ""))
    first=main.create_policy_version(target,1,"static",{},[],"fixture",artifact_ids=[aid])
    with db.connect() as con:
        con.execute("UPDATE tasks SET status='running',active_version=1,active_domain_id=77 WHERE id=?",(target["id"],))
        con.execute("UPDATE policy_versions SET status='approved' WHERE id=?",(first["id"],))
        con.execute("INSERT INTO history_deployments(id,policy_version_id,task_id,bundle_hash,status,active,domain_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex,first["id"],target["id"],"old","loaded",1,77,db.now()))
    def broker(body,**kwargs):
        if body["action"]=="restart":
            assert out.actplane_dsl in body["dsl_text"]
            return {"domain_id":88,"runner_pid":102,"watch_pid":103}
        return {"child":{"child_id":88},"runner_pid":102,"agent_status":"running"}
    monkeypatch.setattr(main,"broker_call",broker)
    request=main.create_scope_request(target["id"],main.ScopeRequestBody(kind="expand",justification="fixture output permission"))
    result=main.review_scope(target["id"],request["id"],main.ReviewRequest(decision="approve"))
    assert result["version"]==2
    with db.connect() as con:
        rows=con.execute("SELECT active,domain_id FROM history_deployments WHERE task_id=? ORDER BY created_at",(target["id"],)).fetchall()
        link=con.execute("SELECT p.artifact_id FROM history_policy_artifacts p JOIN policy_versions v ON v.id=p.policy_version_id WHERE v.task_id=? AND v.version=2",(target["id"],)).fetchone()
    assert [(r["active"],r["domain_id"]) for r in rows]==[(0,77),(1,88)] and link[0]==aid

def test_interrupted_work_recovers_without_promoting_success(client,monkeypatch):
    with db.connect() as con:
        con.execute("DELETE FROM history_jobs")
        con.execute("INSERT INTO history_jobs(id,kind,status,input_json,created_at) VALUES(?,?,?,?,?)",("interrupted-fixture","collect","running","{}",db.now()))
    monkeypatch.setenv("AGENTSCOPE_HISTORY_WORKER","1")
    monkeypatch.setattr(jobs.Worker,"run",lambda self:None)
    w=jobs.Worker();w.start();w.stop()
    with db.connect() as con:row=con.execute("SELECT status,error FROM history_jobs WHERE id='interrupted-fixture'").fetchone()
    assert row["status"]=="interrupted" and "重试" in row["error"]


def test_repeat_artifact_result_is_idempotent_and_partial_is_not_approvable(corpus):
    _,ident=saved(corpus);registry.review_statement(ident,"approve","tester")
    v=registry.load_statement(ident).model_copy(update={"resolved_context":{"task_id":"fixture"}})
    out=pipeline.generate_policy_artifact(v,provider=Stub([translation(v)]))
    first=registry.save_artifact(out,"partial",{"diagnostic":"unsupported hook"})
    repeated=registry.save_artifact(out.model_copy(update={"llm_runs":[{"model":"fixture","duration_ms":123}]}),"partial",{})
    assert first==repeated
    with pytest.raises(ValueError,match="完整编译"):registry.review_artifact(first,"approve","tester")

def test_task_policy_generation_claim_blocks_concurrent_launch(client,seed_task,tmp_path,monkeypatch):
    target=task(seed_task,tmp_path);seen=[]
    def compile(yaml,*args):
        assert main.require_task(target["id"])["status"]=="policy_generating"
        seen.append(client.post("/api/tasks/"+target["id"]+"/policy",json={},headers=AUTH).status_code)
        return "compiled",{}, ""
    monkeypatch.setattr(main,"compile_policy",compile)
    response=client.post("/api/tasks/"+target["id"]+"/policy",json={},headers=AUTH)
    assert response.status_code==200 and seen==[409]
    assert main.require_task(target["id"])["status"]=="policy_review"

def test_generation_exception_recovers_previous_task_state(client,seed_task,tmp_path,monkeypatch):
    target=task(seed_task,tmp_path)
    def fail(*args,**kwargs):raise ValueError("fixture failed compilation")
    monkeypatch.setattr(main,"create_policy_version",fail)
    with pytest.raises(ValueError):main.generate_policy(target["id"],main.PolicyRequest())
    assert main.require_task(target["id"])["status"]=="prepared"

def test_raw_download_rate_limit_fallback_stays_at_fixed_commit(client,tmp_path,monkeypatch):
    monkeypatch.setattr(sources,"ROOT",tmp_path)
    calls=[]
    def reader(url):
        if "/commits/" in url:return json.dumps({"sha":SHA}).encode()
        if "/git/trees/" in url:return b'{"tree":[{"type":"blob","path":"AGENTS.md","mode":"100644"}]}'
        raise urllib.error.HTTPError(url,429,"rate limited",{},None)
    def fallback(repo,ref):
        calls.append((repo,ref))
        return SHA,{"AGENTS.md":{"mode":"100644"}},lambda _:b"- fixture\n"
    monkeypatch.setattr(sources,"git_snapshot",fallback)
    result=sources.collect_documents("https://github.com/example/repo","main",reader=reader)
    assert result["commit"]==SHA and calls==[("example/repo",SHA)]

@pytest.mark.parametrize("attempted_binding",[False,True])
def test_failed_load_retry_requires_no_attempted_domain(client,seed_task,tmp_path,monkeypatch,attempted_binding):
    target=task(seed_task,tmp_path)
    monkeypatch.setattr(main,"compile_policy",lambda *args:("compiled",{}, ""))
    bundle=main.create_policy_version(target,1,"static",{},[],"fixture")
    with db.connect() as con:
        con.execute("UPDATE policy_versions SET status='approved' WHERE id=?",(bundle["id"],))
        con.execute("UPDATE tasks SET status='approved',active_version=1 WHERE id=?",(target["id"],))
    failing=[True]
    def broker(body,**kw):
        if body["action"]=="launch":
            if failing[0] and not attempted_binding:raise RuntimeError("fixture pre-launch failure")
            return {"domain_id":44,"runner_pid":101}
        if body["action"]=="status":
            if failing[0]:return {"available":True,"status":"running","child":{"child_id":45},"runner_pid":101}
            return {"available":True,"status":"running","agent_status":"running","child":{"child_id":44},"runner_pid":101}
        return {"status":"stopped"}
    p=ActPlaneProvider(broker,lambda *_:"prompt",lambda _:("token","credential"),lambda _:None,lambda *_:None,"http://localhost")
    with pytest.raises(RuntimeError):p.load_task_policy(target["id"],bundle["id"])
    with db.connect() as con:row=con.execute("SELECT * FROM history_deployments WHERE task_id=?",(target["id"],)).fetchone()
    assert row["domain_id"]==(44 if attempted_binding else None)
    failing[0]=False
    if attempted_binding:
        with pytest.raises(ValueError,match="尚未启动"):p.load_task_policy(target["id"],bundle["id"])
    else:
        original=p.broker
        checked=[False]
        def checked_broker(body,**kw):
            if body["action"]=="status" and not checked[0]:
                checked[0]=True
                return {"available":True,"status":"stopped"}
            return original(body,**kw)
        p.broker=checked_broker
        assert p.load_task_policy(target["id"],bundle["id"])["binding_confirmed"] and checked[0]

def test_history_bundle_generation_preserves_previous_baseline_settings(client,seed_task,tmp_path,monkeypatch):
    target=task(seed_task,tmp_path)
    with db.connect() as con:con.execute("UPDATE tasks SET settings_json=? WHERE id=?",(json.dumps({"deny_network":True,"read_only":True}),target["id"]))
    captured=[]
    original=main.create_policy_version
    def capture(task,version,mode,settings,*args,**kwargs):
        captured.append(settings)
        return original(task,version,mode,settings,*args,**kwargs)
    monkeypatch.setattr(main,"create_policy_version",capture)
    monkeypatch.setattr(main,"compile_policy",lambda *args:("compiled",{}, ""))
    response=client.post("/api/tasks/"+target["id"]+"/policy",json={"artifact_version_ids":[]},headers=AUTH)
    assert response.status_code==200
    assert captured[0]["deny_network"] and captured[0]["read_only"]

def test_observed_file_creation_limit_is_distinct_from_compilation():
    from agentscope_app.history.capabilities import runtime_limits_for
    assert runtime_limits_for('rule fixture:\n  block write file "/tmp/**" if AGENT')[0]["code"]=="file_creation_directory_entry"
    assert runtime_limits_for(None)==[] and runtime_limits_for("block network * if AGENT")==[]

def test_non_english_approval_requires_english_translation(corpus):
    doc,_=saved(corpus)
    s=statement(doc).model_copy(update={"language":"zh","text_en":""})
    ident=registry.save_extraction(doc,ExtractionResult(statements=[s],coverage={},llm_runs=[]))[0]
    with pytest.raises(ValueError,match="英文"):registry.review_statement(ident,"approve","tester")
    revised=registry.revise_statement(ident,{"statement":{"text_en":"Do not modify unrelated modules."}})
    assert registry.review_statement(revised,"approve","tester")["status"]=="approved"

def test_prompt_templates_are_injected_without_http_or_database(corpus):
    doc,ident=saved(corpus)
    raw={"statements":[statement(doc).model_dump(exclude={"evidence_state","char_start","char_end"})]}
    templates=pipeline.PromptTemplates(extraction="fixture extraction",extraction_version="extract-fixture",review_version="review-fixture",translation="fixture conversion",translation_version="convert-fixture",dsl_reference="fixture grammar")
    stub=Stub([raw,raw])
    pipeline.extract_strategy_statements(doc,provider=stub,templates=templates)
    assert [r[2] for r in stub.calls]==["extract-fixture","review-fixture"]
    assert all(r[0]=="fixture extraction" for r in stub.calls)
    registry.review_statement(ident,"approve","tester")
    v=registry.load_statement(ident).model_copy(update={"resolved_context":{"task_id":"fixture"}})
    converted=Stub([translation(v)])
    pipeline.generate_policy_artifact(v,provider=converted,templates=templates)
    assert converted.calls[0][0]=="fixture conversion" and converted.calls[0][1]["grammar"]=="fixture grammar"
