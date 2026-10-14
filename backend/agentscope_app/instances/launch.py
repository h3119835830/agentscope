"""Execution entry configuration. Commands are argv, never a root shell."""
import os
import re
import shlex
from pathlib import Path
from .policy import clean_resources, digest

DSH = Path('/opt/agentscope/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js')
NODE = Path('/opt/agentscope/bin/node')
HERMES = Path('/home/happy/.local/bin/hermes')
PYTHON = Path('/usr/bin/python3')

def host_path(value):
    value=str(value).strip()
    if re.match(r'^[cC]:[\\/]',value):
        value='/mnt/c/'+value[3:].replace('\\','/')
    return value

def presets():
    return {'environment':'wsl','profiles':[
        {'agent_type':'dsh','kind':'web','command':'dsh web --host 127.0.0.1 --port {port} --no-open','label':'DeepSeek Harness'},
        {'agent_type':'hermes','kind':'web','command':'hermes dashboard --isolated --no-open --skip-build --host 127.0.0.1 --port {port}','label':'Hermes'},
        {'agent_type':'other','kind':'terminal','command':'node ./agent.js','label':'其他 Node / Python Agent'}],
        'notice':'命令以普通用户运行；目录默认只读，写入在安全配置中授权。Windows 原生进程暂未接入受控启动。'}

def canonical(value, agent_type, resources=None):
    if not isinstance(value,dict) or set(value)-{'command','cwd','kind','web_url','native_paths'}:
        raise ValueError('启动配置字段不合法')
    command=str(value.get('command','')).strip()
    if not command or len(command)>8000 or '\n' in command or '\r' in command:
        raise ValueError('请填写一条启动命令')
    if re.search(r'(?i)(?:--(?:api[_-]?key|password|secret|access[_-]?token|token)(?:[=:]|\s+)|(?:api[_-]?key|password|secret|access[_-]?token)\s*[=:])',command):
        raise ValueError('启动命令不能保存凭据，请使用 Agent 原生凭据配置')
    try: argv=shlex.split(command)
    except ValueError: raise ValueError('启动命令引号不完整') from None
    if any(v in ('|','||','&&',';','>','>>','<','&') for v in argv):
        raise ValueError('请直接填写程序及参数，不使用管道、重定向或后台符号')
    kind=value.get('kind','web')
    if kind not in ('web','terminal'):raise ValueError('打开方式必须是网页或终端')
    cwd=host_path(value.get('cwd',''))
    clean_resources([cwd])
    if resources and not any(Path(cwd)==Path(r) or Path(r) in Path(cwd).parents for r in resources):
        raise ValueError('启动目录须位于安全配置的文件访问范围内')
    first=argv[0]
    if first=='dsh' or first in (str(DSH),'/opt/agentscope/dsh/node_modules/.bin/dsh'):
        argv=[str(NODE),str(DSH),*argv[1:]]
    elif first=='node':argv[0]=str(NODE)
    elif first in ('python','python3'):argv[0]=str(PYTHON.resolve())
    elif first=='hermes':argv[0]=str(HERMES)
    program=Path(argv[0]);is_hermes=program==HERMES
    resolved=HERMES if is_hermes else program.resolve()
    if not program.is_absolute() or not is_hermes and not program.exists():raise ValueError('启动程序不存在，请填写已安装程序的绝对路径')
    if resolved not in (NODE.resolve(),PYTHON.resolve(),HERMES):
        raise ValueError('当前受控启动支持已安装的 Node、Python 与 Hermes 入口')
    is_dsh=len(argv)>1 and Path(argv[1])==DSH
    is_hermes=program==HERMES
    if agent_type=='dsh' and not is_dsh:raise ValueError('DeepSeek Harness 连接必须使用其原生启动程序')
    if agent_type=='hermes' and not is_hermes:raise ValueError('Hermes 连接必须使用其原生启动程序')
    if agent_type=='other' and (is_dsh or is_hermes):raise ValueError('请选择对应 Agent 类型，避免遗漏原生会话接入')
    if is_dsh:
        rest=argv[2:]
        if not rest or rest[0]!='web' or kind!='web':
            raise ValueError('本机 DSH 当前已安装网页配置；其他原生终端配置尚未接入，请使用 web')
        if any(a in ('--profile','--patch','--from-default-profile','plugin') or a.startswith(('--profile=','--patch=')) for a in rest):
            raise ValueError('此连接使用原生 web 配置，不能覆盖受控接入插件')
    url=str(value.get('web_url','http://127.0.0.1:{port}/')).strip() if kind=='web' else ''
    if kind=='web':
        if not re.fullmatch(r'http://127\.0\.0\.1:(?:\{port\}|[0-9]{4,5})/(?:[a-zA-Z0-9_./-]*)',url) or '..' in url:
            raise ValueError('网页入口须为本机 HTTP 地址，可用 {port} 自动分配端口')
        port=re.search(r':([0-9]+)/',url)
        if port and not 1024<=int(port[1])<=65000:raise ValueError('网页端口须在 1024 至 65000 之间')
        if is_dsh or is_hermes:
            if not url.endswith('/') or url.count('/')!=3:raise ValueError('此原生网页适配器使用根目录入口')
            if '--host' not in argv or argv.index('--host')+1>=len(argv) or argv[argv.index('--host')+1]!='127.0.0.1' or '--port' not in argv or argv.index('--port')+1>=len(argv):
                raise ValueError('原生网页命令须指定 --host 127.0.0.1 和 --port {port}')
            command_port=argv[argv.index('--port')+1]
            expected=port[1] if port else '{port}'
            if command_port!=expected:raise ValueError('启动命令与网页入口的端口须一致')
    result={'command':command,'argv':argv,'cwd':cwd,'kind':kind,'web_url':url,'native_paths':True,
            'adapter':'native' if agent_type in ('dsh','hermes') else 'process',
            'source':'**/'+('node' if resolved==NODE.resolve() or is_dsh else 'python' if is_hermes else resolved.name)}
    result['hash']=digest(result)
    return result

def validate_saved(value,agent_type,resources):
    if value is None:return None
    result=canonical({k:value[k] for k in ('command','cwd','kind','web_url','native_paths') if k in value},agent_type,resources)
    if result!=value:raise ValueError('启动配置或程序身份已变化，请重新保存连接')
    return result


def validate_policy(value,policy):
    if value and value.get('adapter')=='process' and any(rule['action']=='tool' for rule in policy['rules']):
        raise ValueError('此命令尚无原生工具适配器；文件和网络规则可执行，工具规则暂不支持')
