"""Published templates projected as typed draft tools; invocation never applies."""
import re
import uuid
from . import template_catalog as catalog

def parameter_schema(parameter, template):
    kind=parameter['type'];description=parameter['label']
    if parameter.get('help'):description+='。'+parameter['help']
    schema={'type':'string','description':description}
    if kind=='integer':schema.update(type='integer',minimum=parameter['minimum'],maximum=parameter['maximum'])
    elif kind in ('operations','choices'):
        schema.update(type='array',items={'type':'string','enum':parameter.get('options',template.get('allowed_operations',['write','unlink']))},minItems=1,uniqueItems=True)
    elif kind=='effect':schema['enum']=template.get('allowed_effects',['block','notify','kill'])
    elif kind=='path':
        schema['description']+='。这是已登记本地执行路径的匹配模式，不是自然语言目录选择器、URL 或外部 API 对象 ID。绝对路径字面值只匹配对象自身；目录内容须显式使用递归模式。可用 inspect_resource 确认对象，用 preview_policy_matches 核验实际覆盖。'
    return schema

def definitions(scope='agent'):
    out=[]
    for t in catalog.public_catalog():
        if scope not in t['scopes'] or t.get('retired') or t.get('assistant_alias'):continue
        props={p['key']:parameter_schema(p,t) for p in t['parameters']}
        out.append({'name':'draft_'+re.sub('[^a-zA-Z0-9_]','_',t['id']).lower(),
          'description':t['name']+'。'+t.get('description',t['summary'])+' 仅生成待审批候选；参数校验不是覆盖验证，提交前调用 preview_policy_matches。',
          'template_id':t['id'],'template_version':t['version'],'display_name':t['name'],
          'applicable_when':{'operation':t['operation'],'effect':t['effect'],'stages':['preflight','runtime'],
                             'condition':t.get('description',t['summary'])},
          'input_schema':{'type':'object','properties':{'name':{'type':'string','minLength':1,'maxLength':120},
                 'parameters':{'type':'object','properties':props,'required':list(props),'additionalProperties':False},
                 'reason':{'type':'string','maxLength':600}},'required':['name','parameters'],'additionalProperties':False}})
    return out

def search(query,scope='agent'):
    if not isinstance(query,str) or not 1<=len(query)<=2000:raise ValueError('请提供模板相关性查询')
    terms=set(re.findall(r'[a-zA-Z0-9_-]+|[\u4e00-\u9fff]{1,2}',query.lower()))
    ranked=[]
    for t in definitions(scope):
        text=t['display_name']+' '+t['description']+' '+t['template_id'].lower()
        ranked.append((sum(term in text for term in terms),t))
    return [t for _,t in sorted(ranked,key=lambda x:(-x[0],x[1]['name']))[:8]]

def instantiate(instance_id,tool,args,scope='agent'):
    from .template_configurations import materialize
    if not isinstance(args,dict) or set(args)-{'name','parameters','reason'} or not {'name','parameters'}<=set(args):
        raise ValueError('模板工具参数不符合发布合同')
    definition=next((t for t in definitions(scope) if t['name']==tool),None)
    if not definition:raise ValueError('模板工具不存在或已失效')
    item={'template_id':definition['template_id'],'template_version':definition['template_version'],**args}
    result=materialize('preview_'+uuid.uuid4().hex,instance_id,{**item,'scope':scope,'workspace_id':None})
    return {'configuration':item,'validated':True,'validation_scope':'template_parameters_only','coverage_verified':False,'applied':False,'name':result['name'],
            'requested_operations':result['requested_operations'],'effect':result['effect'],'execution_support':result.get('execution_support',{})}
