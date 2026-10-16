import React,{useEffect,useRef,useState} from 'react';
import {ConfigurationRow,useConfigurationControls} from './TemplateConfigurationControls.jsx';
import {agentName} from './agentInstancePresentation.mjs';
import PolicyContextEvidence from './PolicyContextEvidence.jsx';
import './templateConfigurations.css';
const inputCache=new Map();
export default function TemplatePolicyAssistant({target,scope,workspaceId,api,post,onApprovals}){
 const identity=target.id+':'+scope+':'+(workspaceId||''),request=useRef(null),alive=useRef(true);
 const [data,setData]=useState(null),[text,setText]=useState(inputCache.get(identity)||''),[material,setMaterial]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[selected,setSelected]=useState(''),[legacy,setLegacy]=useState([]);
 const path='/api/policy-templates?scope_id='+encodeURIComponent(target.id);
 async function load(){try{const value=await api(path);if(alive.current)setData(value);}catch(e){if(alive.current)setData(null);throw e;}}
 useEffect(()=>{alive.current=true;load().catch(e=>{if(alive.current)setError(e.message);});if(scope!=='system')api('/api/agent-instances/'+encodeURIComponent(target.id)+'/policy-drafts?'+new URLSearchParams({scope,...(workspaceId?{workspace_id:workspaceId}:{})})).then(v=>{if(alive.current)setLegacy(v.records||[]);}).catch(()=>{});return()=>{alive.current=false;};},[api,path,scope,workspaceId]);
 useEffect(()=>{inputCache.set(identity,text);},[identity,text]);
 const catalog=(data?.catalog||[]).filter(t=>t.scopes.includes(scope)),items=(data?.items||[]).filter(i=>i.scope===scope&&(i.workspace_id||null)===(workspaceId||null));
 const controls=useConfigurationControls({catalog,agents:[target],targetId:target.id,scope,workspaceId,post,onChanged:load,onApprovals});
 async function generate(e){e.preventDefault();if(busy)return;setBusy(true);setError('');try{
  const input={text:text.trim(),scope,workspace_id:workspaceId||null,context_mode:scope==='agent'?'auto':'none',materials:material.trim()?[{name:'本次参考材料',text:material.trim()}]:[]};
  const fingerprint=JSON.stringify(input);if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,key:crypto.randomUUID()};
  const value=await post(scope==='system'?'/api/policy-template-configurations/generate':'/api/agent-instances/'+encodeURIComponent(target.id)+'/template-configurations/generate',{...input,...(scope==='system'?{scope_id:'system'}:{}),request_key:request.current.key});
  if(alive.current){await load();setText('');setMaterial('');request.current=null;}
 }catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setBusy(false);}}
 const history=(data?.generations||[]).filter(g=>g.scope===scope&&(g.workspace_id||null)===(workspaceId||null));
 return <><section className="policy-assistant assistant-v2 flow-assistant" aria-label="策略助手对话"><div className="assistant-chat-messages assistant-v2-messages" aria-live="polite">
 {!history.length&&<div className="assistant-v2-welcome"><span>✦</span><h2>需要为{scope==='system'?'所有 Agent':agentName(target)}配置哪些约束？</h2><p>助手选择已有模板、填写参数，结果保存到模板下的子配置。应用由你确认。</p></div>}
 {history.map(g=><div className="assistant-v2-turn" key={g.request_id}><article className="assistant-v2-user"><p>{g.text}</p><span>你</span></article><article className="assistant-v2-answer"><span className="assistant-v2-message-icon">✦</span><div><p>已保存 {g.items.length} 项模板子配置，尚未审批或应用。</p>{g.context_usage?<PolicyContextEvidence usage={g.context_usage}/>:g.reference_read&&<p>参考资料：{g.reference_read.workspace} · {g.reference_read.paths.join('、')}</p>}{g.questions.map((v,i)=><p key={'q'+i}>需补充：{v}</p>)}{g.gaps.map((v,i)=><p key={'g'+i}>当前模板缺口：{v}</p>)}</div></article></div>)}
 {busy&&<p role="status">{scope==='agent'?'正在分析场景、按需读取资料并填写模板参数…':'正在选择模板并填写参数…'}</p>}{!data&&!error&&<p role="status">正在读取模板与配置…</p>}
 </div><form className="assistant-chat-composer assistant-v2-composer" onSubmit={generate}>{error&&<p role="alert" className="inline-notice warning">{error} <button type="button" className="assistant-text-button" onClick={()=>load().catch(e=>setError(e.message))}>重新读取</button></p>}<textarea aria-label="策略需求" rows={3} maxLength={2000} value={text} onChange={e=>setText(e.target.value)} placeholder="例如：生成订单日报时只使用订单数据，避免读取或修改员工资料。"/>
 <details><summary>补充参考材料</summary><textarea aria-label="本次参考材料" rows={3} maxLength={8000} value={material} onChange={e=>setMaterial(e.target.value)} placeholder="仅填写本次要求需要引用的内容"/></details>
 {scope==='agent'&&<p className="field-note">助手会根据场景查看有权限的工作区，按需选择正文；无需填写参考文件路径。</p>}
 <div><span className="assistant-composer-note">{scope==='system'?'所有 Agent · 仅生成子配置':scope==='workspace'?'历史工作区子配置':'指定 Agent · '+agentName(target)+' · 仅生成子配置'}</span><button className="assistant-send" aria-label="生成策略" disabled={busy||text.trim().length<5||!data||(scope==='workspace'&&!workspaceId)}>{busy?'正在配置…':'按模板生成 ↑'}</button></div></form></section>
 <div className="template-assistant-toolbar"><label>手工配置同一模板 <select aria-label="选择配置模板" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">请选择模板</option>{catalog.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label><button className="button tiny ghost" disabled={!selected} onClick={()=>controls.create(catalog.find(t=>t.id===selected))}>新增子配置</button><button className="button tiny ghost" onClick={()=>load().catch(e=>setError(e.message))}>刷新配置</button></div>
 {items.length>0&&<div className="policy-table-shell template-assistant-records"><div className="table-scroll"><table className="policy-structured-table template-configuration-table" aria-label="当前范围子配置"><thead><tr><th>子配置</th><th>范围</th><th>保护对象</th><th>操作与处置</th><th>状态</th><th>操作</th></tr></thead><tbody>{items.map(row=><ConfigurationRow key={row.id} row={row} onEdit={controls.edit} onSubmit={controls.submit} onArchive={controls.archive} onApprovals={onApprovals}/>)}</tbody></table></div></div>}
 {legacy.length>0&&<details className="template-history-drafts"><summary>此前草案 · {legacy.length} 项</summary>{legacy.map(d=><article key={d.id}><p>{d.text}</p>{d.approval_id&&<button className="assistant-text-button" onClick={()=>onApprovals(d.approval_id)}>查看原审批</button>}</article>)}</details>}{controls.dialogs}</>;
}
