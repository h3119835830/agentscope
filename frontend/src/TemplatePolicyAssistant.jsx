import React,{useEffect,useRef,useState} from 'react';
import {ConfigurationRow,useConfigurationControls} from './TemplateConfigurationControls.jsx';
import {agentName} from './agentInstancePresentation.mjs';
import PolicyContextEvidence from './PolicyContextEvidence.jsx';
import GenerationConfigurations from './GenerationConfigurations.jsx';
import {attachmentTypes,readAttachments,conversationFor} from './policyConversationInput.mjs';
import './templateConfigurations.css';
const inputCache=new Map();
export default function TemplatePolicyAssistant({target,scope,workspaceId,api,post,onApprovals}){
 const identity=target.id+':'+scope+':'+(workspaceId||''),request=useRef(null),alive=useRef(true),fileInput=useRef(null);
 const [data,setData]=useState(null),[text,setText]=useState(inputCache.get(identity)||''),[attachments,setAttachments]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[legacy,setLegacy]=useState([]),[reading,setReading]=useState(false);
 const path='/api/policy-templates?scope_id='+encodeURIComponent(target.id);
 async function load(){try{const value=await api(path);if(alive.current)setData(value);}catch(e){if(alive.current)setData(null);throw e;}}
 useEffect(()=>{alive.current=true;load().catch(e=>{if(alive.current)setError(e.message);});if(scope!=='system')api('/api/agent-instances/'+encodeURIComponent(target.id)+'/policy-drafts?'+new URLSearchParams({scope,...(workspaceId?{workspace_id:workspaceId}:{})})).then(v=>{if(alive.current)setLegacy(v.records||[]);}).catch(()=>{});return()=>{alive.current=false;};},[api,path,scope,workspaceId]);
 useEffect(()=>{inputCache.set(identity,text);},[identity,text]);
 const catalog=(data?.catalog||[]).filter(t=>t.scopes.includes(scope)),items=(data?.items||[]).filter(i=>i.scope===scope&&(i.workspace_id||null)===(workspaceId||null));
 const controls=useConfigurationControls({catalog,agents:[target],targetId:target.id,scope,workspaceId,api,post,onChanged:load,onApprovals});
 async function attach(e){const files=[...e.target.files];e.target.value='';setReading(true);setError('');try{const value=await readAttachments(files,attachments);if(alive.current)setAttachments(value);}catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setReading(false);}}
 async function generate(e){e.preventDefault();if(busy||reading||!data||(!text.trim()&&!attachments.length))return;setBusy(true);setError('');try{
  const input={text:text.trim()||'请阅读附件，提取明确的安全约束并起草配置；缺少信息时请询问。',scope,workspace_id:workspaceId||null,context_mode:scope==='agent'?'auto':'none',materials:attachments,conversation:conversationFor(history)};
  const fingerprint=JSON.stringify(input);if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,key:crypto.randomUUID()};
  const value=await post(scope==='system'?'/api/policy-template-configurations/generate':'/api/agent-instances/'+encodeURIComponent(target.id)+'/template-configurations/generate',{...input,...(scope==='system'?{scope_id:'system'}:{}),request_key:request.current.key});
  if(alive.current){await load();setText('');request.current=null;}
 }catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setBusy(false);}}
 const history=(data?.generations||[]).filter(g=>g.scope===scope&&(g.workspace_id||null)===(workspaceId||null));
 return <><section className="policy-assistant assistant-v2 flow-assistant" aria-label="策略助手对话"><div className="assistant-chat-messages assistant-v2-messages" aria-live="polite">
 {!history.length&&<div className="assistant-v2-welcome"><span>✦</span><h2>需要为{scope==='system'?'所有 Agent':agentName(target)}配置哪些约束？</h2><p>直接描述场景或添加参考文件，助手会读取资料并起草配置。提交审批后，由你批准并确认应用。</p></div>}
 {history.map(g=><div className="assistant-v2-turn" key={g.request_id}><article className="assistant-v2-user"><p>{g.text}</p><span>你</span></article><article className="assistant-v2-answer"><span className="assistant-v2-message-icon">✦</span><div><p>{g.items.length?'本轮起草 '+g.items.length+' 项配置。':g.questions.length?'需要你补充一些信息：':g.gaps.length?'这项需求目前有能力限制：':'请继续描述需要配置的约束。'}</p><GenerationConfigurations generation={g}/>{g.context_usage?<PolicyContextEvidence usage={g.context_usage}/>:g.reference_read&&<p>参考资料：{g.reference_read.workspace} · {g.reference_read.paths.join('、')}</p>}{g.questions.map((v,i)=><p key={'q'+i}>需补充：{v}</p>)}{g.gaps.map((v,i)=><p key={'g'+i}>暂不支持：{v}</p>)}</div></article></div>)}
 {busy&&<p role="status">{scope==='agent'?'正在分析场景并按需读取资料…':'正在分析你的需求…'}</p>}{!data&&!error&&<p role="status">正在读取模板与配置…</p>}
 </div><form className="assistant-chat-composer assistant-v2-composer" onSubmit={generate}>{error&&<p role="alert" className="inline-notice warning">{error} <button type="button" className="assistant-text-button" onClick={()=>load().catch(e=>setError(e.message))}>重新读取</button></p>}<textarea aria-label="策略需求" rows={3} maxLength={2000} value={text} disabled={busy} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();e.currentTarget.form.requestSubmit();}}} placeholder="描述场景、补充要求，或添加参考文件…"/>
 {attachments.length>0&&<ul className="assistant-attachment-list" aria-label="参考文件">{attachments.map(f=><li key={f.name}><span>{f.name}</span><button type="button" aria-label={'移除 '+f.name} disabled={busy||reading} onClick={()=>setAttachments(old=>old.filter(v=>v.name!==f.name))}>×</button></li>)}</ul>}
 <p className="field-note">{scope==='agent'?'可按需读取此 Agent 有权限的工作区文件，无需填写参考文件路径。':'可添加参考文件；所有 Agent 范围不会读取某个实例的工作区。'}<br/>支持 UTF-8 文本；PDF、Word、图片暂不支持。</p>
 <div className="assistant-conversation-actions"><input ref={fileInput} type="file" aria-label="添加参考文件" accept={attachmentTypes} multiple hidden disabled={busy||reading} onChange={attach}/><button type="button" className="assistant-attach-button" disabled={busy||reading} title="UTF-8 文本，每个最多 8000 字符，最多 10 个；PDF、Word 和图片暂不支持" onClick={()=>fileInput.current?.click()}>{reading?'正在读取…':'＋ 添加文件'}</button><span className="assistant-composer-note">{attachments.length?'已添加 '+attachments.length+' 个参考文件 · 可继续对话':'生成后需审批'}</span><button className="assistant-send" aria-label="发送" disabled={busy||reading||(!text.trim()&&!attachments.length)||!data||(scope==='workspace'&&!workspaceId)}>{busy?'正在处理…':'发送 ↑'}</button></div></form></section>
 {items.some(row=>row.origin==='assistant')&&<div className="policy-table-shell template-assistant-records"><div className="table-scroll"><table className="policy-structured-table template-configuration-table" aria-label="助手起草的配置"><thead><tr><th>配置</th><th>范围</th><th>保护对象</th><th>操作与处置</th><th>状态</th><th>操作</th></tr></thead><tbody>{items.filter(row=>row.origin==='assistant').map(row=><ConfigurationRow key={row.id} row={row} onSubmit={controls.submit} onArchive={controls.archive} onApprovals={onApprovals}/>)}</tbody></table></div></div>}
 {legacy.length>0&&<details className="template-history-drafts"><summary>此前草案 · {legacy.length} 项</summary>{legacy.map(d=><article key={d.id}><p>{d.text}</p>{d.approval_id&&<button className="assistant-text-button" onClick={()=>onApprovals(d.approval_id)}>查看原审批</button>}</article>)}</details>}{controls.dialogs}</>;
}
