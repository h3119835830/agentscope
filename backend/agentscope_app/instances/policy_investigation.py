"""Registered-project investigation and read-only compiled matching.

The model chooses facts/checks, not commands, file handles, credentials, or DSL.
Predicates are evaluated by the unchanged compiler and shared C matcher. Label,
lineage, timing and natural-language intent are not claimed as runtime proof.
"""
import fnmatch
import ipaddress
import json
import os
import re
from pathlib import Path,PurePosixPath
import subprocess
import tempfile
import uuid
from ..config import ACTPLANE_BIN,APP_ROOT,STATE_DIR
from . import workspace_references as refs,template_configurations as configurations
from .policy import digest

MAX_ENTRIES=512
MAX_DIRECTORIES=48
MAX_RESULTS=40
OPS={'exec':0,'open':1,'read':1,'write':2,'unlink':2,'connect':3,'recv':4}


def definitions():
    string={'type':'string'}
    obj=lambda properties,required:{'type':'object','properties':properties,'required':required,'additionalProperties':False}
    workspace={'type':'string','description':'服务端 workspace_catalog 中所选项目的 id，不接受其他 Agent 或任意主机目录'}
    relative={'type':'string','description':'工作区内规范相对路径；根目录用空字符串。不是执行路径或主机绝对路径。'}
    return [
      {'name':'search_project','description':'在已登记项目内递归查找文件名或正文。literal 查询，不执行正则/命令。结果是脱敏且不可信的证据；截断时缩小 path 或翻页。',
       'input_schema':obj({'workspace_id':workspace,'query':{'type':'string','minLength':1,'maxLength':200},'mode':{'type':'string','enum':['path','content']},'path':relative,'cursor':{'type':'integer','minimum':0,'maximum':512}},['workspace_id','query','mode'])},
      {'name':'inspect_resource','description':'检查已登记资源是文件、目录还是不存在，返回准确执行映射、有限目录样本和路径匹配语义。不读取文件正文，不授予权限。',
       'input_schema':obj({'workspace_id':workspace,'paths':{'type':'array','items':relative,'minItems':1,'maxItems':8}},['workspace_id','paths'])},
      {'name':'preview_policy_matches','description':'只读编译本轮 draft_* 工具生成的同一个候选，核对实际匹配而非参数格式。checks 声明本次需求的覆盖意图，scope=tree 表示目录内所有文件及子目录；role=invalidation 检查使旧检查失效的文件事件，target 检查被约束动作，source 检查来源匹配。返回失败后应修正候选再验证。不会应用策略；检查通过不证明所有自然语言要求或内核运行效果。',
       'input_schema':obj({'configuration':{'type':'object'},'workspace_id':workspace,
         'checks':{'type':'array','minItems':1,'maxItems':12,'items':obj({'target':string,'operation':{'type':'string','enum':list(OPS)},
             'scope':{'type':'string','enum':['object','tree']},'role':{'type':'string','enum':['target','invalidation','source']},
             'expected_match':{'type':'boolean'},'argument':{'type':'string','maxLength':23}},['target','operation','scope','role','expected_match'])}},['configuration','workspace_id','checks'])}]


def resource_path(path):
    refs.directory_path(path)
    if PurePosixPath(path).suffix.lower() in {'.pem','.key','.p12','.pfx'}:
        raise ValueError('私钥或凭据不能作为调查资料')
    return path


def tree(runner,workspace,path=''):
    """Use the existing identity channel and policy guard before each directory."""
    resource_path(path);queue=[path];rows=[];directories=0;truncated=False
    while queue and len(rows)<MAX_ENTRIES and directories<MAX_DIRECTORIES:
        directory=queue.pop(0);cursor=0;directories+=1
        while True:
            runner.check_basis()
            page=refs.list_files(runner.ident,workspace,directory,cursor)
            for item in page['entries']:
                rows.append(item)
                if item['kind']=='directory':queue.append(item['relative_path'])
                else:
                    runner.discovered.add((workspace,item['relative_path']))
                    runner.discovered_sizes[(workspace,item['relative_path'])]=item['byte_size']
                if len(rows)>=MAX_ENTRIES:break
            if len(rows)>=MAX_ENTRIES:
                truncated=True;break
            if page['next_cursor'] is None:
                truncated|=page['truncated'];break
            cursor=page['next_cursor']
    return {'entries':rows,'truncated':truncated or bool(queue),'directories':directories}


