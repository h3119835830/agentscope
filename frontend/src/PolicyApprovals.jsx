import React,{useEffect,useRef,useState} from 'react';
import ApprovalRevalidation from './ApprovalRevalidation.jsx';
import ApprovalBatch from './ApprovalBatch.jsx';
import {LabelSourceSummary} from './LabelManagement.jsx';
import {approvalNeedsAttention,batchActionFor,batchActionLabel} from './approvalBatch.mjs';
import {DslCode} from './DslCode.jsx';
import {agentName} from './agentInstancePresentation.mjs';
import {originLabel,processLabel,sessionReference,sessionTarget,agentTarget,matchesApproval,approvalTitle} from './approvalPresentation.mjs';
import PolicyRecordTable,{PolicyRecordCells} from './PolicyRecordTable.jsx';
import {approvalPolicyRows,policyRecordFields} from './policyRecords.mjs';

const date=t=>new Date(t).toLocaleString('zh-CN',{hour12:false});
export const approvalDecisionUrl=(id,decision)=>'/api/console/approvals/'+encodeURIComponent(id)+'/'+decision;
const scopeName=p=>({system:'系统策略',agent:'Agent 策略',workspace:'工作区策略',session:'会话策略'})[p.scope_type];
const needs=approvalNeedsAttention;
const scopeLabel=data=>data.scope_label||(data.scope_type==='system'?'全部受控 Agent':data.scope_type==='session'?'当前任务会话':'全部工作区与会话');

function AgentLocation({agent,navigate,detail=false}){
 return <div className="approval-agent-location"><button className="approval-location-link" disabled={!navigate} onClick={()=>navigate?.(agentTarget(agent))}>{agent.name}</button><details><summary>进程证据</summary><small>{processLabel(agent)}</small>{detail&&agent.submitted_pid&&<small>提交时 PID {agent.submitted_pid}</small>}</details></div>;
}
export function SystemAudience({data}){
 const total=data.total_affected_count??data.agents?.length??0;
 return <div className="approval-system-audience"><strong>全部受控 Agent</strong><small>系统配置 · 提交时涉及 {total} 个实例</small></div>;
}
function SessionLocations({data,navigate}){
 const sessions=data.origin_sessions||[];
 return sessions.length?<div className="approval-session-locations">{sessions.map(s=><div key={s.instance_id+':'+s.session_id}><button className="approval-location-link" disabled={!s.available||!navigate} onClick={()=>navigate?.(sessionTarget(s))}>{s.name}{s.available&&' ↗'}</button><small>会话 {sessionReference(s)}</small></div>)}</div>:<span>{originLabel(data)}</span>;
}

