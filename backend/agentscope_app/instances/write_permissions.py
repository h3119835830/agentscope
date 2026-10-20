"""Narrow operator requests over the existing approval/application lifecycle."""
from pathlib import Path
from . import store, system_policy
from .mapping import translate, agent_policy


def detail(ident):
    row = store.get(ident)
    if row['mode'] != 'controlled':
        raise ValueError('仅受控 Agent 支持执行权限申请')
    return {'instance_id':ident, 'generation':row['generation'], 'policy_hash':row['policy_hash'],
            'local_policy':agent_policy(row['local_policy'],row['resources']),
            'effective_policy':agent_policy(row['policy'],row['resources']),
            'limits':{'write_ranges_per_resource':1, 'exact_path_bytes':63},
            'scope':'此 Agent 的共享执行域 · 全部会话',
            'application':'批准不会立即生效；显式应用将暂停并重新建立此 Agent 的执行进程'}


@system_policy.lifecycle
def propose(ident, body):
    from . import controller
    row = store.get(ident)
    if body['generation'] != row['generation'] or body['base_hash'] != row['policy_hash']:
        raise ValueError('运行代次或策略已变化，请刷新后重新申请')
    paths = [translate(p,row['resources'],reverse=True) for p in body['paths']]
    if len(set(paths)) != len(paths):
        raise ValueError('写入目录不能重复')
    rules = list(row['local_policy']['rules'])
    for value in paths:
        path = Path(value)
        if value in row['resources']:
            raise ValueError('此入口不能开放整个资源根目录，请只选择必要的源码或验收产物子目录')
        if not path.is_dir():
            raise ValueError('写入目标必须是已登记资源内已存在的目录；申请不会创建目录')
        if path.is_symlink() or path.resolve() != path:
            raise ValueError('写入目标不能经过符号链接')
        if len((translate(value,row['resources'])+'/**').encode())>=64:
            raise ValueError('目标路径超过当前精确匹配能力，无法提交此授权。需核验受治理的短路径资源映射，不能扩大到父目录代替。')
        if any(r['action']=='write' and r['effect']=='deny' and
               (value==r['target'] or value.startswith(r['target']+'/'))
               for r in row['policy']['rules']):
            raise ValueError('目标仍被已有禁止规则覆盖；新增允许不能抵消禁止，本入口不会删除该限制')
        if any(r['action']=='write' and r['effect']=='allow' and
               (value==r['target'] or value.startswith(r['target']+'/')) for r in rules):
            raise ValueError('目标已有写权限；请检查其他禁止规则，不会重复扩权')
        rules.append({'action':'write','effect':'allow','target':value,'text':body['reason']})
    result = controller.proposals(ident, {'policy':{**row['local_policy'],'rules':rules},
        'generation':body['generation'],'base_hash':body['base_hash'],'request_key':body['request_key']},
        actor='user')
    return {**result,'approval_id':'instance:'+result['id']}