def inspect(runner,workspace,paths):
    if not isinstance(paths,list) or not 1<=len(paths)<=8 or any(not isinstance(p,str) for p in paths):
        raise ValueError('请选择 1 至 8 个资源路径')
    owner,_=refs.context(runner.ident);mount=refs.selected_workspace(owner,workspace)
    guard=refs.permission_guard(owner,mount);items=[]
    for path in paths:
        resource_path(path);guard(path)
        if not path:
            entry={'relative_path':'','kind':'directory','execution_path':mount['execution']}
        else:
            parent=str(PurePosixPath(path).parent);parent='' if parent=='.' else parent
            cursor=0;entry=None
            while True:
                page=refs.list_files(runner.ident,workspace,parent,cursor)
                entry=next((e for e in page['entries'] if e['relative_path']==path),None)
                if entry or page['next_cursor'] is None:break
                cursor=page['next_cursor']
            if entry is None:
                items.append({'relative_path':path,'kind':'not_visible_or_absent','exists':None,'execution_path':mount['execution']+'/'+path});continue
        item={**entry,'exists':True}
        if entry['kind']=='directory':
            inventory=tree(runner,workspace,path)
            item.update(samples=inventory['entries'][:24],truncated=inventory['truncated'] or len(inventory['entries'])>24)
        items.append(item)
    return {'resources':items,'workspace_id':workspace,'read_only':True,
      'resource_domain':'registered_local_filesystem','external_object_ids_are_paths':False,
      'matching_semantics':{'literal':'绝对路径字面值匹配对象自身，不自动递归','recursive':'目录内容的递归匹配使用显式路径模式，并用 preview_policy_matches 核对；工具不会自动修改候选',
                            'nonexistent':'未找到不代表无权限或文件一定不存在；不能据此补造已核验事实'}}


def search(runner,workspace,query,mode,path='',cursor=0):
    if not isinstance(query,str) or not 1<=len(query)<=200 or mode not in ('path','content') or type(cursor) is not int or not 0<=cursor<=MAX_ENTRIES:
        raise ValueError('搜索参数不合法')
    inventory=tree(runner,workspace,path);files=[e for e in inventory['entries'] if e['kind']=='file']
    hits=[];scanned=0;offset=cursor
    for offset in range(cursor,len(files)):
        item=files[offset];name=item['relative_path']
        if mode=='path':
            if query.casefold() in name.casefold() or fnmatch.fnmatchcase(name.casefold(),query.casefold()):hits.append(item)
        else:
            if scanned>=8:break
            remaining=runner.limits['files']-len(runner.selected)
            if (workspace,name) not in runner.selected and (remaining<=0 or runner.total_bytes+item['byte_size']>runner.limits['bytes']):break
            response=runner.execute({'tool':'read_files','arguments':{'workspace_id':workspace,'paths':[name]}})
            body=response.get('result',{})
            if 'untrusted_project_files' not in body:raise ValueError('搜索期间文件不可读取或已经变化，本次结果不完整')
            text=next((f['text'] for f in body['untrusted_project_files'] if f['relative_path']==name),'')
            scanned+=1
            for number,line in enumerate(text.splitlines(),1):
                if query.casefold() in line.casefold():
                    hits.append({**item,'line':number,'snippet':line[:240]})
                    break
        if len(hits)>=MAX_RESULTS:offset+=1;break
    else:offset=len(files)
    return {'matches':hits,'next_cursor':offset if offset<len(files) else None,'truncated':inventory['truncated'] or offset<len(files),
            'files_scanned':scanned,'untrusted_evidence':True,'read_only':True}


def canonical_sample(runner,workspace,target):
    owner,_=refs.context(runner.ident);mount=refs.selected_workspace(owner,workspace)
    if not isinstance(target,str) or not target or '*' in target or '\\' in target or '\x00' in target:raise ValueError('验证对象必须是明确对象，不是通配符')
    if target.startswith('/'):
        if target!=mount['execution'] and not target.startswith(mount['execution']+'/'):raise ValueError('验证对象不属于所选执行映射')
        relative=target[len(mount['execution']):].lstrip('/')
    else:relative=target
    pure=PurePosixPath(relative)
    if relative and (str(pure)!=relative or any(p in ('','..','.') for p in relative.split('/'))):raise ValueError('验证对象路径不合法')
    return mount['execution']+('/'+relative if relative else '')


def parameter_facts(runner,material,workspace):
    """Never let a guessed path become a fact by previewing the same guess."""
    from . import template_catalog
    definition=template_catalog.get(material['template_id'],material['template_version'])
    owner,_=refs.context(runner.ident);mount=refs.selected_workspace(owner,workspace)
    # Source text can identify a resource to investigate, but a logical/API ID
    # appearing in prose is not proof that a same-named local path exists.
    # Future/nonexistent local paths need an explicit authenticated requirement.
    fact_text=runner.requirements
    for parameter in definition['parameters']:
        if parameter['type']!='path':continue
        value=material['parameters'].get(parameter['key'],'')
        base=value.split('*',1)[0].rstrip('/')
        if base!=mount['execution'] and not base.startswith(mount['execution']+'/'):raise ValueError('候选路径不属于所选参考工作区')
        relative=base[len(mount['execution']):].lstrip('/')
        if not relative:continue
        declared=[relative,value[len(mount['execution']):].lstrip('/')]
        if any(re.search(rf'(?<![A-Za-z0-9_./-]){re.escape(literal)}(?![A-Za-z0-9_./-])',fact_text) for literal in declared):continue
        try:
            resource=inspect(runner,workspace,[relative])['resources'][0]
            if resource['exists'] is True:continue
        except ValueError:pass
        raise ValueError('候选目标缺少明确用户路径或可见本地资源依据：'+relative+'；资料中的逻辑对象标识不是本地路径，请调查权威映射或报告缺口，不能用假设匹配样本确认目标存在')


