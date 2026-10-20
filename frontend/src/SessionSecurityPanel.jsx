import React,{useEffect,useRef,useState} from 'react';
import RecordBadge from './RecordBadge.jsx';
import {currentLoadedView} from './productStatus.mjs';
import {useEvidenceClock} from './ProductStatus.jsx';
import './sessionSecurity.css';

export const loadedScopeNames={system:'系统策略',agent:'Agent 策略'};
const operations={read:'读取',write:'写入／修改',unlink:'删除',exec:'执行程序',connect:'建立连接'};
const effects={block:'阻断',kill:'终止进程',notify:'通知',report:'上报'};
const unique=values=>[...new Set(values.filter(Boolean))];
const targets=record=>unique(record.clauses.map(c=>[c.target,c.argument].filter(Boolean).join(' ')));

export function LoadedPolicyDetails({record,onClose}){
 const dialog=useRef(null),origin=useRef(document.activeElement);
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 return <dialog ref={dialog} className="record-drawer loaded-policy-detail" aria-label="已加载策略详情" onCancel={e=>{e.preventDefault();onClose();}}>
  <header className="record-drawer-head"><div><small>{loadedScopeNames[record.scope]} · 加载快照</small><h2>{record.name}</h2></div><button className="button tiny ghost" onClick={onClose}>关闭</button></header>
  <div className="record-drawer-body">
   <p className="field-note">此快照是打开详情时核验的加载版本。同一 Agent 进程内的会话共享策略，不代表本会话已触发。</p>
   {record.description&&<p>{record.description}</p>}
   <p>{record.configuration_revision?'当前加载配置 v'+record.configuration_revision:'未记录对应的配置版本。'}</p><h3>策略内容</h3>
   {record.clauses.map((c,i)=><section className="loaded-policy-clause" key={c.clause_hash+':'+i}><b>{operations[c.operation]||c.operation} · {effects[c.effect]||c.effect}</b><code>{[c.target,c.argument].filter(Boolean).join(' ')}</code>{c.reason&&<p>{c.reason}</p>}<details><summary>完整条件</summary><pre>{c.condition}</pre></details></section>)}
   {record.label_sources?.length>0&&<section><h3>引用的标签来源</h3>{record.label_sources.map(s=><p key={s.id+':'+s.version}><b>{s.label}</b> · 来源版本 {s.version}<code>{s.value}</code></p>)}</section>}

  </div>
 </dialog>;
}

export default function SessionSecurityPanel({data,loading,error,onConfiguration}){
 const raw=data?.loaded_policies,now=useEvidenceClock(raw?.expires_at);
 const view=currentLoadedView(raw,Math.max(now,Date.now())),[scope,setScope]=useState(''),[detail,setDetail]=useState(null);
 useEffect(()=>{setDetail(null);setScope('');},[raw?.instance_id,raw?.generation,raw?.bundle_hash]);
 if(loading&&!view)return <p role="status" className="task-empty">正在核验当前已加载策略…</p>;
 if(!view)return <p role="alert" className="inline-notice warning">未取得当前加载证据，请刷新重试；不会用已保存配置代替加载结果。</p>;
 const retained=view.historical===true;
 const records=(view.records||[]).filter(r=>r.status==='loaded'&&Object.hasOwn(loadedScopeNames,r.scope));
 const shown=records.filter(r=>!scope||r.scope===scope);
 return <div className="session-security-panel">
  <div className="session-security-toolbar"><div><strong>{retained?'上次核验策略':'当前已加载策略'}</strong><span>{retained?(records.length?records.length+' 项 · 当前未核验':'暂无上次核验记录'):view.coverage_complete?records.length+' 项策略':records.length?'已核验 '+records.length+' 项 · 清单不完整':'暂未确认'}</span></div><label className="loaded-policy-filter">策略归属<select aria-label="筛选策略归属" value={scope} onChange={e=>setScope(e.target.value)}><option value="">全部策略</option>{Object.entries(loadedScopeNames).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label></div>
  <p className="session-coverage">{view.notice}</p>
  {view.message&&<p role={view.state==='unverified'||view.state==='incomplete'?'alert':'status'} className="inline-notice warning">{view.message}</p>}
  {shown.length>0?<div className="session-security-table-wrap"><table className="session-security-table loaded-policy-table" aria-label={retained?'上次核验的 ActPlane 策略':'当前已加载到 ActPlane 的策略'}><thead><tr><th>策略名称／对象</th><th>归属</th><th>操作／处置</th><th>状态</th><th>操作</th></tr></thead><tbody>{shown.map(r=><tr key={r.id}>
   <td><strong>{r.name}</strong>{targets(r).slice(0,2).map(t=><code key={t}>{t}</code>)}{targets(r).length>2&&<small>另 {targets(r).length-2} 个对象，见详情</small>}{r.label_sources?.length>0&&<small>{r.label_sources[0].label} 来源：{r.label_sources[0].value}{r.label_sources.length>1?' 等 '+r.label_sources.length+' 项':''}</small>}</td>
   <td>{loadedScopeNames[r.scope]}{r.source_kind==='startup'&&<small>启动规则</small>}</td>
   <td>{unique(r.clauses.map(c=>(operations[c.operation]||c.operation)+' · '+(effects[c.effect]||c.effect))).map(t=><div key={t}>{t}</div>)}</td>
   <td><RecordBadge tone={retained?'neutral':'good'}>{retained?'上次核验':'已加载'}</RecordBadge></td>
   <td><button className="button tiny ghost" onClick={()=>setDetail(r)}>详情</button>{r.document_id&&onConfiguration&&<button className="button tiny ghost" onClick={()=>onConfiguration(r.scope==='system'?'system':view.instance_id,r.document_id)}>到系统查看</button>}</td>
  </tr>)}</tbody></table></div>:<p className="task-empty">{view.coverage_complete?(scope?'此归属当前没有已加载策略。':'当前没有已加载策略。'):'仅展示能够核验的当前内核加载结果。'}</p>}
  {detail&&<LoadedPolicyDetails record={detail} onClose={()=>setDetail(null)}/>}
 </div>;
}
