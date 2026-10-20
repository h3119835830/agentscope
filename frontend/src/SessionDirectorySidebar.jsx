import React,{useEffect,useState} from 'react';
import {agentName} from './agentInstancePresentation.mjs';
export default function SessionDirectorySidebar({api,navigation:n,navigate,collapsed=false,onToggle}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[limit,setLimit]=useState(8);
 useEffect(()=>{let alive=true;setData(null);setError('');setLimit(8);const params=new URLSearchParams({agent_type:n.sessionAgent||'',limit:'100'});api('/api/sessions?'+params).then(value=>{if(alive)setData(value);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[api,n.sessionAgent]);
 const rows=data?.records||[],picked=rows.find(s=>s.id===n.sessionId&&s.instance_id===n.sessionInstance);
 const shown=rows.slice(0,limit);if(picked&&!shown.includes(picked))shown.push(picked);
 const products=[...new Set((data?.connections||[]).map(c=>c.agent_type))];
 return <aside className={'session-workbench-directory'+(collapsed?' is-collapsed':'')} aria-label="真实会话目录">
  <div className="session-directory-header">
   {!collapsed&&<span className="session-directory-heading">会话目录</span>}
   <button type="button" className="session-directory-toggle" aria-label={collapsed?'展开会话目录':'收起会话目录'} title={collapsed?'展开会话目录':'收起会话目录'} aria-expanded={!collapsed} aria-controls="session-directory-list" onClick={onToggle}>
    <span aria-hidden="true">{collapsed?'›':'‹'}</span>{collapsed&&<span className="session-directory-toggle-label" aria-hidden="true">会话目录</span>}
   </button>
  </div>
  <div id="session-directory-list" hidden={collapsed}>
   <label>所属 Agent<select aria-label="面板 Agent 筛选" value={n.sessionAgent||''} onChange={e=>navigate({sessionAgent:e.target.value})}><option value="">全部 Agent</option>{products.map(p=><option key={p} value={p}>{agentName({agent_type:p})}</option>)}</select></label>
   {!data&&!error&&<p role="status" className="session-list-note">正在读取会话…</p>}{error&&<p role="alert" className="session-list-note">会话目录读取失败，请返回目录重试。</p>}
   {shown.map(s=><button key={s.instance_id+':'+s.id} className="session-switch" aria-pressed={s.instance_id===n.sessionInstance&&s.id===n.sessionId} onClick={()=>navigate({sessionInstance:s.instance_id,sessionId:s.id,sessionTab:'policies'})}><strong>{s.name||'未命名会话'}</strong><small>{agentName({id:s.instance_id,agent_type:s.agent_type,name:s.instance_name,display_name:s.instance_display_name})} · {s.historical?'历史记录':s.running?'活动中':'已保存'}</small></button>)}
   {rows.length>limit&&<button className="button tiny ghost" onClick={()=>setLimit(v=>v+8)}>更多会话</button>}{(data?.next_cursor||data?.errors?.length>0)&&<p className="session-list-note">会话映射尚不完整，完整目录可继续分页查看。</p>}
   <button className="button tiny ghost" onClick={()=>navigate({sessionInstance:'',sessionId:'',sessionCursor:0})}>完整会话目录 ↗</button>
  </div>
 </aside>;
}
