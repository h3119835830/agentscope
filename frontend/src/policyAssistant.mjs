import {bindGeneratedSource} from './policySources.mjs';
// The conversation is scoped to one exact registered Agent; generated artifacts have no application authority.
export const generationBusy=status=>['queued','running'].includes(status);
export const generationLabel=status=>({queued:'已排队',running:'正在生成',completed:'生成完成',partial:'部分完成',failed:'生成失败',cancelled:'已取消',interrupted:'已中断'})[status]||status;
export function assistantInput(text,target,previous=[],context=null){
 if(!target?.id||target.id==='system'||target.mode!=='controlled')throw Error('请选择受控 Agent。');
 if(text.trim().length<5||text.length>2000)throw Error('请填写 5–2000 字的策略需求。');
 const prior=previous.slice(-4).map(t=>{const p=t.kind==='template'?t.candidate?.presentation:null;return p?['已在对话中配置的候选（尚未应用）：'+p.name,...Object.entries(p.values||{}).map(([k,v])=>k+'：'+v),'触发操作：'+p.operation,'处置：'+p.effect,'反馈：'+p.reason].join('\n'):t.text;}).join('\n');
 return {text:[text.trim(),prior?'此前需求（本次需求为最新补充）：\n'+prior:''].filter(Boolean).join('\n\n'),enforcement_level:'per_event',context_requirement:context?'project':'self_contained',...(context?{agent_context:{instance_id:target.id,session_id:context.session_id,context_hash:context.context_hash}}:{})};
}
export function generatedHandoff(result,target,id=crypto.randomUUID()){
 if(!target?.id||target.id==='system'||target.mode!=='controlled')throw Error('请选择具体的受控 Agent。');
 const dsl=result.artifact?.actplane_dsl;
 if(!dsl?.trim())throw Error('此生成结果没有可导入的 DSL，请先补充需求。');
 const statement=result.record?.statement||{};
 const original_dsl=bindGeneratedSource(dsl,target);
 const name=(statement.text_zh||statement.text_original||'助手生成策略').slice(0,80);
 const metadata=Object.fromEntries([...original_dsl.matchAll(/^\s*rule\s+([\w-]+):/gm)].map(m=>[m[1],{statement:statement.text_zh||statement.text_original||name,context_requirement:statement.context_requirement||'self_contained',context_reason:'策略助手生成；导入前请核对本 Agent 的范围。'}]));
 return {id,targetId:target.id,scopeType:'agent',templateId:'策略助手',caveat:'生成结果仅作为候选；需在目标 Agent 编辑器中重新校验，并由你确认应用。',document:{id,name,original_dsl,metadata}};
}
