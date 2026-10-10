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
        if not isinstance(raw,dict) or set(raw)-{'id','name','original_dsl','metadata'}: raise ValueError('DSL 文档字段不合法')
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
        out.append(dict(id=ident,name=name or ident,original_dsl=text,metadata=metadata));ids.add(ident)
    if size>50000: raise ValueError('全部导入 DSL 合计不能超过 50000 字节')
    return sorted(out,key=lambda d:d['id'])

def fingerprint(documents,resources): return digest({'documents':documents,'resources':resources}) if documents else None

def adapter_binary():
    return os.getenv('AGENTSCOPE_DSL_ADAPTER',str(Path(__file__).parent/'dsl-adapter/target/release/agentscope-dsl-adapter'))

def prepare(documents,resources):
    results=[]
    for doc in documents:
        ns='d'+digest([doc['scope_id'],doc['id']])[:12]
        try:
            result=subprocess.run([adapter_binary()],input=json.dumps({'dsl':doc['original_dsl'],'namespace':ns,'resources':resources,'locked':doc['scope_id']=='system'}),capture_output=True,text=True,timeout=8)
            value=json.loads(result.stdout)
        except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError) as e: raise ValueError('ActPlane DSL 解析适配器不可用') from e
        if result.returncode or not value.get('ok'): raise ValueError(value.get('error','DSL 解析失败'))
        parsed=value['document']
        if set(doc['metadata'])-{r['rule_name'] for r in parsed['rules']}: raise ValueError('策略说明包含 DSL 中不存在的 rule')
        for meta in doc['metadata'].values():
            if meta.get('context_requirement','self_contained')!='self_contained' and not meta.get('context_reason','').strip():
                raise ValueError('project / task 策略必须填写已解决的上下文依据，再重新校验')
        results.append({**doc,**parsed})
    return results
