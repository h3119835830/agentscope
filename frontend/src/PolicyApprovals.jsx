import React,{useEffect,useRef,useState} from 'react';
import ApprovalRevalidation from './ApprovalRevalidation.jsx';
import ApprovalBatch from './ApprovalBatch.jsx';
import ApprovalDsl from './ApprovalDsl.jsx';
import {approvalNeedsAttention,batchActionFor,batchActionLabel} from './approvalBatch.mjs';
import {originLabel,processLabel,sessionReference,sessionTarget,agentTarget,matchesApproval,approvalTitle} from './approvalPresentation.mjs';
import {PolicyRecordCells} from './PolicyRecordTable.jsx';
import {approvalPolicyRows,policyRecordFields} from './policyRecords.mjs';

const date=t=>new Date(t).toLocaleString('zh-CN',{hour12:false});
export const approvalDecisionUrl=(id,decision)=>'/api/console/approvals/'+encodeURIComponent(id)+'/'+decision;
const needs=approvalNeedsAttention;
const scopeLabel=data=>data.scope_label||(data.scope_type==='system'?'全部受控 Agent':data.scope_type==='session'?'当前任务会话':'全部工作区与会话');
const tabFor=row=>row.status==='pending'?'pending':row.status==='approved'?'approved':needs(row.status)?'attention':'processed';

function AgentLocation({agent,navigate}){
 return <div className="approval-agent-location"><button className="approval-location-link" disabled={!navigate} onClick={()=>navigate?.(agentTarget(agent))}>{agent.name}</button><details><summary>进程证据</summary><small>{processLabel(agent)}</small></details></div>;
}
export function SystemAudience({data}){
 const total=data.total_affected_count??data.agents?.length??0;
 return <div className="approval-system-audience"><strong>全部受控 Agent</strong><small>系统配置 · 提交时涉及 {total} 个实例</small></div>;
}
function SessionLocations({data,navigate}){
 return data.origin_sessions?.length?<>{data.origin_sessions.map(s=><div key={s.instance_id+':'+s.session_id}><button className="approval-location-link" disabled={!s.available||!navigate} onClick={()=>navigate?.(sessionTarget(s))}>{s.name}{s.available&&' ↗'}</button><small>会话 {sessionReference(s)}</small></div>)}</>:<span>{originLabel(data)}</span>;
}

// Decisions stay on their own record. Applying requires an explicit inline
// acknowledgement; displaying or selecting a record never submits a decision.
export function ApprovalRecordActions({row:r,onAction,onRevalidate,busy=false}){
 const [confirming,setConfirming]=useState(false),[ack,setAck]=useState(false);
 const grouped=(r.configuration_records?.length||0)>1;
 return <div className="approval-inline-actions" role="group" aria-label={r.name+'的审批操作'}>
  {grouped?<button className="button tiny ghost" disabled={busy} onClick={()=>onAction?.(r,'split')}>拆分记录</button>:<>
   {r.can_approve&&<button className="button tiny primary" disabled={busy} onClick={()=>onAction?.(r,'approve')}>批准</button>}
   {r.can_reject&&<button className="button tiny ghost" disabled={busy} onClick={()=>onAction?.(r,'reject')}>{r.status==='approved'?'撤回':'拒绝'}</button>}
   {r.can_apply&&!confirming&&<button className="button tiny primary" disabled={busy} onClick={()=>{setConfirming(true);setAck(false);}}>应用</button>}
   {r.can_apply&&confirming&&<div className="approval-inline-confirm"><p>仅应用这条策略；将重新加载{r.scope_type==='system'?'受影响 Agent':'此 Agent'}，影响其全部会话。</p><label><input type="checkbox" checked={ack} disabled={busy} onChange={e=>setAck(e.target.checked)}/>已核对此策略与影响范围</label><button className="button tiny primary" disabled={busy||!ack} onClick={()=>onAction?.(r,'apply')}>确认应用</button><button className="button tiny ghost" disabled={busy} onClick={()=>setConfirming(false)}>取消</button></div>}
   {r.revalidation&&<button className="button tiny ghost" disabled={busy} onClick={()=>onRevalidate?.(r)}>{r.revalidation.available?'重新校验':'返回配置'}</button>}
  </>}
 </div>;
}

