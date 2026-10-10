import React,{useEffect,useState} from 'react';
import ActPlanePolicies from './ActPlanePolicies.jsx';
import AgentPolicyTemplates from './AgentPolicyTemplates.jsx';
import HistoryLibrary from './HistoryLibrary.jsx';
import {tabKeys} from './consoleState.mjs';
const historyModules=[{page:'generate',title:'策略生成'},{page:'records',title:'历史策略记录'},{page:'audit',title:'生成记录'}];
const tabs=[['policies','系统策略'],['templates','策略与模板'],['generations','生成记录']];
export default function SystemWorkbench({api,post,navigation:n,navigate,onHandoff,...historyProps}){
 const [agents,setAgents]=useState(null),[error,setError]=useState('');
 const tab=n.systemTab||'policies',selected=['generate','records'].includes(tab)?'generations':tab;
 useEffect(()=>{if(tab!=='templates')return;let alive=true;setAgents(null);api('/api/agent-instances').then(d=>{if(alive){setAgents(d.instances||[]);setError('');}}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false};},[api,tab]);
 return <div className="content task-console policy-workbench system-workbench"><div className="policy-page-heading"><div><h1>系统</h1><p>配置系统策略，管理 Agent 模板与真实生成记录。</p></div></div><div role="tablist" className="policy-page-tabs" aria-label="系统模块">{tabs.map(([key,title])=><button key={key} id={'system-tab-'+key} role="tab" aria-selected={selected===key} aria-controls="system-panel" tabIndex={selected===key?0:-1} onClick={()=>navigate({systemTab:key,historyModuleIndex:key==='generations'?2:0})} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),selected,k=>navigate({systemTab:k,historyModuleIndex:k==='generations'?2:0}))}>{title}</button>)}</div>
 <section role="tabpanel" id="system-panel" aria-labelledby={'system-tab-'+selected}>{tab==='policies'&&<ActPlanePolicies key="system" scopeId="system" api={api} post={post}/>}
 {tab==='templates'&&(error?<p role="alert" className="inline-notice warning">{error}</p>:!agents?<p role="status">正在读取可导入的 Agent…</p>:<AgentPolicyTemplates agents={agents} targetId={n.policyAgent} onHandoff={onHandoff}/>)}
 {selected==='generations'&&<HistoryLibrary {...historyProps} api={api} post={post} moduleIndex={tab==='generate'?0:tab==='records'?1:2} modules={historyModules} onModuleChange={i=>navigate({systemTab:['generate','records','generations'][i],historyModuleIndex:i})}/>}
 </section></div>;
}
