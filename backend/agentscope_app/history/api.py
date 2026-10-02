import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .. import db
from . import jobs, registry
from .sources import read_document

router=APIRouter(prefix="/api/history",tags=["history"])
class CollectRequest(BaseModel):
    repo_url: str
    ref: str = "main"
    additional_paths: list[str] = []
class ExtractRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1,max_length=100)
class Review(BaseModel):
    decision: str
    reviewed_by: str = "研究者"

def invoke(fn,*args):
    try: return fn(*args)
    except (ValueError,OSError) as e: raise HTTPException(409,str(e)) from None

@router.post("/sources")
def collect(body:CollectRequest):
    from .sources import relative_path
    from ..services.github import parse_github_url
    invoke(parse_github_url,body.repo_url)
    for path in body.additional_paths: invoke(relative_path,path)
    return jobs.enqueue("collect",body.model_dump())

@router.get("/jobs")
def list_jobs():
    with db.connect() as con:
        return [db.row_dict(r) for r in con.execute("SELECT * FROM history_jobs ORDER BY created_at DESC LIMIT 100")]

@router.get("/jobs/{ident}")
def job(ident:str):
    with db.connect() as con: row=con.execute("SELECT * FROM history_jobs WHERE id=?",(ident,)).fetchone()
    if not row: raise HTTPException(404,"作业不存在")
    return db.row_dict(row)

@router.post("/jobs/{ident}/retry")
def retry(ident:str):
    record=job(ident)
    if record["status"] not in ("failed","interrupted"): raise HTTPException(409,"只能重试失败/中断作业")
    return jobs.enqueue(record["kind"],record["input"],ident)

@router.get("/documents")
def documents():
    with db.connect() as con:
        rows=[dict(r) for r in con.execute("SELECT * FROM history_documents ORDER BY collected_at DESC")]
    for row in rows: row.pop("snapshot_path",None)
    return rows

@router.get("/documents/{ident}")
def document(ident:str):
    return invoke(read_document,ident).model_dump()

@router.post("/extractions")
def extract(body:ExtractRequest):
    for ident in body.document_ids: invoke(read_document,ident)
    return jobs.enqueue("extract",body.model_dump())

@router.get("/statements")
def statements(document_id:str|None=None,status:str|None=None):
    query="SELECT v.*,s.text FROM strategy_statement_versions v JOIN strategies s ON s.id=v.strategy_id WHERE 1=1"
    params=[]
    if document_id: query+=" AND v.document_id=?"; params.append(document_id)
    if status: query+=" AND v.review_status=?"; params.append(status)
    query+=" ORDER BY v.created_at DESC,v.version DESC LIMIT 1000"
    with db.connect() as con: return [db.row_dict(r) for r in con.execute(query,params)]

@router.post("/statements/{ident}/revisions")
def revise(ident:str,changes:dict):
    return {"id":invoke(registry.revise_statement,ident,changes)}

@router.post("/statements/{ident}/review")
def review_statement(ident:str,body:Review):
    return invoke(registry.review_statement,ident,body.decision,body.reviewed_by)

@router.post("/statements/{ident}/artifacts")
def translate(ident:str):
    record=invoke(registry.load_statement,ident)
    if record.review_status!="approved": raise HTTPException(409,"请先批准语句版本")
    return jobs.enqueue("translate",{"statement_version_id":ident})

@router.get("/artifacts")
def artifacts(status:str|None=None):
    with db.connect() as con:
        sql="SELECT * FROM history_artifacts"
        if status: sql+=" WHERE review_status=?"
        rows=[db.row_dict(r) for r in con.execute(sql+" ORDER BY created_at DESC LIMIT 1000",[status] if status else [])]
        for row in rows:
            row["deployments"]=[dict(r) for r in con.execute("""SELECT d.* FROM history_deployments d
              JOIN history_policy_artifacts p ON p.policy_version_id=d.policy_version_id WHERE p.artifact_id=?
              ORDER BY d.created_at DESC""",(row["id"],))]
    from .capabilities import runtime_limits_for
    for row in rows:
        row["runtime_limits"]=runtime_limits_for(row["artifact"].get("actplane_dsl"))
        for deployment in row["deployments"]:
            deployment["receipt"]=json.loads(deployment.pop("receipt_json"))
    return rows

@router.post("/artifacts/{ident}/review")
def review_artifact(ident:str,body:Review):
    return invoke(registry.review_artifact,ident,body.decision,body.reviewed_by)

@router.post("/artifacts/{ident}/compile")
def compile_artifact(ident:str):
    with db.connect() as con: row=con.execute("SELECT id FROM history_artifacts WHERE id=?",(ident,)).fetchone()
    if not row: raise HTTPException(404,"DSL 产物不存在")
    return jobs.enqueue("compile",{"artifact_id":ident})
