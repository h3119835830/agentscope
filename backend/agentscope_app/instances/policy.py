"""Typed instance policy. Natural language is never executable policy."""
import hashlib, ipaddress, json
from pathlib import Path
from .mapping import translate
ACTIONS = {'read', 'write', 'tool', 'network', 'behavior'}
EFFECTS = {'allow', 'deny', 'confirm'}

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def clean_resources(paths):
    if not isinstance(paths, list) or not 1 <= len(paths) <= 16:
        raise ValueError('请登记 1 至 16 个资源目录')
    result = []
    for value in paths:
        p = Path(value)
        if not p.is_absolute() or p.is_symlink() or str(p.resolve(strict=True)) != str(p) or not p.is_dir():
            raise ValueError('资源必须是已存在的规范绝对目录')
        if not any(str(p).startswith(root) for root in ('/home/happy/projects/', '/mnt/c/Users/happy/Desktop/projects/', '/s/instance-resources/')):
            raise ValueError('资源目录须在本机项目目录或 Demo 的 instance-resources 下')
        if any(p == Path(old) or p in Path(old).parents or Path(old) in p.parents for old in result):
            raise ValueError('资源目录不能重复或相互包含')
        result.append(str(p))
    return sorted(result)

def default_policy():
    return {'rules': [], 'network': 'model_only'}

def canonical(value, resources):
    if set(value) - {'rules', 'network'} or value.get('network', 'model_only') not in ('model_only', 'disabled'):
        raise ValueError('不支持的实例策略字段')
    if not isinstance(value.get('rules',[]),list): raise ValueError('策略规则必须是记录数组')
    rules = []
    for raw in value.get('rules', []):
        if not isinstance(raw, dict) or set(raw) - {'action', 'target', 'effect', 'text'}:
            raise ValueError('策略只接受行为、目标、决定和补充约束')
        action, effect = raw.get('action'), raw.get('effect')
        target, text = str(raw.get('target', '')).strip(), str(raw.get('text', '')).strip()
        if action not in ACTIONS or effect not in EFFECTS or len(text) > 2000 or len(target) > 1000:
            raise ValueError('策略字段不合法')
        if action in ('read', 'write'):
            target=translate(target,resources,reverse=True)
            p = Path(target)
            if not p.is_absolute() or str(p.resolve(strict=True)) != target or p.is_symlink():
                raise ValueError('文件目标必须存在且不能使用符号链接')
            if not any(p == Path(r) or Path(r) in p.parents for r in resources):
                raise ValueError('文件目标超出已登记资源')
            if effect=='deny':
                protected=[p,*p.rglob('*')] if p.is_dir() else [p]
                if any(t.is_symlink() or t.is_file() and t.stat().st_nlink!=1 for t in protected):
                    raise ValueError('保护目标不能包含符号链接或已有硬链接别名')
            if effect == 'confirm':
                raise ValueError('文件权限通过扩权候选统一确认，请选择允许或禁止')
            if len((translate(target,resources)+('/**' if p.is_dir() else '')).encode())>=64:
                raise ValueError('目标路径超过当前 ActPlane 的精确规则长度；请选择较短的共同保护目录')
        elif action == 'network':
            address=ipaddress.IPv4Address(target)
            if address.is_loopback: raise ValueError('不能修改实例控制连接')
            if effect != 'deny':
                raise ValueError('额外网络当前只支持禁止 IPv4')
        elif action == 'tool':
            if not target or not all(c.isalnum() or c in '_-' for c in target):
                raise ValueError('请填写原生工具名称')
        elif not text:
            raise ValueError('请填写行为约定')
        rules.append({'action': action, 'target': target, 'effect': effect, 'text': text})
    if len(rules) > 100:
        raise ValueError('策略最多 100 条')
    rules = sorted({json.dumps(r, sort_keys=True, ensure_ascii=False): r for r in rules}.values(), key=lambda r: (r['action'],r['target'],r['effect'],r['text']))
    for base in resources:
        grants=[r for r in rules if r['action']=='write' and r['effect']=='allow' and (Path(r['target'])==Path(base) or Path(base) in Path(r['target']).parents)]
        if len(grants)>1: raise ValueError('每个资源目录支持一个连续写入范围，请使用一个共同目录并单独禁止保护文件')
    return {'rules': rules, 'network': value.get('network', 'model_only')}

def restrictive(old, new):
    if old['network'] == 'disabled' and new['network'] != 'disabled':
        return False
    for rule in old['rules']:
        if rule['action'] != 'behavior' and rule['effect'] != 'allow' and rule not in new['rules']:
            return False
    return not any(r['effect'] == 'allow' and r not in old['rules'] and r['action'] != 'behavior' for r in new['rules'])

def records(policy, resources, active=False):
    result = [
        {'sentence':'实例内全部会话及子进程继承平台底线，不能写入控制目录或自行扩权。','source':'平台底线','method':'隔离挂载、非特权身份与 ActPlane','result':'已核验' if active else '待启动核验'},
        {'sentence':'只读已登记资源目录；写入必须有明确授权。','source':'实例默认策略','method':'隔离挂载与 ActPlane','result':'已核验' if active else '待启动核验'},
        {'sentence':'仅连接本机控制端、DNS 和启动层解析的模型 IPv4 地址。' if policy['network']=='model_only' else '禁止模型和外部网络连接，保留本机控制端。','source':'实例策略','method':'实例 cgroup 网络过滤','result':'已核验' if active else '待启动核验'}
    ]
    verbs={'read':'读取','write':'修改与删除','tool':'使用工具','network':'连接 IPv4','behavior':'行为约定'}
    effects={'allow':'允许','deny':'禁止','confirm':'须经确认'}
    for r in policy['rules']:
        sentence = r['text'] if r['action']=='behavior' else effects[r['effect']]+verbs[r['action']]+'「'+r['target']+'」'+('；'+r['text'] if r['text'] else '。')
        result.append({**r,'sentence':sentence,'source':'实例策略','method':'行为约定' if r['action']=='behavior' else '原生 Hook' if r['action']=='tool' else '网络过滤' if r['action']=='network' else '隔离挂载与 ActPlane','result':'不作强制执行声明' if r['action']=='behavior' else '执行前检查' if active and r['action']=='tool' else '已核验' if active else '待启动核验'})
    return result
