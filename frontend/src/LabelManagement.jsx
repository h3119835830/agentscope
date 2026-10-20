import React,{useEffect,useRef,useState} from 'react';
import {configurationAgentLabel} from './policyConfigurationPresentation.mjs';
import {staleSourceSelections} from './informationFlowPresentation.mjs';
import './labelManagement.css';

export function LabelSourceSummary({sources=[],scopeLabel,documents=[]}){
 const rows=documents.length?documents.filter(d=>d.label_sources?.length).map(d=>({name:d.name,sources:d.label_sources})):sources.length?[{name:'SECRET 来源',sources}]:[];
 if(!rows.length)return null;
 return <section className="label-source-summary" aria-label="标签来源摘要"><h3>引用标签与来源</h3>
 {rows.map((row,i)=><div key={i}><strong>{row.name}</strong><ul>{row.sources.map(s=><li key={s.id+':'+s.version}><span className="tag">SECRET</span> <code>{s.value}</code> · 来源 v{s.version}<small>{scopeLabel||(s.scope_id==='system'?'全部受控 Agent':'指定 Agent 的全部工作区与会话')}</small></li>)}</ul></div>)}
 <p className="spl-note">仅此配置明确引用的来源参与规则；处置以获批规则为准，标签本身不禁止读取或外发。</p></section>;
}

export function LabelSourcePicker({api,target,selected=[],snapshots=[],onChange,disabled=false}){
 const [data,setData]=useState(null),[error,setError]=useState('');
 const key=JSON.stringify(selected);
 useEffect(()=>{let alive=true;setData(null);setError('');
  if(api&&target)api('/api/security/labels?scope_id='+encodeURIComponent(target)).then(v=>{if(alive)setData(v);}).catch(e=>{if(alive)setError(e.message);});
  return()=>{alive=false;};
 },[api,target]);
 const refs=JSON.parse(key);
 return <details className="label-source-picker"><summary>选择已登记的 SECRET 来源{refs.length?' · '+refs.length+' 项':''}</summary>
 <p className="spl-note">默认只使用本配置填写或选择的来源，不会引用标签目录中的其他路径。</p>
 {error&&<p role="alert">{error}</p>}
 {!data&&!error&&<p role="status">{target?'正在读取来源…':'请先选择范围'}</p>}
 {data?.sources.filter(s=>!s.archived).map(s=>{
  const checked=refs.some(r=>r.id===s.id&&r.version===s.version);
  return <label key={s.id}><input type="checkbox" disabled={disabled} checked={checked} onChange={e=>onChange(e.target.checked?[...refs.filter(r=>r.id!==s.id),{id:s.id,version:s.version}]:refs.filter(r=>r.id!==s.id))}/><code>{s.value}</code> · v{s.version}</label>;
 })}
 {data&&staleSourceSelections(refs,data.sources).map(ref=>{
  const old=snapshots.find(s=>s.id===ref.id&&s.version===ref.version);
  return <div key={ref.id+':'+ref.version}><span>{old?.value||'已固定的历史来源'} · v{ref.version}（保持原版本，不自动升级）</span><button type="button" className="button tiny ghost" disabled={disabled} onClick={()=>onChange(refs.filter(r=>r.id!==ref.id||r.version!==ref.version))}>取消此引用</button></div>;
 })}
 {data&&!data.sources.some(s=>!s.archived)&&<p>此范围尚无已登记来源。</p>}
 </details>;
}

