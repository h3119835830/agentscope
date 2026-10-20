"""Server-owned execution boundaries and recorded synthetic runtime evidence.

This is capability presentation/validation, never a receipt that a live Agent is
protected. Historical definitions and configuration hashes stay immutable.
"""
import copy
import json
from pathlib import Path
from .policy import digest
from . import git_templates

_EVIDENCE=Path(__file__).with_name('template_runtime_acceptance.json')
_LABEL_EVIDENCE=Path(__file__).with_name('label_runtime_acceptance.json')
def contract(definition):
    keys=('id','renderer','operation','system_preset','command','fixed_fields','dsl_clause_template','allowed_operations','allowed_effects','label_contract','source_label')
    value={k:copy.deepcopy(definition[k]) for k in keys if k in definition}
    value['parameters']=[{k:copy.deepcopy(p[k]) for k in ('key','type','options','minimum','maximum') if k in p} for p in definition['parameters']]
    return digest(value)

def evidence(definition):
    for source in (_LABEL_EVIDENCE,_EVIDENCE):
        if not source.exists():continue
        report=json.loads(source.read_text())
        row=report.get('templates',{}).get(definition['id'])
        if row and row.get('contract_hash')==contract(definition):
            return {**row,'date':report['date'],'kernel_release':report['kernel_release'],'binary_sha256':report['binary_sha256']}
    return None

def presentation(definition):
    previous=git_templates.presentation(definition)
    kind=definition['renderer']
    if kind=='system':
        from .policy_library import CATALOG
        preset=next(p for p in CATALOG if p['id']==definition['system_preset'])
        mode=preset['mode']
        kind={'exec':'exec','endpoint':'endpoint','flow':'flow','remote':'remote'}.get(mode,'file')
    else:mode=None
    descriptions={
      'file':(['按配置路径、文件名或后缀匹配指定文件访问；block 在文件操作前拒绝。','notify 记录并继续；kill 终止命中进程。'],
              ['按文件内容识别秘密、按用户意图判断资料用途。','修改与删除独立授权：当前两者共用执行访问组。']),
      'boundary':(['在指定文件变更范围内执行限制，保留匹配例外的原有权限。'],
                  ['例外不授予新权限；修改与删除不能分别授权。']),
      'lineage':(['按已观测的生成程序执行链限制文件变更。'],
                 ['校验具体脚本、参数、签名或生成内容是否正确。']),
      'exec':(['按程序匹配启动事件；block 可事前拒绝整个程序。'],
              ['按命令行参数选择性事前阻断；程序名不能代替脚本内容校验。']),
      'endpoint':(['按 IPv4 地址、地址前缀或全部目标匹配新连接。'],
                  ['按域名、端口或 HTTP 内容控制；IPv6 和已有连接的全部发送。']),
      'flow':(['观测敏感文件来源并传播标签，对带标签进程的新 IPv4 连接执行限制。'],
              ['按发送正文判断是否泄密；覆盖全部外发通道和已有连接发送。']),
      'remote':(['按已观测的网络来源标签匹配后续指定程序启动。'],
                ['判断脚本是否恶意、校验下载内容或签名、精确识别 shell 管道。']),
    }
    if previous:result=previous
    else:
        supported,unsupported=descriptions[kind]
        result={'status':'limited','applicable':True,'event_type':'跨事件' if kind in ('lineage','flow','remote') else '单事件',
                'supported':supported,'unsupported':unsupported,
                'boundary':['仅作用于已受控的 Agent 及其后代执行域；共享进程中的会话共享策略。','保存、批准、加载和实际拦截是不同状态；以下实测不代表当前实例已启用。','kill 只保证命中后终止，可能已有操作副作用；网络实测中接收端已接受连接，不能等同于事前 block。']}
        if kind=='flow':result['boundary'].append('共享进程的敏感标签可能影响后续正常连接，包括模型请求。')
        if mode in ('suffix','filename','tail','flow'):result['boundary'].append('文件后缀匹配需运行引擎能力核验；匹配值最多 63 字节。')
    if definition['id'] in git_templates.RETIRED:
        result.update(applicable=False,status='legacy')
        result['boundary']=['历史模板只读；不能新增、编辑或重新应用。已生效策略保留，可走审批停用。']
        if definition['id']=='RQ1-CHECK':result['unsupported']+=['旧检查仅要求检查程序执行事件，不校验成功退出码；默认 block 不支持。请使用新版 Git 检查模板。']
    proof=evidence(definition)
    result['verification']={'state':'rejected','date':proof['date'],'cases':proof['cases'],'effects':[], 'scope':'已实测仅保存草案，单项、批量提交及重新校验均被拒绝；没有运行拦截能力。'} if proof and kind=='unsupported' else {'state':'verified','date':proof['date'],'cases':proof['cases'],'effects':proof['effects'],
                            'scope':'合成文件、本地仓库和本机接收端；核对命中事件、子进程结果及实际副作用。'} if proof else {'state':'not_verified','scope':'尚无匹配当前模板执行合同的真实运行验收记录。'}
    return result

def ensure_editable(definition):
    if definition['id'] in git_templates.RETIRED:
        raise ValueError('历史模板已停用新建与编辑入口，请选择对应的新版 Git 模板；原配置和审批记录保留。')

def ensure_applicable(definition,effect,*,removing=False):
    if removing:return
    if definition['id'] in git_templates.RETIRED:
        raise ValueError('历史模板不能重新提交或应用，请选择新版 Git 模板；已生效策略可审批停用。')
    git_templates.ensure_applicable(definition)
    proof=evidence(definition)
    if proof and effect not in proof['effects']:
        raise ValueError('此模板的所选动作尚未通过真实运行验收，不能提交或应用。')
