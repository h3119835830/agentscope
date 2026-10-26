import React from 'react';
import {DslCode} from './DslCode.jsx';
import {approvalDslDocuments} from './approvalDsl.mjs';

export default function ApprovalDsl({data,plan}){
 const documents=approvalDslDocuments(data,plan);
 return <div className="approval-dsl">{documents.length?documents.map(d=><section key={d.id}>
  {(documents.length>1||d.removal)&&<small>{d.removal?'停用此 DSL':'本条 DSL'} · {d.name}</small>}
  <DslCode text={d.text}/>
 </section>):<><p>此记录未保存可展示的 DSL。</p>{(data.change_items||[]).map((c,i)=><p key={i}>{c.label}：{c.before} → {c.after}</p>)}</>}
 {data.configuration_records?.some(r=>r.template?.id==='RQ1-GENERATED')&&<small>只按程序执行链匹配，不核验具体脚本、参数或报告内容。</small>}
 </div>;
}
