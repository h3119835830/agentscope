import React from 'react';
import SecurityNotice from './SecurityNotice.jsx';
import RecordBadge from './RecordBadge.jsx';
import {agentName} from './agentInstancePresentation.mjs';
export default function ProductOverview({dash,status,onNav,onSessions}){
 const agents=dash?.agents||[],stats=dash?.stats;
 return <div className="content product-overview"><div className="page-head"><div><h1>总览</h1><p>查看 Agent 的连接、保护状态和待处理策略。</p></div><SecurityNotice/></div>
 {!dash?<p role="status">正在读取 Agent…</p>:<>
 <section className="metric-grid product-metrics">{[['Agent',stats.agents],['保护已核验',stats.verified_agents],...(stats.strategies?[['历史策略',stats.strategies]]:[]),...(stats.pending_strategies?[['待审核策略',stats.pending_strategies]]:[])].map(([name,count])=><div className="metric" key={name}><span>{name}</span><strong>{count}</strong></div>)}</section>
 <section className="panel table-panel"><div className="panel-head"><h2>Agent 状态</h2><button className="button ghost" onClick={()=>onNav('connections')}>管理 Agent</button></div>{agents.length?<div className="table-scroll"><table><thead><tr><th>Agent</th><th>运行状态</th><th>保护状态</th><th/></tr></thead><tbody>{agents.map(a=><tr key={a.id}><td><b>{agentName(a)}</b>{a.connected&&a.pid&&<small>PID {a.pid}</small>}</td><td><RecordBadge tone={a.connected?'good':'neutral'}>{a.status==='unknown'?'状态未知':a.connected?'已连接':'未运行'}</RecordBadge></td><td><RecordBadge tone={a.active?'good':a.connected?'warn':'neutral'}>{a.status==='unknown'?'当前未核验':a.active?'策略绑定已核验':a.connected?'保护未核验':'未运行'}</RecordBadge></td><td><button className="button tiny ghost" onClick={()=>onSessions(a.id)}>查看会话</button></td></tr>)}</tbody></table></div>:<p className="task-empty">添加 Agent 后可查看连接与保护状态。</p>}</section>
 </>}
 {status&&(!status.broker?.available||!status.bpf_lsm)&&<p role="alert" className="inline-notice warning">{status.error?'状态读取失败，请刷新后重试。':'保护服务当前不可用，请检查服务连接。'}</p>}
 </div>;
}
