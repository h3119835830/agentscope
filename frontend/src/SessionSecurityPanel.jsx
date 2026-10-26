import React,{useEffect,useRef,useState} from 'react';
import RecordBadge from './RecordBadge.jsx';
import PolicyRecordHead from './PolicyRecordHead.jsx';
import {policyAction,clauseAction} from './policyRecordPresentation.mjs';
import {currentLoadedView} from './productStatus.mjs';
import {useEvidenceClock} from './ProductStatus.jsx';
import './sessionSecurity.css';

export const loadedScopeNames={system:'系统策略',agent:'Agent 策略'};
const operations={read:'读取',write:'写入／修改',unlink:'删除',exec:'执行程序',connect:'建立连接'};
const stages={startup:'运行前',runtime:'运行时'};
const source=record=>record.source_label||'运行前 · '+(record.scope==='system'?'系统继承':'Agent 继承');
export function LoadedPolicyDetails({record,onClose}){
 const dialog=useRef(null),origin=useRef(document.activeElement);
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 const dsl=record.compilation?.dsl||record.original_dsl;
 return <dialog ref={dialog} className="record-drawer loaded-policy-detail" aria-label="已加载策略详情" onCancel={e=>{e.preventDefault();onClose();}}>
  <header className="record-drawer-head"><div><small>{source(record)}</small><h2>{record.name}</h2></div><button className="button tiny ghost" onClick={onClose}>关闭</button></header>
  <div className="record-drawer-body">
   {record.description&&<p>{record.description}</p>}
   {record.configuration_revision&&<p>加载时配置 v{record.configuration_revision}</p>}
   {record.statement&&<p>{record.statement}</p>}
   {(record.clauses||[]).map((c,i)=><section className="loaded-policy-clause" key={c.clause_hash+':'+i}><b>{operations[c.operation]||c.operation} · {policyAction(c.effect)}</b><code>{[c.target,c.argument].filter(Boolean).join(' ')}</code>{c.reason&&<p>{c.reason}</p>}<details><summary>完整条件</summary><pre>{c.condition}</pre></details></section>)}
   {record.trigger?.text&&<section><h3>触发原文</h3><p>{record.trigger.text}</p></section>}
   {record.template_reference&&<section><h3>参考模板</h3><p>{record.template_reference.items?.length?record.template_reference.items.map(t=>t.name).join('、'):record.template_reference.searched?'已检索已审核模板，未引用具体模板。':'未记录模板引用。'}</p></section>}
   {record.label_sources?.length>0&&<section><h3>引用的标签来源</h3>{record.label_sources.map(s=><p key={s.id+':'+s.version}><b>{s.label}</b> · 来源版本 {s.version}<code>{s.value}</code></p>)}</section>}
   {dsl&&<details className="runtime-policy-dsl"><summary>查看 DSL</summary><pre>{dsl}</pre></details>}
  </div>
 </dialog>;
}

export default function SessionSecurityPanel({data,loading,error}){
 const raw=data?.loaded_policies,now=useEvidenceClock(raw?.expires_at);
 const current=currentLoadedView(raw,Math.max(now,Date.now()));
 const projection=data?.policy_records;
 const [stage,setStage]=useState(''),[detail,setDetail]=useState(null);
 useEffect(()=>{setDetail(null);setStage('');},[projection?.instance_id,projection?.session_id,raw?.instance_id,raw?.generation]);
 const records=projection?.records||(current?.records||[]).filter(r=>r.status==='loaded'&&Object.hasOwn(loadedScopeNames,r.scope));
 const live=current&&!current.historical&&current.loading_status?.state==='loaded';
 const shown=records.filter(r=>!stage||(r.stage||'startup')===stage);
 if(loading&&!data)return <p role="status" className="task-empty">正在读取策略…</p>;
 return <div className="session-security-panel">
  <div className="session-security-toolbar"><span/>
   <label className="loaded-policy-filter">策略来源<select aria-label="筛选策略来源" value={stage} onChange={e=>setStage(e.target.value)}><option value="">全部策略</option>{Object.entries(stages).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
  </div>
  {!live&&records.length>0&&<p className="session-coverage">当前加载状态未核验，以下为保存的继承和追加记录。</p>}
  {error&&<p role="alert" className="runtime-policy-notice">暂时无法刷新，继续显示已读取的记录。</p>}
  {shown.length>0?<div className="runtime-policies"><table aria-label="会话策略记录"><PolicyRecordHead status/><tbody>{shown.map(r=><tr key={r.id}>
   <td><span className="runtime-policy-name">{r.name}</span></td>
   <td>{policyAction(r.default_action||clauseAction(r.clauses))}</td>
   <td>{source(r)}</td>
   <td><RecordBadge tone={live&&r.status==='loaded'?'good':'neutral'}>{r.status==='loaded'&&live?'已加载':r.stage==='runtime'&&r.status==='applied'?'已追加 · 当前未核验':'历史加载'}</RecordBadge></td>
   <td className="runtime-policy-actions"><button className="runtime-policy-action" onClick={()=>setDetail(r)}>详情</button></td>
  </tr>)}</tbody></table></div>:<p className="task-empty">{loading?'正在读取策略…':stage?'没有此来源的策略记录。':'暂无可展示的继承或追加策略记录。'}</p>}
  {detail&&<LoadedPolicyDetails record={detail} onClose={()=>setDetail(null)}/>}
 </div>;
}
