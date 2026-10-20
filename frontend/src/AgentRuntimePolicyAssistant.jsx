import React,{useEffect,useState} from 'react';
import RecordBadge from './RecordBadge.jsx';

const hookNames={tool_start:'工具调用前',tool_result:'工具返回后',tool_denied:'工具被拒绝'};
const when=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'未记录';

export default function AgentRuntimePolicyAssistant({target,api}){
 const [events,setEvents]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{let alive=true;setEvents(null);setError('');api('/api/agent-instances/'+encodeURIComponent(target.id)+'/events').then(v=>{if(alive)setEvents((v.events||[]).filter(e=>e.generation===target.generation&&hookNames[e.kind]).slice(0,20));}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[api,target.id,target.generation,revision]);
 const running=!!target.generation&&['open','paused'].includes(target.gate),hookConnected=running&&target.mode==='controlled';
 return <div className="runtime-policy-assistant">
  <div className="runtime-policy-summary"><div><span>运行时 Hook</span><RecordBadge tone={hookConnected?'good':'warn'}>{hookConnected?'已接入':'当前未运行'}</RecordBadge><small>工具结果、拒绝和内核反馈应自动触发评估</small></div><div><span>Pi 自动评估</span><RecordBadge tone="warn">尚未接通</RecordBadge><small>当前后端还没有 RQ4 自动生成作业，页面不会伪装成已启用</small></div><div><span>增量热装载</span><RecordBadge tone="warn">尚未接通</RecordBadge><small>只允许新增／收紧，内核接纳后才算生效</small></div><div><span>作用范围</span><strong>此 Agent 共享执行域</strong><small>来源会话不形成会话独立策略；子 Agent 可使用子域</small></div></div>
  <p className="inline-notice warning">当前只完成运行时 Hook 采集。符合 ActPlane RQ4 的自动 Pi 评估、单调增量校验、内核热装载和回执链尚未实现，不能把手工生成的候选显示成运行时自动策略。</p>
  <section className="runtime-hook-records"><header><div><h2>自动触发证据</h2><p>这里展示 Hook 事实，不需要人工选择“生成依据”。接通后，控制面会自动冻结当前 generation、策略指纹和执行域，再启动一次受限 Pi 评估。</p></div><button className="button tiny ghost" onClick={()=>setRevision(v=>v+1)}>刷新记录</button></header>
   {error&&<p role="alert" className="inline-notice warning">{error}</p>}
   {!events&&!error&&<p role="status">正在读取运行时 Hook…</p>}
   {events?.length?<div className="table-scroll"><table className="policy-structured-table runtime-hook-table" aria-label="运行时 Hook 记录"><thead><tr><th>触发点</th><th>工具／来源会话</th><th>时间</th><th>自动化状态</th></tr></thead><tbody>{events.map(e=><tr key={e.seq}><td><strong>{hookNames[e.kind]}</strong><small>记录 {e.seq}</small></td><td><code>{e.tool||'未记录工具'}</code><small>{e.session_id?'来自一个 Agent 会话（仅作来源）':'共享域事件'}</small></td><td>{when(e.created_at)}</td><td><RecordBadge tone="warn">等待自动评估器</RecordBadge></td></tr>)}</tbody></table></div>:events&&<p className="task-empty">当前运行代次还没有可用的 Hook 记录。运行时策略不能通过手工描述代替真实触发证据。</p>}
  </section>
  {!running&&<p className="task-empty">运行时自动闭环需要一个已启动的受控 Agent；运行前策略仍可在“运行前策略助手”中配置。</p>}
 </div>;
}
