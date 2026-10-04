
import hashlib
import json
from pathlib import Path
import pytest
from agentscope_app import db, main
from agentscope_app.services import corpus
from agentscope_app.history import catalog, jobs

AUTH={"Authorization":"Bearer test-admin-token-not-for-production"}

@pytest.fixture
def rq1(client,tmp_path,monkeypatch):
    monkeypatch.setattr(db,"DB_PATH",tmp_path/"persistent.sqlite3")
    db.init_db()
    root=tmp_path/"dataset"
    directory=root/"RQ1/corpus";directory.mkdir(parents=True)
    body=b"- Never write private files.\n"
    source={"repo":"example/repo","files":[{"path":"AGENTS.md","last_commit_sha":"a"*40,
        "raw_url":"https://raw.githubusercontent.com/example/repo/"+("a"*40)+"/AGENTS.md",
        "content_sha256":hashlib.sha256(body).hexdigest()}]}
    (directory/"manifest.jsonl").write_text(json.dumps(source)+"\n")
    (directory/"candidate_rules.tsv").write_text("example__repo\t- Never write private files.\nmissing__repo\tDo not publish without approval.\nmissing__repo\tDo not publish without approval.\n")
    monkeypatch.setattr(corpus,"CORPUS_ROOT",root)
    monkeypatch.setattr(corpus,"CACHE",tmp_path/"cache")
    monkeypatch.setattr(corpus,"fetch_one",lambda item:(item,body.decode()))
    return directory

def test_rq1_fixed_bundle_and_hash_tampering(client,tmp_path,monkeypatch):
    monkeypatch.setattr(corpus,"CORPUS_ROOT",tmp_path/"absent")
    info=corpus.dataset_info()
    rows=corpus.load_local()
    assert info["artifact_commit"]=="63db86945c9b8618a46aa68c8de214bc4b8343d9"
    assert len(rows)==866 and len({corpus.source_import_key(s,t) for s,t,_ in rows})==721
    directory=tmp_path/"bad/RQ1/corpus";directory.mkdir(parents=True)
    original=corpus.corpus_files()
    for name in ("manifest.jsonl","candidate_rules.tsv","provenance.json"):
        (directory/name).write_bytes((original/name).read_bytes())
    with (directory/"candidate_rules.tsv").open("a") as f:f.write("\nchanged")
    monkeypatch.setattr(corpus,"CORPUS_ROOT",tmp_path/"bad")
    with pytest.raises(ValueError,match="hash"):corpus.dataset_info()

def test_rq1_import_idempotent_null_sources_and_preserves_edits(rq1):
    first=corpus.import_rq1()
    assert first["input_count"]==3 and first["unique_count"]==2 and first["inserted_count"]==2
    assert first["verified_count"]==1 and first["unverified_count"]==1
    rows=catalog.page(source_kind="rq1_corpus")["items"]
    row=next(r for r in rows if r["source_verified"])
    revised=catalog.revise(row["id"],{"text":"Human reviewed interpretation of the original RQ1 policy."},"tester")
    main.review_strategy(row["id"],main.ReviewRequest(decision="approve",reviewed_by="tester"))
    catalog.archive(row["id"],True,"tester")
    null=next(r for r in rows if not r["source_verified"])
    second=corpus.import_rq1()
    assert second["inserted_count"]==0 and second["reused_count"]==2
    assert catalog.page(source_kind="rq1_corpus",archived="all")["total"]==2
    current=catalog.detail(row["id"])
    assert current["text"]==revised["text"] and current["revision"]==2 and current["status"]=="approved"
    assert current["is_archived"]==1 and current["source_verified"]==0
    assert catalog.detail(null["id"])["source_commit"] is None
    assert current["revisions"][0]["snapshot"]["text"]==row["text"]

