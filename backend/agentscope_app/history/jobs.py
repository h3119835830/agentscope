import json
import os
import threading
import uuid
from .. import db
from .pipeline import extract_strategy_statements,generate_policy_artifact
from .registry import load_statement,save_artifact,save_extraction
from .sources import collect_documents,read_document

def enqueue(kind,payload,retry_of=None):
    if kind not in ("collect","extract","translate","compile","rq1_import"): raise ValueError("作业类型不支持")
    ident=uuid.uuid4().hex
    with db.connect() as con:
        con.execute("INSERT INTO history_jobs(id,kind,status,input_json,created_at,retry_of) VALUES(?,?,?,?,?,?)",
            (ident,kind,"queued",json.dumps(payload,ensure_ascii=False),db.now(),retry_of))
    worker.wake.set()
    return {"id":ident,"status":"queued"}

def execute(kind,payload):
    if kind=="rq1_import":
        from ..services.corpus import import_rq1
        return import_rq1()
    if kind=="collect": return collect_documents(**payload)
    if kind=="extract":
        results=[]
        for ident in payload["document_ids"]:
            document=read_document(ident); result=extract_strategy_statements(document)
            versions=save_extraction(document,result)
            results.append({"document_id":ident,"statement_version_ids":versions,"coverage":result.coverage,"llm_runs":result.llm_runs})
        return {"documents":results}
    if kind=="compile":
        with db.connect() as con:
            row=con.execute("SELECT * FROM history_artifacts WHERE id=?",(payload["artifact_id"],)).fetchone()
        if not row: raise ValueError("DSL 产物不存在")
        from .pipeline import digest,validate_fragment
        data=json.loads(row["artifact_json"])
        if digest(data)!=row["content_sha256"]: raise ValueError("DSL hash 不一致")
        dsl=data["actplane_dsl"]
        if not dsl: raise ValueError("产物没有可编译 DSL")
        validate_fragment(dsl,"h_"+row["statement_version_id"].replace("-","")[:16]+"_")
        from ..main import compile_policy
        yaml="version: 1\npolicy: |\n  source AGENT = exec \"**\"\n"+"\n".join("  "+line for line in dsl.splitlines())+"\n"
        state,info,error=compile_policy(yaml,uuid.uuid4().hex,1)
        info={**info,"diagnostic":error}
        with db.connect() as con:
            con.execute("UPDATE history_artifacts SET compile_state=?,compile_json=? WHERE id=?",(state,json.dumps(info),row["id"]))
            con.execute("INSERT INTO history_compilations VALUES(?,?,?,?,?,?,?,?,?)",(uuid.uuid4().hex,row["id"],None,None,digest(dsl),state,"ActPlane CLI",json.dumps(info),db.now()))
        return {"artifact_id":row["id"],"compile_state":state}
    statement=load_statement(payload["statement_version_id"])
    if statement.review_status!="approved": raise ValueError("请先批准语句版本")
    from ..main import compile_policy
    from ..config import ACTPLANE_BIN
    import subprocess
    try: compiler_version=subprocess.run([str(ACTPLANE_BIN),"--version"],capture_output=True,text=True,timeout=5).stdout.strip()
    except Exception: compiler_version="unavailable"
    attempts=[]; diagnostic=None
    for attempt in range(2):
        candidate=generate_policy_artifact(statement,compiler_diagnostic=diagnostic)
        state=candidate.state; details={}
        if state=="invalid_candidate":
            diagnostic="; ".join(candidate.policy_record["compile_check"]["diagnostics"])
            details={"diagnostic":diagnostic,"compiler_version":compiler_version}
        if candidate.actplane_dsl and state!="invalid_candidate":
            dsl='source AGENT = exec "**"\n'+candidate.actplane_dsl
            yaml="version: 1\npolicy: |\n"+"\n".join("  "+line for line in dsl.splitlines())+"\n"
            state,details,diagnostic=compile_policy(yaml,uuid.uuid4().hex,attempt+1)
            details={**details,"compiler_version":compiler_version,"diagnostic":diagnostic}
        ident=save_artifact(candidate,state,details); attempts.append(ident)
        if state not in ("compile_failed","invalid_candidate"): break
    return {"artifact_id":ident,"attempt_ids":attempts,"compile_state":state}

class Worker:
    def __init__(self):
        self.wake=threading.Event(); self.stop_event=threading.Event(); self.thread=None
    def start(self):
        if os.getenv("AGENTSCOPE_HISTORY_WORKER","1")=="0": return
        if self.thread and self.thread.is_alive(): return
        with db.connect() as con:
            con.execute("UPDATE history_jobs SET status='interrupted',error='服务重启中断，允许重试',finished_at=? WHERE status='running'",(db.now(),))
        self.stop_event.clear()
        self.thread=threading.Thread(target=self.run,name="history-worker",daemon=True); self.thread.start()
    def stop(self):
        self.stop_event.set(); self.wake.set()
        if self.thread: self.thread.join(timeout=2)
    def run_one(self):
        with db.connect() as con:
            row=con.execute("SELECT * FROM history_jobs WHERE status='queued' ORDER BY created_at,rowid LIMIT 1").fetchone()
            if not row: return False
            changed=con.execute("UPDATE history_jobs SET status='running',started_at=? WHERE id=? AND status='queued'",(db.now(),row["id"])).rowcount
        if not changed: return True
        try:
            result=execute(row["kind"],json.loads(row["input_json"]))
            with db.connect() as con: con.execute("UPDATE history_jobs SET status='completed',result_json=?,finished_at=? WHERE id=?",(json.dumps(result,ensure_ascii=False),db.now(),row["id"]))
        except Exception as e:
            with db.connect() as con: con.execute("UPDATE history_jobs SET status='failed',error=?,finished_at=? WHERE id=?",(type(e).__name__+": "+str(e)[:1200],db.now(),row["id"]))
        return True
    def run(self):
        while not self.stop_event.is_set():
            if not self.run_one(): self.wake.wait(2); self.wake.clear()

worker=Worker()