export function ApprovalRecords({rows,navigate,selection,onAction,onRevalidate,busy=false,focusedId=''}){
 const [expanded,setExpanded]=useState([]);
 const projected=rows.some(r=>r.record_key)?rows:approvalPolicyRows(rows),selected=selection?.ids||[];
 const all=projected.length>0&&projected.every(r=>selected.includes(r.id)),some=projected.some(r=>selected.includes(r.id));
 return <div className="policy-record-scroll"><table className="policy-record-table" aria-label="策略审批记录"><thead><tr>{selection&&<th><input type="checkbox" aria-label="全选当前审批记录" checked={all} aria-checked={some&&!all?'mixed':all} ref={e=>{if(e)e.indeterminate=some&&!all;}} disabled={selection.disabled||!projected.length} onChange={()=>selection.onAll(!all)}/></th>}{policyRecordFields.map(field=><th key={field}>{field}</th>)}<th>操作</th></tr></thead><tbody>{projected.map(r=><React.Fragment key={r.id}><tr id={'approval-record-'+r.id} className={focusedId===r.id?'approval-record-focused':''}>
  {selection&&<td><input type="checkbox" aria-label={'选择 '+approvalTitle(r)} checked={selected.includes(r.id)} disabled={selection.disabled} onChange={()=>selection.onToggle(r.id)}/></td>}
  <PolicyRecordCells record={r.policy_record||{name:approvalTitle(r),scope:scopeLabel(r),target:(r.change_items||[]).map(c=>c.label+'：'+c.before+' → '+c.after).join('；')||'已保存的策略变更',operation:'策略配置变更',conditions:'以当前配置核验为准',effect:'按已保存配置',status:r.configuration_status?.label||'状态待核验'}} scope={r.scope_type==='system'?<SystemAudience data={r}/>:<><span>{r.target_name}</span><small>{scopeLabel(r)}</small><details><summary>关联信息</summary><small>适用 Agent</small>{(r.agents||[]).map(a=><AgentLocation key={a.id} agent={a} navigate={navigate}/>)}<small>生成会话</small><SessionLocations data={r} navigate={navigate}/></details></>} name={<><strong title={approvalTitle(r)}>{approvalTitle(r)}</strong><small>{date(r.created_at)}</small><button className="approval-dsl-toggle" aria-expanded={expanded.includes(r.id)} aria-controls={"approval-dsl-"+r.id} onClick={()=>setExpanded(old=>old.includes(r.id)?old.filter(id=>id!==r.id):[...old,r.id])}>DSL</button>{r.reason&&needs(r.status)&&<small className="approval-record-reason">{r.reason}</small>}</>}/>
  <td><ApprovalRecordActions row={r} onAction={onAction} onRevalidate={onRevalidate} busy={busy}/></td>
 </tr>{expanded.includes(r.id)&&<tr className="approval-dsl-row" id={"approval-dsl-"+r.id}><td colSpan={policyRecordFields.length+1+(selection?1:0)}><ApprovalDsl data={r}/></td></tr>}</React.Fragment>)}</tbody></table></div>;
}

