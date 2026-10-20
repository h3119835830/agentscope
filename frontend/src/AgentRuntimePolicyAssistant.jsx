import React,{useEffect,useState} from 'react';
import RecordBadge from './RecordBadge.jsx';
import TemplatePolicyAssistant from './TemplatePolicyAssistant.jsx';

const hookNames={tool_start:'工具调用前',tool_result:'工具返回后',tool_denied:'工具被拒绝'};
const when=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'未记录';

export default function AgentRuntimePolicyAssistant({target,api,post,onApprovals}){
 const [events,setEvents]=useState(null),[error,setError]=useState(''),[selected,setSelected]=useState(null),[revision,setRevision]=useState(0);
 useEffect(()=>{let alive=true;setEvents(null);setError('');setSelected(null);api('/api/agent-instances/'+encodeURIComponent(target.id)+'/events').then(v=>{if(alive)setEvents((v.events||[]).filter(e=>e.generation===target.generation&&hookNames[e.kind]).slice(0,20));}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[api,target.id,target.generation,revision]);
 const running=!!target.generation&&['open','paused'].includes(target.gate),hookConnected=running&&target.mode==='controlled';
 return <div className="runtime-policy-assistant">
  <div className="runtime-policy-summary"><div><span>运行时 Hook</span><RecordBadge tone={hookConnected?'good':'warn'}>{hookConnected?'已接入':'当前未运行'}</RecordBadge><small>工具调用前后事件由原生集成记录</small></div><div><span>策略生成</span><RecordBadge tone={running?'neutral':'warn'}>{running?'可人工触发 Pi':'等待运行代次'}</RecordBadge><small>选择 Hook 后由受限助手选模板、填参数</small></div><div><span>作用范围</span><strong>此 Agent 共享执行域</strong><small>来源会话不形成会话独立策略</small></div></div>
  <section className="runtime-hook-records"><header><div><h2>最近的运行时 Hook</h2><p>选择一条真实事件作为本轮生成依据；Hook 和生成候选都不会自动批准或应用。</p></div><button className="button tiny ghost" onClick={()=>setRevision(v=>v+1)}>刷新 Hook</button></header>
   {error&&<p role="alert" className="inline-notice warning">{error}</p>}
   {!events&&!error&&<p role="status">正在读取运行时 Hook…</p>}
   {events?.length?<div className="table-scroll"><table className="policy-structured-table runtime-hook-table" aria-label="运行时 Hook 记录"><thead><tr><th>触发点</th><th>工具／来源会话</th><th>时间</th><th>操作</th></tr></thead><tbody>{events.map(e=><tr key={e.seq}><td><strong>{hookNames[e.kind]}</strong><small>记录 {e.seq}</small></td><td><code>{e.tool||'未记录工具'}</code><small>{e.session_id?'来自一个 Agent 会话（仅作来源）':'共享域事件'}</small></td><td>{when(e.created_at)}</td><td><button className="button tiny ghost" aria-pressed={selected===e.seq} onClick={()=>setSelected(selected===e.seq?null:e.seq)}>{selected===e.seq?'已选为依据':'作为生成依据'}</button></td></tr>)}</tbody></table></div>:events&&<p className="task-empty">当前运行代次还没有可用的工具 Hook 记录。也可以直接描述运行中发现的风险。</p>}
  </section>
  {running?<TemplatePolicyAssistant key={target.id+':runtime'} target={target} scope="agent" workspaceId={null} stage="runtime" runtimeEventSeq={selected} api={api} post={post} onApprovals={onApprovals}/>:<p className="task-empty">运行时助手需要一个已启动的受控 Agent；运行前策略仍可在“运行前策略助手”中配置。</p>}
 </div>;
}
