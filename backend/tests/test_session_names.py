import http.server
import json
import threading
import pytest
from agentscope_app.instances import session_names as names

@pytest.fixture(autouse=True)
def clean_cache():
    names._CACHE.clear()
    yield
    names._CACHE.clear()

@pytest.mark.parametrize('url',[
 'https://127.0.0.1:18020/?token=x','http://example.com:18020/?token=x',
 'http://127.0.0.1:80/?token=x','http://user@127.0.0.1:18020/?token=x',
 'http://127.0.0.1:18020/other?token=x','http://127.0.0.1:18020/?token=x#data',
 'http://127.0.0.1:18020/?url=x',
])
def test_native_metadata_never_follows_an_arbitrary_address(url):
    with pytest.raises(ValueError): names.native_origin(url)

def test_native_list_transport_only_reads_projected_names():
    calls=[]
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_GET(self):
            calls.append(('GET',self.path));self.send_response(303)
            self.send_header('Set-Cookie','test-native=ok; Path=/');self.send_header('Location','./');self.end_headers()
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(('POST',self.path,body))
            assert self.headers['Cookie']=='test-native=ok'
            data={'rpcId':body['rpcId'],'result':{'ok':True,'value':{'items':[
                {'sessionId':'s1','cwd':'/w/0','updatedAt':123,'projections':{'values':{'title':'检查库存','private':'DO NOT EXPORT'}}}
            ]}}}
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps(data).encode())
    server=http.server.HTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try: result=names.read_native_names(f'http://127.0.0.1:{server.server_port}/?token=test-only')
    finally: server.shutdown();worker.join();server.server_close()
    assert result=={'s1':{'name':'检查库存','resource':'/w/0','updated_at':123}}
    assert calls[1][1:] == ('/api/session/list',{'type':'client-request','rpcId':'agentscope-session-names','method':'session/list','payload':{'args':{'_request':{}}}})
    assert len(calls)==2 and 'DO NOT EXPORT' not in json.dumps(result)

def test_metadata_join_is_bound_to_existing_session_and_workspace(monkeypatch):
    monkeypatch.setattr(names,'read_native_names',lambda _:{
        's1':{'name':'自己的会话','resource':'/w/0','updated_at':12},
        's2':{'name':'其他目录','resource':'/w/9','updated_at':13},
        'foreign':{'name':'其他实例','resource':'/w/0','updated_at':14}})
    row={'id':'i','mode':'controlled','agent_type':'dsh','connected':True,'generation':'a','pid':42}
    result={'sessions':[{'id':'s1','resource':'/source','execution_resource':'/w/0','process_ids':[42]},
                        {'id':'s2','resource':'/source','execution_resource':'/w/0','process_ids':[]}]}
    got=names.with_session_names(row,result,lambda:{'url':'native'})
    assert len(got['sessions'])==2 and got['sessions'][0]['name']=='自己的会话'
    assert 'name' not in got['sessions'][1] and got['sessions'][1]['process_ids']==[]
    assert got['sessions'][0]['process_ids']==[42] and result['sessions'][0].get('name') is None

def test_metadata_failure_keeps_sessions_and_process_ownership(monkeypatch):
    monkeypatch.setattr(names,'read_native_names',lambda _:(_ for _ in ()).throw(OSError('unavailable')))
    result={'sessions':[{'id':'s1','process_ids':[]}]}
    row={'id':'i','mode':'controlled','agent_type':'dsh','connected':True}
    got=names.with_session_names(row,result,lambda:{'url':'native'})
    assert got['sessions']==result['sessions'] and got['names_available'] is False

def test_cache_is_invalidated_by_generation_or_executor(monkeypatch):
    calls=[]
    monkeypatch.setattr(names,'read_native_names',lambda _:calls.append(1) or {})
    row={'id':'i','mode':'controlled','agent_type':'dsh','connected':True,'generation':'a','pid':42}
    for current in (row,row,{**row,'generation':'b'},{**row,'pid':43}):
        names.with_session_names(current,{'sessions':[]},lambda:{'url':'native'})
    assert len(calls)==3

def test_unconnected_or_observed_instances_do_not_open_native_pages():
    def forbidden(): raise AssertionError('must not open')
    result={'sessions':[]}
    for row in ({'mode':'observed','agent_type':'dsh','connected':True},{'mode':'controlled','agent_type':'dsh','connected':False}):
        assert names.with_session_names(row,result,forbidden) is result
