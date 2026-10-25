import React,{useEffect,useState} from 'react';
import RecordBadge from './RecordBadge.jsx';
import LifecycleSettings from './LifecycleSettings.jsx';
import {publicAuditText} from './auditPresentation.mjs';

const stages={runtime:'运行时评估',postrun:'运行后审计'},states={queued:'等待分析',running:'正在分析',completed:'已完成',failed:'分析失败'};
const categories={integrity:'完整性',confidentiality:'保密性',availability:'可用性',workflow:'流程风险',uncertain:'待核实'};
const dispositions={confirmed_risk:'已确认风险',false_positive:'已确认误报',needs_investigation:'待进一步调查'};
const severity={low:'低',medium:'中',high:'高',uncertain:'待核实'};
const outcomes={blocked_attempt:'尝试已被阻止',process_killed:'进程已终止',needs_review:'尚需核实'};
const integrityLabel=value=>value===true?'与登记基线一致':value===false?'发生变化，需核实':'无法完成核对，完整性未知';

function ResultSummary({job}){
 const result=job.result;
 if(job.state==='failed')return '本次分析未完成，不代表已通过审计。';
 if(!result)return '尚无结论';
 const text=job.stage==='postrun'?`发现 ${result.findings?.length||0} 项审计结论，请展开核对证据。`:
  result.decision==='no_change'?'当前证据下无需新增策略':'已起草候选，等待人工核对；尚未应用。';
 const analysis=publicAuditText(result.summary||result.generation?.summary);
 return <>{text}{analysis&&<details className="audit-analysis"><summary>查看分析说明</summary><p>{analysis}</p></details>}</>;
}

export function AuditRecords({data,post,root,onRefresh,navigate}){
 const [selected,setSelected]=useState(null),[disposition,setDisposition]=useState('needs_investigation'),[note,setNote]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function review(e){e.preventDefault();setBusy(true);setError('');try{await post(root+'/jobs/'+encodeURIComponent(selected.job.id)+'/review',{input_hash:selected.job.input_hash,finding_id:selected.finding.id,disposition,note});setSelected(null);setNote('');onRefresh();}catch{setError('复核记录未保存，请检查连接后重试。');}finally{setBusy(false);}}
 async function retry(job){setBusy(true);setError('');try{await post(root+'/jobs/'+encodeURIComponent(job.id)+'/retry',{input_hash:job.input_hash});onRefresh();}catch{setError('分析未重新排队，请刷新记录后重试。');}finally{setBusy(false);}}
 return <>{!data.configuration?.enabled&&<p className="inline-notice">当前 Agent 尚未启用自动评估与审计。工具和内核原始记录仍可在运行事件中查看。</p>}{error&&<p role="alert" className="inline-notice warning">{error}</p>}
 {(data.records||[]).length?<div className="table-scroll"><table className="session-events"><thead><tr><th>阶段／时间</th><th>状态</th><th>结论</th><th>操作</th></tr></thead><tbody>{data.records.map(job=><tr key={job.id}>
  <td><b>{stages[job.stage]}</b><small>{new Date(job.created_at).toLocaleString('zh-CN',{hour12:false})}</small></td>
  <td><RecordBadge tone={job.state==='failed'?'bad':job.state==='completed'?'good':'neutral'}>{states[job.state]||'状态待核实'}</RecordBadge></td>
  <td><ResultSummary job={job}/>
   {job.result?.findings?.map(f=>{const review=(data.reviews||[]).filter(r=>r.job_id===job.id&&r.finding_id===f.id).at(-1);return <details key={f.id}>
    <summary>{categories[f.category]} · {severity[f.severity]} · {outcomes[f.outcome]||'待核实'}</summary><p>{publicAuditText(f.explanation)}</p>
    <p>引用 {f.evidence_ids.length} 条已读取证据 · {review?dispositions[review.disposition]:'尚未人工复核'}</p>{review&&<p>复核说明：{review.note}</p>}
    {post&&<button className="button tiny ghost" onClick={()=>{setSelected({job,finding:f});setNote('');}}>标记／复核</button>}</details>;})}
   {job.result?.integrity?.length>0&&<details><summary>文件完整性核对</summary>{job.result.integrity.map(f=><p key={f.path}><code>{f.path}</code> · {integrityLabel(f.unchanged)}</p>)}<p>仅比较登记与审计时的文件摘要，不代表持续监控。</p></details>}
  </td>
  <td>{job.state==='failed'&&post&&<button className="button tiny ghost" disabled={busy} onClick={()=>retry(job)}>重试分析</button>}{job.result?.decision==='needs_approval'&&<button className="button tiny ghost" onClick={()=>navigate({page:'approvals'})}>查看审批</button>}</td>
 </tr>)}</tbody></table></div>:<p className="task-empty">本会话暂无自动评估或审计记录。</p>}
 {selected&&<form className="inline-notice" onSubmit={review}><label>人工复核<select value={disposition} onChange={e=>setDisposition(e.target.value)}>{Object.entries(dispositions).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><label>复核说明<textarea required maxLength={2000} value={note} onChange={e=>setNote(e.target.value)}/></label><p>只追加复核意见，不改原始证据、模型结论或已加载策略。</p><button className="button primary" disabled={busy||!note.trim()}>保存复核</button><button type="button" className="button ghost" disabled={busy} onClick={()=>setSelected(null)}>取消</button></form>}
 <p className="session-coverage">策略命中不等于恶意或实际损害；未关联事件与未采集操作不在本次审计覆盖范围内。候选策略仍须单独审批和应用。</p></>;
}

export default function SessionAudit({instanceId,sessionId,api,post,navigate}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 const root='/api/policy-lifecycle/'+encodeURIComponent(instanceId);
 useEffect(()=>{let alive=true,inflight=false;async function load(){if(inflight)return;inflight=true;try{const value=await api(root+'?session_id='+encodeURIComponent(sessionId));if(alive){setData(value);setError('');}}catch{if(alive)setError('审计记录读取失败，请检查连接后刷新。');}finally{inflight=false;}}load();const timer=setInterval(load,7000);return()=>{alive=false;clearInterval(timer);};},[root,sessionId,api,revision]);
 return <>{error&&<p role="alert" className="inline-notice warning">{error}</p>}{data?<><AuditRecords data={data} root={root} post={post} navigate={navigate} onRefresh={()=>setRevision(v=>v+1)}/>{post&&<LifecycleSettings key={data.configuration?.baseline_at||'unconfigured'} instanceId={instanceId} configuration={data.configuration} api={api} post={post} onSaved={()=>setRevision(v=>v+1)}/>}</>:!error&&<p role="status" className="task-empty">正在读取审计记录…</p>}</>;
}
