import importlib.util
import sqlite3
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

def test_hermes_projection_preserves_saved_names_and_live_process_join(tmp_path,monkeypatch):
    path=Path(__file__).resolve().parents[2]/'integrations/hermes-instance/__init__.py'
    spec=importlib.util.spec_from_file_location('isolated_hermes_sessions',path)
    plugin=importlib.util.module_from_spec(spec);spec.loader.exec_module(plugin)
    monkeypatch.setenv('HERMES_HOME',str(tmp_path))
    with sqlite3.connect(tmp_path/'state.db') as con:
        con.execute('CREATE TABLE sessions (id TEXT,cwd TEXT,title TEXT,started_at INTEGER)')
        con.executemany('INSERT INTO sessions VALUES (?,?,?,?)', [('saved','/w/0','已保存名称',1),('live-key','/w/0','旧名称',2)])
    server=SimpleNamespace(_sessions_lock=threading.Lock(),_sessions={'live-ui':{'session_key':'live-key','cwd':'/w/0','pending_title':'当前名称','running':False}})
    monkeypatch.setitem(sys.modules,'tui_gateway',SimpleNamespace(server=server))
    rows={r['id']:r for r in plugin.sessions()}
    assert rows['saved']['name']=='已保存名称' and rows['saved']['process_ids']==[] and rows['saved']['status']=='stored'
    assert rows['live-key']['name']=='当前名称' and rows['live-key']['runtime_session_id']=='live-ui'
    assert rows['live-key']['process_ids']==[plugin.os.getpid()] and rows['live-key']['status']=='idle'
