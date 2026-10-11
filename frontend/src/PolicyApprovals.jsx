import React,{useEffect,useRef,useState} from 'react';
import {DslCode} from './DslCode.jsx';
import {approvalLabel,disposition} from './policyExperience.mjs';
import {operationLabel} from './policyRecordPresentation.mjs';
import {agentName} from './agentInstancePresentation.mjs';
import {originLabel,processLabel,sessionReference,sessionTarget,agentTarget,matchesApproval} from './approvalPresentation.mjs';
const date=t=>new Date(t).toLocaleString('zh-CN',{hour12:false});
const needs=s=>['invalid','failed','stale'].includes(s);
const targetResult=(data,target)=>{const status=data.application?.targets?.find(t=>t.id===target.id)?.status;return {active:'加载时已核验',load_on_start:'已保存，启动时加载',failed:'应用失败，已暂停',paused:'执行已暂停'}[status]||(target.active?'确认后重新加载执行器':'启动时加载');};

function AgentLocation({agent,navigate,detail=false}){
 return <div className="approval-agent-location"><button className="approval-location-link" disabled={!navigate} onClick={()=>navigate?.(agentTarget(agent))}>{agent.name}</button><small className="approval-process"><span className={'approval-process-dot '+(agent.pid?'running':'')}/>{processLabel(agent)}</small>{detail&&agent.submitted_pid&&<small>提交时 PID {agent.submitted_pid}</small>}</div>;
}
function SessionLocations({data,navigate,detail=false}){
 const sessions=data.origin_sessions||[];
 return sessions.length?<div className="approval-session-locations">{sessions.map(s=><div key={s.instance_id+':'+s.session_id}><button className="approval-location-link approval-session-name" title={s.name} disabled={!s.available||!navigate} onClick={()=>navigate?.(sessionTarget(s))}>{s.name}{s.available&&' ↗'}</button><small title={s.session_id}>会话 {sessionReference(s)}{detail&&s.generation_pid?` · 生成时 PID ${s.generation_pid}`:''}</small>{detail&&!s.available&&<small>保留了生成关联，当前无法打开会话记录</small>}</div>)}</div>:<div className="approval-unlinked"><span>{originLabel(data)}</span><small>{data.scope_type==='system'?'适用于所有受控 Agent':'此连接的全部会话'}</small></div>;
}
export function ApprovalDetail({data,onClose,onDecision,busy,navigate}){
 const dialog=useRef(null),origin=useRef(document.activeElement),[tab,setTab]=useState('configuration'),[error,setError]=useState('');
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 const previous=data.previous_documents,changed=new Set(data.documents.filter(d=>!previous?.some(p=>p.id===d.id&&p.original_dsl===d.original_dsl)).map(d=>d.id)),records=previous?data.records.filter(r=>changed.has(r.document_id)):data.records,removed=previous?.filter(d=>!data.documents.some(n=>n.id===d.id))||[];
 async function decide(decision){setError('');try{await onDecision(data,decision);}catch(e){setError(e.message);}}
 const agents=data.agents||data.targets.map(t=>({...t,name:agentName(t),pid:null}));
 return <dialog ref={dialog} className="policy-review-dialog approval-detail-dialog" aria-label="策略审批详情" onCancel={e=>{e.preventDefault();if(!busy)onClose();}}>
  <header className="experience-detail-head"><span className="experience-symbol">✓</span><div><small>{data.scope_type==='system'?'系统策略变更':'Agent 策略变更'}</small><h2>审批详情</h2></div><button className="experience-close" aria-label="关闭审批详情" disabled={busy} onClick={onClose}>×</button></header>
  <div className="experience-detail-context"><span>{data.target_name}</span><span className={'experience-status '+(data.can_apply?'ready':'attention')}>{approvalLabel(data.status)}</span><time>{date(data.created_at)}</time></div>
  <div className="experience-detail-tabs" role="tablist" aria-label="审批详情"><button role="tab" aria-selected={tab==='configuration'} onClick={()=>setTab('configuration')}>变更内容</button><button role="tab" aria-selected={tab==='dsl'} onClick={()=>setTab('dsl')}>完整 DSL</button></div>
  <div className="experience-detail-body">
   <div className="approval-location-summary"><section><h3>对应 Agent</h3>{agents.map(a=><AgentLocation key={a.id} agent={a} navigate={busy?undefined:navigate} detail/>)}</section><section><h3>生成会话</h3><SessionLocations data={data} navigate={busy?undefined:navigate} detail/></section></div>
   {data.reason&&<p className="experience-callout">{data.reason}</p>}{error&&<p className="inline-notice warning" role="alert">{error}</p>}
   {tab==='configuration'?<>
    <section className="experience-section"><div className="experience-section-heading"><h3>本次策略变更</h3><span>{records.length} 条新增或更新{removed.length>0&&` · 移除 ${removed.length} 个文档`}</span></div>{records.length?<div className="approval-config-list">{records.map(r=><article key={r.id}><div className="approval-config-title"><span>{previous?previous.some(p=>p.id===r.document_id)?'修改':'新增':'候选'}</span><strong>{r.statement}</strong></div><div className="approval-clause-list">{r.clauses.map((c,i)=><div key={i}><b className={'approval-effect '+c.effect}>{disposition(c.effect)}</b><span>{operationLabel(c.operation)}</span><code>{c.target}</code></div>)}</div></article>)}</div>:<p className="experience-note">{removed.length?'本次只移除下列文档，其余配置与继承约束继续保留。':changed.size?'未取得可展示的编译规则，请检查完整 DSL 或重新校验。':'配置内容未改变，将重新加载已确认的配置。'}</p>}{removed.map(d=><div className="approval-removed" key={d.id}><span>移除</span>{d.name}</div>)}</section>
    <section className="experience-section"><div className="experience-section-heading"><h3>影响范围</h3><span>{data.total_affected_count} 个 Agent</span></div><p className="experience-note">{data.scope_type==='system'?'系统策略适用于全部受控 Agent。':'应用将更新此 Agent 的共享策略，影响其全部工作区与会话。'}{(data.origin_sessions||[]).length>0&&'生成会话用于定位需求和工作区，不限定策略的执行范围。'}</p><div className="approval-target-list">{agents.map(t=><div key={t.id}><span className="approval-target-icon">A</span><div><strong>{t.name}</strong><small>全部工作区与会话</small></div><span>{targetResult(data,t)}</span></div>)}</div>{data.total_affected_count>agents.length&&<p className="experience-note">另有 {data.total_affected_count-agents.length} 个已收起的登记实例也在系统策略范围内。</p>}</section>
    <section className="experience-section approval-validation"><span>✓</span><div><h3>{data.can_apply?'环境与编译校验通过':'校验状态'}</h3><p>{data.can_apply?'应用前会再次核对策略版本、运行身份和工作区，变化后需要重新校验。':approvalLabel(data.status)}</p></div></section>
   </>:data.documents.map(d=><section className="experience-section" key={d.id}><h3>{d.name}</h3><DslCode text={d.original_dsl}/></section>)}
  </div>
  <footer className="experience-detail-footer"><span>{data.can_apply?'批准后将重新加载受影响的 Agent，策略才会应用。':'查看记录不会改变运行策略'}</span>{['pending','stale','invalid','failed'].includes(data.status)&&<button className="button ghost" disabled={busy} onClick={()=>decide('reject')}>拒绝</button>}{data.can_apply&&<button className="button primary" disabled={busy} onClick={()=>decide('confirm')}>{busy?'正在处理…':'批准并应用'}</button>}</footer>
 </dialog>;
}
export function ApprovalRecords({rows,navigate}){
 return <table aria-label="策略审批记录"><colgroup><col className="approval-col-policy"/><col className="approval-col-agent"/><col className="approval-col-session"/><col className="approval-col-status"/><col className="approval-col-action"/></colgroup><thead><tr><th>策略变更</th><th>Agent / PID</th><th>生成会话</th><th>状态 / 提交时间</th><th>操作</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}>
  <td data-label="策略变更"><button className="approval-record-title" onClick={()=>navigate({approvalId:r.id})}>{r.name}</button><small>{r.scope_type==='system'?'系统策略':'Agent 策略'} · {r.document_count} 个配置文档</small></td>
  <td data-label="Agent / PID">{(r.agents||[]).map(a=><AgentLocation key={a.id} agent={a} navigate={navigate}/>)}{!(r.agents||[]).length&&<span>{r.target_name}</span>}</td>
  <td data-label="生成会话"><SessionLocations data={r} navigate={navigate}/></td>
  <td data-label="状态 / 提交时间"><span className={'experience-status '+(r.can_apply?'ready':'attention')}>{approvalLabel(r.status)}</span><small className="approval-date">{date(r.created_at)}</small></td>
  <td data-label="操作"><button className="approval-detail-link" onClick={()=>navigate({approvalId:r.id})}>{r.can_apply?'查看并审批':'查看详情'} <span>↗</span></button></td>
 </tr>)}</tbody></table>;
}
export default function PolicyApprovals({api,post,navigation:n,navigate,onChanged}){
 const [page,setPage]=useState(null),[selected,setSelected]=useState(null),[tab,setTab]=useState('pending'),[q,setQ]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 useEffect(()=>{let alive=true;async function load(){try{const data=await api('/api/console/approvals');if(alive){setPage(data);setError('');}}catch(e){if(alive)setError(e.message);}}load();const timer=setInterval(load,7000);return()=>{alive=false;clearInterval(timer);};},[api,revision]);
 useEffect(()=>{let alive=true;setSelected(null);if(n.approvalId)api('/api/console/approvals/'+encodeURIComponent(n.approvalId)).then(v=>{if(alive)setSelected(v);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[api,n.approvalId,revision]);
 const rows=page?.records||[],counts={pending:rows.filter(r=>r.status==='pending').length,attention:rows.filter(r=>needs(r.status)).length,processed:rows.filter(r=>['applied','rejected','applying'].includes(r.status)).length},visible=rows.filter(r=>(tab==='pending'?r.status==='pending':tab==='attention'?needs(r.status):['applied','rejected','applying'].includes(r.status))&&matchesApproval(r,q));
 async function decide(p,decision){setBusy(true);try{const base=p.scope_id==='system'?'/api/security/system/dsl':'/api/agent-instances/'+encodeURIComponent(p.scope_id)+'/dsl';await post(base+'/proposals/'+encodeURIComponent(p.id)+'/'+decision,{proposal_hash:p.proposal_hash});setRevision(x=>x+1);onChanged?.();}finally{setBusy(false);}}
 return <div className="content approval-workbench">
  <div className="approval-toolbar"><div className="approval-filter-tabs" role="tablist" aria-label="审批记录"><button role="tab" aria-selected={tab==='pending'} onClick={()=>setTab('pending')}>待审批 <span>{counts.pending}</span></button><button role="tab" aria-selected={tab==='attention'} onClick={()=>setTab('attention')}>需要处理 <span>{counts.attention}</span></button><button role="tab" aria-selected={tab==='processed'} onClick={()=>setTab('processed')}>已处理 <span>{counts.processed}</span></button></div><button className="button tiny ghost" onClick={()=>setRevision(x=>x+1)}>刷新</button></div>
  <div className="approval-search"><input type="search" aria-label="搜索审批记录" placeholder="搜索策略、Agent、会话或 PID" value={q} onChange={e=>setQ(e.target.value)}/><span>查看并核对后，由你批准应用。</span></div>
  {error&&<p role="alert" className="inline-notice warning">{error}</p>}<div className="approval-records"><ApprovalRecords rows={visible} navigate={navigate}/>{!visible.length&&<div className="experience-empty">{page?'当前没有匹配的审批记录。':'正在读取审批记录…'}</div>}</div>
  {selected&&<ApprovalDetail key={selected.id+revision} data={selected} busy={busy} onClose={()=>navigate({approvalId:''})} onDecision={decide} navigate={navigate}/>}
 </div>;
}
