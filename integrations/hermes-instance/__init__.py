"""Independent Hermes native plugin; no prompt rewrites or ERP dependency."""
import hmac, http.server, json, os, sqlite3, threading, time, urllib.request, uuid
from pathlib import Path
_SERVER=None
_LOCK=threading.RLock()
_CALLS={}
_ID=os.environ.get('AGENTSCOPE_INSTANCE_ID')
_TOKEN=os.environ.get('AGENTSCOPE_INSTANCE_TOKEN')
_GEN=os.environ.get('AGENTSCOPE_GENERATION')
_BASE=os.environ.get('AGENTSCOPE_INSTANCE_URL')
_SECRET=os.environ.get('AGENTSCOPE_NATIVE_TOKEN')
_RESOURCES=json.loads(os.environ.get('AGENTSCOPE_RESOURCES','[]'))

def api(path,body):
    req=urllib.request.Request(_BASE+path,data=json.dumps({'generation':_GEN,**body}).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+_TOKEN})
    with urllib.request.urlopen(req,timeout=12) as response: return json.load(response)

def before(tool_name='',session_id='',tool_call_id='',task_id='',**kwargs):
    if not session_id: return {'action':'block','message':'Cannot attribute this operation to a native Hermes session.'}
    key=tool_call_id or uuid.uuid4().hex
    value={'session_id':session_id,'call_id':key,'tool':tool_name}
    try:
        result=api('/lease',value)
        if not result.get('allowed'): return {'action':'block','message':result.get('reason','Instance execution paused')}
        with _LOCK: _CALLS[(session_id,tool_call_id or task_id,tool_name)]=value
    except Exception:
        return {'action':'block','message':'AgentScope connection unavailable. Instance tool execution is paused.'}

def after(tool_name='',session_id='',tool_call_id='',task_id='',**kwargs):
    with _LOCK: value=_CALLS.pop((session_id,tool_call_id or task_id,tool_name),None)
    if value:
        try: api('/result',{**value,'succeeded':kwargs.get('status') not in ('error','cancelled','blocked')})
        except Exception: pass  # Outstanding lease forces restart before future policy application.

def sessions():
    result={}
    path=Path(os.environ['HERMES_HOME'])/'state.db'
    if path.exists():
        con=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
        try:
            for sid,cwd,title in con.execute('SELECT id,cwd,title FROM sessions ORDER BY started_at DESC LIMIT 200'):
                result[sid]={'id':sid,'name':title,'resource':cwd,'process_ids':[],'mapping':'native_session_database','status':'stored'}
        finally: con.close()
    try:
        from tui_gateway import server
        with server._sessions_lock:
            for sid,s in server._sessions.items():
                stored=s['session_key']
                result[stored]={'id':stored,'name':s.get('pending_title') or result.get(stored,{}).get('name'),'runtime_session_id':sid,'resource':s.get('cwd'),'process_ids':[os.getpid()],'mapping':'native_gateway','running':s.get('running',False),'status':'running' if s.get('running') else 'idle'}
    except Exception: pass
    return list(result.values())

class Transport:
    def __init__(self,rid): self.rid=rid;self.ready=threading.Event();self.response=None
    def write(self,value):
        if value.get('id')==self.rid: self.response=value;self.ready.set()
        return True
    def close(self): pass

def rpc(method,params):
    from tui_gateway import server
    rid=uuid.uuid4().hex;transport=Transport(rid)
    result=server.dispatch({'jsonrpc':'2.0','id':rid,'method':method,'params':params},transport)
    if result is None:
        if not transport.ready.wait(30): raise ValueError('Native Hermes RPC timed out')
        result=transport.response
    if 'error' in result: raise ValueError('Native Hermes rejected operation')
    return result.get('result',{})

def register(ctx):
    global _SERVER
    ctx.register_hook('pre_tool_call',before)
    ctx.register_hook('post_tool_call',after)
    ctx.register_tool(name='agentscope_instance_scope',toolset='agentscope-instance',schema={'name':'agentscope_instance_scope','description':'Read the current policy shared by every session of this instance.','parameters':{'type':'object','properties':{}}},handler=lambda args,**kwargs:json.dumps(api('/scope',{})))
    def propose(args,**kwargs):
        return json.dumps(api('/policy/proposals',{'policy':json.loads(args['policy_json']),'base_hash':args['base_hash'],'request_key':args['request_key']}))
    ctx.register_tool(name='agentscope_instance_propose',toolset='agentscope-instance',schema={'name':'agentscope_instance_propose','description':'Propose typed instance policy. Verified restriction restarts this instance; expansion requires user confirmation.','parameters':{'type':'object','properties':{'policy_json':{'type':'string'},'base_hash':{'type':'string'},'request_key':{'type':'string'}},'required':['policy_json','base_hash','request_key']}},handler=propose)
    if _SERVER or not _ID: return
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            try:
                if not hmac.compare_digest(self.headers.get('authorization',''),'Bearer '+_SECRET): raise ValueError('Unauthorized')
                size=int(self.headers.get('content-length','0'))
                if size>18000: raise ValueError('Request too large')
                data=json.loads(self.rfile.read(size) or b'{}');op=data.get('operation')
                if op=='observe': result={'pid':os.getpid(),'sessions':sessions(),'inflight':len(_CALLS)}
                elif op=='open_url': result={'url':'http://127.0.0.1:'+os.environ['AGENTSCOPE_WEB_PORT']+'/'}
                elif op=='create':
                    if data['resource'] not in _RESOURCES: raise ValueError('Unregistered resource')
                    created=rpc('session.create',{'cwd':data['resource'],'source':'web','title':'AgentScope 实例会话'})
                    result={'session_id':created['session_id'],'stored_session_id':created.get('stored_session_id')}
                elif op=='prompt':
                    # Native gateway owns context, cwd, model resolution and execution.
                    result=rpc('prompt.submit',{'session_id':data['session_id'],'text':data['text']})
                elif op=='inspect':
                    from tui_gateway import server
                    with server._sessions_lock:
                        session=server._sessions.get(data['session_id'])
                        result={'session_id':data['session_id'],'status':'running' if session and session.get('running') else 'idle','agent_error':bool(session and session.get('agent_error'))}
                elif op=='cancel': result=rpc('session.interrupt',{'session_id':data['session_id']})
                elif op=='flush':
                    from tui_gateway import server
                    with server._sessions_lock: current=list(server._sessions.values())
                    for s in current: server._finalize_session(s)
                    result={'ok':True}
                else: raise ValueError('Operation unavailable')
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(result).encode())
            except Exception:
                self.send_response(409);self.end_headers();self.wfile.write(b'{"error":"Native operation unavailable"}')
    try:
        _SERVER=http.server.ThreadingHTTPServer(('127.0.0.1',int(os.environ['AGENTSCOPE_NATIVE_PORT'])),Handler)
    except OSError:
        return  # Native child sessions install hooks but reuse the main bridge.
    threading.Thread(target=_SERVER.serve_forever,daemon=True,name='agentscope-native-bridge').start()
