import React,{useEffect,useState} from 'react';
import AgentPolicyTemplates from './AgentPolicyTemplates.jsx';
import ProductGenerationHistory from './ProductGenerationHistory.jsx';
import SystemPolicyLibrary from './SystemPolicyLibrary.jsx';
import {tabKeys} from './consoleState.mjs';
const tabs=[['policies','系统策略'],['templates','策略与模板'],['generations','生成记录']];
export default function SystemWorkbench({api,post,navigation:n,navigate,onHandoff}){
 const [agents,setAgents]=useState(null),[error,setError]=useState('');
 const tab=n.systemTab||'policies',selected=['generate','records'].includes(tab)?'generations':tab;
 useEffect(()=>{if(selected==='generations')return;let alive=true;async function load(){try{const d=await api('/api/agent-instances');if(alive){setAgents(d.instances||[]);setError('');}}catch{if(alive){setAgents(null);setError('暂时无法读取 Agent 连接，正在重试。');}}}load();const timer=setInterval(load,7000);return()=>{alive=false;clearInterval(timer);};},[api,selected]);
 return <div className="content task-console policy-workbench system-workbench"><div role="tablist" className="policy-page-tabs" aria-label="系统模块">{tabs.map(([key,title])=><button key={key} id={'system-tab-'+key} role="tab" aria-selected={selected===key} aria-controls="system-panel" tabIndex={selected===key?0:-1} onClick={()=>navigate({systemTab:key,historyModuleIndex:key==='generations'?2:0})} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),selected,k=>navigate({systemTab:k,historyModuleIndex:k==='generations'?2:0}))}>{title}</button>)}</div>
 {error&&tab==='policies'&&<p role="alert" className="inline-notice warning">{error}</p>}<section role="tabpanel" id="system-panel" aria-labelledby={'system-tab-'+selected}>{tab==='policies'&&<SystemPolicyLibrary api={api} post={post}/>}
 {tab==='templates'&&(error?<p role="alert" className="inline-notice warning">{error}</p>:!agents?<p role="status">正在读取可导入的 Agent…</p>:<AgentPolicyTemplates agents={agents} targetId={n.policyAgent} onHandoff={onHandoff}/>)}
 {selected==='generations'&&<ProductGenerationHistory api={api}/>}
 </section></div>;
}
