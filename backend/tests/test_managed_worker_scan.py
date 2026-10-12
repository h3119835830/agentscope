from agentscope_app import db
from agentscope_app.managed import controller as c
from agentscope_app.managed.worker import Worker


def prepare(seed_task,tmp_path,phase,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'worker.sqlite3')
    db.init_db();ident='bounded-worker-'+phase;seed_task(ident)
    workspace=tmp_path/ident;log=workspace/'.actplane/events.jsonl'
    log.parent.mkdir(parents=True);log.write_text('initial\n')
    with db.connect() as con:
        con.execute('UPDATE tasks SET workspace=? WHERE id=?',(str(workspace),ident))
        c.save(con,ident,{'phase':phase,'gate':'open','revision':1,'policy_hash':'approved','archive':'x'*1000000})
    return ident,log


def test_ended_log_gets_final_and_later_drain_without_repeated_state_decode(seed_task,tmp_path,monkeypatch):
    ident,log=prepare(seed_task,tmp_path,'ended',monkeypatch);w=Worker();drains=[]
    monkeypatch.setattr(w,'collect_task',lambda task:drains.append(task))
    w.collect_once();w.collect_once()
    assert drains.count(ident)==1
    log.write_text('initial\nlate kernel denial\n');w.collect_once()
    assert drains.count(ident)==2


def test_unchanged_log_does_not_skip_active_protection_check(seed_task,tmp_path,monkeypatch):
    ident,_=prepare(seed_task,tmp_path,'running',monkeypatch);w=Worker();drains=[];failures=[]
    monkeypatch.setattr(w,'collect_task',lambda task:drains.append(task))
    monkeypatch.setattr(c,'broker',lambda *a,**k:{'status':'running','domain_verified':True})
    w.collect_once();w.binding_checks[ident]=0
    monkeypatch.setattr(c,'broker',lambda *a,**k:{'status':'offline'})
    monkeypatch.setattr(w,'fail',lambda task,*a:failures.append(task))
    w.collect_once()
    assert drains.count(ident)==1 and failures.count(ident)==1
