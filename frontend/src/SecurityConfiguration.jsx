import React,{useEffect,useRef,useState} from 'react';
import InstanceSecurity from './InstanceSecurity.jsx';
import {tabKeys} from './consoleState.mjs';
import {proposalDraft} from './instanceSecurity.mjs';
import ActPlanePolicies from './ActPlanePolicies.jsx';

export function SystemSecurityRules({data,error,busy,onPropose,onConfirm,onReload}){
 if(!data)return <p className="task-empty" role={error?'alert':'status'}>{error?'系统规则读取失败：'+error:'正在读取系统规则…'}{error&&<button type="button" className="button tiny ghost" onClick={onReload}>重新读取</button>}</p>;
 return <section className="system-security" aria-label="系统共享规则">
  {error&&<p className="inline-notice warning" role="alert">{error}</p>}
  {data.phase!=='ready'&&<p className="inline-notice warning" role="alert">上次系统规则应用未完成，执行保持暂停。<button type="button" className="button tiny ghost" disabled={busy} onClick={()=>onPropose(proposalDraft(data,data.policy))}>重新核验并应用</button></p>}
  <InstanceSecurity scope="system" row={data} pending={data.proposals||[]} busy={busy} onPropose={onPropose} onConfirm={onConfirm}/>
 </section>;
}

export function SystemSecurityConfiguration({api,post,onChanged}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const sequence=useRef(0),mounted=useRef(false);
 async function refresh(){const n=++sequence.current;try{const value=await api('/api/security/system');if(mounted.current&&n===sequence.current){setData(value);setError('');}}catch(e){if(mounted.current&&n===sequence.current){setError(e.message);setData(null);}}}
 useEffect(()=>{mounted.current=true;refresh();const timer=setInterval(refresh,5000);return()=>{mounted.current=false;sequence.current++;clearInterval(timer);};},[api]);
 async function act(fn){setBusy(true);setError('');try{const value=await fn();await refresh();onChanged?.();return {ok:true,value};}catch(e){if(mounted.current)setError(e.message);return {ok:false};}finally{if(mounted.current)setBusy(false);}}
 return <SystemSecurityRules data={data} error={error} busy={busy} onReload={refresh}
  onPropose={candidate=>act(()=>post('/api/security/system/proposals',{policy:candidate.policy,base_hash:candidate.base_hash,revision:Number(candidate.generation),request_key:crypto.randomUUID()}))}
  onConfirm={proposal=>act(()=>post('/api/security/system/proposals/'+proposal.id+'/confirm',{proposal_hash:proposal.proposal_hash}))}/>;
}

export default function SecurityConfiguration({row,api,post,onSystemChanged,initialScope='agent',...props}){
 const [scope,setScope]=useState(initialScope);
 const tabs=[['system','系统策略','所有 Agent 共用'],['agent','Agent 策略','所有工作区共用']];
 return <div className="security-configuration">
  <div className="security-scope-tabs" role="tablist" aria-label="安全配置作用范围">{tabs.map(([key,title,caption])=><button type="button" role="tab" key={key} id={'security-scope-'+key} aria-controls={'security-scope-panel-'+key} aria-selected={scope===key} tabIndex={scope===key?0:-1} onClick={()=>setScope(key)} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),scope,setScope)}><b>{title}</b><small>{caption}</small></button>)}</div>
  <div role="tabpanel" id={'security-scope-panel-'+scope} aria-labelledby={'security-scope-'+scope}>
   {scope==='system'||row.mode==='controlled'?<ActPlanePolicies key={scope} scopeId={scope==='system'?'system':row.id} api={api} post={post} onChanged={onSystemChanged}/>:<p className="task-empty">当前 Agent 尚未接管执行。添加受控连接后，可配置其所有工作区共用的规则。</p>}
  </div>
 </div>;
}
