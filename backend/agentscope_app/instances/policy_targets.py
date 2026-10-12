"""Policy ownership is independent of evidence paths and executor identity.

Native workspace/session application deliberately has no loader in this release.
Never infer support from a shared PID, cwd, or a client supplied capability flag.
"""

LOCAL_BLOCK = '当前连接尚不支持独立工作区或会话执行绑定；请先接入独立受控执行，策略不会应用到整个 Agent。'


def generated_target(context, scene=False):
    work = context['environment_binding']['values']['workspace']
    return {'scope': 'workspace' if scene else 'session',
            'instance_id': context['instance_id'],
            'workspace_id': work.get('native_workspace_id'),
            'session_id': None if scene else context['session_id']}


def label(target, context=None):
    scope = target['scope']
    if scope == 'system': return '全部受控 Agent'
    if scope == 'agent': return '全部工作区与会话'
    if scope == 'workspace':
        if not target.get('workspace_id'): return '工作区身份待核验'
        work = (context or {}).get('environment_binding', {}).get('values', {}).get('workspace', {})
        return '工作区：' + (work.get('name') or work.get('host') or '身份待核验')
    return '当前会话及其子进程'


def capability(target):
    if target['scope'] not in ('workspace', 'session'):
        return {'supported': True, 'reason': ''}
    missing = target['scope'] == 'workspace' and not target.get('workspace_id')
    return {'supported': False, 'reason':
            '尚未取得可信工作区身份，请核验原生工作区登记；不能按目录或会话猜测归属。' if missing else LOCAL_BLOCK}
