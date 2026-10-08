"""Non-authoritative local discovery. Never grants execution privileges."""
import re,threading,time
from urllib.parse import urlsplit
_lock=threading.Lock()
_windows={}
def local_url(value):
    u=urlsplit(value)
    if u.scheme!='http' or u.hostname!='127.0.0.1' or not u.port or not 1024<=u.port<=65535 or u.username or u.password or u.path not in ('','/') or u.query or u.fragment:
        raise ValueError('手动入口仅接受 http://127.0.0.1:端口/，不能提交命令或凭据')
    return 'http://127.0.0.1:'+str(u.port)+'/'
def windows_report(rows):
    now=time.monotonic();result={}
    if len(rows)>100: raise ValueError('发现记录过多')
    for row in rows:
        path=row['executable'].replace('/','\\').lower()
        kind=row['agent_type']
        codex_paths=(r'\\appdata\\local\\openai\\codex\\bin\\[a-f0-9]+\\codex\.exe$',r'\\\.vscode\\extensions\\openai\.chatgpt-[^\\]+\\bin\\windows-x86_64\\codex\.exe$')
        allowed=(kind=='codex' and path.endswith('\\codex.exe') and ('\\openai.codex_' in path or '\\programs\\codex\\' in path or any(re.search(pattern,path) for pattern in codex_paths))) or (kind=='hermes-desktop' and path.endswith('\\hermes.exe') and '\\programs\\hermes' in path)
        if not allowed: raise ValueError('进程安装路径无法识别，普通 Python / Node 不能登记为 Agent')
        key='windows-'+str(row['pid'])+'-'+row['started_at']
        result[key]={**row,'id':key,'name':row['name'],'environment':'windows','connected':False,'status':'discovered','resources':[],'source':'Windows 安装路径与 OS 进程观测','_observed':now}
    with _lock:
        _windows.clear();_windows.update(result)
    return {'accepted':len(result)}
def windows_snapshot():
    with _lock: rows=[dict(r) for r in _windows.values()]
    for r in rows:
        age=time.monotonic()-r.pop('_observed')
        r['evidence_age_seconds']=round(age,2)
        if age>=8:r['status']='stale'
        r.update(mode='observed',security='仅发现，未接入执行',active=False)
    return rows
