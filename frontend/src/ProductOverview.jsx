import React from 'react';
import SecurityNotice from './SecurityNotice.jsx';
import ValueAnnouncement from './ValueAnnouncement.jsx';
import RecordBadge from './RecordBadge.jsx';
import ProductStatus,{useEvidenceClock} from './ProductStatus.jsx';
import {currentStatus} from './productStatus.mjs';
import {agentName} from './agentInstancePresentation.mjs';
export default function ProductOverview({dash,status,error,onRetry,onNav,onSessions}){
 const agents=dash?.agents||[],stats=dash?.stats;
 const expiry=agents.map(a=>a.product_status?.loading?.expires_at).filter(t=>Date.parse(t)>Date.now()).sort()[0];
 const now=useEvidenceClock(expiry),verified=agents.filter(a=>currentStatus(a.product_status?.loading,'loading',Math.max(now,Date.now()),!!error).state==='loaded').length;
 const checked=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'暂无核验记录';
 const formalEntry=typeof location!=='undefined'&&location.hostname==='127.0.0.1'?location.href.replace('127.0.0.1','localhost'):null;
 return <div className="content product-overview"><div className="page-head"><div><p>查看 Agent 的运行、加载核验和待处理事项。</p></div><div className="security-notice-actions"><ValueAnnouncement/></div></div>
 {error&&<div role="alert" className="inline-notice warning">控制台数据不可达，当前运行与保护状态未知：{error} <button className="button tiny ghost" onClick={onRetry}>重新读取</button>{formalEntry&&<a className="button tiny ghost" href={formalEntry}>打开正式入口</a>}</div>}
 {dash&&<p className="overview-control-state">{error?'等待控制台恢复；上次成功读取':'控制台可达 · 最近读取'}：{checked(dash.observedAt)}。执行保护以各实例的当前核验为准。</p>}
 {!dash?!error&&<p role="status">正在读取 Agent…</p>:<>
 <section className="metric-grid product-metrics">{[['Agent',stats.agents],['加载已核验',verified],...(stats.pending_approvals?[['待审批',stats.pending_approvals]]:[])].map(([name,count])=><div className="metric" key={name}><span>{name}</span><strong>{count}</strong></div>)}</section>
 <section className="panel table-panel"><div className="panel-head"><h2>Agent 状态</h2><button className="button ghost" onClick={()=>onNav('connections')}>管理 Agent</button></div>{agents.length?<div className="table-scroll"><table><thead><tr><th>Agent</th><th>运行状态</th><th>加载核验</th><th/></tr></thead><tbody>{agents.map(a=><tr key={a.id}><td><b>{agentName(a)}</b></td><td><ProductStatus value={a.product_status?.runtime} dimension="runtime" failed={!!error}/></td><td><ProductStatus value={a.product_status?.loading} failed={!!error}/></td><td><button className="button tiny ghost" onClick={()=>onSessions(a.id)}>查看会话</button></td></tr>)}</tbody></table></div>:<p className="task-empty">添加 Agent 后可查看连接与保护状态。</p>}</section>
 </>}
 {status&&(!status.broker?.available||!status.bpf_lsm)&&<p role="alert" className="inline-notice warning">{status.error?'状态读取失败，请刷新后重试。':'保护服务当前不可用，请检查服务连接。'}</p>}
 </div>;
}
