"""Published, server-owned configuration contracts; the model cannot add rules."""
import copy
import json
from pathlib import Path
from .policy_library import CATALOG as SYSTEM_CATALOG

# Selection metadata is shared by people and Agents, not part of immutable DSL
# definitions or template_hash. Description edits must not invalidate approval.
DESCRIPTIONS = json.loads(Path(__file__).with_name('template_descriptions.json').read_text())


def field(key, label, default='', kind='text', **extra):
    return {'key': key, 'label': label, 'default': default, 'type': kind, **extra}


def template(ident, name, category, summary, renderer, parameters, *, effect='block', operation='open', note=''):
    return {'id': ident, 'version': 1, 'name': name, 'category': category, 'summary': summary,
            'renderer': renderer, 'parameters': parameters, 'effect': effect, 'operation': operation,
            'scopes': ['agent', 'workspace'], 'note': note,
            'reason': summary + ' 请在允许的范围内继续任务，必要时提交最小变更需求。'}


PATH = field('target', '保护对象的路径', kind='path')
CHANGES = field('operations', '需要限制的操作', 'write,unlink', 'operations')
CATALOG = [
    template('RQ1-ENV', '敏感配置访问限制', '文件保护', '禁止读取指定的敏感文件。', 'file', [PATH]),
    template('RQ1-CONTRACT', '开发契约文件保护', '文件保护', '保护开发契约文件的修改与删除。', 'file', [PATH, CHANGES], operation='write'),
    template('FILE-READ', '文件读取限制', '文件保护', '禁止读取指定文件或目录中的资料。', 'file', [PATH]),
    template('FILE-CHANGE', '文件修改与删除限制', '文件保护', '限制指定文件或目录的修改与删除。', 'file', [PATH, CHANGES], operation='write'),
    template('WRITE-BOUNDARY', '文件变更范围约束', '文件保护', '限制变更范围，仅为指定路径保留例外。', 'boundary',
             [field('target', '受约束的文件范围', kind='path'), field('exception', '保留变更权限的路径范围', kind='path')], operation='write',
             note='例外只保留现有访问权限，不授予写权限；修改与删除属于同一执行访问组。'),
    template('RQ1-GENERATED', '生成文件写入约束', '生成产物', '生成文件的变更应经过指定程序的执行链。', 'lineage',
             [PATH, field('producer', '生成程序名', kind='program')], operation='write',
             note='按程序执行链匹配，不证明特定脚本、参数或生成内容正确。'),
    template('RQ1-CHECK', '提交前检查顺序', '开发流程', '代码变更后，提交前应出现指定检查程序的执行事件。', 'workflow',
             [PATH, field('checker', '检查程序名', kind='program')], operation='exec',
             note='当前运行后端不支持按提交参数事前 block；可保存配置，编译不支持时不能应用。'),
    template('RQ1-DELETE', '文件删除提醒', '行为提醒', '记录并反馈指定文件的变更操作。', 'file', [PATH, CHANGES],
             operation='unlink', effect='notify', note='提醒会继续执行；当前修改与删除共用访问组。'),
    template('RQ1-GIT', '高风险 Git 操作约束', '开发流程', '匹配高风险 Git 参数后终止命中进程。', 'git', [],
             operation='exec', effect='kill', note='参数来自执行后观察，不能保证危险操作事前未发生。'),
    template('EXEC-BLOCK', '程序执行限制', '进程与网络', '禁止 Agent 及后代启动指定程序。', 'exec',
             [field('program', '程序名或路径', kind='program')], operation='exec'),
    template('EXEC-AUDIT', '程序执行记录', '进程与网络', '记录 Agent 及后代启动指定程序的事件。', 'exec',
             [field('program', '程序名或路径', '*', 'program')], operation='exec', effect='notify'),
    template('NET-BLOCK', '网络连接限制', '进程与网络', '禁止向指定 IPv4 地址或地址前缀建立连接。', 'endpoint',
             [field('endpoint', 'IPv4 地址、前缀或 *', kind='endpoint')], operation='connect',
             note='约束新连接，不等同于已有连接发送、DNS 或完整流量控制。'),
    template('NET-AUDIT', '网络连接记录', '进程与网络', '记录指定 IPv4 目标的连接事件。', 'endpoint',
             [field('endpoint', 'IPv4 地址、前缀或 *', '*', 'endpoint')], operation='connect', effect='notify'),
    template('SECRET-EGRESS', '敏感资料外发限制', '跨事件保护', '接触指定敏感来源后，禁止向指定目标建立连接。', 'flow',
             [field('target', '敏感来源路径', kind='path'), field('endpoint', '受限制的 IPv4 目标', '*', 'endpoint')], operation='connect',
             note='标签沿已观测的进程与文件传播；新连接限制不证明所有外发通道已覆盖。'),
    template('REMOTE-EXEC', '网络输入后的执行提醒', '跨事件保护', '接触网络输入后，记录指定程序的启动。', 'remote',
             [field('program', '程序名或路径', kind='program')], operation='exec', effect='notify',
             note='来源标签不是脚本内容或签名校验。'),
]

for alias, canonical in [('RQ1-ENV','FILE-READ'), ('RQ1-CONTRACT','FILE-CHANGE')]:
    next(t for t in CATALOG if t['id'] == alias)['assistant_alias'] = canonical

for preset in SYSTEM_CATALOG:
    CATALOG.append({**template('SYS-' + preset['id'], preset['name'], '系统 · ' + preset['category'],
                              preset['description'], 'system',
                              [field('values', '匹配对象（每行一个）', preset['values'], 'lines')],
                              effect=preset['effect'], operation=preset['ops'][0], note=preset.get('note', '')),
                    'scopes': ['system'], 'reason': preset['reason'], 'system_preset': preset['id']})


HISTORICAL = {(t['id'], t['version']): copy.deepcopy(t) for t in CATALOG}
for item in CATALOG:
    item['version'] = 2
    item['scopes'] = ['system', 'agent']
    if item['renderer'] == 'system':
        preset = next(p for p in SYSTEM_CATALOG if p['id'] == item['system_preset'])
        item['parameters'] += [field('operations', '触发操作', ','.join(preset['ops']), 'operations'),
                               field('effect', '匹配后的动作', preset['effect'], 'effect')]
        item['allowed_operations'] = ['exec'] if preset['mode'] in ('exec','remote') else ['connect'] if preset['mode'] in ('endpoint','flow') else ['open','write','unlink']


def get(ident, version=1):
    item = next((t for t in CATALOG if t['id'] == ident and t['version'] == version), None) or HISTORICAL.get((ident, version))
    if not item or type(version) is not int:
        raise ValueError('模板不存在或版本已经变化，请刷新模板列表')
    return copy.deepcopy(item)


def public_catalog():
    return [{**{k: copy.deepcopy(v) for k, v in t.items() if k not in ('renderer', 'system_preset')},
             'description':DESCRIPTIONS[t['id']]} for t in CATALOG]
