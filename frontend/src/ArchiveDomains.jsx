import React,{useEffect,useRef,useState} from 'react';
import DomainGraph from './DomainGraph.jsx';

export function archiveDomainPath(task,version,key) {
 const base=`/api/tasks/${encodeURIComponent(task)}/archive/domains`;
 return key?`${base}/${encodeURIComponent(key)}`:version===null||version===undefined?base:`${base}?version=${encodeURIComponent(version)}`;
}
function Fields({items}) {return <dl className="record-fields">{items.map(([label,value])=><React.Fragment key={label}><dt>{label}</dt><dd>{typeof value==='boolean'?(value?'是':'否'):value??'未记录'}</dd></React.Fragment>)}</dl>;}
function DomainEvidence({domain}) {
 return <><div className="record-tags">{(domain.labels||[]).map(label=><span className="record-tag" key={label}>{label}</span>)}</div><Fields items={[
 ['域 ID',domain.domain_id],['历史版本',`v${domain.version}`],['域职责',domain.role==='baseline'?'启动底线域':'任务执行域'],
 ['策略源 hash 核验',domain.available],['加载时核验通过',domain.loading_verification_passed],
 ['策略源',domain.source==='confirmed_policy_hash'?'策略包与加载回执 hash 一致':domain.source==='root_owned_watch_artifact'?'root 所有的 watch 策略与控制记录':'材料缺失或未核验'],['策略包 hash',domain.policy_hash]
 ]}/><p className="muted">标签来自已记录 DSL 的 source 声明。历史加载记录不代表当前在线或策略正在生效。</p>
 {domain.available&&typeof domain.dsl==='string'?<details className="record-note"><summary>查看该次加载的 DSL</summary><pre className="record-code">{domain.dsl}</pre></details>:<p className="muted">没有与该次加载证据一致的 DSL。</p>}</>;
}

export function HistoricalGraphNotice({graph}){const missing=graph?.missing_sources||[];return <>{(graph?.notice||missing.length>0)&&<details className="archive-technical"><summary>历史材料说明{missing.length?`（${missing.length} 项缺失或未核验）`:''}</summary>{graph.notice&&<p className="muted">{graph.notice}</p>}{missing.length>0&&<ul>{missing.map((item,i)=><li key={item.key||i}>{item.role==='baseline'?'底线域':item.role==='task'?'任务域':'历史加载'}：材料未记录或未核验{item.reason?` · ${item.reason}`:''}</li>)}</ul>}</details>}</>;}

export default function ArchiveDomains({task,api,defaultOpen=false,showProcesses=false,view='graph',files={records:[]},onAudit}) {
 const [open,setOpen]=useState(defaultOpen),[version,setVersion]=useState(null),[graph,setGraph]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 const [selected,setSelected]=useState(null),[detail,setDetail]=useState(null),[detailError,setDetailError]=useState(''),[detailBusy,setDetailBusy]=useState(false);
 const graphSeq=useRef(0),detailSeq=useRef(0),heading=useRef(null),trigger=useRef(null);
 useEffect(()=>{setVersion(null);setGraph(null);setSelected(null);setDetail(null);setError('');},[task]);
 useEffect(()=>{
  const seq=++graphSeq.current;detailSeq.current++;setSelected(null);setDetail(null);setDetailError('');setDetailBusy(false);
  if(!open)return;
  setBusy(true);setError('');setGraph(null);
  api(archiveDomainPath(task,version)).then(result=>{if(!result||!Array.isArray(result.nodes)||!Array.isArray(result.edges)||!Array.isArray(result.versions))throw new Error('历史域接口尚未就绪或返回内容不完整，请稍后重试。');if(seq===graphSeq.current)setGraph(result);}).catch(e=>{if(seq===graphSeq.current)setError(e.message);}).finally(()=>{if(seq===graphSeq.current)setBusy(false);});
  return()=>{graphSeq.current++;};
 },[task,api,open,version,retry]);
 useEffect(()=>{if(selected)heading.current?.focus();},[selected]);
 async function selectDomain(node) {
  trigger.current=document.activeElement;const seq=++detailSeq.current;setSelected(node);setDetail(null);setDetailError('');setDetailBusy(true);
  try {const result=await api(archiveDomainPath(task,null,node.key));if(seq===detailSeq.current)setDetail(result);}
  catch(e){if(seq===detailSeq.current)setDetailError(e.message);}
  finally{if(seq===detailSeq.current)setDetailBusy(false);}
 }
 function selectProcess(node){trigger.current=document.activeElement;detailSeq.current++;setSelected(node);setDetail(null);setDetailError('');setDetailBusy(false);}
 return <details className="record-note" open={open} onToggle={e=>{if(e.target===e.currentTarget)setOpen(e.currentTarget.open);}}>
  <summary>历史域、进程与 DSL</summary>
  {open&&<><p className="muted">历史加载记录；PID 不代表当前在线。</p>
   {busy&&<p role="status">正在读取历史域…</p>}
   {error&&<p role="alert">{error} <button className="button ghost tiny" onClick={()=>setRetry(n=>n+1)}>重试</button></p>}
   {graph&&<><HistoricalGraphNotice graph={graph}/>{view==='graph'&&<DomainGraph graph={graph} files={files} onAudit={onAudit||(()=>{})} historical fresh={false} onVersion={setVersion} onDomain={selectDomain} onProcess={selectProcess}/>}<div hidden={view!=='processes'&&!showProcesses}>{(view==='processes'||showProcesses)&&<section className="archive-process-table"><div className="graph-toolbar"><h3>已记录进程</h3><select aria-label="关联进程的历史版本" value={graph.version} onChange={e=>setVersion(Number(e.target.value))}>{graph.versions.map(v=><option key={v.version} value={v.version}>v{v.version} · 加载记录</option>)}</select></div><div className="archive-table-scroll"><table className="archive-records-table"><thead><tr><th>历史角色</th><th>历史 PID</th><th>版本</th><th>记录时间</th></tr></thead><tbody>{graph.nodes.filter(n=>n.kind==='process'&&n.pid!=null).map(n=><tr key={n.key}><td>{n.title}</td><td>{n.pid}</td><td>v{n.version}</td><td>{n.recorded_at||'未记录'}</td></tr>)}{!graph.nodes.some(n=>n.kind==='process'&&n.pid!=null)&&<tr><td colSpan={4}>该版本未记录进程 PID。</td></tr>}</tbody></table></div></section>}</div></>}
   {selected&&view==='graph'&&<section className="record-note" aria-label="历史节点详情"><div className="graph-toolbar"><h3 ref={heading} tabIndex="-1">{selected.title}</h3><button className="button ghost tiny" onClick={()=>{detailSeq.current++;setSelected(null);setDetail(null);trigger.current?.isConnected&&trigger.current.focus();}}>收起详情</button></div>
    {detailBusy&&<p role="status">正在读取加载证据…</p>}
    {detailError&&<p role="alert">{detailError} <button className="button ghost tiny" onClick={()=>selectDomain(selected)}>重试</button></p>}
    {detail&&<DomainEvidence domain={detail}/>}
    {selected.kind==='process'&&<><Fields items={[['历史 PID',selected.pid],['历史角色',({runner:'任务 runner',watch:'策略 watch',executor:'DSH 执行进程',agent:'DSH 执行进程'})[selected.role]||selected.role],['历史版本',`v${selected.version}`],['记录时间',selected.recorded_at]]}/><p className="muted">PID 来自该次加载收据，不是当前进程采样。</p></>}
   </section>}
  </>}
 </details>;
}