export function ApprovalDetail({data,onClose,onDecision,onRevalidate,busy,navigate,recordId=''}){
 const dialog=useRef(null),origin=useRef(document.activeElement),[error,setError]=useState(''),[ack,setAck]=useState(false);
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 const records=(data.configuration_records||[]).map(row=>({...row,scope:{...row.scope,label:[data.target_name,scopeLabel(data)].filter(Boolean).join(' · ')},approval_status:data.status,configuration_status:data.configuration_status}));
 const focused=records.find(row=>row.id===recordId),displayed=focused?[focused]:records;
 const previous=data.previous_documents,removed=previous?.filter(d=>!(data.documents||[]).some(n=>n.id===d.id))||(data.document_changes?.removed||[]).map((name,index)=>({id:'removed-'+index,name}));
 const batchSize=records.length,documents=data.documents||[],agents=data.agents||(data.targets||[]).map(t=>({...t,name:agentName(t),pid:null}));
 const batchLabel=batchSize>1?'整批 '+batchSize+' 项':'此项';
 async function decide(decision){setError('');try{await onDecision(data,decision);}catch(e){setError(e.message);}}
 return <dialog ref={dialog} className="policy-review-dialog approval-detail-dialog" aria-label="策略审批详情" onCancel={e=>{e.preventDefault();if(!busy)onClose();}}>
  <header className="experience-detail-head"><span className="experience-symbol">✓</span><div><small>{scopeName(data)} · 审批</small><h2>{focused?.name||approvalTitle(data)}</h2></div><button className="experience-close" aria-label="关闭审批详情" disabled={busy} onClick={onClose}>×</button></header>
  <div className="experience-detail-context"><span>{data.target_name}</span><span>{data.configuration_status?.label||'状态待核验'}</span><time>{date(data.created_at)}</time></div>
  <div className="experience-detail-body">
   {batchSize>1&&<p className="approval-batch-scope">此记录属于同一批 {batchSize} 项策略。批准、拒绝和应用均作用于整批；各项保留独立策略记录。</p>}
   {recordId&&!focused&&<p role="alert">此批中未找到指定策略记录；下面展示整批内容。</p>}
   {data.reason&&<p className="experience-callout">{data.reason}</p>}{error&&<p role="alert" className="inline-notice warning">{error}</p>}
   <section className="experience-section"><h3>策略记录</h3>{displayed.length?<PolicyRecordTable rows={displayed} detail label="审批策略记录"/>:data.change_items?.length?<table className="approval-change-table" aria-label="权限变更对照"><thead><tr><th>配置</th><th>原配置</th><th>候选配置</th></tr></thead><tbody>{data.change_items.map((c,i)=><tr key={i}><th>{c.label}</th><td>{c.before}</td><td>{c.after}</td></tr>)}</tbody></table>:<><p>{data.explanation||'此历史记录没有结构化配置快照，请核对技术证据。'}</p>{data.records?.map(r=><p key={r.id}>{r.statement}</p>)}</>}
    {focused&&batchSize>1&&<details className="policy-inheritance"><summary>查看同批其他 {batchSize-1} 项</summary><PolicyRecordTable rows={records.filter(row=>row.id!==focused.id)} detail label="同批其他策略记录"/></details>}
   </section>
   {removed.length>0&&<section className="experience-section"><h3>{removed.length} 项变更</h3>{removed.map(row=><div key={row.id} className="approval-removed"><span>移除</span>{row.name}</div>)}</section>}
   <section className="experience-section"><h3>影响范围</h3><div className="approval-location-summary"><section><h3>适用 Agent</h3>{data.scope_type==='system'?<SystemAudience data={data}/>:agents.map(a=><AgentLocation key={a.id} agent={a} navigate={busy?undefined:navigate} detail/>)}</section><section><h3>生成会话</h3><SessionLocations data={data} navigate={busy?undefined:navigate}/></section></div><p>{scopeLabel(data)} · {data.total_affected_count} 个登记实例</p></section>
   {data.revalidated_from&&<p>由旧记录重新校验产生 <button className="assistant-text-button" disabled={busy} onClick={()=>navigate?.({approvalId:data.revalidated_from.source_id,approvalRecordId:''})}>查看原记录 ↗</button></p>}
   {data.revalidated_versions?.length>0&&<button className="assistant-text-button" disabled={busy} onClick={()=>navigate?.({approvalId:data.revalidated_versions[0].new_approval_id,approvalRecordId:''})}>查看最近一次重新校验 ↗</button>}
   {data.reference_materials?.length>0&&<details className="policy-inheritance"><summary>参考材料 · {data.reference_materials.length} 份</summary>{data.reference_materials.map((m,i)=><article key={i}><strong>{m.name}</strong><p className="flow-reference-text">{m.text}</p></article>)}</details>}
   {documents.length>0&&<details className="policy-inheritance"><summary>技术证据</summary><LabelSourceSummary documents={documents} scopeLabel={data.scope_label}/>{documents.map(d=><section key={d.id}><h3>{d.name}</h3><DslCode text={d.original_dsl}/></section>)}</details>}
   <p className="experience-note">{data.can_approve||data.can_apply?data.validation_label||'环境与编译校验通过；应用前再次核对候选、基线和执行目标。':data.configuration_status?.label}</p>
  </div>
  <footer className="experience-detail-footer"><span>{data.can_approve?'批准只保存决定，不改变运行进程。':data.can_apply?'应用会暂停并重建受影响实例，核验后恢复。':'查看记录不会改变运行策略'}</span>
   {(data.can_approve||data.can_apply)&&<label className="flow-ack"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>已核对{batchLabel}内容与影响范围</label>}
   {data.can_reject&&<button className="button ghost" disabled={busy} onClick={()=>decide('reject')}>{data.status==='approved'?'撤回变更':'拒绝'+(batchSize>1?'整批':'')}</button>}
   {data.revalidation&&<button className="button primary" disabled={busy} onClick={()=>data.revalidation.available?(onRevalidate?onRevalidate(data):navigate?.({page:'approvals',approvalId:data.id})):navigate?.(data.revalidation.destination)}>{data.revalidation.available?'重新校验':'返回所属配置'}</button>}
   {data.can_approve&&<button className="button primary" disabled={busy||!ack} onClick={()=>decide('approve')}>{busy?'正在处理…':'批准'+(batchSize>1?'整批 '+batchSize+' 项':'变更')}</button>}
   {data.can_apply&&<button className="button primary" disabled={busy||!ack} onClick={()=>decide('apply')}>{busy?'正在应用…':'应用'+(batchSize>1?'整批 '+batchSize+' 项':'策略')}</button>}
  </footer>
 </dialog>;
}

