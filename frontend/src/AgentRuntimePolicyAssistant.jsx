import React,{useEffect,useState} from 'react';
import RecordBadge from './RecordBadge.jsx';

const hookNames={tool_start:'工具调用前',tool_result:'工具返回后',tool_denied:'工具被拒绝'};
const when=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'未记录';

export default function AgentRuntimePolicyAssistant({target,api}){
 const [events,setEvents]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{let alive=true;setEvents(null);setError('');api('/api/agent-instances/'+encodeURIComponent(target.id)+'/events').then(v=>{if(alive)setEvents((v.events||[]).filter(e=>e.generation===target.generation&&hookNames[e.kind]).slice(0,20));}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[api,target.id,target.generation,revision]);
 return <div className="runtime-policy-assistant">
  <section className="runtime-hook-records"><header><div><h2>工具运行事件</h2><p>Agent 共享执行域；工具回执不等同于内核命中。</p></div><button className="button tiny ghost" onClick={()=>setRevision(v=>v+1)}>刷新记录</button></header>
   {error&&<p role="alert" className="inline-notice warning">{error}</p>}
   {!events&&!error&&<p role="status">正在读取运行事件…</p>}
   {events?.length?<div className="table-scroll"><table className="policy-structured-table runtime-hook-table" aria-label="运行事件"><thead><tr><th>事件</th><th>工具／来源</th><th>时间</th><th>结果</th></tr></thead><tbody>{events.map(e=><tr key={e.seq}><td><strong>{hookNames[e.kind]}</strong></td><td>{e.tool||'未记录工具'}<small>{e.session_id?'已关联会话':'共享域事件'}</small></td><td>{when(e.created_at)}</td><td><RecordBadge>{e.kind==='tool_result'?(e.detail?.succeeded?'工具报告成功':'工具报告失败'):e.kind==='tool_denied'?'准入拒绝':'准入通过'}</RecordBadge></td></tr>)}</tbody></table></div>:events&&<p className="task-empty">本次运行暂无工具运行事件。</p>}
  </section>
 </div>;
}
