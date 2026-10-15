import React,{useEffect,useState} from 'react';
import NativeAgentWorkspaces from './NativeAgentWorkspaces.jsx';
import ActPlanePolicies from './ActPlanePolicies.jsx';
import TemplatePolicyAssistant from './TemplatePolicyAssistant.jsx';
import SystemPolicyLibrary from './SystemPolicyLibrary.jsx';
import LegacyWorkspacePolicies from './LegacyWorkspacePolicies.jsx';
import {agentName,agentProcessLabel,visibleAgentInstances} from './agentInstancePresentation.mjs';
import {tabKeys} from './consoleState.mjs';
import './policyFlow.css';

export default function AgentPolicyWorkbench({api,post,navigation:n,navigate,candidate,onConsumed}){
 const [agents,setAgents]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0),[detail,setDetail]=useState(null);
 // Historical workspace links remain read-only; they never become Agent candidates.
 const legacy=n.policyScope==='workspace',scope=n.policyScope==='system'?'system':'agent';
 const workspace=n.policyWorkspace||'',targetId=n.policyAgent||'',tab=n.agentPolicyTab||'assistant';
 useEffect(()=>{let alive=true,inflight=false;async function load(){if(inflight)return;inflight=true;try{const value=await api('/api/console/agents');if(alive){setAgents(value.instances||[]);setError('');}}catch(e){if(alive){setAgents(null);setError(e.message);}}finally{inflight=false;}}load();const timer=setInterval(load,7000);return()=>{alive=false;clearInterval(timer);};},[api,revision]);
 const choices=visibleAgentInstances(agents||[]),row=agents?.find(a=>a.id===targetId);
 useEffect(()=>{if(scope==='agent'&&!legacy&&agents&&!targetId&&choices.length)navigate({policyAgent:choices.find(a=>a.mode==='controlled')?.id||choices[0].id,policyScope:'agent',policyWorkspace:'',policySession:''});},[agents,targetId,navigate,scope,legacy]);
 useEffect(()=>{let alive=true;setDetail(null);if(targetId&&scope==='agent')api('/api/agent-instances/'+encodeURIComponent(targetId)).then(value=>{if(alive)setDetail({...value,_target:targetId});}).catch(()=>{});return()=>{alive=false;};},[api,targetId,scope,revision,row?.generation]);
 const target=row?(detail?._target===targetId?{...row,...detail,policy_source:row.policy_source}:row):null;
 const tabs=[['assistant','策略助手'],['policies','已配置策略'],['workspaces','参考工作区']];
 const selectScope=value=>navigate({policyScope:value,policyWorkspace:'',policySession:'',agentPolicyTab:'assistant'});
 return <div className="content task-console policy-workbench agent-policy-flow">
  <div className="policy-target-bar">
   <label>作用范围<select aria-label="策略作用范围" value={legacy?'workspace':scope} onChange={e=>selectScope(e.target.value)}>
    <option value="system">全部受控 Agent</option><option value="agent">指定 Agent</option>{legacy&&<option value="workspace" disabled>历史工作区草案 · 只读</option>}
   </select></label>
   {scope==='agent'&&<label>指定 Agent<select aria-label="策略目标 Agent" value={targetId} onChange={e=>navigate({policyAgent:e.target.value,policyWorkspace:'',policySession:'',policyScope:'agent'})}><option value="" disabled>请选择 Agent</option>{choices.map(a=><option key={a.id} value={a.id}>{agentProcessLabel(a)}{a.mode!=='controlled'?' · 仅观测':''}</option>)}</select></label>}
   <button className="button tiny ghost" onClick={()=>setRevision(v=>v+1)}>刷新</button><button className="assistant-text-button" onClick={()=>navigate({page:'approvals',approvalId:''})}>查看审批 ↗</button>
  </div>
  {scope==='system'?<SystemPolicyLibrary key="system" api={api} post={post} showScope/>:<>
   {error&&<p role="alert" className="inline-notice warning">{error} <button className="button tiny ghost" onClick={()=>setRevision(v=>v+1)}>重新读取</button></p>}
   {!agents&&!error&&<p role="status">正在读取 Agent…</p>}
   {agents&&!choices.length&&<p className="task-empty">尚未登记 Agent，请先到 Agent 连接添加。</p>}
   {agents&&targetId&&!row&&<p role="alert">当前 Agent 不存在或不可读取，请重新选择目标。</p>}
   {legacy?<LegacyWorkspacePolicies key={targetId+':'+workspace} targetId={targetId} workspaceId={workspace} api={api} onApprovals={id=>navigate({page:'approvals',approvalId:id})} onCreate={()=>selectScope('agent')}/>:<>
    <p className="policy-scope-note">此 Agent 的全部工作区与会话继承。工作区是参考资料，具体文件和目录在策略参数中限定。</p>
    <div className="agent-workbench-bar"><div role="tablist" className="policy-page-tabs" aria-label="Agent 页面">{tabs.map(([k,title])=><button key={k} role="tab" aria-selected={tab===k} aria-controls={'agent-policy-panel-'+k} id={'agent-policy-tab-'+k} tabIndex={tab===k?0:-1} onClick={()=>navigate({agentPolicyTab:k})} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),tab,key=>navigate({agentPolicyTab:key}))}>{title}</button>)}</div></div>
    {target&&<section role="tabpanel" id={'agent-policy-panel-'+tab} aria-labelledby={'agent-policy-tab-'+tab}>
     {tab==='workspaces'?<><p className="field-note">只浏览此 Agent 已登记且有权读取的工作区。浏览不会改变策略范围，也不会自动把文件内容发送给策略助手。</p><NativeAgentWorkspaces id={targetId} api={api}/></>:target.mode!=='controlled'?<p className="task-empty">此连接仅用于观测，受控接入后可配置策略。</p>:tab==='assistant'?<TemplatePolicyAssistant key={targetId} target={target} scope="agent" workspaceId={null} api={api} post={post} onApprovals={id=>navigate({page:'approvals',approvalId:id||''})}/>:<ActPlanePolicies key={targetId} ownedOnly scopeId={targetId} scopeLabel={agentName(target)} recordScopeLabel={'指定 Agent · '+agentName(target)} api={api} post={post} candidate={candidate} onCandidateConsumed={onConsumed?.consume} onApprovals={id=>navigate({page:'approvals',approvalId:id})} onInherited={()=>selectScope('system')}/>}
    </section>}
   </>}
  </>}
 </div>;
}
