import React,{useEffect,useRef,useState} from 'react';
import {DslCode} from './DslCode.jsx';
import {approvalLabel,disposition} from './policyExperience.mjs';
import {operationLabel} from './policyRecordPresentation.mjs';
import {approvalTitle,processLabel} from './approvalPresentation.mjs';
import {batchActionLabel,prepareApprovalBatch,executeApprovalBatch} from './approvalBatch.mjs';
import './approvalBatch.css';

function Content({entry}){
 const data=entry.data,plan=entry.plan,previous=data.previous_documents;
 const changed=data.documents?.filter(d=>!previous?.some(p=>p.id===d.id&&p.original_dsl===d.original_dsl))||[];
 const records=previous?data.records?.filter(r=>changed.some(d=>d.id===r.document_id)):data.records;
 return <details className="approval-batch-content"><summary>查看变更内容</summary>
 {plan?plan.comparisons.map((c,i)=><section key={i}><strong>{c.name}</strong><p>{c.before_version?'原 v'+c.before_version:'原候选'} → {c.after_version?'本次 v'+c.after_version:c.removal?'停用':'保留原内容'} · {c.same_content?'内容一致':'内容已变化，请核对'}</p><p>{c.after_summary}</p>{c.before_dsl&&<details><summary>查看原文对照</summary><small>原候选</small><DslCode text={c.before_dsl}/><small>本次采用</small><DslCode text={c.after_dsl||'移除此文档'}/></details>}</section>):<>
 {(data.change_items||[]).map((c,i)=><p key={i}><strong>{c.label}</strong>：{c.before} → {c.after}</p>)}
 {(records||[]).map(r=><section key={r.id}><strong>{r.statement}</strong>{r.clauses.map((c,i)=><p key={i}>{disposition(c.effect)} · {operationLabel(c.operation)} · {c.target}</p>)}</section>)}
 {(data.document_changes?.removed||[]).map((name,i)=><p key={i}>停用：{name}</p>)}
 {!!data.documents?.length&&<details><summary>完整 DSL 与原配置</summary>{previous?.map(d=><section key={'old'+d.id}><strong>原配置 · {d.name}</strong><DslCode text={d.original_dsl}/></section>)}{data.documents.map(d=><section key={d.id}><strong>候选 · {d.name}</strong><DslCode text={d.original_dsl}/></section>)}</details>}
 </>}
 </details>;
}
export default function ApprovalBatch({rows,action,api,post,onClose,onFinished,onOpenRecord,onReturnConfig}){
 const dialog=useRef(null),origin=useRef(document.activeElement),alive=useRef(true);
 const [batch,setBatch]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[ack,setAck]=useState(false),[results,setResults]=useState(null),[done,setDone]=useState(false);
 useEffect(()=>{alive.current=true;dialog.current?.showModal();prepareApprovalBatch(rows,action,api).then(value=>{if(alive.current)setBatch(value);}).catch(e=>{if(alive.current)setError(e.message);});return()=>{alive.current=false;dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 const eligible=batch?.entries.filter(e=>!e.error).length||0,entries=results||batch?.entries||[],label=batchActionLabel(action);
 async function run(){if(!batch||!ack||busy||done||!eligible)return;setBusy(true);try{const values=await executeApprovalBatch(batch,api,post,value=>{if(alive.current)setResults(value);});if(alive.current){setResults(values);setDone(true);onFinished();}}catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setBusy(false);}}
 return <dialog ref={dialog} className="policy-review-dialog approval-batch-dialog" aria-label={label} onCancel={e=>{e.preventDefault();if(!busy)onClose();}}>
 <header className="experience-detail-head"><div><small>已选择 {rows.length} 项记录</small><h2>{label}</h2></div><button className="experience-close" aria-label="关闭批量操作" disabled={busy} onClick={onClose}>×</button></header>
 <div className="experience-detail-body">
 <p className="experience-note">{action==='clear'?'从列表收起记录，保留原始记录与审计；已生效策略继续执行。可在“已清理记录”中恢复。':action==='restore'?'恢复记录在原状态列表中的可见性，审批状态与执行策略保持原样。':action==='approve'?'批准只保存决定，之后仍需单独应用。':action==='apply'?'应用将逐项核对批准回执，并可能暂停、重建受影响 Agent，影响其全部会话。':'重新校验只创建新候选，新候选仍需重新批准并单独应用。'}</p>
 {action==='apply'&&<p className="experience-note">按列表顺序逐项处理；基线或范围发生变化时保留失败结果，不自动合并或重新批准。</p>}
 {!batch&&!error&&<p role="status">正在读取所选记录的内容与范围…</p>}{error&&<p role="alert" className="inline-notice warning">{error}</p>}
 {batch&&<><p className="approval-batch-summary" role="status">{done?`处理完成：已提交 ${entries.filter(e=>['success','unverified'].includes(e.outcome)).length} 项，失败 ${entries.filter(e=>e.outcome==='failed').length} 项，跳过 ${entries.filter(e=>e.outcome==='skipped').length} 项。`:busy?`正在处理 ${results?.length||0} / ${batch.entries.length} 项…`:`可处理 ${eligible} 项，其余 ${batch.entries.length-eligible} 项将跳过。`}</p>
 <div className="table-scroll"><table className="approval-batch-table" aria-label="批量操作记录"><thead><tr><th>策略与变更</th><th>作用范围</th><th>状态与结果</th></tr></thead><tbody>{batch.entries.map(entry=>{const result=results?.find(r=>r.id===entry.id),data=entry.data;return <tr key={entry.id}><td><strong>{approvalTitle(data)}</strong>{!entry.error&&!['clear','restore'].includes(action)&&<Content entry={entry}/>}</td><td>{data.scope_type==='system'?'全部受控 Agent':data.target_name}{data.scope_type!=='system'&&data.agents?.length>0&&<small>{data.agents.map(processLabel).join('、')}</small>}<small>{data.scope_type==='system'?`涉及 ${entry.plan?.target_count??data.total_affected_count??0} 个实例`:data.scope_label}</small></td><td>{result?<><span>{result.outcome==='success'?(action==='clear'?(result.cleared?'已清理，审计保留':'记录状态已变化，保持可见'):action==='restore'?'已恢复':approvalLabel(result.status)):result.outcome==='failed'?'处理失败':result.outcome==='skipped'?'已跳过':'状态待核验'}</span>{result.message&&<p>{result.message}</p>}{result.outcome==='success'&&<button className="assistant-text-button" disabled={busy} onClick={()=>onOpenRecord(result.resultId)}>查看{action==='revalidate'?'新候选':'记录'} ↗</button>}</>:entry.error?<><span>将跳过</span><p>{entry.error}</p></>:<span>{approvalLabel(data.status)}</span>}{(entry.error||['failed','skipped'].includes(result?.outcome))&&data.revalidation?.destination&&<button className="assistant-text-button" disabled={busy||!onReturnConfig} onClick={()=>onReturnConfig(data.revalidation.destination)}>返回所属配置 ↗</button>}</td></tr>;})}</tbody></table></div></>}
 </div><footer className="experience-detail-footer">{!done&&batch&&<label className="flow-ack"><input type="checkbox" checked={ack} disabled={busy||!eligible} onChange={e=>setAck(e.target.checked)}/>{['clear','restore'].includes(action)?'已核对所选记录，原始记录与审计保留':'已核对所选变更内容与作用范围'}</label>}<div className="actions"><button className="button ghost" disabled={busy} onClick={onClose}>{done?'关闭':'取消'}</button>{!done&&<button className="button primary" disabled={!batch||!eligible||!ack||busy} onClick={run}>{busy?'正在处理…':`确认${label}${eligible?' '+eligible+' 项':''}`}</button>}</div></footer>
 </dialog>;
}
