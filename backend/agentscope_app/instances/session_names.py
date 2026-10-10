"""Read native display metadata; never activate sessions or infer process ownership."""
import http.cookiejar
import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from websockets.sync.client import connect as websocket_connect
from websockets.exceptions import WebSocketException

_CACHE = {}
_LOCK = threading.Lock()
_LIMIT = 2_000_000

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_): return None

def native_origin(url):
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme != 'http' or parts.hostname != '127.0.0.1' or parts.username or parts.password
            or parts.path != '/' or parts.fragment or not parts.port or not 1024 <= parts.port <= 65535
            or set(urllib.parse.parse_qs(parts.query)) != {'token'}):
        raise ValueError('Invalid native metadata address')
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, '', '', ''))

def native_connection(url):
    origin = native_origin(url)
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(jar), NoRedirect())
    try:
        with opener.open(url, timeout=2) as response:
            if response.status != 200: raise ValueError('Native authentication unavailable')
    except urllib.error.HTTPError as error:
        try:
            if error.code != 303 or error.headers.get('Location') not in ('./', '/'):
                raise ValueError('Native authentication unavailable') from None
        finally: error.close()
    return origin,opener,jar

def session_names(origin,opener):
    request = {'type':'client-request', 'rpcId':'agentscope-session-names',
               'method':'session/list', 'payload':{'args':{'_request':{}}}}
    with opener.open(urllib.request.Request(origin+'/api/session/list', data=json.dumps(request).encode(),
            headers={'Content-Type':'application/json'}), timeout=2) as response:
        raw = response.read(_LIMIT+1)
    if len(raw) > _LIMIT: raise ValueError('Native metadata too large')
    message = json.loads(raw)
    if message.get('rpcId') != request['rpcId'] or not message.get('result',{}).get('ok'):
        raise ValueError('Native metadata unavailable')
    names = {}
    for item in message['result']['value']['items']:
        title = item.get('projections',{}).get('values',{}).get('title')
        stamp = item.get('updatedAt')
        names[item['sessionId']] = {'name':title[:500] if isinstance(title,str) else None,
            'resource':item.get('cwd'), 'updated_at':stamp if isinstance(stamp,(int,float)) and math.isfinite(stamp) else None}
    return names

def read_native_names(url):
    origin,opener,_ = native_connection(url)
    return session_names(origin,opener)

def workspace_baseline(origin,jar):
    """Read one authoritative DSH baseline, then close the read-only stream."""
    with websocket_connect(origin.replace('http://','ws://',1)+'/api/remote.mux',
            additional_headers={'Cookie':'; '.join(c.name+'='+c.value for c in jar)},
            open_timeout=2,close_timeout=.2,max_size=_LIMIT,proxy=None) as connection:
        connection.send(json.dumps({'type':'open','streamId':'agentscope-workspaces',
            'endpoint':'workspace/follow','payload':{'args':{}}}))
        frame=json.loads(connection.recv(timeout=2))
        value=frame.get('value') if isinstance(frame,dict) else None
        if (not isinstance(frame,dict) or frame.get('type')!='item' or frame.get('streamId')!='agentscope-workspaces'
                or not isinstance(value,dict) or value.get('type')!='baseline'):
            raise ValueError('Native workspace baseline unavailable')
        baseline=value.get('value')
        items=baseline.get('items') if isinstance(baseline,dict) else None
        if not isinstance(items,list):raise ValueError('Invalid native workspace baseline')
        return items

def read_native_metadata(url):
    origin,opener,jar=native_connection(url)
    names=session_names(origin,opener)
    try:workspaces=workspace_baseline(origin,jar)
    except (OSError,ValueError,KeyError,TypeError,TimeoutError,WebSocketException):workspaces=[]
    joined={}
    for workspace in workspaces:
        if not isinstance(workspace,dict):continue
        ident,path,title=workspace.get('workspaceId'),workspace.get('path'),workspace.get('title')
        if not isinstance(ident,str) or not ident or not isinstance(path,str) or not path:continue
        members=workspace.get('sessionIds')
        if not isinstance(members,list):continue
        for sid in members:
            if not isinstance(sid,str) or sid not in names or names[sid]['resource']!=path:continue
            info={'id':ident,'name':title if isinstance(title,str) and title.strip() else None,
                  'path':path,'source':'dsh_workspace_registry'}
            joined[sid]=info if sid not in joined else None  # Ambiguous membership is never guessed.
    return {sid:{**meta,'native_workspace':joined.get(sid)} for sid,meta in names.items()}

def with_session_names(row, result, open_instance):
    if row.get('mode') != 'controlled' or row.get('agent_type') != 'dsh' or not row.get('connected'):
        return result
    key = (row['id'],row.get('generation'),row.get('pid'))
    now = time.monotonic()
    with _LOCK: cached = _CACHE.get(key)
    if cached and now-cached[0] < 5:
        names = cached[1]
    else:
        try: names = read_native_metadata(open_instance()['url'])
        except (OSError,ValueError,KeyError,TypeError,RuntimeError):
            return {**result,'sessions':[{**s,'native_workspace':None} for s in result.get('sessions',[])],'names_available':False}
        with _LOCK:
            if len(_CACHE) >= 64: _CACHE.pop(next(iter(_CACHE)))
            _CACHE[key] = (now,names)
    sessions = []
    for session in result.get('sessions',[]):
        session={**session,'native_workspace':None}
        meta = names.get(session['id'])
        if meta and isinstance(meta['resource'],str) and meta['resource'] in (session.get('execution_resource'),session.get('resource')):
            session = {**session,'name':meta['name'],'updated_at':meta['updated_at'],
                       'native_workspace':meta.get('native_workspace')}
        sessions.append(session)
    return {**result,'sessions':sessions,'names_available':True}
