import React,{useEffect,useRef,useState} from 'react';
import PolicyRecordTable from './PolicyRecordTable.jsx';
import {agentName} from './agentInstancePresentation.mjs';
import PolicyAssistantResponse from './PolicyAssistantResponse.jsx';
import {attachmentTypes,readAttachments} from './policyConversationInput.mjs';
import './templateConfigurations.css';
const inputCache=new Map();
export default function TemplatePolicyAssistant({target,scope,workspaceId,referenceWorkspaceId,referenceWorkspaceName,stage='preflight',runtimeEventSeq,api,post,onApprovals,onConfiguration}){
 const runtime=stage==='runtime',selectedReference=!!referenceWorkspaceId,referenceLabel=referenceWorkspaceName||'所选参考工作区',identity=target.id+':'+scope+':'+(workspaceId||'')+':'+stage+':'+(referenceWorkspaceId||''),request=useRef(null),alive=useRef(true),fileInput=useRef(null);
 const [data,setData]=useState(null),[text,setText]=useState(inputCache.get(identity)||''),[attachments,setAttachments]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[legacy,setLegacy]=useState([]),[reading,setReading]=useState(false);
 const [fresh,setFresh]=useState(false);
 const path='/api/policy-templates?scope_id='+encodeURIComponent(target.id);
 async function load(){try{const value=await api(path);if(alive.current)setData(value);}catch(e){if(alive.current)setData(null);throw e;}}
 useEffect(()=>{alive.current=true;load().catch(e=>{if(alive.current)setError(e.message);});if(scope!=='system')api('/api/agent-instances/'+encodeURIComponent(target.id)+'/policy-drafts?'+new URLSearchParams({scope,...(workspaceId?{workspace_id:workspaceId}:{})})).then(v=>{if(alive.current)setLegacy(v.records||[]);}).catch(()=>{});return()=>{alive.current=false;};},[api,path,scope,workspaceId]);
 useEffect(()=>{inputCache.set(identity,text);},[identity,text]);
 const catalog=(data?.catalog||[]).filter(t=>t.scopes.includes(scope)),items=(data?.items||[]).filter(i=>i.scope===scope&&(i.workspace_id||null)===(workspaceId||null));
 async function attach(e){const files=[...e.target.files];e.target.value='';setReading(true);setError('');try{const value=await readAttachments(files,attachments);if(alive.current)setAttachments(value);}catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setReading(false);}}
 async function generate(e){e.preventDefault();if(busy||reading||!data||(!text.trim()&&!attachments.length))return;setBusy(true);setError('');try{
  const input={text:text.trim()||'请阅读附件，提取明确的安全约束并起草配置；缺少信息时请询问。',scope,workspace_id:workspaceId||null,
   reference_workspace_id:referenceWorkspaceId||null,stage,runtime_event_seq:runtimeEventSeq||null,
   context_mode:scope==='agent'?'auto':'none',materials:attachments,
   parent_request_id:!fresh&&history.at(-1)?.generation_basis?history.at(-1).request_id:null,
   conversation:[]};
  const fingerprint=JSON.stringify(input);if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,key:crypto.randomUUID()};
  const value=await post(scope==='system'?'/api/policy-template-configurations/generate':'/api/agent-instances/'+encodeURIComponent(target.id)+'/template-configurations/generate',{...input,...(scope==='system'?{scope_id:'system'}:{}),request_key:request.current.key});
  if(alive.current){await load();setText('');setFresh(false);request.current=null;}
 }catch(e){if(alive.current){setError(e.message);request.current=null;await load().catch(()=>{});}}finally{if(alive.current)setBusy(false);}}
 const history=(data?.generations||[]).filter(g=>g.scope===scope&&(g.workspace_id||null)===(workspaceId||null)&&(g.stage||'preflight')===stage&&(!referenceWorkspaceId||(g.reference_workspace_id||null)===referenceWorkspaceId));
 const assistantItems=items.filter(row=>row.origin===(runtime?'runtime_assistant':'assistant'));
 const fill=value=>setText(value);
 const turn=g=><div className="assistant-v2-turn" key={g.request_id}><article className="assistant-v2-user"><p>{g.text}</p><span>你</span></article><article className="assistant-v2-answer"><span className="assistant-v2-message-icon">✦</span><PolicyAssistantResponse generation={g}/></article></div>;
 return <><div className="assistant-conversation-actions"><span>{fresh?'新场景：不沿用此前资料':history.at(-1)?.generation_basis?'继续当前场景：服务端复核并恢复已读文件和配置':'此前记录仅供查看；本轮重新读取场景'}</span><button className="assistant-text-button" disabled={busy||reading} onClick={()=>{setFresh(true);request.current=null;setAttachments([]);setError('');}}>开始新场景</button></div><section className={'policy-assistant assistant-v2 flow-assistant'+(!history.length?' assistant-empty':'')} aria-label={runtime?'运行时策略助手对话':'运行前策略助手对话'}><div className="assistant-chat-messages assistant-v2-messages" aria-live="polite">
 {!history.length&&<div className="assistant-v2-welcome"><span>✦</span><h2>{runtime?'根据当前运行情况生成哪些策略？':'需要为'+(scope==='system'?'所有 Agent':agentName(target))+'配置哪些约束？'}</h2><p>{runtime?'描述希望增加或调整的约束，助手从已发布模板中选择并起草。':'描述场景，或指定要读取的文件。指定文件后，正文读取范围仅限这些文件。'}</p><div className="flow-quick-start"><button type="button" onClick={()=>fill(runtime?'请分析当前 Hook 并生成策略候选。':'请读取当前 Agent 工作区的 AGENTS.md，根据其中的要求生成策略候选。')}>{runtime?'分析当前 Hook':'读取 AGENTS.md 生成策略'}</button></div></div>}
 {history.length>1&&<details className="assistant-previous-turns"><summary>此前分析 · {history.length-1} 轮{history.slice(0,-1).some(g=>g.generation_state==='failed')?'（含未完成记录）':''}</summary>{history.slice(0,-1).map(turn)}</details>}
 {history.length>0&&turn(history.at(-1))}
 {busy&&<p role="status">{runtime?'正在结合 Hook 与当前策略选择模板…':scope==='agent'?'正在分析场景并按需读取资料…':'正在分析你的需求…'}</p>}{!data&&!error&&<p role="status">正在读取模板与配置…</p>}
 </div><form className="assistant-chat-composer assistant-v2-composer" onSubmit={generate}>{error&&<p role="alert" className="inline-notice warning">{error} <button type="button" className="assistant-text-button" onClick={()=>load().catch(e=>setError(e.message))}>重新读取</button></p>}<textarea aria-label="策略需求" rows={3} maxLength={2000} value={text} disabled={busy} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();e.currentTarget.form.requestSubmit();}}} placeholder="描述场景、补充要求，或添加参考文件…"/>
 {attachments.length>0&&<ul className="assistant-attachment-list" aria-label="参考文件">{attachments.map(f=><li key={f.name}><span>{f.name}</span><button type="button" aria-label={'移除 '+f.name} disabled={busy||reading} onClick={()=>setAttachments(old=>old.filter(v=>v.name!==f.name))}>×</button></li>)}</ul>}
 <p className="field-note">{scope==='agent'?((selectedReference?'仅参考 '+referenceLabel+'。':'')+'指定文件时仅读取指定正文；目录检查仍可用于核对策略对象。'):'可添加 UTF-8 参考文件。'}</p>
 <div className="assistant-conversation-actions"><input ref={fileInput} type="file" aria-label="添加参考文件" accept={attachmentTypes} multiple hidden disabled={busy||reading} onChange={attach}/><button type="button" className="assistant-attach-button" disabled={busy||reading} title="UTF-8 文本，每个最多 8000 字符，最多 10 个；PDF、Word 和图片暂不支持" onClick={()=>fileInput.current?.click()}>{reading?'正在读取…':'＋ 添加文件'}</button><span className="assistant-composer-note">{attachments.length?'已添加 '+attachments.length+' 个参考文件 · 可继续对话':'生成后需审批'}</span><button className="assistant-send" aria-label="发送" disabled={busy||reading||(!text.trim()&&!attachments.length)||!data||(scope==='workspace'&&!workspaceId)}>{busy?'正在处理…':'发送 ↑'}</button></div></form></section>
 {assistantItems.length>0&&<details className="template-assistant-records"><summary>全部策略记录 · {assistantItems.length} 项</summary><PolicyRecordTable rows={assistantItems} label="助手起草的配置" actions={row=><button className="button tiny ghost" onClick={()=>onConfiguration?.(row.scope_id,row.id)}>管理配置</button>}/></details>}
 {legacy.length>0&&<details className="template-history-drafts"><summary>此前草案 · {legacy.length} 项</summary>{legacy.map(d=><article key={d.id}><p>{d.text}</p>{d.approval_id&&<button className="assistant-text-button" onClick={()=>onApprovals(d.approval_id)}>查看原审批</button>}</article>)}</details>}</>;
}