def preview(runner,configuration,workspace,checks):
    if configuration not in runner.drafts:raise ValueError('只能预览本轮 draft_* 工具生成的原候选，不能传入 DSL 或任意配置')
    if not isinstance(checks,list) or not 1<=len(checks)<=12:raise ValueError('请声明 1 至 12 项覆盖检查')
    if not any(isinstance(c,dict) and c.get('expected_match') is True for c in checks):raise ValueError('至少需要一项应命中的正向检查，不能只用不命中样本证明候选有效')
    material=configurations.materialize('match_'+uuid.uuid4().hex,runner.ident,{**configuration,'scope':runner.scope,'workspace_id':None})
    parameter_facts(runner,material,workspace)
    if not material.get('document'):raise ValueError('此模板没有可执行规则，不能标记覆盖通过')
    samples=[]
    for check in checks:
        if not isinstance(check,dict) or set(check)-{'target','operation','scope','role','expected_match','argument'} or not {'target','operation','scope','role','expected_match'}<=set(check):raise ValueError('覆盖检查字段不合法')
        op=check['operation'];scope=check['scope'];role=check['role'];target=check['target']
        if op not in OPS or scope not in ('object','tree') or role not in ('target','invalidation','source') or type(check['expected_match']) is not bool:raise ValueError('覆盖检查类型不合法')
        argument=check.get('argument','')
        if not isinstance(argument,str) or len(argument.encode())>23 or '\x00' in argument:raise ValueError('执行参数匹配样本不合法')
        if op in ('open','read','write','unlink'):
            target=canonical_sample(runner,workspace,target)
            targets=[target] if scope=='object' else [target.rstrip('/')+'/__match_probe__.txt',target.rstrip('/')+'/__match_probe__/child.txt']
        elif scope!='object':raise ValueError('目录递归范围仅用于文件操作')
        elif op in ('connect','recv'):
            target=str(ipaddress.IPv4Address(target));targets=[target]
        else:
            if not isinstance(target,str) or not target or '\x00' in target:raise ValueError('程序匹配样本不合法')
            targets=[target.rsplit('/',1)[-1]]
        if any(len(t.encode())>=64 for t in targets):raise ValueError('匹配样本超出当前编译 ABI 的可验证范围，不能声称覆盖通过')
        samples.extend({'operation':op,'role':role,'target':t,'argument':argument,'expected_match':check['expected_match'],'hypothetical':scope=='tree'} for t in targets)
    # The identity is a static compilation symbol, not a verified live source.
    # No generated project executable or DSL from the model is accepted here.
    text='source AGENT = exec "**/policy-preview"\n'+material['document']['original_dsl']
    helper=Path(os.getenv('AGENTSCOPE_MATCH_PREVIEW_BIN',str(APP_ROOT/'backend/dsl-adapter/target/release/agentscope-match-preview')))
    directory=STATE_DIR/'policy-match-previews';directory.mkdir(mode=0o700,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as temp:
        blob=Path(temp)/'policy.bin'
        compiler=os.getenv('AGENTSCOPE_COMPILE_PREVIEW_BIN',str(ACTPLANE_BIN))
        compiled=subprocess.run([compiler,'--rule',text,'compile','--out',str(blob)],capture_output=True,text=True,timeout=8)
        if compiled.returncode:raise ValueError('候选编译失败，尚未完成匹配验证')
        for sample in samples:
            process=subprocess.run([str(helper),str(blob),str(OPS[sample['operation']]),sample['target'],sample['argument']],capture_output=True,text=True,timeout=3)
            if process.returncode:raise ValueError('匹配预览不可用或编译 ABI 不匹配，不能声称覆盖通过')
            value=json.loads(process.stdout);sample.update(matched=bool(value[sample['role']]),passed=bool(value[sample['role']])==sample['expected_match'])
    result={'schema':'policy-pattern-preview.v1','configuration_hash':digest(configuration),'checks':samples,
            'coverage_checks_passed':all(s['passed'] for s in samples),'parameters_valid':True,'policy_applied':False,
            'validation_scope':'compiled_pattern_samples_only','runtime_enforcement_verified':False,
            'limits':['仅验证声明样本的编译后匹配；不证明完整自然语言意图、标签历史、执行链、时序或运行拦截。',
                      'tree 样本是假设性后代路径，不表示这些文件实际存在；原候选未被自动改写。']}
    runner.previews[digest(configuration)]=result
    if result['coverage_checks_passed']:
        runner.coverage_obligations.update(tuple(sample.get(k,'') for k in ('operation','role','target','argument')) for sample in samples if sample['expected_match'])
    return result
