import time
import uuid
import pytest
from fastapi.testclient import TestClient
from agentscope_app import db, development, local_browser, main

BASE = "http://127.0.0.1:18003"
ADMIN = {"Authorization":"Bearer test-admin-token-not-for-production"}
ORIGIN = {"Origin":BASE}


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.setattr(local_browser, "LOCAL_BROWSER_LOGIN", True)
    with TestClient(main.app,base_url=BASE,client=("127.0.0.1",52000)) as client:
        yield client


def connect(client):
    ticket=client.post("/api/auth/local-browser-ticket",headers=ADMIN,json={}).json()["ticket"]
    response=client.post("/api/auth/local-browser-redeem",headers=ORIGIN,json={"ticket":ticket})
    assert response.status_code==200
    return ticket, response


def test_local_browser_enters_scope_without_receiving_admin_token(browser):
    assert browser.get("/api/tasks").status_code==401
    ticket,response=connect(browser)
    cookie=response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert ticket not in cookie and main.ADMIN_TOKEN not in cookie
    assert browser.get("/api/auth/mode").json()["local_browser_session"]
    assert browser.get("/api/tasks").status_code==200
    created=browser.post("/api/scope-demo/tasks",headers=ORIGIN,json={})
    assert created.status_code==200
    scope=browser.get("/api/tasks/"+created.json()["task_id"]+"/scope-manager")
    assert scope.status_code==200 and scope.json()["current"] is None


def test_agent_and_browser_cannot_mint_new_launch_tickets(browser,seed_task,monkeypatch):
    monkeypatch.setattr(development,"DEV_NO_AUTH",True)
    assert browser.post("/api/auth/local-browser-ticket",headers=ORIGIN,json={}).status_code==401
    task="browser-agent-"+uuid.uuid4().hex
    seed_task(task)
    token,_=main.issue_task_token(task)
    headers={**ORIGIN,"Authorization":"Bearer "+token,"Sec-Fetch-Site":"same-origin"}
    assert browser.post("/api/auth/local-browser-ticket",headers=headers,json={}).status_code==401
    assert browser.post("/api/tasks/"+task+"/scope-manager/changes/missing/review",headers=headers,json={}).status_code==401
    connect(browser)
    assert browser.post("/api/auth/local-browser-ticket",headers=ORIGIN,json={}).status_code==401
    assert browser.get("/api/tasks",headers=headers).status_code==401


def test_launch_ticket_is_single_use_and_expires(browser):
    ticket,_=connect(browser)
    assert browser.post("/api/auth/local-browser-redeem",headers=ORIGIN,json={"ticket":ticket}).status_code==401
    ticket=browser.post("/api/auth/local-browser-ticket",headers=ADMIN,json={}).json()["ticket"]
    with db.connect() as con:
        con.execute("UPDATE local_browser_access SET expires_at=? WHERE hash=?",(time.time()-1,local_browser.digest(ticket)))
    assert browser.post("/api/auth/local-browser-redeem",headers=ORIGIN,json={"ticket":ticket}).status_code==401


@pytest.mark.parametrize("headers",[
    {},
    {"Origin":"https://outside.example"},
    {"Origin":"http://127.0.0.1:18002"},
    {"Origin":BASE,"Sec-Fetch-Site":"same-site"},
])
def test_browser_write_requires_same_origin(browser,headers):
    connect(browser)
    assert browser.post("/api/scope-demo/tasks",headers=headers,json={}).status_code==401


def test_browser_session_expiration_and_logout(browser):
    connect(browser)
    value=browser.cookies.get(local_browser.COOKIE)
    assert browser.post("/api/auth/local-browser-close",headers=ORIGIN,json={}).status_code==200
    assert browser.get("/api/auth/check").status_code==401
    browser.cookies.set(local_browser.COOKIE,value,domain="127.0.0.1",path="/api")
    assert browser.get("/api/tasks").status_code==401
    connect(browser)
    value=browser.cookies.get(local_browser.COOKIE)
    with db.connect() as con:
        con.execute("UPDATE local_browser_access SET expires_at=? WHERE hash=?",(time.time()-1,local_browser.digest(value)))
    assert browser.get("/api/tasks").status_code==401


@pytest.mark.parametrize("peer,enabled",[("10.0.0.2",True),("127.0.0.1",False)])
def test_launcher_is_local_and_opt_in(monkeypatch,peer,enabled):
    monkeypatch.setattr(local_browser,"LOCAL_BROWSER_LOGIN",enabled)
    with TestClient(main.app,base_url=BASE,client=(peer,52000)) as client:
        assert client.post("/api/auth/local-browser-ticket",headers=ADMIN,json={}).status_code==403



def test_control_lock_is_audited_and_restart_keeps_unrevoked_browser_session(browser):
    connect(browser)
    db.init_db()  # The session is persistent state, not an API process-local cache.
    assert browser.get('/api/auth/check').status_code==200
    response=browser.post('/api/auth/local-browser-close',headers=ORIGIN,json={})
    assert response.status_code==200 and browser.get('/api/auth/check').status_code==401
    with db.connect() as con:
        row=con.execute("SELECT actor,details_json FROM audit_log WHERE action='local_browser_locked' ORDER BY created_at DESC LIMIT 1").fetchone()
    assert row['actor']=='local_operator' and 'explicit_control_lock' in row['details_json']
