import React,{useEffect,useState} from 'react';
import ActPlanePolicies from './ActPlanePolicies.jsx';
import AgentPolicyTemplates from './AgentPolicyTemplates.jsx';
import {agentName,agentProcessLabel,visibleAgentInstances} from './agentInstancePresentation.mjs';
import {tabKeys} from './consoleState.mjs';
export default function AgentPolicyWorkbench({api,post,navigation:n,navigate,candidate,onConsumed}){
 const [agents,setAgents]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{let alive=true;async function load(){try{const d=await api('/api/agent-instances');if(alive){setAgents(d.instances||[]);setError('');}}catch(e){if(alive){setAgents(null);setError(e.message);}}}load();const timer=setInterval(load,7000);return()=>{alive=false;clearInterval(timer);};},[api,revision]);
 const choices=visibleAgentInstances(agents||[]),targetId=n.policyAgent||'',row=agents?.find(a=>a.id===targetId),tab=n.agentPolicyTab||'assistant';
 // Default only on first entry; a missing explicitly selected target must not fall through to another Agent.
 useEffect(()=>{if(agents&&!targetId&&choices.length)navigate({policyAgent:choices.find(a=>a.mode==='controlled'&&a.connected)?.id||choices[0].id});},[agents,targetId,navigate]);
 const tabs=[['assistant','策略助手'],['policies','Agent 策略']];
 return <div className="content task-console policy-workbench"><div className="policy-page-heading"><div><h1>Agent</h1><p>为选定 Agent 起草和管理策略，所有工作区与会话共用。</p></div><button className="button ghost" onClick={()=>setRevision(x=>x+1)}>刷新</button></div>
 {error&&<p role="alert" className="inline-notice warning">{error}</p>}{!agents&&!error&&<p role="status">正在读取 Agent…</p>}
 {agents&&<><div className="agent-policy-target"><label>Agent<select aria-label="策略目标 Agent" value={targetId} onChange={e=>navigate({policyAgent:e.target.value})}><option value="" disabled>请选择 Agent</option>{choices.map(a=><option key={a.id} value={a.id}>{agentProcessLabel(a)}{a.mode!=='controlled'?' · 仅观测':''}</option>)}</select></label>{row&&<span className="policy-layer">{row.mode==='controlled'?'第二层 · Agent 专属策略':'仅观测连接'}</span>}<button className="button ghost" onClick={()=>navigate({page:'strategies',systemTab:'policies'})}>系统策略 ↗</button></div>
 {!choices.length&&<p className="task-empty">尚未登记 Agent，请先到 Agent 连接添加。</p>}{targetId&&!row&&<p role="alert">当前 Agent 不存在或读取不可用，请重新选择目标。</p>}
 {row&&<><div role="tablist" className="policy-page-tabs" aria-label="Agent 页面">{tabs.map(([key,title])=><button key={key} role="tab" aria-selected={tab===key} aria-controls={'agent-policy-panel-'+key} id={'agent-policy-tab-'+key} tabIndex={tab===key?0:-1} onClick={()=>navigate({agentPolicyTab:key})} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),tab,k=>navigate({agentPolicyTab:k}))}>{title}</button>)}</div>
 <section role="tabpanel" id={'agent-policy-panel-'+tab} aria-labelledby={'agent-policy-tab-'+tab}>{tab==='assistant'?<><p className="field-note policy-assistant-note">当前支持从模板起草候选 DSL。自然语言策略生成由后续 Agent 助手接入。</p><AgentPolicyTemplates agents={agents} targetId={targetId} fixedTarget onHandoff={onConsumed.handoff}/></>:row.mode==='controlled'?<ActPlanePolicies key={targetId} scopeId={targetId} scopeLabel={agentName(row)} api={api} post={post} candidate={candidate} onCandidateConsumed={onConsumed.consume}/>:<p className="task-empty">此连接仅用于观测；受控接入后可导入和配置 Agent 策略。</p>}</section></>}
 </>}
 </div>;
}