function SourceEditor({source,agents,post,onClose,onSaved}){
 const dialog=useRef(null),origin=useRef(document.activeElement),request=useRef(crypto.randomUUID());
 const [scope,setScope]=useState(source?.scope_id||'system'),[matcher,setMatcher]=useState(source?.matcher||'exact'),[value,setValue]=useState(source?.value||''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 function change(fn,v){fn(v);request.current=crypto.randomUUID();}
 async function save(e){e.preventDefault();setBusy(true);setError('');try{
  await post('/api/security/label-sources'+(source?'/'+source.id+'/versions':''),{label:'SECRET',scope_id:scope,matcher,value,base_version:source?.version||0,request_key:request.current});await onSaved();
 }catch(e){setError(e.message);}finally{setBusy(false);}}
 return <dialog ref={dialog} className="spl-dialog label-source-editor" aria-label={source?'编辑来源':'登记来源'} onCancel={e=>{e.preventDefault();if(!busy)onClose();}}><form onSubmit={save}>
 <header className="record-drawer-head"><h2>{source?'编辑 SECRET 来源':'登记 SECRET 来源'}</h2><button type="button" className="button ghost" disabled={busy} onClick={onClose}>关闭</button></header>
 <div className="record-drawer-body spl-form"><label>适用范围<select value={scope} disabled={!!source||busy} onChange={e=>change(setScope,e.target.value)}><option value="system">全部受控 Agent</option>{agents.filter(a=>a.mode==='controlled').map(a=><option key={a.id} value={a.id}>{configurationAgentLabel(a,agents)}</option>)}</select></label>
 <label>匹配方式<select value={matcher} disabled={busy} onChange={e=>change(setMatcher,e.target.value)}><option value="exact">精确文件</option><option value="directory">目录及其下级</option><option value="pattern">引擎路径匹配</option>{scope==='system'&&<option value="suffix">文件后缀</option>}</select></label>
 <label>来源路径<input required maxLength={1000} aria-label="来源路径" value={value} disabled={busy} onChange={e=>change(setValue,e.target.value)} placeholder={matcher==='suffix'?'.env':'/受控资源/敏感文件'}/></label>
 <p className="spl-note">{source?'保存会生成新版本，已保存配置继续引用旧版本。':'同范围相同匹配条件会复用已有来源。'}登记只保存资料，不加载执行规则。</p>{error&&<p role="alert" className="spl-error">{error}</p>}</div>
 <footer className="spl-editor-footer"><button type="button" className="button ghost" disabled={busy} onClick={onClose}>取消</button><button className="button primary" disabled={busy}>{busy?'正在保存…':source?'保存新版本':'登记来源'}</button></footer>
 </form></dialog>;
}

function LabelDetail({label,data,agents,post,onClose,onRefresh}){
 const dialog=useRef(null),origin=useRef(document.activeElement),[editing,setEditing]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[confirm,setConfirm]=useState(null);
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 const sources=data.sources.filter(s=>s.label===label.name);
 const scope=s=>s.scope_id==='system'?'全部受控 Agent':configurationAgentLabel(agents.find(a=>a.id===s.scope_id)||{id:s.scope_id},agents);
 async function archive(s){setBusy(true);setError('');try{await post('/api/security/label-sources/'+s.id+'/archive',{version:s.version});setConfirm(null);await onRefresh();}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <dialog ref={dialog} className="record-drawer label-detail" aria-label={label.name+' 标签详情'} onCancel={e=>{e.preventDefault();if(!busy)onClose();}}><header className="record-drawer-head"><h2>{label.name}</h2><button className="button ghost" disabled={busy} onClick={onClose}>关闭</button></header><div className="record-drawer-body">
 <p>{label.description}</p><dl className="security-facts"><dt>适用对象</dt><dd>{label.subjects}</dd><dt>赋予方式</dt><dd>{label.assignment}</dd></dl>
 {error&&<p role="alert">{error}</p>}
 {label.reserved?<p className="inline-notice">系统保留，只读展示；管理员和 Agent 均不能手工赋予 AGENT。</p>:<>
 <div className="label-record-heading"><h3>来源记录</h3><button className="button primary" onClick={()=>setEditing({})}>登记来源</button></div>
 {sources.length?<div className="table-scroll"><table className="label-records"><thead><tr><th>来源／范围</th><th>登记与引用</th><th>操作</th></tr></thead><tbody>{sources.map(s=><tr key={s.id}><td><code>{s.value}</code><small>{scope(s)} · v{s.version}</small></td><td>{s.archived?'已归档':s.references.some(r=>r.source_version===s.version)?'被引用':s.references.length?'已登记 · 历史版本被引用':'已登记'}<small>{s.references.length} 条版本引用</small>{s.references.some(r=>r.applied_revision)&&<small>应用引用的来源版本：{[...new Set(s.references.filter(r=>r.applied_revision).map(r=>'v'+r.source_version))].join('、')}</small>}</td><td>{!s.archived&&<><button className="button tiny ghost" onClick={()=>setEditing(s)}>编辑</button><button className="button tiny ghost" onClick={()=>setConfirm(s)}>归档</button></>}</td></tr>)}</tbody></table></div>:<p className="task-empty">尚未登记来源。</p>}
 <h3>引用策略</h3>{sources.flatMap(s=>s.references.map(r=><p key={s.id+':'+r.configuration_id+':'+r.configuration_version}><strong>{r.name}</strong> · 配置 v{r.configuration_version} → 来源 v{r.source_version}<small>{scope(s)} · {r.applied_revision?'对应应用版本 v'+r.applied_revision:'此版本尚未纳入当前应用配置'}</small></p>))}
 {confirm&&<section className="inline-notice warning" aria-label="确认归档来源"><p>归档 {confirm.value}？历史引用和已生效策略保留，新的配置不再选用此来源。</p><button className="button ghost" disabled={busy} onClick={()=>setConfirm(null)}>取消</button><button className="button primary" disabled={busy} onClick={()=>archive(confirm)}>确认归档</button></section>}
 </>}
 </div>{editing&&<SourceEditor source={editing.id?editing:null} agents={agents} post={post} onClose={()=>setEditing(null)} onSaved={async()=>{setEditing(null);await onRefresh();}}/>}</dialog>;
}

export default function LabelManagement({api,post,agents=[]}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[selected,setSelected]=useState(''),[notice,setNotice]=useState(false);
 const seq=useRef(0);
 async function load(){const n=++seq.current;try{const value=await api('/api/security/labels');if(n===seq.current){setData(value);setError('');}}catch(e){if(n===seq.current)setError(e.message);}}
 useEffect(()=>{load();return()=>{seq.current++;};},[api]);
 const label=data?.labels.find(l=>l.name===selected);
 return <section className="label-management"><div className="label-record-heading"><div><h2>标签管理</h2><p>来源登记与策略执行分开管理。</p></div><div className="actions"><button className="button ghost" onClick={()=>setNotice(true)}>标签使用说明</button><button className="button ghost" onClick={load}>刷新</button></div></div>
 {error&&<p className="inline-notice warning" role="alert">{error}</p>}
 {!data&&!error&&<p role="status">正在读取标签目录…</p>}
 {data&&<div className="table-scroll"><table className="label-records"><thead><tr><th>标签</th><th>说明</th><th>来源数量</th><th>引用配置</th><th>操作</th></tr></thead><tbody>{data.labels.map(l=><tr key={l.name}><td><strong>{l.name}</strong>{l.reserved&&<small>系统保留</small>}</td><td>{l.description}</td><td>{l.reserved?'可信启动管理':l.source_count}</td><td>{l.reserved?'执行身份绑定':l.configuration_count}</td><td><button className="button tiny ghost" onClick={()=>setSelected(l.name)}>详情</button></td></tr>)}</tbody></table></div>}
 {data?.historical_references.length>0&&<details><summary>历史标签引用</summary><p>只读保留原始语义，不转换成新版 SECRET 来源。</p>{data.historical_references.map(r=><p key={r.configuration_id+':'+r.configuration_version}>{r.name} · v{r.configuration_version} · {r.labels.join('、')}</p>)}</details>}
 {label&&<LabelDetail label={label} data={data} agents={agents} post={post} onClose={()=>setSelected('')} onRefresh={load}/>}
 {notice&&<LabelNotice onClose={()=>setNotice(false)}/>}
 </section>;
}

function LabelNotice({onClose}){
 const ref=useRef(null),origin=useRef(document.activeElement);
 useEffect(()=>{ref.current?.showModal();return()=>{ref.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 return <dialog ref={ref} className="spl-dialog label-source-editor" aria-label="标签使用说明" onCancel={e=>{e.preventDefault();onClose();}}><header className="record-drawer-head"><h2>标签使用说明</h2><button className="button ghost" onClick={onClose}>关闭</button></header><div className="record-drawer-body"><LabelUsageContent/></div></dialog>;
}

export function LabelUsageContent(){
 return <section aria-label="标签与信息流使用说明">
 <p>此处展示本期已开放的标签，不是 ActPlane 的全部标签。ActPlane 标签名由策略定义。</p>
 <p><strong>AGENT</strong>：执行身份，由可信启动流程赋予。只读，不用于给普通文件手工分类。</p>
 <p><strong>SECRET</strong>：管理员登记敏感文件来源，配置编写者明确选择引用；已批准并应用后，引擎自动传播。</p>
 <p>登记 → 配置引用 → 批准 → 单独应用。标签本身不代表禁止读取或外发，限制来自获批规则。</p>
 <p>来源编辑生成新版本，旧配置不自动更新。历史 SENSITIVE、REMOTE、CODE 原样保留。</p>
 <p>本期不开放 UNTRUSTED、REVIEWED、脱敏和审核背书。信息流仅表示 ActPlane 原生标签传播产生的规则命中，不等于秘密正文流向证明。</p>
 <p>原生证据只报告当前命中和首个可用来源，不代表完整逐跳传播链。旧的自定义传播记录仅历史留存，不进入产品投影。</p>
 </section>;
}
