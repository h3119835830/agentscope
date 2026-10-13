import React,{useEffect,useState} from 'react';
import ActPlanePolicies from './ActPlanePolicies.jsx';
import AgentPolicyDrafts from './AgentPolicyDrafts.jsx';
import {agentName,agentProcessLabel,visibleAgentInstances} from './agentInstancePresentation.mjs';
import {tabKeys} from './consoleState.mjs';
import './policyFlow.css';
export default function AgentPolicyWorkbench({api,post,navigation:n,navigate,candidate,onConsumed}){
 const [agents,setAgents]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 const [detail,setDetail]=useState(null),[context,setContext]=useState(null),[contextError,setContextError]=useState('');
 const scope=n.policyScope==='workspace'?'workspace':'agent',workspace=n.policyWorkspace||'',targetId=n.policyAgent||'',tab=n.agentPolicyTab||'assistant';
 useEffect(()=>{let alive=true,inflight=false;async function load(){if(inflight)return;inflight=true;try{const value=await api('/api/console/agents');if(alive){setAgents(value.instances||[]);setError('');}}catch(e){if(alive){setAgents(null);setError(e.message);}}finally{inflight=false;}}load();const timer=setInterval(load,7000);return()=>{alive=false;clearInterval(timer);};},[api,revision]);
 const choices=visibleAgentInstances(agents||[]),row=agents?.find(a=>a.id===targetId);
 useEffect(()=>{if(agents&&!targetId&&choices.length)navigate({policyAgent:choices.find(a=>a.mode==='controlled')?.id||choices[0].id,policyScope:'agent',policyWorkspace:'',policySession:''});},[agents,targetId,navigate]);
 useEffect(()=>{let alive=true;setDetail(null);if(targetId)api('/api/agent-instances/'+encodeURIComponent(targetId)).then(value=>{if(alive)setDetail({...value,_target:targetId});}).catch(()=>{});return()=>{alive=false;};},[api,targetId,revision,row?.generation]);
 const target=row?(detail?._target===targetId?{...row,...detail,policy_source:row.policy_source}:row):null;
 useEffect(()=>{let alive=true;setContext(null);setContextError('');if(targetId){const params=new URLSearchParams({scope});if(scope==='workspace'&&workspace)params.set('workspace_id',workspace);api('/api/agent-instances/'+encodeURIComponent(targetId)+'/policy-context?'+params).then(value=>{if(alive)setContext(value);}).catch(e=>{if(alive)setContextError(e.message);});}return()=>{alive=false;};},[api,targetId,scope,workspace,revision,row?.generation,row?.active]);
 const tabs=[['assistant','策略助手'],['policies','已配置策略']];
 return <div className="content task-console policy-workbench agent-policy-flow">
  <div className="policy-target-bar"><label>策略目标 Agent<select aria-label="策略目标 Agent" value={targetId} onChange={e=>navigate({policyAgent:e.target.value,policyWorkspace:'',policySession:''})}><option value="" disabled>请选择 Agent</option>{choices.map(a=><option key={a.id} value={a.id}>{agentProcessLabel(a)}{a.mode!=='controlled'?' · 仅观测':''}</option>)}</select></label><button className="button tiny ghost" onClick={()=>setRevision(v=>v+1)}>刷新</button><button className="assistant-text-button" onClick={()=>navigate({page:'approvals',approvalId:''})}>查看审批 ↗</button></div>
  {error&&<p role="alert" className="inline-notice warning">{error} <button className="button tiny ghost" onClick={()=>setRevision(v=>v+1)}>重新读取</button></p>}
  {!agents&&!error&&<p role="status">正在读取 Agent…</p>}
  {agents&&!choices.length&&<p className="task-empty">尚未登记 Agent，请先到 Agent 连接添加。</p>}
  {agents&&targetId&&!row&&<p role="alert">当前 Agent 不存在或不可读取，请重新选择目标。</p>}
  <div className="policy-scope-switch" role="group" aria-label="策略作用范围">{[['agent','Agent 长期基线'],['workspace','工作区策略']].map(([s,label])=><button key={s} aria-pressed={scope===s} onClick={()=>navigate({policyScope:s,policyWorkspace:'',policySession:''})}>{label}</button>)}</div>
  <p className="policy-scope-note">{scope==='agent'?'此实例的全部工作区与会话继承，无需选择会话。':'仅此实例的指定工作区；缺少独立执行绑定时不应用。'}</p>
  {scope==='workspace'&&<div className="policy-workspace-selection"><label>策略对应工作区<select aria-label="策略对应工作区" value={workspace} onChange={e=>navigate({policyWorkspace:e.target.value})}><option value="">请选择已核验的工作区</option>{context?.workspaces?.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label><span>{context?.workspaces?.find(w=>w.id===workspace)?.path||'没有可信身份时先保存草案，不根据目录猜测归属。'}</span></div>}
  <div className="agent-workbench-bar"><div role="tablist" className="policy-page-tabs" aria-label="Agent 页面">{tabs.map(([k,title])=><button key={k} role="tab" aria-selected={tab===k} aria-controls={'agent-policy-panel-'+k} id={'agent-policy-tab-'+k} tabIndex={tab===k?0:-1} onClick={()=>navigate({agentPolicyTab:k})} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),tab,key=>navigate({agentPolicyTab:key}))}>{title}</button>)}</div></div>
  {target&&<section role="tabpanel" id={'agent-policy-panel-'+tab} aria-labelledby={'agent-policy-tab-'+tab}>
   {target.mode!=='controlled'?<p className="task-empty">此连接仅用于观测，受控接入后可配置策略。</p>:tab==='assistant'?<AgentPolicyDrafts key={targetId+':'+scope+':'+workspace} target={target} scope={scope} workspaceId={workspace||null} context={context} contextError={contextError} onRefreshContext={()=>setRevision(v=>v+1)} api={api} post={post} onApprovals={id=>navigate({page:'approvals',approvalId:id||''})}/>:scope==='agent'?<ActPlanePolicies key={targetId} ownedOnly scopeId={targetId} scopeLabel={agentName(target)} api={api} post={post} candidate={candidate} onCandidateConsumed={onConsumed.consume} onApprovals={id=>navigate({page:'approvals',approvalId:id})} onInherited={()=>navigate({page:'strategies',systemTab:'policies'})}/>:<><p className="task-empty">当前没有可独立应用的工作区配置。草案保留在助手中，候选可提交审查。</p><details className="policy-inheritance"><summary>继承约束 · 只读查看</summary><button className="button ghost" onClick={()=>navigate({policyScope:'agent',agentPolicyTab:'policies'})}>查看 Agent 长期基线 ↗</button><button className="button ghost" onClick={()=>navigate({page:'strategies',systemTab:'policies'})}>查看系统策略 ↗</button></details></>}
  </section>}
 </div>;
}