export function ApprovalRecords({rows,navigate,selection}){
 const projected=rows.some(r=>r.record_key)?rows:approvalPolicyRows(rows),selected=selection?.ids||[];
 const all=projected.length>0&&projected.every(r=>selected.includes(r.id)),some=projected.some(r=>selected.includes(r.id));
 return <div className="policy-record-scroll"><table className="policy-record-table" aria-label="策略审批记录"><thead><tr>{selection&&<th><input type="checkbox" aria-label="全选当前审批批次" checked={all} aria-checked={some&&!all?'mixed':all} ref={e=>{if(e)e.indeterminate=some&&!all;}} disabled={selection.disabled||!projected.length} onChange={()=>selection.onAll(!all)}/></th>}{policyRecordFields.map(field=><th key={field}>{field}</th>)}<th>操作</th></tr></thead><tbody>{projected.map(r=><tr key={r.record_key}>
  {selection&&<td><input type="checkbox" aria-label={'选择 '+approvalTitle(r)+(r.batch_size>1?' 所在整批 '+r.batch_size+' 项':'')} checked={selected.includes(r.id)} disabled={selection.disabled} onChange={()=>selection.onToggle(r.id)}/></td>}
  <PolicyRecordCells record={r.policy_record||{name:approvalTitle(r),scope:scopeLabel(r),target:'见变更详情',operation:'见变更详情',conditions:'见变更详情',effect:'见变更详情',status:r.configuration_status?.label||'状态待核验'}} scope={r.scope_type==='system'?<SystemAudience data={r}/>:<><span>{r.target_name}</span><small>{scopeLabel(r)}</small><details><summary>关联信息</summary><small>适用 Agent</small>{(r.agents||[]).map(a=><AgentLocation key={a.id} agent={a} navigate={navigate}/>)}<small>生成会话</small><SessionLocations data={r} navigate={navigate}/></details></>} name={<><button className="approval-record-title" onClick={()=>navigate({approvalId:r.id,approvalRecordId:r.configuration_id||''})}>{approvalTitle(r)}</button><small>{r.batch_size>1?'同批 '+r.batch_size+' 项 · ':''}{date(r.created_at)}</small></>}/>
  <td><button className="approval-detail-link" onClick={()=>navigate({approvalId:r.id,approvalRecordId:r.configuration_id||''})}>查看{r.can_approve?'并审批':r.can_apply?'并应用':'详情'} ↗</button></td>
 </tr>)}</tbody></table></div>;
}

