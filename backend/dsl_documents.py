"""Shared, bounded adapter to the existing ActPlane AST. No execution authority."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def canonical_documents(values):
    if not isinstance(values,list) or len(values)>20: raise ValueError('最多导入 20 个 DSL 文档')
    out=[]; ids=set(); size=0
    for raw in values:
        if not isinstance(raw,dict) or set(raw)-{'id','name','original_dsl','metadata','generation_binding','managed_identity','label_sources'}: raise ValueError('DSL 文档字段不合法')
        ident=raw.get('id',''); text=raw.get('original_dsl',''); name=raw.get('name','')
        if not isinstance(ident,str) or not ident or len(ident)>80 or not all(c.isascii() and (c.isalnum() or c in '_-') for c in ident) or ident in ids: raise ValueError('DSL 文档 ID 不合法或重复')
        if not isinstance(text,str) or not text.strip() or '\x00' in text: raise ValueError('请填写 UTF-8 DSL 文本')
        if not isinstance(name,str) or len(name)>120: raise ValueError('文档名称过长')
        size+=len(text.encode())
        metadata=raw.get('metadata',{})
        if not isinstance(metadata,dict) or len(metadata)>100: raise ValueError('策略说明必须按 rule 名称登记')
        for key,value in metadata.items():
            if not isinstance(key,str) or len(key)>160 or not isinstance(value,dict) or set(value)-{'statement','context_requirement','context_reason'}: raise ValueError('策略说明字段不合法')
            if value.get('context_requirement','self_contained') not in ('self_contained','project','task'): raise ValueError('上下文需求不合法')
            if any(not isinstance(value.get(k,''),str) or len(value.get(k,''))>2000 for k in ('statement','context_reason')): raise ValueError('策略说明过长')
        doc=dict(id=ident,name=name or ident,original_dsl=text,metadata=metadata)
        if 'label_sources' in raw:
            sources=raw['label_sources']
            if not isinstance(sources,list) or not 1<=len(sources)<=16:
                raise ValueError('标签来源快照格式不合法')
            for source in sources:
                if not isinstance(source,dict) or set(source)!={'id','version','label','scope_id','matcher','value','patterns','snapshot_hash'}:
                    raise ValueError('标签来源快照字段不合法')
                if source['label']!='SECRET' or type(source['version']) is not int or source['version']<1:
                    raise ValueError('标签来源版本或标签不合法')
                if any(not isinstance(source[k],str) or len(source[k])>1000 for k in ('id','scope_id','matcher','value','snapshot_hash')):
                    raise ValueError('标签来源字段过长')
                if not isinstance(source['patterns'],list) or not 1<=len(source['patterns'])<=2 or any(not isinstance(p,str) or len(p.encode())>63 for p in source['patterns']):
                    raise ValueError('标签来源路径不合法')
                if digest({k:v for k,v in source.items() if k!='snapshot_hash'})!=source['snapshot_hash']:
                    raise ValueError('标签来源快照校验失败')
            doc['label_sources']=sources
        if 'managed_identity' in raw:
            if raw['managed_identity'] is not True:raise ValueError('托管身份标记不合法')
            doc['managed_identity']=True
        if 'generation_binding' in raw:
            binding=raw['generation_binding']
            if not isinstance(binding,dict) or set(binding)!={'artifact_id','context_hash'} or not all(isinstance(v,str) and len(v)<=64 and v and all(c in '0123456789abcdef' for c in v) for v in binding.values()):raise ValueError('生成候选关联不合法')
            doc['generation_binding']=binding
        out.append(doc);ids.add(ident)
    if size>50000: raise ValueError('全部导入 DSL 合计不能超过 50000 字节')
    return sorted(out,key=lambda d:d['id'])

def fingerprint(documents,resources): return digest({'documents':documents,'resources':resources}) if documents else None

def adapter_binary():
    return os.getenv('AGENTSCOPE_DSL_ADAPTER',str(Path(__file__).parent/'dsl-adapter/target/release/agentscope-dsl-adapter'))

def prepare(documents,resources,agent_source=None,resource_views=None):
    results=[]
    for doc in documents:
        ns='d'+digest([doc['scope_id'],doc['id']])[:12]
        text=doc['original_dsl'];binding=None
        if doc.get('managed_identity'):
            import re
            if not agent_source or not re.fullmatch(r'\*\*/[a-zA-Z0-9_.-]{1,15}',agent_source):raise ValueError('此配置需要可信的受控 Agent 启动身份')
            if re.search(r'^\s*(?:source\s+AGENT\s*=|(?:declassify|endorse)\s+AGENT\b)',text,re.M):raise ValueError('AGENT 身份由受控启动流程管理，不能在文档中覆盖')
            binding={'label':'AGENT','pattern':agent_source,'basis':'broker-controlled-launch-profile'}
            text='source AGENT = exec '+json.dumps(agent_source)+'\n\n'+text
        try:
            result=subprocess.run([adapter_binary()],input=json.dumps({'dsl':text,'namespace':ns,'resources':resources,'resource_views':resource_views,'locked':doc['scope_id']=='system'}),capture_output=True,text=True,timeout=8)
            value=json.loads(result.stdout)
        except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError) as e: raise ValueError('ActPlane DSL 解析适配器不可用') from e
        if result.returncode or not value.get('ok'): raise ValueError(value.get('error','DSL 解析失败'))
        parsed=value['document']
        if binding:
            parsed['identity_binding']=binding
            for rule in parsed['rules']:
                rule['source_start_line']-=2;rule['source_end_line']-=2
        if set(doc['metadata'])-{r['rule_name'] for r in parsed['rules']}: raise ValueError('策略说明包含 DSL 中不存在的 rule')
        for meta in doc['metadata'].values():
            if meta.get('context_requirement','self_contained')!='self_contained' and not meta.get('context_reason','').strip():
                raise ValueError('project / task 策略必须填写已解决的上下文依据，再重新校验')
        results.append({**doc,**parsed})
    return results
