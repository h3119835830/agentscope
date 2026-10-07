import os
import sys
import tempfile
from pathlib import Path

os.environ["AGENTSCOPE_STATE_DIR"] = tempfile.mkdtemp(prefix="agentscope-test-")
# Never inherit a service database, broker socket, task tree, or worker setting.
for setting in ('AGENTSCOPE_DB','AGENTSCOPE_TASK_ROOT','AGENTSCOPE_POLICY_DIR','AGENTSCOPE_LOG_DIR','AGENTSCOPE_CORPUS_ROOT','AGENTSCOPE_SERVICE_HOME','AGENTSCOPE_RUNTIME_DIR','AGENTSCOPE_DSH_HOME','DSH_HOME','AGENTSCOPE_PUBLIC_URL'):
    os.environ.pop(setting,None)
os.environ['AGENTSCOPE_BROKER_SOCKET']=str(Path(os.environ['AGENTSCOPE_STATE_DIR'])/'unavailable.sock')
os.environ['AGENTSCOPE_SCOPE_WORKER']='0'
os.environ['AGENTSCOPE_ADMIN_TOKEN'] = "test-admin-token-not-for-production"
os.environ["AGENTSCOPE_DEV_NO_AUTH"] = "0"
os.environ["AGENTSCOPE_POLICY_NORMALIZATION"] = "legacy"  # Legacy contracts; normalization tests explicitly enable it.
os.environ["ACTPLANE_BIN"] = "/missing/actplane"
os.environ["DSH_BIN"] = "/missing/dsh"
os.environ["AGENTSCOPE_HISTORY_WORKER"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
os.environ.setdefault('AGENTSCOPE_INSTANCE_WORKER', '0')
from agentscope_app import db
from agentscope_app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seed_task():
    def create(task_id):
        now = db.now()
        with db.connect() as con:
            con.execute(
                "INSERT INTO tasks(id,name,repo_url,repo,commit_sha,ref_requested,workspace,output_dir,prompt,agent,dsh_profile,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (task_id, task_id, "https://github.com/example/repo", "example/repo", "a" * 40, "main", "/tmp/work", "/tmp/output", "test task", "dsh", "headless", "running", now, now),
            )
    return create
