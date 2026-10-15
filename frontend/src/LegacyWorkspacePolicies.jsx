import React,{useEffect,useState} from 'react';

export default function LegacyWorkspacePolicies({targetId,workspaceId,api,onApprovals,onCreate}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{let active=true;setData(null);setError('');if(!targetId)return;
  const path='/api/agent-instances/'+encodeURIComponent(targetId)+'/policy-drafts?'+new URLSearchParams({scope:'workspace',...(workspaceId?{workspace_id:workspaceId}:{})});
  Promise.all([api(path),api('/api/policy-templates?scope_id='+encodeURIComponent(targetId))]).then(([drafts,configs])=>{if(active)setData({drafts:drafts.records||[],configs:(configs.items||[]).filter(c=>c.scope==='workspace'&&(!workspaceId||c.workspace_id===workspaceId))});}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};
 },[targetId,workspaceId,api,revision]);
 return <section aria-label="历史工作区草案"><p className="inline-notice warning">此链接保留原工作区归属，只读查看。不会转为整个 Agent 的策略；新配置请明确选择作用范围。</p><button className="button tiny ghost" onClick={onCreate}>新建指定 Agent 配置</button>
 {error&&<p role="alert">{error} <button className="button tiny ghost" onClick={()=>setRevision(v=>v+1)}>重新读取</button></p>}{!data&&!error&&<p role="status">正在读取历史草案…</p>}
 {data&&<div className="table-scroll"><table className="task-record-table" aria-label="历史工作区配置"><thead><tr><th>配置 / 需求</th><th>原作用范围</th><th>操作</th></tr></thead><tbody>{[...data.configs,...data.drafts].map(row=><tr key={row.id}><td>{row.name||row.text}</td><td>{row.scope_label||'原指定工作区'} · 只读</td><td>{row.approval_id?<button className="assistant-text-button" onClick={()=>onApprovals(row.approval_id)}>查看原审批</button>:'保留原记录'}</td></tr>)}{!data.configs.length&&!data.drafts.length&&<tr><td colSpan={3}>没有历史工作区草案。</td></tr>}</tbody></table></div>}</section>;
}
