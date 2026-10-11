import {agentPolicySource,sourceDeclarations} from './policySources.mjs';
// Browser-side candidate construction only. Compilation and authority stay in the control API.
export function templateDefaults(template,target){
 const root=target?.resources?.[0]?.replace(/\/$/,'');
 return Object.fromEntries(template.parameters.map(p=>[p.key,p.key==='target'&&root&&p.value.startsWith('/workspace/')?root+p.value.slice('/workspace'.length):p.value]));
}
export function materializeTemplate(template,values,goal='',id=crypto.randomUUID(),sources=null){
 if(!['agent','system'].includes(template.scope_type))throw Error('未知策略类型。');
 for(const parameter of template.parameters){
  const value=values[parameter.key];
  if(typeof value!=='string'||!value.trim()||/[\u0000-\u001f]/.test(value))throw Error('请填写'+parameter.label+'，不能包含控制字符。');
  if(parameter.key==='target'&&(!value.startsWith('/')||value.split('/').includes('..')))throw Error('保护对象须使用绝对路径，不能包含 ..。');
  if(/["\\]/.test(value))throw Error('DSL 参数不能包含引号或反斜杠。');
  if(value.length>1000)throw Error('参数过长。');
 }
 if(typeof template.reason!=='string'||!template.reason.trim()||/[\u0000-\u001f"\\]/.test(template.reason))throw Error('反馈说明不能包含引号、反斜杠或控制字符。');
 if(goal.length>1000)throw Error('策略说明不能超过 1000 字。');
 const fill=line=>line.replace(/\{\{(\w+)\}\}/g,(_,key)=>{if(!Object.hasOwn(values,key))throw Error('缺少模板参数');return JSON.stringify(values[key]);});
 const rule=(template.rule_id||template.id).toLowerCase().replace(/[^a-z0-9_-]/g,'-');
 const text=['# '+template.name,sourceDeclarations(sources),...(template.sources||[]).map(fill),'',`rule ${rule}:`,...template.clauses.map(line=>'  '+fill(line)),'  because '+JSON.stringify(template.reason)].join('\n');
 return {id,name:template.name,original_dsl:text,metadata:{[rule]:{statement:template.summary,context_requirement:template.parameters.length?'project':'self_contained',context_reason:template.parameters.length?('已指定保护对象。'+goal).trim():''}}};
}
export function createHandoff(template,values,goal,target,id=crypto.randomUUID()){
 if(template.scope_type!=='agent'||!target?.id||target.id==='system'||target.mode!=='controlled')throw Error('请选择具体的受控 Agent；仅观测连接不能导入策略。');
 return {id,targetId:target.id,scopeType:'agent',templateId:template.id,evidenceUid:template.uid,caveat:template.caveat,document:materializeTemplate(template,values,goal,id,[agentPolicySource(target)])};
}
export function createSystemHandoff(template,values,goal='',id=crypto.randomUUID(),sources=null){
 if(template.scope_type!=='system')throw Error('请选择系统配置项。');
 return {id,targetId:'system',scopeType:'system',templateId:template.id,caveat:template.caveat,document:materializeTemplate(template,values,goal,id,sources)};
}
export function appendHandoff(data,candidate,scopeId){
 if(candidate.scopeType!==(scopeId==='system'?'system':'agent')||candidate.targetId!==scopeId||data.scope_id!==scopeId)throw Error('候选与当前策略范围不一致，请重新选择目标。');
 const documents=structuredClone(data.documents||[]),doc=structuredClone(candidate.document);
 if(documents.some(d=>d.id===doc.id))throw Error('该候选文档已存在，请重新创建。');
 documents.push(doc);
 if(documents.length>20)throw Error('最多保存 20 个 DSL 文档。');
 if(new TextEncoder().encode(documents.map(d=>d.original_dsl).join('')).length>50000)throw Error('全部 DSL 合计不能超过 50000 字节。');
 return documents;
}
export const previewMatches=(preview,checked,documents,stale=false)=>!stale&&preview?.state==='pending'&&(!preview.approval||preview.approval.can_apply)&&checked===JSON.stringify(documents);
