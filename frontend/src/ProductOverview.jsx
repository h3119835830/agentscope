import React from 'react';
import SecurityNotice from './SecurityNotice.jsx';
import RecordBadge from './RecordBadge.jsx';
import {agentName} from './agentInstancePresentation.mjs';
export default function ProductOverview({dash,status,error,onRetry,onNav,onSessions}){
 const agents=dash?.agents||[],stats=dash?.stats;
 const checked=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'暂无核验记录';
 const formalEntry=typeof location!=='undefined'&&location.hostname==='127.0.0.1'?location.href.replace('127.0.0.1','localhost'):null;
 return <div className="content product-overview"><div className="page-head"><div><p>查看 Agent 的连接、保护状态和待处理策略。</p></div><SecurityNotice/></div>
 <section className="overview-value" aria-label="系统行为保护的价值"><p className="overview-value-lead">让授权管到脚本真正做的事。</p><p>测试脚本读了什么、后台进程做了什么、报告把什么发了出去，都需要执行时检查。</p><div className="overview-value-points"><span><b>凭证仍受保护</b> · 插件偷读会被检查</span><span><b>验收依据保持不变</b> · 源码可改，测试受保护</span><span><b>数据来源参与判断</b> · 同一地址也可区别处理</span></div></section>
 {error&&<div role="alert" className="inline-notice warning">控制台数据不可达，当前运行与保护状态未知：{error} <button className="button tiny ghost" onClick={onRetry}>重新读取</button>{formalEntry&&<a className="button tiny ghost" href={formalEntry}>打开正式入口</a>}</div>}
 {dash&&<p className="overview-control-state">{error?'等待控制台恢复；上次成功读取':'控制台可达 · 最近读取'}：{checked(dash.observedAt)}。执行保护以各实例的当前核验为准。</p>}
 {!dash?!error&&<p role="status">正在读取 Agent…</p>:<>
 <section className="metric-grid product-metrics">{[['Agent',stats.agents],['保护已核验',stats.verified_agents],...(stats.strategies?[['历史策略',stats.strategies]]:[]),...(stats.pending_approvals?[['待审批',stats.pending_approvals]]:[])].map(([name,count])=><div className="metric" key={name}><span>{name}</span><strong>{count}</strong></div>)}</section>
 <section className="panel table-panel"><div className="panel-head"><h2>Agent 状态</h2><button className="button ghost" onClick={()=>onNav('connections')}>管理 Agent</button></div>{agents.length?<div className="table-scroll"><table><thead><tr><th>Agent</th><th>运行状态</th><th>执行保护</th><th/></tr></thead><tbody>{agents.map(a=>{const unknown=['unknown','stale'].includes(a.status);return <tr key={a.id}><td><b>{agentName(a)}</b>{a.connected&&a.pid&&<small>PID {a.pid}</small>}</td><td><RecordBadge tone={a.connected?'good':'neutral'}>{unknown?'当前状态未知':a.connected?'已连接':a.status==='paused'?'执行暂停':'未运行'}</RecordBadge>{a.last_state_reason&&<small>{a.last_state_reason}</small>}</td><td><RecordBadge tone={a.active?'good':a.connected?'warn':'neutral'}>{unknown?'当前未核验':a.active?'策略绑定已核验':a.connected?'保护未核验':'执行未开放'}</RecordBadge><small className="overview-last-check">最近核验：{checked(a.last_verified_at)}</small></td><td><button className="button tiny ghost" onClick={()=>onSessions(a.id)}>查看会话</button></td></tr>;})}</tbody></table></div>:<p className="task-empty">添加 Agent 后可查看连接与保护状态。</p>}</section>
 </>}
 {status&&(!status.broker?.available||!status.bpf_lsm)&&<p role="alert" className="inline-notice warning">{status.error?'状态读取失败，请刷新后重试。':'保护服务当前不可用，请检查服务连接。'}</p>}
 </div>;
}
