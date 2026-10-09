"""Read native display metadata; never activate sessions or infer process ownership."""
import http.cookiejar
import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

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

def read_native_names(url):
    origin = native_origin(url)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
    try:
        with opener.open(url, timeout=2) as response:
            if response.status != 200: raise ValueError('Native authentication unavailable')
    except urllib.error.HTTPError as error:
        try:
            if error.code != 303 or error.headers.get('Location') not in ('./', '/'):
                raise ValueError('Native authentication unavailable') from None
        finally: error.close()
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

def with_session_names(row, result, open_instance):
    if row.get('mode') != 'controlled' or row.get('agent_type') != 'dsh' or not row.get('connected'):
        return result
    key = (row['id'],row.get('generation'),row.get('pid'))
    now = time.monotonic()
    with _LOCK: cached = _CACHE.get(key)
    if cached and now-cached[0] < 5:
        names = cached[1]
    else:
        try: names = read_native_names(open_instance()['url'])
        except (OSError,ValueError,KeyError,TypeError,RuntimeError):
            return {**result,'names_available':False}
        with _LOCK:
            if len(_CACHE) >= 64: _CACHE.pop(next(iter(_CACHE)))
            _CACHE[key] = (now,names)
    sessions = []
    for session in result.get('sessions',[]):
        meta = names.get(session['id'])
        if meta and isinstance(meta['resource'],str) and meta['resource'] in (session.get('execution_resource'),session.get('resource')):
            session = {**session,'name':meta['name'],'updated_at':meta['updated_at']}
        sessions.append(session)
    return {**result,'sessions':sessions,'names_available':True}
