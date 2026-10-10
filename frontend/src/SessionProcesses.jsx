import React from 'react';
import RecordBadge from './RecordBadge.jsx';
import {sessionProcessRow} from './sessionProcesses.mjs';
export default function SessionProcesses({agentType,data,error,onRefresh}){
 const rows=(data?.sessions||[]).map(sessionProcessRow);
 const showWorkspace=agentType!=='hermes'&&(agentType==='dsh'||rows.some(row=>row.workspace));
 return <section className="session-processes" aria-label="会话与进程列表">
  <div className="session-process-heading"><div><h3>会话与进程</h3><span>{data?`${rows.length} 个会话`:'读取会话中…'}</span></div><button type="button" className="button tiny ghost" onClick={onRefresh}>刷新列表</button></div>
  {error&&<p role="alert" className="inline-notice warning">会话读取失败：{error}</p>}
  {data?.executor_shared&&rows.some(row=>row.pids.length>0)&&<p className="field-note">同一 PID 表示多个会话共用执行进程。</p>}
  {data?.names_available===false&&<p className="field-note">会话名称暂时不可读取，ID 与进程关联仍来自当前会话记录。</p>}
  <div className="table-scroll" tabIndex={0} aria-label="会话记录表格"><table className={'session-process-table'+(showWorkspace?' has-workspace':'')}><thead><tr><th>会话名称</th><th>会话 ID</th>{showWorkspace&&<th>工作区</th>}<th>状态</th><th>执行进程（PID）</th></tr></thead><tbody>
   {rows.map(row=><tr key={row.id}><td><b className="session-process-name" title={row.name}>{row.name}</b></td><td><code className="session-process-id">{row.id}</code></td>{showWorkspace&&<td>{row.workspace?<div className="session-workspace" title={row.workspace}><span className="session-workspace-name"><svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9H3Z"/></svg>{row.workspaceName}</span><code className="session-workspace-path">{row.workspace}</code></div>:<span className="session-process-inactive">未提供</span>}</td>}<td><RecordBadge tone={row.tone}>{row.label}</RecordBadge></td><td>{row.pids.length?<div className="session-process-pids">{row.pids.map(pid=><RecordBadge key={pid} tone="info" dot={false} mono>{pid}</RecordBadge>)}{data.executor_shared&&<small>共享进程</small>}</div>:<span className="session-process-inactive">未运行</span>}</td></tr>)}
   {!rows.length&&<tr><td colSpan={showWorkspace?5:4} className="task-empty" role={data||error?undefined:'status'}>{error?'无法读取会话，请刷新重试。':!data?'正在读取会话…':data.disconnected?'Agent 当前未连接，暂无可读取的会话进程。':'暂无会话。'}</td></tr>}
  </tbody></table></div>
 </section>;
}