def test_rq1_default_twenty_rows_and_source_filter_before_pagination(rq1,client):
    with db.connect() as con:
        for n in range(45):
            con.execute("INSERT INTO strategies(id,text,category,category_confidence,context_scope,execution_layer,status,sentence_sha256,source_kind,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("rq1-"+str(n),"RQ1 numbered statement "+str(n),"semantic",1,"project","repository_instruction","pending_review",str(n),"rq1_corpus",db.now()))
    manual=catalog.create({"text":"manual policy outside RQ1","category":"semantic","context_scope":"project","execution_layer":"repository_instruction"},"tester")
    with db.connect() as con:
        con.execute("UPDATE strategies SET source_kind='history_document' WHERE id=?",(manual["id"],))
    pages=[client.get("/api/history/records",params={"source_kind":"rq1_corpus","offset":offset},headers=AUTH).json() for offset in (0,20,40)]
    assert [len(p["items"]) for p in pages]==[20,20,5]
    assert all(p["total"]==45 and p["limit"]==20 for p in pages)
    assert len({r["id"] for p in pages for r in p["items"]})==45
    assert all(r["source_kind"]=="rq1_corpus" for p in pages for r in p["items"])
    assert client.get("/api/history/records",params={"source_kind":"bad"},headers=AUTH).status_code==409
    assert main.dashboard()["stats"]["strategies"]==45

def test_rq1_seed_job_and_database_restart_preserve_records(rq1):
    first=corpus.ensure_seed_job()
    assert first["status"]=="queued" and corpus.ensure_seed_job()["id"]==first["id"]
    assert jobs.worker.run_one()
    with db.connect() as con:
        assert con.execute("SELECT status FROM history_jobs WHERE id=?",(first["id"],)).fetchone()[0]=="completed"
        before=con.execute("SELECT id,text,status,sentence_sha256 FROM strategies ORDER BY id").fetchall()
    db.init_db()
    assert corpus.ensure_seed_job() is None
    with db.connect() as con:
        after=con.execute("SELECT id,text,status,sentence_sha256 FROM strategies ORDER BY id").fetchall()
    assert [tuple(r) for r in before]==[tuple(r) for r in after]

def test_failed_rq1_seed_is_retryable_and_not_success(rq1,client,monkeypatch):
    ident=corpus.ensure_seed_job()["id"]
    monkeypatch.setattr(corpus,"import_rq1",lambda:(_ for _ in ()).throw(ValueError("fixture snapshot mismatch")))
    assert jobs.worker.run_one()
    with db.connect() as con:
        row=con.execute("SELECT status,error FROM history_jobs WHERE id=?",(ident,)).fetchone()
        assert row["status"]=="failed" and "snapshot mismatch" in row["error"]
        assert con.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]==0
    assert corpus.ensure_seed_job()=={"id":ident,"status":"failed"}
    retry=client.post("/api/history/jobs/"+ident+"/retry",headers=AUTH)
    assert retry.status_code==200 and retry.json()["id"]!=ident

def test_cached_source_hash_mismatch_is_not_verified(client,tmp_path,monkeypatch):
    monkeypatch.setattr(corpus,"CACHE",tmp_path)
    body=b"- Never expose private keys."
    file={"path":"AGENTS.md","raw_url":"https://raw.githubusercontent.com/example/repo/"+("a"*40)+"/AGENTS.md",
        "content_sha256":hashlib.sha256(body).hexdigest()}
    cached=tmp_path/hashlib.sha256(file["raw_url"].encode()).hexdigest()
    cached.write_bytes(b"untrusted cached body")
    class Response:
        data=body
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,limit):return self.data
    class Opener:
        def open(self,*args,**kwargs):return Response()
    monkeypatch.setattr(corpus.urllib.request,"build_opener",lambda *args:Opener())
    _,result=corpus.fetch_one(({"repo":"example/repo"},file))
    assert result==body.decode() and cached.read_bytes()==body
    cached.write_bytes(b"untrusted cached body")
    Response.data=b"wrong remote snapshot"
    assert corpus.fetch_one(({"repo":"example/repo"},file))[1] is None
