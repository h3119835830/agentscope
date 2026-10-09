import React from 'react';
import RecordBadge from './RecordBadge.jsx';
import {sessionProcessRow} from './sessionProcesses.mjs';
export default function SessionProcesses({data,error,onRefresh}){
 const rows=(data?.sessions||[]).map(sessionProcessRow);
 return <section className="session-processes" aria-label="会话与进程列表">
  <div className="session-process-heading"><div><h3>会话与进程</h3><span>{data?`${rows.length} 个会话`:'读取会话中…'}</span></div><button type="button" className="button tiny ghost" onClick={onRefresh}>刷新列表</button></div>
  {error&&<p role="alert" className="inline-notice warning">会话读取失败：{error}</p>}
  {data?.executor_shared&&rows.some(row=>row.pids.length>0)&&<p className="field-note">同一 PID 表示多个会话共用执行进程。</p>}
  {data?.names_available===false&&<p className="field-note">会话名称暂时不可读取，ID 与进程关联仍来自当前会话记录。</p>}
  <div className="table-scroll" tabIndex={0}><table className="session-process-table"><thead><tr><th>会话名称</th><th>会话 ID</th><th>状态</th><th>执行进程（PID）</th></tr></thead><tbody>
   {rows.map(row=><tr key={row.id}><td><b className="session-process-name" title={row.name}>{row.name}</b></td><td><code className="session-process-id">{row.id}</code></td><td><RecordBadge tone={row.tone}>{row.label}</RecordBadge></td><td>{row.pids.length?<div className="session-process-pids">{row.pids.map(pid=><RecordBadge key={pid} tone="info" dot={false} mono>{pid}</RecordBadge>)}{data.executor_shared&&<small>共享进程</small>}</div>:<span className="session-process-inactive">未运行</span>}</td></tr>)}
   {!rows.length&&<tr><td colSpan={4} className="task-empty" role={data||error?undefined:'status'}>{error?'无法读取会话，请刷新重试。':!data?'正在读取会话…':data.disconnected?'Agent 当前未连接，暂无可读取的会话进程。':'暂无会话。'}</td></tr>}
  </tbody></table></div>
 </section>;
}