export default function PolicyApprovals({api,post,navigation:n,navigate,onChanged}){
 const decisionRequest=useRef(null);
 const [recovering,setRecovering]=useState(null),[page,setPage]=useState(null),[selected,setSelected]=useState(null),[tab,setTab]=useState('pending'),[q,setQ]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 const [checked,setChecked]=useState([]),[batch,setBatch]=useState(null),[showCleared,setShowCleared]=useState(false);
 useEffect(()=>{let alive=true;setPage(null);async function load(){try{const data=await api('/api/console/approvals'+(showCleared?'?cleared=true':''));if(alive){setPage(data);setError('');}}catch(e){if(alive)setError(e.message);}}load();const timer=setInterval(load,7000);return()=>{alive=false;clearInterval(timer);};},[api,revision,showCleared]);
 useEffect(()=>{let alive=true;setSelected(null);if(n.approvalId)api('/api/console/approvals/'+encodeURIComponent(n.approvalId)).then(v=>{if(alive)setSelected(v);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[api,n.approvalId,revision]);
 const rows=(page?.records||[]).filter(r=>!!r.cleared===showCleared),projected=approvalPolicyRows(rows),inTab=(r,t)=>t==='pending'?r.status==='pending':t==='approved'?r.status==='approved':t==='attention'?needs(r.status):['applied','rejected','applying'].includes(r.status);
 const counts=Object.fromEntries(['pending','approved','attention','processed'].map(t=>[t,projected.filter(r=>inTab(r,t)).length])),visible=projected.filter(r=>inTab(r,tab)&&matchesApproval(r,q));
 const visibleIds=[...new Set(visible.map(r=>r.id))],visibleBatches=rows.filter(r=>visibleIds.includes(r.id)),chosen=visibleBatches.filter(r=>checked.includes(r.id)),locked=busy||!!batch,action=showCleared?'restore':batchActionFor(tab);
 const selection={ids:chosen.map(r=>r.id),disabled:locked,onToggle:id=>setChecked(old=>old.includes(id)?old.filter(v=>v!==id):[...old,id]),onAll:value=>setChecked(value?visibleIds:[])};
 function changeTab(value){setChecked([]);setTab(value);}
 async function decide(p,decision){setBusy(true);try{const fingerprint=p.id+':'+decision+':'+p.candidate_hash+':'+p.approval_hash;if(decisionRequest.current?.fingerprint!==fingerprint)decisionRequest.current={fingerprint,key:crypto.randomUUID()};const body={proposal_hash:p.candidate_hash||p.proposal_hash,...(decision!=='reject'?{request_key:decisionRequest.current.key}:{}),...(decision==='apply'?{approval_hash:p.approval_hash}:{})};await post(approvalDecisionUrl(p.id,decision),body);decisionRequest.current=null;setTab(decision==='approve'?'approved':'processed');setRevision(x=>x+1);onChanged?.();}finally{setBusy(false);}}
 return <div className="content approval-workbench">
  <div className="approval-toolbar"><div className="approval-filter-tabs" role="tablist" aria-label="审批记录">{[['pending','待审批'],['approved','待应用'],['attention','需要处理'],['processed','已处理']].map(([value,label])=><button key={value} role="tab" disabled={locked} aria-selected={tab===value} onClick={()=>changeTab(value)}>{label} <span>{counts[value]}</span></button>)}</div><div className="approval-list-tools"><button className="button tiny ghost" disabled={locked} onClick={()=>{setChecked([]);setShowCleared(value=>!value);if(!showCleared&&['pending','approved'].includes(tab))setTab('processed');}}>{showCleared?'返回审批列表':'已清理记录'+(page?.cleared_count?' '+page.cleared_count:'')}</button><button className="button tiny ghost" disabled={locked} onClick={()=>{setChecked([]);setRevision(x=>x+1);}}>刷新</button></div></div>
  <div className="approval-search"><input type="search" aria-label="搜索审批记录" placeholder="搜索策略、Agent、会话或 PID" value={q} disabled={locked} onChange={e=>{setChecked([]);setQ(e.target.value);}}/><span>每项策略一条记录；同批审批一并处理。</span></div>
  {showCleared&&<p>正在查看已清理记录，保留原审批状态。</p>}
  {tab==='attention'&&!showCleared&&<p className="approval-attention-note">需要处理：包括需重新校验、校验未通过、应用未完成和暂不能应用的记录。</p>}
  <div className="approval-batch-toolbar" aria-label="审批批量操作"><button className="button tiny ghost" disabled={locked||!visible.length} onClick={()=>selection.onAll(chosen.length!==visibleBatches.length)}>{chosen.length&&chosen.length===visibleBatches.length?'取消全选':'全选当前结果'}</button><span>已选 {chosen.length} 批 · {approvalPolicyRows(chosen).length} 项策略</span>
   {showCleared?<><button className="button tiny ghost" disabled={locked||!visible.length} onClick={()=>setBatch({action:'restore',rows:visibleBatches})}>恢复当前结果</button><button className="button tiny primary" disabled={locked||!chosen.length} onClick={()=>setBatch({action:'restore',rows:chosen})}>恢复所选</button></>:<><button className="button tiny ghost" disabled={locked||!visibleBatches.some(r=>r.can_clear)} onClick={()=>setBatch({action:'clear',rows:visibleBatches})}>清理当前结果</button><button className="button tiny ghost" disabled={locked||!chosen.some(r=>r.can_clear)} onClick={()=>setBatch({action:'clear',rows:chosen})}>清理所选</button>{action&&<button className="button tiny primary" disabled={locked||!chosen.length} onClick={()=>setBatch({action,rows:chosen})}>{batchActionLabel(action)}</button>}</>}
  </div>
  {error&&<p role="alert" className="inline-notice warning">{error}</p>}<div className="approval-records"><ApprovalRecords rows={visible} navigate={navigate} selection={selection}/>{!visible.length&&<p>{page?'当前没有匹配的审批记录。':'正在读取审批记录…'}</p>}</div>
  {selected&&<ApprovalDetail key={selected.id+revision+(n.approvalRecordId||'')} data={selected} recordId={n.approvalRecordId} busy={busy} onClose={()=>navigate({approvalId:'',approvalRecordId:''})} onDecision={decide} onRevalidate={setRecovering} navigate={navigate}/>}
  {recovering&&<ApprovalRevalidation key={recovering.id} data={recovering} api={api} post={post} onClose={()=>setRecovering(null)} navigate={target=>{setRecovering(null);navigate(target);}} onCreated={result=>{setRecovering(null);setTab('pending');setQ('');setRevision(r=>r+1);navigate({approvalId:result.id,approvalRecordId:''});onChanged?.();}}/>}
  {batch&&<ApprovalBatch {...batch} api={api} post={post} onClose={()=>setBatch(null)} onFinished={()=>{setChecked([]);setRevision(r=>r+1);onChanged?.();}} onOpenRecord={id=>{setBatch(null);navigate({approvalId:id,approvalRecordId:''});}} onReturnConfig={target=>{setBatch(null);navigate(target);}}/>}
 </div>;
}
