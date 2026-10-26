import React,{useEffect,useState} from 'react';
import UnifiedPolicyLibrary from './UnifiedPolicyLibrary.jsx';
import ProductGenerationHistory from './ProductGenerationHistory.jsx';
import LabelManagement from './LabelManagement.jsx';
import {tabKeys} from './consoleState.mjs';
const tabs=[['policies','策略与配置'],['labels','标签管理'],['generations','生成记录']];
export default function SystemWorkbench({api,post,navigation:n,navigate}){
 const [agents,setAgents]=useState(null),[error,setError]=useState('');
 const tab=n.systemTab||'policies',selected=tab==='labels'?'labels':['generate','records','generations'].includes(tab)?'generations':'policies';
 useEffect(()=>{if(selected==='generations')return;let alive=true,timer;async function load(){try{const d=await api('/api/agent-instances');if(alive){setAgents(d.instances||[]);setError('');}}catch{if(alive){setAgents(null);setError('暂时无法读取 Agent 连接，正在重试。');}}finally{if(alive)timer=setTimeout(load,7000);}}load();return()=>{alive=false;clearTimeout(timer);};},[api,selected]);
 return <div className="content task-console policy-workbench system-workbench"><div role="tablist" className="policy-page-tabs" aria-label="系统模块">{tabs.map(([key,title])=><button key={key} id={'system-tab-'+key} role="tab" aria-selected={selected===key} aria-controls="system-panel" tabIndex={selected===key?0:-1} onClick={()=>navigate({systemTab:key,historyModuleIndex:key==='generations'?2:0})} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),selected,k=>navigate({systemTab:k,historyModuleIndex:k==='generations'?2:0}))}>{title}</button>)}</div>
 {error&&selected==='policies'&&<p role="alert" className="inline-notice warning">{error}</p>}<section role="tabpanel" id="system-panel" aria-labelledby={'system-tab-'+selected}>{selected==='policies'&&<UnifiedPolicyLibrary agents={agents||[]} targetId={n.policyScope==='system'?'system':n.policyAgent} configurationId={n.configurationId} api={api} post={post} onApprovals={(id,recordId)=>navigate({page:'approvals',approvalId:id,approvalRecordId:recordId||''})}/>}
 {selected==='generations'&&<ProductGenerationHistory api={api}/>}
 {selected==='labels'&&<LabelManagement api={api} post={post} agents={agents||[]}/>}
 </section></div>;
}
