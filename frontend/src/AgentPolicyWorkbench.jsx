import React,{useEffect,useState} from 'react';
import ActPlanePolicies from './ActPlanePolicies.jsx';
import AgentPolicyAssistant from './AgentPolicyAssistant.jsx';
import {agentName,agentProcessLabel,visibleAgentInstances} from './agentInstancePresentation.mjs';
import {tabKeys} from './consoleState.mjs';
export default function AgentPolicyWorkbench({api,post,navigation:n,navigate,candidate,onConsumed}){
 const [agents,setAgents]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0),[context,setContext]=useState(null),[contextError,setContextError]=useState('');
 useEffect(()=>{let alive=true;async function load(){try{const d=await api('/api/agent-instances');if(alive){setAgents(d.instances||[]);setError('');}}catch(e){if(alive){setAgents(null);setError(e.message);}}}load();const timer=setInterval(load,7000);return()=>{alive=false;clearInterval(timer);};},[api,revision]);
 const choices=visibleAgentInstances(agents||[]),targetId=n.policyAgent||'',row=agents?.find(a=>a.id===targetId),tab=n.agentPolicyTab||'assistant';
 useEffect(()=>{if(agents&&!targetId&&choices.length)navigate({policyAgent:choices.find(a=>a.mode==='controlled'&&a.connected)?.id||choices[0].id});},[agents,targetId,navigate]);
 useEffect(()=>{let alive=true;setContext(null);setContextError('');if(!targetId)return;api('/api/agent-instances/'+encodeURIComponent(targetId)+'/policy-context'+(n.policySession?'?session_id='+encodeURIComponent(n.policySession):'')).then(value=>{if(alive)setContext(value);}).catch(e=>{if(alive)setContextError(e.message);});return()=>{alive=false;};},[api,targetId,n.policySession,revision]);
 const tabs=[['assistant','策略助手'],['policies','Agent 策略']];
 const targetSelect=<select aria-label="策略目标 Agent" value={targetId} onChange={e=>navigate({policyAgent:e.target.value,policySession:''})}><option value="" disabled>请选择 Agent</option>{choices.map(a=><option key={a.id} value={a.id}>{agentProcessLabel(a)}{a.mode!=='controlled'?' · 仅观测':''}</option>)}</select>;
 return <div className={'content task-console policy-workbench'+(tab==='assistant'?' agent-assistant-page':'')}>
 {error&&<p role="alert" className="inline-notice warning">{error}</p>}{!agents&&!error&&<p role="status">正在读取 Agent…</p>}
 <div className="agent-workbench-bar"><div role="tablist" className="policy-page-tabs" aria-label="Agent 页面">{tabs.map(([key,title])=><button key={key} role="tab" aria-selected={tab===key} aria-controls={'agent-policy-panel-'+key} id={'agent-policy-tab-'+key} tabIndex={tab===key?0:-1} onClick={()=>navigate({agentPolicyTab:key})} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),tab,k=>navigate({agentPolicyTab:k}))}>{title}</button>)}</div><div className="agent-workbench-actions"><button className="button tiny ghost" onClick={()=>setRevision(x=>x+1)}>刷新</button><button className="button tiny ghost" onClick={()=>navigate({page:'strategies',systemTab:'policies'})}>系统策略 ↗</button></div></div>
 {agents&&<>{!choices.length&&<p className="task-empty">尚未登记 Agent，请先到 Agent 连接添加。</p>}{targetId&&!row&&<p role="alert">当前 Agent 不存在或读取不可用，请重新选择目标。{targetSelect}</p>}
 {row&&<><section role="tabpanel" id={'agent-policy-panel-'+tab} aria-labelledby={'agent-policy-tab-'+tab}>{tab==='assistant'?<AgentPolicyAssistant key={targetId+':'+(context?.session_id||n.policySession||'')} target={row} targetSelect={targetSelect} context={context} contextError={contextError} onSession={sid=>navigate({policySession:sid})} onViewSession={sid=>navigate({page:'sessions',sessionInstance:targetId,sessionId:sid,sessionTab:'policies'})} api={api} post={post} onHandoff={onConsumed.handoff} onApprovals={id=>navigate({page:'approvals',approvalId:id||''})} onTemplates={()=>navigate({page:'strategies',systemTab:'templates',policyAgent:targetId})}/>:<><div className="agent-policy-target">{targetSelect}</div>{row.mode==='controlled'?<ActPlanePolicies key={targetId} scopeId={targetId} scopeLabel={agentName(row)} api={api} post={post} candidate={candidate} onCandidateConsumed={onConsumed.consume} onApprovals={id=>navigate({page:'approvals',approvalId:id})}/>:<p className="task-empty">此连接仅用于观测；受控接入后可配置 Agent 策略。</p>}</>}</section></>}
 </>}
 </div>;
}
