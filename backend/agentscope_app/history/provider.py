"""Load only a stored approved bundle via the existing ActPlane command broker."""
import hashlib
import json
import uuid
from .. import db
from .registry import selected_artifacts
from .models import LoadReceipt

class ActPlaneProvider:
    def __init__(self,broker,prompt_builder,issue_token,revoke_token,revoke_tokens,public_url):
        self.broker=broker; self.prompt_builder=prompt_builder; self.issue_token=issue_token
        self.revoke_token=revoke_token; self.revoke_tokens=revoke_tokens; self.public_url=public_url

    def load_task_policy(self,task_id: str,approved_policy_version_id: str) -> LoadReceipt:
        with db.connect() as con:
            task=con.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone()
            version=con.execute("SELECT * FROM policy_versions WHERE id=? AND task_id=?",(approved_policy_version_id,task_id)).fetchone()
            if not task or not version or version["status"]!="approved" or version["compile_state"]!="compiled":
                raise ValueError("任务策略版本未获完整编译及批准")
            last=con.execute("SELECT status,domain_id,runner_pid,receipt_json FROM history_deployments WHERE task_id=? ORDER BY created_at DESC LIMIT 1",(task_id,)).fetchone()
            retryable=(task["status"]=="failed" and not task["active_pid"] and not task["active_domain_id"] and last and last["status"]=="load_failed" and not last["domain_id"] and not last["runner_pid"] and json.loads(last["receipt_json"]).get("cleanup_confirmed",True))
            if (task["status"]!="approved" and not retryable) or task["active_version"]!=version["version"]:
                raise ValueError("只能加载尚未启动任务的当前批准版本")
            task=dict(task); version=dict(version)
            artifact_ids=[r[0] for r in con.execute("SELECT artifact_id FROM history_policy_artifacts WHERE policy_version_id=?",(version["id"],))]
            links={r["artifact_id"]:r["artifact_hash"] for r in con.execute("SELECT * FROM history_policy_artifacts WHERE policy_version_id=?",(version["id"],))}
        if retryable:
            current=self.broker({"action":"status","task_id":task_id},timeout=8)
            if current.get("available") and current.get("status")!="stopped":
                raise ValueError("前次失败任务的进程清理未确认，不能重试加载")
        from ..bootstrap.validation import verify_version
        with db.connect() as con: bootstrap_binding=verify_version(con,task_id,version["id"])
        if bootstrap_binding:
            from ..bootstrap.validation import verify_initial_assets
            verify_initial_assets(task_id)
        artifacts=selected_artifacts(task,artifact_ids)
        if any(links[r["id"]]!=r["content_sha256"] for r in artifacts): raise ValueError("批准后的产物 hash 不一致")
        bundle_hash=hashlib.sha256(version["policy_yaml"].encode()).hexdigest()
        compile_info=json.loads(version["compile_json"])
        saved_hash=compile_info.get("submitted_bundle_hash")
        if saved_hash and saved_hash!=bundle_hash: raise ValueError("批准后的策略包 hash 不一致")
        deployment_id=uuid.uuid4().hex
        with db.connect() as con:
            changed=con.execute("UPDATE tasks SET status='starting',updated_at=? WHERE id=? AND status=? AND active_version=?",
                (db.now(),task_id,task["status"],version["version"])).rowcount
            if not changed: raise ValueError("任务已被另一启动请求接管")
            con.execute("INSERT INTO history_deployments(id,policy_version_id,task_id,bundle_hash,status,created_at) VALUES(?,?,?,?,?,?)",
                (deployment_id,version["id"],task_id,bundle_hash,"loading",db.now()))
        credential_id=None; receipt={}
        try:
            prompt=self.prompt_builder(task,json.loads(version["source_strategy_ids"]))
            with db.connect() as con:
                event_baseline={'count':con.execute('SELECT count(*) FROM runtime_events WHERE task_id=?',(task_id,)).fetchone()[0],'captured_at':db.now()}
            token,credential_id=self.issue_token(task_id)
            receipt=self.broker({"action":"launch","task_id":task_id,"version":version["version"],
                "workspace":task["workspace"],"output_dir":task["output_dir"],"prompt":prompt,
                "dsl_text":version["dsl_text"],"policy_yaml":version["policy_yaml"],
                "dsh_profile":task["dsh_profile"],"task_token":token,"agentscope_url":self.public_url},timeout=35)
            domain=receipt.get("domain_id"); pid=receipt.get("runner_pid")
            if type(domain) is not int or domain<=0 or type(pid) is not int or pid<=0:
                raise RuntimeError("ActPlane 缺少有效进程域绑定回执")
            status=self.broker({"action":"status","task_id":task_id},timeout=8)
            child=status.get("child") or {}
            if child.get("child_id")!=domain or status.get("runner_pid")!=pid:
                raise RuntimeError("ActPlane 子进程域回查未确认")
            receipt={**receipt,"deployment_id":deployment_id,"bundle_hash":bundle_hash,
                     "binding_confirmed":True,"artifact_version_ids":artifact_ids,'event_baseline':event_baseline}
            self.revoke_tokens(task_id,credential_id)
            with db.connect() as con:
                con.execute("UPDATE tasks SET status='running',active_pid=?,active_domain_id=?,watch_pid=?,updated_at=? WHERE id=?",
                    (pid,domain,receipt.get("watch_pid"),db.now(),task_id))
                con.execute("UPDATE history_deployments SET status='loaded',active=?,domain_id=?,runner_pid=?,receipt_json=? WHERE id=?",
                    (int(status.get("agent_status")=="running"),domain,pid,json.dumps(receipt),deployment_id))
                db.audit(con,task_id,"task_launched","AgentScope",receipt)
            return receipt
        except Exception as e:
            if credential_id: self.revoke_token(credential_id)
            cleanup_confirmed=False;cleanup_status="unknown"
            try:
                cleanup=self.broker({"action":"stop","task_id":task_id},timeout=12)
                cleanup_status=cleanup.get("status","unknown");cleanup_confirmed=cleanup_status in ("stopped","not_running")
            except Exception: pass
            with db.connect() as con:
                con.execute("UPDATE tasks SET status='failed',updated_at=? WHERE id=?",(db.now(),task_id))
                attempted_domain=receipt.get("domain_id") if type(receipt.get("domain_id")) is int else None
                attempted_pid=receipt.get("runner_pid") if type(receipt.get("runner_pid")) is int else None
                con.execute("UPDATE history_deployments SET status='load_failed',active=0,domain_id=?,runner_pid=?,receipt_json=?,ended_at=? WHERE id=?",
                    (attempted_domain,attempted_pid,json.dumps({"error":str(e)[:1000],"attempted_domain_id":attempted_domain,"attempted_runner_pid":attempted_pid,"cleanup_status":cleanup_status,"cleanup_confirmed":cleanup_confirmed}),db.now(),deployment_id))
            raise
