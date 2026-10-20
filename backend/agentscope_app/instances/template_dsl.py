"""Server-owned DSL patterns and read-only previews; never an approval or load."""
import copy
import json
import re


def render_clause(pattern, parameters):
    def value(match):
        key=match[1]
        if key not in parameters:raise ValueError('模板 DSL 参数未声明：'+key)
        v=parameters[key]
        return str(v) if key in ('effect','exit_code') else json.dumps(v,ensure_ascii=False)
    # One pass: text contained in a parameter is never interpreted as a template.
    return re.sub(r'\{\{([a-z_]+)\}\}',value,pattern)


def fixed_git_definition(base):
    if base['renderer'] not in ('git-command','git-check','git-tokens'):
        return None
    definition=copy.deepcopy(base)
    definition['contract']='git-fixed-command.v1'
    definition['fixed_fields']={'program':'git'}
    if base.get('command'):definition['fixed_fields']['command']=base['command']
    definition['parameters']=[p for p in definition['parameters'] if p['key']!='program']
    token='"'+base['command']+'"' if base.get('command') else '{{tokens}}'
    definition['dsl_clause_template']='{{effect}} exec "git" '+token+' if AGENT'
    if base['renderer']=='git-check':
        definition['dsl_clause_template']+=' unless after exec {{checker}} exits {{exit_code}} since write {{target}}'
    definition['disabled_effects']={'block':'ActPlane 在执行后观察 Git 参数，暂不支持按 commit/push 参数事前 block；kill 是命中后终止。'}
    return definition


def verify_git_save(definition, previous=None, parameters=None):
    if definition['renderer'] not in ('git-command','git-check','git-tokens'):return
    if definition.get('contract')=='git-fixed-command.v1':return
    if previous is None:
        raise ValueError('Git 模板已固定命令，请刷新并选择新版模板；不能用历史版本新增配置。')
    if (parameters or {}).get('program')!=previous['parameters'].get('program'):
        raise ValueError('历史 Git 配置的命令不能修改；请选择新版模板保存新版本。')


def preview_definition(definition, parameters=None, effect=None, reason=None):
    from .template_configurations import normalize_parameter,render_document
    t=copy.deepcopy(definition)
    values=parameters if parameters is not None else {p['key']:p['default'] for p in t['parameters']}
    if not isinstance(values,dict) or set(values)-{p['key'] for p in t['parameters']}:
        raise ValueError('DSL 预览只能填写模板声明的参数，不能修改固定命令或 DSL')
    if effect is not None:
        if effect not in t.get('allowed_effects',('block','notify','kill')):raise ValueError('此模板不支持所选处置动作')
        t['effect']=effect
    normalized={};missing=[];errors=[]
    for p in t['parameters']:
        v=values.get(p['key'],p['default'])
        if v in ('',None) or v==[]:
            missing.append(p['label']);normalized[p['key']]='{{'+p['key']+'}}'
        else:
            try:normalized[p['key']]=normalize_parameter(p,v,t)
            except ValueError as exc:
                errors.append(str(exc));normalized[p['key']]='{{'+p['key']+'}}'
    feedback=reason or t['reason']
    if not isinstance(feedback,str) or len(feedback)>600 or re.search(r'[\x00-\x1f]',feedback):raise ValueError('反馈说明无效')
    if t['renderer']=='unsupported':
        return {'state':'unsupported','dsl':None,'missing':missing,'errors':errors,'preview_only':True}
    # Missing multi-value inputs are rendered as one explicit placeholder clause.
    for p in t['parameters']:
        if p['type'] in ('operations','choices') and isinstance(normalized[p['key']],str):normalized[p['key']]=[normalized[p['key']]]
    sentinel=None
    if t['renderer']=='system' and normalized.get('values')=='{{values}}':
        from .policy_library import CATALOG
        mode=next(p['mode'] for p in CATALOG if p['id']==t['system_preset'])
        sentinel={'suffix':'.__preview_values__','flow':'.__preview_values__','endpoint':'127.0.0.254',
                  'exact':'/__preview_values__','directory':'/__preview_values__'}.get(mode,'__preview_values__')
        normalized['values']=sentinel
    # Invalid action/operation selections must never produce an apparently valid DSL.
    if errors:return {'state':'invalid','dsl':None,'missing':missing,'errors':errors,'preview_only':True}
    document,*_=render_document(t,normalized,'preview',t['name'],feedback)
    text=document['original_dsl']
    if sentinel:text=text.replace(sentinel,'{{values}}')
    return {'state':'incomplete' if missing else 'complete','dsl':text,'missing':missing,'errors':[], 'preview_only':True}


def preview(ident, body):
    from . import template_catalog
    t=template_catalog.get(ident,body['template_version'])
    if t.get('label_contract')=='explicit-secret-sources.v1' and body.get('scope_id'):
        from .template_configurations import materialize
        try:
            payload=materialize('preview',body['scope_id'],{
                'template_id':ident,'template_version':t['version'],'scope':'system' if body['scope_id']=='system' else 'agent',
                'name':t['name'],'reason':body.get('reason') or t['reason'],'parameters':body['parameters'],
                'label_source_refs':body.get('label_source_refs',[])},preview_effect=body.get('effect'))
            return {'state':'complete','dsl':payload['document']['original_dsl'],'label_sources':payload['label_sources'],
                    'errors':[],'missing':[],'preview_only':True,'template_id':ident,'template_version':t['version']}
        except ValueError as exc:
            return {'state':'invalid','dsl':None,'errors':[str(exc)],'missing':[],'preview_only':True}
    result=preview_definition(t,body.get('parameters'),body.get('effect'),body.get('reason'))
    return {**result,'template_id':ident,'template_version':t['version']}
