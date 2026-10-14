import React,{useEffect,useRef,useState} from 'react';
import {DslCode} from './DslCode.jsx';
export default function ApprovalRevalidation({data,api,post,onClose,onCreated,navigate}){
 const dialog=useRef(null),origin=useRef(document.activeElement),alive=useRef(true),attempt=useRef(null);
 const [plan,setPlan]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[ack,setAck]=useState(false);
 const endpoint='/api/console/approvals/'+encodeURIComponent(data.id);
 async function load(){setLoading(true);setError('');setAck(false);setPlan(null);try{const next=await api(endpoint+'/revalidation');if(alive.current)setPlan(next);}catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setLoading(false);}}
 useEffect(()=>{alive.current=true;dialog.current?.showModal();load();return()=>{alive.current=false;dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[endpoint]);
 async function create(){if(!ack||!plan||busy)return;setBusy(true);setError('');try{if(attempt.current?.hash!==plan.plan_hash)attempt.current={hash:plan.plan_hash,key:crypto.randomUUID()};const result=await post(endpoint+'/revalidate',{plan_hash:plan.plan_hash,request_key:attempt.current.key});if(alive.current)onCreated(result);}catch(e){if(alive.current)setError(e.message);}finally{if(alive.current)setBusy(false);}}
 return <dialog ref={dialog} className="policy-review-dialog approval-revalidation-dialog" aria-label="重新校验策略" onCancel={e=>{e.preventDefault();if(!busy)onClose();}}>
  <header className="experience-detail-head"><div><small>重新校验</small><h2>{data.name}</h2></div><button className="experience-close" aria-label="关闭重新校验" disabled={busy} onClick={onClose}>×</button></header>
  <div className="experience-detail-body">{loading&&<p role="status">正在读取当前配置、策略基线和执行目标…</p>}{error&&<p role="alert" className="inline-notice warning">{error}</p>}
   {plan&&<><p>{plan.message}</p><p className="approval-revalidation-scope"><strong>{plan.scope_label}</strong><span>本次涉及 {plan.target_count} 个实例</span></p>
    <div className="table-scroll"><table className="approval-change-table" aria-label="重新校验配置对照"><thead><tr><th>策略</th><th>原候选</th><th>本次采用</th></tr></thead><tbody>{plan.comparisons.map((c,i)=><tr key={i}><th><span className="approval-revalidation-name">{c.name}</span></th><td>{c.before_version?`v${c.before_version}`:'原候选内容'}<small>{c.before_summary|| (c.removal?'原停用目标':'原策略内容')}</small></td><td>{c.after_version?`v${c.after_version}`:c.removal?'仍停用此文档':'保留原候选内容'}<small>{c.after_summary}</small><span className={'approval-revalidation-content '+(c.same_content?'same':'changed')}>{c.same_content?'内容一致':'内容已变化，请核对'}</span></td></tr>)}</tbody></table></div>
    {plan.comparisons.some(c=>c.before_dsl)&&<details className="policy-inheritance"><summary>查看配置原文与差异</summary>{plan.comparisons.filter(c=>c.before_dsl).map((c,i)=><section key={i}><h3>{c.name}</h3><div className="dsl-diff"><section><h4>原候选</h4><DslCode text={c.before_dsl}/></section><section><h4>本次采用</h4><DslCode text={c.after_dsl}/></section></div></section>)}</details>}
    <p className="experience-note">重新校验只编译并创建新候选，不批准、不应用，也不重启 Agent。</p></>}
  </div>
  <footer className="experience-detail-footer"><div>{plan&&<label className="flow-ack"><input type="checkbox" checked={ack} disabled={busy} onChange={e=>setAck(e.target.checked)}/>已核对本次采用的配置与范围</label>}<button className="assistant-text-button" disabled={busy} onClick={()=>navigate?.(data.revalidation.destination)}>返回所属配置</button></div><div className="actions"><button className="button ghost" disabled={busy} onClick={onClose}>取消</button>{error&&<button className="button ghost" disabled={busy||loading} onClick={load}>重新读取</button>}<button className="button primary" disabled={!plan||!ack||busy||loading} onClick={create}>{busy?'正在校验…':'校验并生成新候选'}</button></div></footer>
 </dialog>;
}