export default function PolicyApprovals({api,post,navigation:n,navigate,onChanged}){
 const request=useRef(null);
 const [recovering,setRecovering]=useState(null),[page,setPage]=useState(null),[located,setLocated]=useState(null),[tab,setTab]=useState('pending'),[q,setQ]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 const [checked,setChecked]=useState([]),[batch,setBatch]=useState(null),[showCleared,setShowCleared]=useState(false),[focused,setFocused]=useState('');
 useEffect(()=>{let alive=true;async function load(){try{const value=await api('/api/console/approvals'+(showCleared?'?cleared=true':''));if(alive){setPage(value);setError('');}}catch(e){if(alive)setError(e.message);}}load();const timer=setInterval(load,7000);return()=>{alive=false;clearInterval(timer);};},[api,revision,showCleared]);
 useEffect(()=>{let alive=true;if(!n.approvalId){setFocused('');return;}api('/api/console/approvals/'+encodeURIComponent(n.approvalId)).then(row=>{
  if(!alive)return;
  if(row.replacement_approvals?.length){const child=row.replacement_approvals.find(r=>r.configuration_id===n.approvalRecordId);navigate({approvalId:child?.id||'',approvalRecordId:''});return;}
  setLocated(row);setFocused(row.id);setTab(tabFor(row));
 }).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[api,n.approvalId,n.approvalRecordId,revision]);
 useEffect(()=>{if(focused&&page)document.getElementById('approval-record-'+focused)?.scrollIntoView({block:'center'});},[focused,page?.records?.length]);
 const rows=(page?.records||[]).filter(r=>!!r.cleared===showCleared),projected=approvalPolicyRows(rows),visible=projected.filter(r=>tabFor(r)===tab&&matchesApproval(r,q));
 const counts=Object.fromEntries(['pending','approved','attention','processed'].map(t=>[t,projected.filter(r=>tabFor(r)===t).length]));
 const chosen=visible.filter(r=>checked.includes(r.id)),locked=busy||!!batch,action=showCleared?'restore':batchActionFor(tab);
 const selection={ids:chosen.map(r=>r.id),disabled:locked,onToggle:id=>setChecked(old=>old.includes(id)?old.filter(v=>v!==id):[...old,id]),onAll:value=>setChecked(value?visible.map(r=>r.id):[])};
 function changeTab(value){setChecked([]);setTab(value);}
 async function decide(row,decision){if(busy)return;setBusy(true);setError('');try{
  const current=await api('/api/console/approvals/'+encodeURIComponent(row.id));
  if(current.id!==row.id||current.candidate_hash!==row.candidate_hash)throw Error('策略内容已变化，请刷新后重新核对。');
  const fingerprint=row.id+':'+decision+':'+row.candidate_hash+':'+row.approval_hash;
  if(request.current?.fingerprint!==fingerprint)request.current={fingerprint,key:crypto.randomUUID()};
  const body=decision==='split'?{}:{proposal_hash:row.candidate_hash||row.proposal_hash,...(decision!=='reject'?{request_key:request.current.key}:{}),...(decision==='apply'?{approval_hash:row.approval_hash}:{})};
  await post(approvalDecisionUrl(row.id,decision),body);request.current=null;setChecked([]);setRevision(v=>v+1);onChanged?.();
 }catch(e){setError(e.message);}finally{setBusy(false);}}
 function recover(row){if(row.revalidation?.available)setRecovering(row);else navigate(row.revalidation.destination);}
 return <div className="content approval-workbench">
  <div className="approval-toolbar"><div className="approval-filter-tabs" role="tablist" aria-label="审批记录">{[['pending','待审批'],['approved','待应用'],['attention','需要处理'],['processed','已处理']].map(([value,label])=><button key={value} role="tab" disabled={locked} aria-selected={tab===value} onClick={()=>changeTab(value)}>{label} <span>{counts[value]}</span></button>)}</div><div className="approval-list-tools"><button className="button tiny ghost" disabled={locked} onClick={()=>{setChecked([]);setShowCleared(v=>!v);if(!showCleared&&['pending','approved'].includes(tab))setTab('processed');}}>{showCleared?'返回审批列表':'已清理记录'+(page?.cleared_count?' '+page.cleared_count:'')}</button><button className="button tiny ghost" disabled={locked} onClick={()=>{setChecked([]);setRevision(v=>v+1);}}>刷新</button></div></div>
  <div className="approval-search"><input type="search" aria-label="搜索审批记录" placeholder="搜索策略、Agent、会话或 PID" value={q} disabled={locked} onChange={e=>{setChecked([]);setQ(e.target.value);}}/><span>每条策略独立审批，批准后再单独应用。</span></div>
  {showCleared&&<p>正在查看已清理记录，保留原审批状态。</p>}{tab==='attention'&&!showCleared&&<p className="approval-attention-note">需要处理：包括需重新校验、校验未通过、应用未完成和暂不能应用的记录。</p>}
  <div className="approval-batch-toolbar" aria-label="审批批量操作"><button className="button tiny ghost" disabled={locked||!visible.length} onClick={()=>selection.onAll(chosen.length!==visible.length)}>{chosen.length&&chosen.length===visible.length?'取消全选':'全选当前结果'}</button><span>已选 {chosen.length} 条记录</span>
   {showCleared?<><button className="button tiny ghost" disabled={locked||!visible.length} onClick={()=>setBatch({action:'restore',rows:visible})}>恢复当前结果</button><button className="button tiny primary" disabled={locked||!chosen.length} onClick={()=>setBatch({action:'restore',rows:chosen})}>恢复所选</button></>:<><button className="button tiny ghost" disabled={locked||!visible.some(r=>r.can_clear)} onClick={()=>setBatch({action:'clear',rows:visible})}>清理当前结果</button><button className="button tiny ghost" disabled={locked||!chosen.some(r=>r.can_clear)} onClick={()=>setBatch({action:'clear',rows:chosen})}>清理所选</button>{action&&<button className="button tiny primary" disabled={locked||!chosen.length} onClick={()=>setBatch({action,rows:chosen})}>{batchActionLabel(action)}</button>}</>}
  </div>
  {error&&<p role="alert" className="inline-notice warning">{error}</p>}<div className="approval-records"><ApprovalRecords rows={visible} focusedId={focused} navigate={navigate} selection={selection} onAction={decide} onRevalidate={recover} busy={locked}/>{!visible.length&&<p>{page?'当前没有匹配的审批记录。':'正在读取审批记录…'}</p>}</div>
  {recovering&&<ApprovalRevalidation key={recovering.id} data={recovering} api={api} post={post} onClose={()=>setRecovering(null)} navigate={target=>{setRecovering(null);navigate(target);}} onCreated={result=>{setRecovering(null);setTab('pending');setQ('');setRevision(v=>v+1);navigate({approvalId:result.id,approvalRecordId:''});onChanged?.();}}/>}
  {batch&&<ApprovalBatch {...batch} api={api} post={post} onClose={()=>setBatch(null)} onFinished={()=>{setChecked([]);setRevision(v=>v+1);onChanged?.();}} onOpenRecord={id=>{setBatch(null);navigate({approvalId:id,approvalRecordId:''});}} onReturnConfig={target=>{setBatch(null);navigate(target);}}/>}
 </div>;
}
